"""Interactive CLI for testing the GenomeChat agent API.

Provides a Claude-like interface for interacting with the agent API.
Supports streaming responses, plan visualization, and conversation management.
"""

import asyncio
import json
import sys
from typing import Optional

import httpx
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from src.cli.auth import (
    TokenStorage,
    get_current_user,
    login,
    refresh_access_token,
    register,
)

console = Console()

# Request timeouts, in seconds.
#
# These bound a whole agent run, not a single HTTP hop: one turn can fan out to
# the SQL agent and the coder, and each sandbox call is itself allowed up to
# settings.sandbox_timeout. A plain "chart this table" turn measured 323s in
# practice, so the previous 300s standard timeout fired *after* the backend had
# already done the work — the run completed server-side and the client threw it
# away. Keep these comfortably above the slowest realistic turn.
STANDARD_TIMEOUT_SECONDS = 600.0
DEEP_RESEARCH_TIMEOUT_SECONDS = 1200.0


def _timeout_for_mode(research_mode: str) -> float:
    """Return the client timeout appropriate for a research mode."""
    return (
        DEEP_RESEARCH_TIMEOUT_SECONDS
        if research_mode == "deep_research"
        else STANDARD_TIMEOUT_SECONDS
    )


class AgentCLI:
    """Interactive CLI client for the GenomeChat agent API."""

    def __init__(self, api_url: str = "http://localhost:8000", research_mode: str = "standard"):
        """Initialize CLI client.

        Args:
            api_url: Base URL of the API server
            research_mode: Research mode ("standard" or "deep_research")
        """
        self.api_url = api_url.rstrip("/")
        self.thread_id: Optional[str] = None
        self.research_mode = research_mode
        self.timeout = _timeout_for_mode(research_mode)
        self.client = httpx.AsyncClient(timeout=self.timeout)
        self.conversation_history: list[dict[str, str]] = []

        # Authentication
        self.token_storage = TokenStorage()
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.current_user: Optional[dict] = None

        # Load tokens from storage
        self.access_token, self.refresh_token = self.token_storage.load_tokens()

    async def check_health(self) -> bool:
        """Check if API server is healthy.

        Returns:
            True if server is healthy, False otherwise
        """
        try:
            response = await self.client.get(f"{self.api_url}/health")
            return response.status_code == 200
        except Exception:
            return False

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers if token is available.

        Returns:
            Dictionary with Authorization header if token exists, empty dict otherwise
        """
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        return {}

    async def _validate_token(self) -> bool:
        """Validate current access token.

        Returns:
            True if token is valid, False otherwise
        """
        if not self.access_token:
            return False

        try:
            user = await get_current_user(self.api_url, self.access_token)
            if user:
                self.current_user = user
                return True
            return False
        except Exception:
            return False

    async def _refresh_token_if_needed(self) -> bool:
        """Refresh access token if refresh token is available.

        Returns:
            True if token was refreshed, False otherwise
        """
        if not self.refresh_token:
            return False

        try:
            token_data = await refresh_access_token(self.api_url, self.refresh_token)
            if token_data:
                self.access_token = token_data["access_token"]
                self.refresh_token = token_data["refresh_token"]
                self.current_user = token_data.get("user")
                self.token_storage.save_tokens(
                    self.access_token,
                    self.refresh_token,
                    self.current_user.get("email") if self.current_user else None,
                )
                return True
            return False
        except Exception:
            return False

    async def _handle_auth_error(self) -> bool:
        """Handle authentication error by attempting token refresh.

        Returns:
            True if auth was restored, False otherwise
        """
        if await self._refresh_token_if_needed():
            return True

        # Refresh failed, clear tokens
        self.access_token = None
        self.refresh_token = None
        self.current_user = None
        self.token_storage.clear_tokens()
        return False

    def _print_agent_panel(self, agent_name: str, content: str) -> None:
        """Print a panel for an agent's response.

        Args:
            agent_name: Name of the agent
            content: Content of the response
        """
        color_map = {
            "Orchestrator": "green",
            "Coder": "blue",
            "Data Analyst": "yellow",
            "Coordinator": "magenta",
            "Assistant": "green",
        }
        color = color_map.get(agent_name, "white")

        console.print(
            Panel(
                Markdown(content),
                title=f"[{color}]🤖 {agent_name}[/{color}]",
                border_style=color,
            )
        )
        console.print()

    async def chat_stream(self, message: str) -> None:
        """Send message and stream response with plan updates.

        Args:
            message: User message to send
        """
        # Add to conversation history
        self.conversation_history.append({"role": "user", "content": message})

        # Prepare request
        payload = {
            "message": message,
            "research_mode": self.research_mode,
        }
        if self.thread_id:
            payload["thread_id"] = self.thread_id

        # State for multi-agent streaming
        full_response = Text()
        current_agent = None
        current_buffer = ""
        thinking_shown = False

        try:
            # Stream response with auth headers
            headers = self._get_auth_headers()
            async with self.client.stream(
                "POST",
                f"{self.api_url}/chat/stream",
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code == 401:
                    # Token expired, try to refresh
                    if await self._handle_auth_error():
                        # Retry request with new token
                        headers = self._get_auth_headers()
                        async with self.client.stream(
                            "POST",
                            f"{self.api_url}/chat/stream",
                            json=payload,
                            headers=headers,
                        ) as retry_response:
                            if retry_response.status_code != 200:
                                error_text = await retry_response.aread()
                                console.print(f"[red]Error: {retry_response.status_code}[/red]")
                                console.print(f"[red]{error_text.decode()}[/red]")
                                return
                            response = retry_response
                    else:
                        console.print(
                            "[yellow]Authentication expired. Please login again with /login[/yellow]"
                        )
                        return
                elif response.status_code != 200:
                    error_text = await response.aread()
                    console.print(f"[red]Error: {response.status_code}[/red]")
                    console.print(f"[red]{error_text.decode()}[/red]")
                    return

                # Parse SSE events
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    try:
                        data = json.loads(line[6:])  # Remove "data: " prefix
                        event_type = data.get("type")
                        content = data.get("content", "")

                        if event_type == "thinking":
                            # Show thinking indicator with agent name if available
                            agent_name = data.get("agent_name")
                            if agent_name and content:
                                # Show agent-specific thinking with content (reasoning)
                                console.print(f"[dim]🤔 {agent_name}: {content}[/dim]")
                                console.print()
                            elif not thinking_shown:
                                # Fallback to generic thinking message (for initial thinking events without agent)
                                console.print("[dim]🤔 Agent is thinking...[/dim]")
                                thinking_shown = True

                        elif event_type == "agent_start":
                            # Show agent start indicator
                            agent_name = data.get("agent_name")
                            if agent_name:
                                console.print(f"[dim]🔄 {agent_name} is working...[/dim]")
                                console.print()

                        elif event_type == "agent_end":
                            # Show complete agent response in panel
                            agent_name = data.get("agent_name")
                            content = data.get("content", "")
                            if agent_name and content:
                                self._print_agent_panel(agent_name, content)
                                console.print()  # Add spacing after panel

                        elif event_type == "token":
                            # Token events are now only for orchestrator final responses and coordinator
                            # Worker agents use agent_start/agent_end instead
                            agent_name = data.get("agent_name", "Assistant")

                            # Handle agent switch - print previous agent's panel
                            if (
                                current_agent is not None
                                and agent_name != current_agent
                                and current_buffer
                            ):
                                self._print_agent_panel(current_agent, current_buffer)
                                current_buffer = ""

                            # Set current agent and accumulate tokens (don't print immediately)
                            if current_agent is None or agent_name != current_agent:
                                current_agent = agent_name
                                current_buffer = content
                            else:
                                # Same agent - just accumulate tokens
                                current_buffer += content

                            full_response.append(content)

                            # Update thread_id if provided
                            if "thread_id" in data:
                                self.thread_id = data["thread_id"]

                        elif event_type == "plan":
                            # Show plan update
                            try:
                                plan_data = (
                                    json.loads(content) if isinstance(content, str) else content
                                )
                                plan_panel = Panel(
                                    Markdown(self._format_plan(plan_data)),
                                    title="[cyan]📋 Plan Update[/cyan]",
                                    border_style="cyan",
                                    width=120,  # Explicit width to prevent truncation
                                )
                            except Exception:
                                plan_panel = Panel(
                                    content,
                                    title="[cyan]📋 Plan Update[/cyan]",
                                    border_style="cyan",
                                    width=120,  # Explicit width to prevent truncation
                                )
                            console.print(plan_panel)
                            console.print()

                        elif event_type == "error":
                            console.print(f"[red]Error: {content}[/red]")
                            return

                        elif event_type == "end":
                            break

                    except json.JSONDecodeError:
                        continue

            # Display final buffered response
            if current_buffer and current_agent:
                self._print_agent_panel(current_agent, current_buffer)

            # Add to conversation history
            if full_response:
                self.conversation_history.append(
                    {"role": "assistant", "content": str(full_response)}
                )

        except httpx.TimeoutException:
            console.print(
                f"[red]Stream timed out after {self.timeout / 60:.0f} minutes. The backend "
                f"may still have completed the turn — check the conversation history.[/red]"
            )
        except httpx.RequestError as e:
            # Several httpx transport errors stringify to "", so name the class too.
            console.print(f"[red]Connection error ({type(e).__name__}): {e or 'no detail'}[/red]")
        except Exception as e:
            console.print(f"[red]Unexpected error ({type(e).__name__}): {e or 'no detail'}[/red]")

    async def chat_sync(self, message: str) -> None:
        """Send message and get complete response (non-streaming).

        Args:
            message: User message to send
        """
        # Add to conversation history
        self.conversation_history.append({"role": "user", "content": message})

        # Prepare request
        payload = {
            "message": message,
            "research_mode": self.research_mode,
        }
        if self.thread_id:
            payload["thread_id"] = self.thread_id

        try:
            headers = self._get_auth_headers()
            response = await self.client.post(f"{self.api_url}/chat", json=payload, headers=headers)

            # Handle 401 - token expired
            if response.status_code == 401:
                if await self._handle_auth_error():
                    # Retry request with new token
                    headers = self._get_auth_headers()
                    response = await self.client.post(
                        f"{self.api_url}/chat", json=payload, headers=headers
                    )
                else:
                    console.print(
                        "[yellow]Authentication expired. Please login again with /login[/yellow]"
                    )
                    return

            response.raise_for_status()

            data = response.json()
            assistant_message = data.get("message", "")
            self.thread_id = data.get("thread_id", self.thread_id)

            # Display response
            console.print()
            console.print(
                Panel(
                    Markdown(assistant_message),
                    title="[green]🤖 Assistant[/green]",
                    border_style="green",
                )
            )
            console.print()

            # Add to conversation history
            self.conversation_history.append({"role": "assistant", "content": assistant_message})

        except httpx.HTTPStatusError as e:
            console.print(f"[red]HTTP Error: {e.response.status_code}[/red]")
            try:
                error_data = e.response.json()
                console.print(f"[red]{error_data.get('detail', 'Unknown error')}[/red]")
            except Exception:
                console.print(f"[red]{e.response.text}[/red]")
        except httpx.TimeoutException:
            # str(httpx.ReadTimeout()) is the empty string, so the generic
            # handler below used to render this as a bare "Error:" with no
            # cause. Say what timed out, and that the server may have finished
            # anyway — the run keeps going server-side after the client bails.
            console.print(
                f"[red]Timed out after {self.timeout / 60:.0f} minutes waiting for "
                f"{self.api_url}/chat[/red]"
            )
            console.print(
                "[yellow]The backend may still have completed the turn — check the "
                "conversation history before re-asking. Streaming mode (/stream) avoids "
                "this by showing progress as it arrives.[/yellow]"
            )
        except httpx.RequestError as e:
            console.print(f"[red]Connection error ({type(e).__name__}): {e or 'no detail'}[/red]")
        except Exception as e:
            console.print(f"[red]Error ({type(e).__name__}): {e or 'no detail'}[/red]")

    def _format_plan(self, plan_data: dict) -> str:
        """Format plan data as markdown with Claude Code-style checkboxes.

        Args:
            plan_data: Plan dictionary with thought, title, steps

        Returns:
            Formatted markdown string with checkboxes and status indicators
        """
        if isinstance(plan_data, str):
            try:
                plan_data = json.loads(plan_data)
            except Exception:
                return plan_data

        markdown = []

        # Show title if present (bold, at top)
        if "title" in plan_data and plan_data.get("title"):
            markdown.append(f"**{plan_data['title']}**")
            markdown.append("")

        # Optional: Show thought if present (subtle, italic)
        if "thought" in plan_data and plan_data.get("thought"):
            markdown.append(f"*{plan_data['thought']}*")
            markdown.append("")

        if "steps" in plan_data and plan_data["steps"]:
            for i, step in enumerate(plan_data["steps"], 1):
                status = step.get("status", "pending")
                agent_name = step.get("agent_name", "unknown")
                # Prefer title (concise) for display, fall back to description
                step_text = step.get("title") or step.get("description", "Untitled task")

                # Determine checkbox state based on status
                if status == "completed":
                    checkbox = "[x]"
                    formatted_text = f"~~{step_text}~~"
                elif status == "in_progress":
                    checkbox = "[→]"  # Arrow for in progress
                    formatted_text = f"**{step_text}**"  # Bold for active
                elif status == "failed":
                    checkbox = "[!]"  # Exclamation for failed
                    formatted_text = f"{step_text}"
                else:  # pending
                    checkbox = "[ ]"
                    formatted_text = f"{step_text}"

                # Add agent name and step number
                markdown.append(f"{i}. {checkbox} [{agent_name}] {formatted_text}")

                # Show result if present and completed
                if status == "completed" and step.get("result"):
                    result = step.get("result", "")
                    # Truncate long results
                    if len(result) > 100:
                        result = result[:97] + "..."
                    markdown.append(f"   *✓ {result}*")

        return "\n".join(markdown) if markdown else "No tasks"

    def show_help(self) -> None:
        """Display help message."""
        auth_status = (
            f"Logged in as: **{self.current_user.get('email', 'Unknown')}**"
            if self.current_user
            else "**Not authenticated** (anonymous mode)"
        )
        help_text = f"""
**Commands:**
  `/help`       - Show this help message
  `/clear`      - Clear conversation history
  `/thread`     - Show current thread ID
  `/thread <id>` - Set thread ID for conversation continuity
  `/sync`       - Switch to non-streaming mode
  `/stream`     - Switch to streaming mode (default)
  `/mode`       - Show current research mode
  `/mode standard` - Set research mode to standard (efficient, direct)
  `/mode deep`  - Set research mode to deep research (comprehensive analysis)
  `/login <email> <password>` - Login with email and password
  `/register <email> <name> <password>` - Register new user
  `/logout`     - Logout and clear authentication tokens
  `/whoami`     - Show current user information
  `/conversations` - List all your conversations (requires auth)
  `/history <id>` - Show messages from a conversation (requires auth)
  `/delete <id>` - Delete a conversation (requires auth)
  `/exit`       - Exit the CLI

**Current Settings:**
  Research Mode: **{self.research_mode}**
  Authentication: {auth_status if "auth_status" in locals() else ("Logged in as: **" + self.current_user.get("email", "Unknown") + "**" if self.current_user else "**Not authenticated** (anonymous mode)")}

**Usage:**
  Just type your message and press Enter to send.
  Use Ctrl+C to cancel a request.
        """
        console.print(
            Panel(Markdown(help_text.strip()), title="[blue]📖 Help[/blue]", border_style="blue")
        )
        console.print()

    def show_thread_info(self) -> None:
        """Display current thread information."""
        if self.thread_id:
            console.print(f"[cyan]Current Thread ID:[/cyan] {self.thread_id}")
        else:
            console.print(
                "[yellow]No thread ID set. A new thread will be created on next message.[/yellow]"
            )
        console.print()

    def show_research_mode(self) -> None:
        """Display current research mode."""
        mode_descriptions = {
            "standard": "Efficient, direct responses. Completes requested tasks without unnecessary exploration.",
            "deep_research": "Comprehensive, multi-faceted analysis. Conducts thorough research with iterative deepening and cross-validation.",
        }
        description = mode_descriptions.get(self.research_mode, "Unknown mode")
        console.print(f"[cyan]Current Research Mode:[/cyan] [bold]{self.research_mode}[/bold]")
        console.print(f"[dim]{description}[/dim]")
        console.print()

    def set_research_mode(self, mode: str) -> None:
        """Set research mode.

        Args:
            mode: Research mode ("standard" or "deep" or "deep_research")
        """
        # Normalize mode input
        if mode.lower() in ["deep", "deep_research"]:
            self.research_mode = "deep_research"
            # Recreate client with increased timeout for deep research
            self.timeout = _timeout_for_mode(self.research_mode)
            self.client = httpx.AsyncClient(timeout=self.timeout)
            console.print("[green]Research mode set to: deep_research[/green]")
            console.print(
                "[dim]Comprehensive analysis mode enabled. Research will be more thorough.[/dim]"
            )
            console.print(
                f"[dim]Timeout increased to {self.timeout / 60:.0f} minutes for longer queries.[/dim]"
            )
        elif mode.lower() == "standard":
            self.research_mode = "standard"
            # Recreate client with standard timeout
            self.timeout = _timeout_for_mode(self.research_mode)
            self.client = httpx.AsyncClient(timeout=self.timeout)
            console.print("[green]Research mode set to: standard[/green]")
            console.print(
                "[dim]Efficient mode enabled. Responses will be direct and focused.[/dim]"
            )
        else:
            console.print(f"[red]Invalid mode: {mode}[/red]")
            console.print("[yellow]Use 'standard' or 'deep'[/yellow]")
        console.print()

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history.clear()
        console.print("[green]Conversation history cleared.[/green]")
        console.print()

    async def handle_login(self, command_input: str) -> None:
        """Handle /login command.

        Args:
            command_input: Full command input string
        """
        parts = command_input.split()
        if len(parts) < 3:
            console.print("[red]Usage: /login <email> <password>[/red]")
            console.print("[yellow]Example: /login user@example.com MyPassword123![/yellow]")
            console.print()
            return

        email = parts[1]
        password = parts[2]

        console.print("[yellow]Logging in...[/yellow]")
        success, message, token_data = await login(self.api_url, email, password)

        if success and token_data:
            self.access_token = token_data["access_token"]
            self.refresh_token = token_data["refresh_token"]
            self.current_user = token_data.get("user")
            self.token_storage.save_tokens(
                self.access_token,
                self.refresh_token,
                self.current_user.get("email") if self.current_user else None,
            )
            console.print(f"[green]✅ {message}[/green]")
            if self.current_user:
                console.print(
                    f"[green]Logged in as: {self.current_user.get('name')} ({self.current_user.get('email')})[/green]"
                )
            console.print()
        else:
            console.print(f"[red]❌ {message}[/red]")
            console.print()

    async def handle_register(self, command_input: str) -> None:
        """Handle /register command.

        Args:
            command_input: Full command input string
        """
        parts = command_input.split(maxsplit=3)
        if len(parts) < 4:
            console.print("[red]Usage: /register <email> <name> <password>[/red]")
            console.print(
                '[yellow]Example: /register user@example.com "John Doe" MyPassword123![/yellow]'
            )
            console.print(
                "[dim]Note: Password must be at least 8 characters with uppercase, lowercase, number, and special character[/dim]"
            )
            console.print()
            return

        email = parts[1]
        name = parts[2]
        password = parts[3]

        console.print("[yellow]Registering...[/yellow]")
        success, message, token_data = await register(self.api_url, email, name, password)

        if success and token_data:
            self.access_token = token_data["access_token"]
            self.refresh_token = token_data["refresh_token"]
            self.current_user = token_data.get("user")
            self.token_storage.save_tokens(
                self.access_token,
                self.refresh_token,
                self.current_user.get("email") if self.current_user else None,
            )
            console.print(f"[green]✅ {message}[/green]")
            if self.current_user:
                console.print(
                    f"[green]Registered and logged in as: {self.current_user.get('name')} ({self.current_user.get('email')})[/green]"
                )
            console.print()
        else:
            console.print(f"[red]❌ {message}[/red]")
            console.print()

    async def handle_logout(self) -> None:
        """Handle /logout command."""
        if not self.access_token:
            console.print("[yellow]Not logged in[/yellow]")
            console.print()
            return

        self.access_token = None
        self.refresh_token = None
        self.current_user = None
        self.token_storage.clear_tokens()
        console.print("[green]✅ Logged out successfully[/green]")
        console.print()

    async def handle_whoami(self) -> None:
        """Handle /whoami command."""
        if not self.access_token:
            console.print("[yellow]Not authenticated (anonymous mode)[/yellow]")
            console.print("[dim]Use /login to authenticate[/dim]")
            console.print()
            return

        # Try to get fresh user info
        user = await get_current_user(self.api_url, self.access_token)
        if user:
            self.current_user = user
            console.print(
                Panel(
                    Markdown(f"""
**Email:** {user.get("email")}
**Name:** {user.get("name")}
**Role:** {user.get("role", "user")}
                """),
                    title="[green]👤 Current User[/green]",
                    border_style="green",
                )
            )
        else:
            console.print("[yellow]Could not fetch user information[/yellow]")
            if self.current_user:
                console.print(f"[dim]Last known: {self.current_user.get('email')}[/dim]")
        console.print()

    async def handle_conversations_list(self) -> None:
        """Handle /conversations command - list all conversations."""
        if not self.access_token:
            console.print("[yellow]Authentication required. Use /login first.[/yellow]")
            console.print()
            return

        try:
            headers = self._get_auth_headers()
            response = await self.client.get(f"{self.api_url}/conversations", headers=headers)

            if response.status_code == 401:
                if await self._handle_auth_error():
                    # Retry with new token
                    headers = self._get_auth_headers()
                    response = await self.client.get(
                        f"{self.api_url}/conversations", headers=headers
                    )
                else:
                    console.print(
                        "[yellow]Authentication expired. Please login again with /login[/yellow]"
                    )
                    console.print()
                    return

            if response.status_code != 200:
                console.print(f"[red]Error: {response.status_code}[/red]")
                console.print()
                return

            data = response.json()
            conversations = data.get("conversations", [])
            count = data.get("count", 0)

            if count == 0:
                console.print("[yellow]No conversations found[/yellow]")
                console.print("[dim]Start chatting to create your first conversation[/dim]")
                console.print()
                return

            # Build markdown table
            from datetime import datetime

            markdown_lines = [f"**Total Conversations:** {count}\n"]
            markdown_lines.append("| ID | Title | Updated |")
            markdown_lines.append("|---|---|---|")

            for conv in conversations:
                conv_id = conv["id"][:8] + "..."  # Truncate ID for display
                title = conv["title"][:50]  # Truncate long titles
                updated = conv["updated_at"]

                # Parse and format date
                try:
                    dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    formatted_date = dt.strftime("%b %d, %Y %H:%M")
                except Exception:
                    formatted_date = updated[:19]  # Fallback to ISO format

                markdown_lines.append(f"| `{conv_id}` | {title} | {formatted_date} |")

            console.print(
                Panel(
                    Markdown("\n".join(markdown_lines)),
                    title="[blue]💬 Your Conversations[/blue]",
                    border_style="blue",
                )
            )
            console.print()

        except Exception as e:
            console.print(f"[red]Failed to list conversations: {e}[/red]")
            console.print()

    async def handle_conversation_history(self, conversation_id: str) -> None:
        """Handle /history <id> command - show conversation history.

        Args:
            conversation_id: ID of the conversation to view
        """
        if not self.access_token:
            console.print("[yellow]Authentication required. Use /login first.[/yellow]")
            console.print()
            return

        try:
            headers = self._get_auth_headers()
            response = await self.client.get(
                f"{self.api_url}/conversations/{conversation_id}/history", headers=headers
            )

            if response.status_code == 401:
                if await self._handle_auth_error():
                    headers = self._get_auth_headers()
                    response = await self.client.get(
                        f"{self.api_url}/conversations/{conversation_id}/history", headers=headers
                    )
                else:
                    console.print(
                        "[yellow]Authentication expired. Please login again with /login[/yellow]"
                    )
                    console.print()
                    return

            if response.status_code == 404:
                console.print(f"[red]Conversation not found: {conversation_id}[/red]")
                console.print()
                return
            elif response.status_code != 200:
                console.print(f"[red]Error: {response.status_code}[/red]")
                console.print()
                return

            data = response.json()
            messages = data.get("messages", [])

            console.print(
                Panel(
                    Markdown(f"**Title:** {data['title']}\n**Messages:** {len(messages)}"),
                    title=f"[blue]💬 Conversation: {data['id'][:12]}...[/blue]",
                    border_style="blue",
                )
            )
            console.print()

            # Display messages
            for idx, msg in enumerate(messages, 1):
                msg_type = msg.get("type", "unknown")
                content = msg.get("content", "")

                if msg_type == "human":
                    console.print(f"[cyan bold]{idx}. You:[/cyan bold]")
                    console.print(Markdown(content))
                elif msg_type == "ai":
                    console.print(f"[green bold]{idx}. Assistant:[/green bold]")
                    console.print(Markdown(content))
                else:
                    console.print(f"[dim]{idx}. System:[/dim]")
                    console.print(f"[dim]{content}[/dim]")
                console.print()

        except Exception as e:
            console.print(f"[red]Failed to get conversation history: {e}[/red]")
            console.print()

    async def handle_conversation_delete(self, conversation_id: str) -> None:
        """Handle /delete <id> command - delete a conversation.

        Args:
            conversation_id: ID of the conversation to delete
        """
        if not self.access_token:
            console.print("[yellow]Authentication required. Use /login first.[/yellow]")
            console.print()
            return

        # Confirm deletion
        console.print(
            f"[yellow]Are you sure you want to delete conversation {conversation_id}?[/yellow]"
        )
        confirm = console.input(Text("Type 'yes' to confirm: ", style="yellow")).strip().lower()

        if confirm != "yes":
            console.print("[dim]Deletion cancelled[/dim]")
            console.print()
            return

        try:
            headers = self._get_auth_headers()
            response = await self.client.delete(
                f"{self.api_url}/conversations/{conversation_id}", headers=headers
            )

            if response.status_code == 401:
                if await self._handle_auth_error():
                    headers = self._get_auth_headers()
                    response = await self.client.delete(
                        f"{self.api_url}/conversations/{conversation_id}", headers=headers
                    )
                else:
                    console.print(
                        "[yellow]Authentication expired. Please login again with /login[/yellow]"
                    )
                    console.print()
                    return

            if response.status_code == 404:
                console.print(f"[red]Conversation not found: {conversation_id}[/red]")
                console.print()
                return
            elif response.status_code == 204:
                console.print(f"[green]✅ Conversation deleted: {conversation_id}[/green]")
                # Clear thread_id if it matches deleted conversation
                if self.thread_id == conversation_id:
                    self.thread_id = None
                    console.print("[dim]Thread ID cleared[/dim]")
                console.print()
            else:
                console.print(f"[red]Error: {response.status_code}[/red]")
                console.print()

        except Exception as e:
            console.print(f"[red]Failed to delete conversation: {e}[/red]")
            console.print()

    async def run(self, streaming: bool = True, research_mode: str = "standard") -> None:
        """Run the interactive CLI loop.

        Args:
            streaming: Whether to use streaming mode by default
            research_mode: Initial research mode ("standard" or "deep_research")
        """
        # Set initial research mode
        self.research_mode = research_mode
        # Check server health
        console.print("[yellow]Checking API server...[/yellow]")
        if not await self.check_health():
            console.print("[red]❌ Cannot connect to API server![/red]")
            console.print(f"[red]Make sure the server is running at {self.api_url}[/red]")
            console.print(
                "[yellow]Start the server with:[/yellow] [cyan]uv run python main.py[/cyan]"
            )
            return

        console.print("[green]✅ Connected to API server[/green]")
        console.print()

        # Validate token if available
        if self.access_token:
            if await self._validate_token():
                console.print(
                    f"[green]✅ Authenticated as: {self.current_user.get('email') if self.current_user else 'Unknown'}[/green]"
                )
            else:
                # Token invalid, try refresh
                if not await self._refresh_token_if_needed():
                    console.print(
                        "[yellow]⚠️  Stored token is invalid. Please login again with /login[/yellow]"
                    )
                    self.access_token = None
                    self.refresh_token = None
            console.print()

        # Show welcome message
        auth_status = (
            f"Logged in as **{self.current_user.get('email', 'Unknown')}**"
            if self.current_user
            else "**Anonymous mode**"
        )
        welcome = Panel(
            Markdown(
                f"""
# Welcome to GenomeChat CLI

Type your message and press Enter to chat with the agent.
Use `/help` for commands, `/exit` to quit.

**Status:** {auth_status}
                """
            ),
            title="[bold blue]🤖 GenomeChat Agent CLI[/bold blue]",
            border_style="blue",
        )
        console.print(welcome)
        console.print()

        use_streaming = streaming

        # Show current settings
        console.print(f"[dim]Research Mode: {self.research_mode}[/dim]")
        console.print(f"[dim]Streaming: {'enabled' if use_streaming else 'disabled'}[/dim]")
        auth_indicator = f"[dim]Auth: {self.current_user.get('email') if self.current_user else 'Anonymous'}[/dim]"
        console.print(auth_indicator)
        console.print()

        # Main loop
        while True:
            try:
                # Get user input
                prompt = Text("You: ", style="bold cyan")
                user_input = console.input(prompt).strip()

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    command = user_input.split()[0].lower()

                    if command == "/exit":
                        console.print("[yellow]Goodbye! 👋[/yellow]")
                        break
                    elif command == "/help":
                        self.show_help()
                    elif command == "/clear":
                        self.clear_history()
                    elif command == "/thread":
                        if len(user_input.split()) > 1:
                            self.thread_id = user_input.split()[1]
                            console.print(f"[green]Thread ID set to: {self.thread_id}[/green]")
                        else:
                            self.show_thread_info()
                    elif command == "/sync":
                        use_streaming = False
                        console.print("[yellow]Switched to non-streaming mode[/yellow]")
                    elif command == "/stream":
                        use_streaming = True
                        console.print("[yellow]Switched to streaming mode[/yellow]")
                    elif command == "/mode":
                        if len(user_input.split()) > 1:
                            mode_arg = user_input.split()[1]
                            self.set_research_mode(mode_arg)
                        else:
                            self.show_research_mode()
                    elif command == "/login":
                        await self.handle_login(user_input)
                    elif command == "/register":
                        await self.handle_register(user_input)
                    elif command == "/logout":
                        await self.handle_logout()
                    elif command == "/whoami":
                        await self.handle_whoami()
                    elif command == "/conversations":
                        await self.handle_conversations_list()
                    elif command == "/history":
                        if len(user_input.split()) > 1:
                            conv_id = user_input.split()[1]
                            await self.handle_conversation_history(conv_id)
                        else:
                            console.print("[red]Usage: /history <conversation_id>[/red]")
                            console.print("[dim]Use /conversations to list all conversations[/dim]")
                            console.print()
                    elif command == "/delete":
                        if len(user_input.split()) > 1:
                            conv_id = user_input.split()[1]
                            await self.handle_conversation_delete(conv_id)
                        else:
                            console.print("[red]Usage: /delete <conversation_id>[/red]")
                            console.print("[dim]Use /conversations to list all conversations[/dim]")
                            console.print()
                    else:
                        console.print(f"[red]Unknown command: {command}[/red]")
                        console.print("[yellow]Use /help for available commands[/yellow]")
                    continue

                # Send message
                if use_streaming:
                    await self.chat_stream(user_input)
                else:
                    await self.chat_sync(user_input)

            except KeyboardInterrupt:
                console.print("\n[yellow]Request cancelled. Press Ctrl+C again to exit.[/yellow]")
                console.print()
            except EOFError:
                console.print("\n[yellow]Goodbye! 👋[/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                console.print()

        await self.client.aclose()


async def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="GenomeChat Agent CLI")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="API server URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Use non-streaming mode",
    )
    parser.add_argument(
        "--research-mode",
        choices=["standard", "deep_research", "deep"],
        default="standard",
        help="Research mode: 'standard' for efficient responses, 'deep_research' for comprehensive analysis (default: standard)",
    )
    args = parser.parse_args()

    # Normalize research mode
    research_mode = (
        "deep_research" if args.research_mode in ["deep", "deep_research"] else "standard"
    )

    cli = AgentCLI(api_url=args.url, research_mode=research_mode)
    await cli.run(streaming=not args.no_stream, research_mode=research_mode)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Goodbye! 👋[/yellow]")
        sys.exit(0)
