"""MCP Context Provider for MAGI deliberation system.

Connects to Google Calendar, Gmail, Google Drive, and GitHub via MCP
to gather real-world context before deliberation. This enriches the
user's question with scheduled events, emails, documents, and repo
activity, making agent analysis more grounded and personalized.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "mcp_config.json"


class MCPContextProvider:
    """Gathers context from Google Calendar, Gmail, Drive, and GitHub.

    Usage:
        provider = MCPContextProvider()  # loads mcp_config.json
        enriched = await provider.gather_context(
            question="Should I change jobs?",
            base_context="Senior dev, 3 years"
        )
        # enriched now includes calendar events, emails, docs, PRs, etc.
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path or DEFAULT_CONFIG_PATH)
        self.servers: dict[str, dict] = {}
        self._load_config()

    def _load_config(self) -> None:
        if not self.config_path.exists():
            logger.info("No MCP config at %s — context enrichment disabled", self.config_path)
            return

        config = json.loads(self.config_path.read_text())
        self.servers = config.get("mcpServers", {})
        logger.info("Loaded MCP config: %d servers (%s)", len(self.servers), ", ".join(self.servers))

    @property
    def enabled(self) -> bool:
        return len(self.servers) > 0

    async def gather_context(
        self,
        question: str,
        base_context: str = "",
    ) -> str:
        """Connect to all MCP servers and gather relevant context.

        Returns enriched context combining base_context with data
        from Google Calendar, Gmail, Drive, and GitHub.
        """
        if not self.enabled:
            return base_context

        context_parts: list[str] = []
        if base_context:
            context_parts.append(base_context)

        for server_name, server_config in self.servers.items():
            try:
                server_context = await self._gather_from_server(
                    server_name, server_config, question
                )
                if server_context:
                    context_parts.append(server_context)
            except Exception as exc:
                logger.warning("MCP server '%s' failed: %s", server_name, exc)

        return "\n\n---\n\n".join(context_parts) if context_parts else base_context

    async def _gather_from_server(
        self,
        server_name: str,
        server_config: dict,
        question: str,
    ) -> str | None:
        params = StdioServerParameters(
            command=server_config["command"],
            args=server_config.get("args", []),
            env=server_config.get("env"),
        )

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                gatherers = {
                    "google-calendar": self._gather_calendar,
                    "gmail": self._gather_gmail,
                    "google-drive": self._gather_drive,
                    "github": self._gather_github,
                }

                gatherer = gatherers.get(server_name)
                if not gatherer:
                    logger.debug("Unknown MCP server '%s', skipping", server_name)
                    return None

                return await gatherer(session, question)

    # ── Google Calendar ─────────────────────────────────────────

    async def _gather_calendar(self, session: ClientSession, question: str) -> str | None:
        """Pull upcoming events from Google Calendar."""
        return await self._call_tool_safe(
            session,
            tool_name="gcal_list_events",
            tool_args={"max_results": 10},
            header="[Google Calendar — upcoming events]",
        )

    # ── Gmail ───────────────────────────────────────────────────

    async def _gather_gmail(self, session: ClientSession, question: str) -> str | None:
        """Search Gmail for emails relevant to the deliberation question."""
        available = await self._available_tools(session)

        if "gmail_search_messages" in available:
            return await self._call_tool_safe(
                session,
                tool_name="gmail_search_messages",
                tool_args={"query": question, "max_results": 5},
                header="[Gmail — relevant messages]",
            )

        if "gmail_list_messages" in available:
            return await self._call_tool_safe(
                session,
                tool_name="gmail_list_messages",
                tool_args={"max_results": 5},
                header="[Gmail — recent messages]",
            )

        return None

    # ── Google Drive ────────────────────────────────────────────

    async def _gather_drive(self, session: ClientSession, question: str) -> str | None:
        """Search Google Drive for documents relevant to the question."""
        available = await self._available_tools(session)

        if "drive_search_files" in available:
            return await self._call_tool_safe(
                session,
                tool_name="drive_search_files",
                tool_args={"query": question, "max_results": 5},
                header="[Google Drive — relevant documents]",
            )

        if "drive_list_files" in available:
            return await self._call_tool_safe(
                session,
                tool_name="drive_list_files",
                tool_args={"max_results": 5},
                header="[Google Drive — recent documents]",
            )

        return None

    # ── GitHub ──────────────────────────────────────────────────

    async def _gather_github(self, session: ClientSession, question: str) -> str | None:
        """Pull recent PRs, issues, and activity from GitHub."""
        available = await self._available_tools(session)
        parts: list[str] = []

        # Recent PRs
        if "list_pull_requests" in available:
            pr_text = await self._call_tool_safe(
                session,
                tool_name="list_pull_requests",
                tool_args={"state": "open", "per_page": 5},
                header="Open PRs:",
            )
            if pr_text:
                parts.append(pr_text)

        # Recent issues
        if "list_issues" in available:
            issues_text = await self._call_tool_safe(
                session,
                tool_name="list_issues",
                tool_args={"state": "open", "per_page": 5},
                header="Open issues:",
            )
            if issues_text:
                parts.append(issues_text)

        # Notifications
        if "list_notifications" in available:
            notif_text = await self._call_tool_safe(
                session,
                tool_name="list_notifications",
                tool_args={"per_page": 5},
                header="Recent notifications:",
            )
            if notif_text:
                parts.append(notif_text)

        if not parts:
            return None

        return "[GitHub — repository activity]\n" + "\n".join(parts)

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    async def _available_tools(session: ClientSession) -> set[str]:
        result = await session.list_tools()
        return {t.name for t in result.tools}

    @staticmethod
    async def _call_tool_safe(
        session: ClientSession,
        tool_name: str,
        tool_args: dict[str, Any],
        header: str,
    ) -> str | None:
        """Call an MCP tool and return formatted text, or None on failure."""
        try:
            result = await session.call_tool(tool_name, tool_args)
            texts = [
                block.text for block in result.content
                if hasattr(block, "text") and block.text
            ]
            if not texts:
                return None
            return f"{header}\n" + "\n".join(texts)
        except Exception as exc:
            logger.debug("Tool %s failed: %s", tool_name, exc)
            return None
