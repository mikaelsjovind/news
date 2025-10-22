# Slack Bot Implementation Plan

## Overview

Implement Slack bot interface for the news agent with user-based access control. The implementation follows a clean separation of concerns with agents handling business logic and interfaces handling I/O.

## Architecture

```
news/
├── core/                      # Business logic (unchanged)
│   ├── database.py
│   ├── source_manager.py
│   ├── feed_fetcher.py
│   ├── article_manager.py
│   ├── profile_manager.py
│   └── feedback_manager.py
│
├── agents/                    # Pure agent implementations
│   ├── chat.py               # Refactored: export create_chat_client()
│   ├── analyzer.py           # Refactored: export create_analyzer_client()
│   └── mcp_tools.py          # Unchanged
│
├── interfaces/               # Interface adapters (NEW!)
│   ├── __init__.py
│   ├── chat_cli.py          # Terminal chat interface
│   ├── chat_slack.py        # Slack chat interface (WITH USER RESTRICTION!)
│   └── fetch_and_analyze_cli.py  # Background job interface
│
└── main.py                   # Entry point - launches interfaces
```

## Naming Convention

**Format**: `{what}_{service}.py`

**Chat interfaces**:
- `chat_cli.py` - Chat via terminal
- `chat_slack.py` - Chat via Slack
- `chat_discord.py` - Chat via Discord (future)
- `chat_api.py` - Chat via REST API (future)

**Other interfaces**:
- `fetch_and_analyze_cli.py` - Background fetch+analyze via CLI
- `summaries_slack.py` - Scheduled summaries in Slack (future)

**Benefit**: Alphabetical sorting groups all chat implementations together!

## Key Components

### 1. Agent Refactoring

**agents/chat.py** - Export reusable functions:
```python
"""Chat Agent - Pure agent implementation (interface-agnostic)"""

# Tools for chat agent (24 tools)
CHAT_TOOLS = [
    'save_feedback', 'analyze_reading_patterns', 'get_feedback_summary',
    'compare_ai_vs_user', 'mark_read', 'mark_articles_read', 'get_articles',
    'search_articles', 'get_article', 'trigger_deep_analysis',
    'save_deep_analysis', 'mark_all_read', 'update_profile', 'get_profile',
    'add_interest', 'remove_interest', 'adjust_threshold', 'get_stats',
    'get_source_prefs', 'trending_topics', 'suggest_sources', 'list_sources',
    'add_source', 'remove_source', 'validate_feed'
]

def create_chat_mcp_server():
    """Create MCP server with chat tools (24 tools)"""
    # Implementation...

def get_chat_system_prompt(profile_mgr) -> str:
    """Get system prompt for chat agent"""
    # Implementation...

async def create_chat_client(db, model: str = "claude-sonnet-4-5-20250929"):
    """Create configured chat agent client

    Returns ClaudeSDKClient ready to use by any interface.
    """
    # Implementation...
```

**agents/analyzer.py** - Similar refactoring:
```python
"""Analyzer Agent - Pure agent implementation (interface-agnostic)"""

# Tools for analyzer agent (5 tools only - read-only)
ANALYZER_TOOLS = [
    'get_articles', 'get_article', 'get_profile', 'get_stats', 'trigger_deep_analysis'
]

def create_analyzer_mcp_server():
    # Implementation...

def get_analyzer_system_prompt() -> str:
    # Implementation...

async def create_analyzer_client(db):
    # Implementation...
```

### 2. CLI Chat Interface

**interfaces/chat_cli.py** - Terminal interface:
```python
"""CLI interface for interactive chat with news agent"""

import asyncio
from rich.console import Console
from claude_agent_sdk import AssistantMessage, TextBlock

from agents.chat import create_chat_client
from core.database import Database

console = Console()

STARTUP_PROMPT = """[Progressive reading startup prompt...]"""

async def run():
    """Run interactive CLI chat"""
    db = Database()

    console.print("\n[bold blue]🤖 Agent-driven Nyhetsläsare[/bold blue]\n")

    async with await create_chat_client(db) as client:
        # Startup routine
        await client.query(STARTUP_PROMPT)
        # Collect and display response...

        # Conversation loop
        while True:
            user_input = input().strip()
            if user_input.lower() in ['exit', 'quit', 'avsluta', 'q']:
                break
            await client.query(user_input)
            # Display response...

def main():
    """Entry point for CLI chat interface"""
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Avslutad[/yellow]")
```

### 3. Slack Chat Interface (WITH SECURITY)

**interfaces/chat_slack.py** - Slack interface with user restriction:
```python
"""Slack interface for interactive chat with news agent
SECURITY: Only allows specific user ID (private news bot)
"""

import os
import re
import asyncio
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from claude_agent_sdk import AssistantMessage, TextBlock

from agents.chat import create_chat_client
from core.database import Database

class SlackChatInterface:
    """Slack adapter for chat agent via Socket Mode (WebSocket)

    IMPORTANT: This bot is restricted to a single user for privacy.
    Set SLACK_ALLOWED_USER_ID in .env file.
    """

    def __init__(self):
        self.db = Database()
        self.allowed_user_id = os.getenv("SLACK_ALLOWED_USER_ID")

        if not self.allowed_user_id:
            raise ValueError(
                "SLACK_ALLOWED_USER_ID not set in .env!\n"
                "This bot requires user ID restriction for privacy."
            )

        self.app = App(
            token=os.getenv("SLACK_BOT_TOKEN"),
            signing_secret=os.getenv("SLACK_SIGNING_SECRET")
        )
        self._setup_listeners()

        print(f"🔒 Bot restricted to user: {self.allowed_user_id}")

    def _setup_listeners(self):
        """Register Slack event handlers with security checks"""

        @self.app.event("app_mention")
        def handle_mention(event, say):
            # Security check
            if not self._is_authorized_user(event["user"]):
                say("⛔ Denna bot är privat och endast tillgänglig för ägaren.")
                print(f"❌ Unauthorized access attempt by user: {event['user']}")
                return

            asyncio.run(self._handle_message(event["text"], say, event["channel"]))

        @self.app.event("message")
        def handle_dm(event, say):
            # Ignore bot's own messages
            if event.get("bot_id"):
                return

            # Security check
            if not self._is_authorized_user(event.get("user")):
                say("⛔ Denna bot är privat och endast tillgänglig för ägaren.")
                print(f"❌ Unauthorized DM attempt by user: {event.get('user')}")
                return

            # Only respond in DMs
            if event.get("channel_type") == "im":
                asyncio.run(self._handle_message(event["text"], say, event["channel"]))

    def _is_authorized_user(self, user_id: str) -> bool:
        """Check if user is authorized to use the bot"""
        is_authorized = user_id == self.allowed_user_id

        if not is_authorized:
            print(f"⚠️  Security: Blocked user {user_id} (allowed: {self.allowed_user_id})")

        return is_authorized

    async def _handle_message(self, text: str, say, channel_id: str):
        """Process message via chat agent and respond"""
        clean_text = self._remove_mention(text)

        if not clean_text:
            say("Hej! Fråga mig om dina nyheter. Till exempel: 'visa olästa artiklar'")
            return

        print(f"📨 Processing query: {clean_text[:50]}...")

        try:
            async with await create_chat_client(self.db) as client:
                await client.query(clean_text)

                response_parts = []
                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                response_parts.append(block.text)

                response = "\n".join(response_parts)

            formatted = self._format_for_slack(response)
            say(formatted)

            print(f"✅ Response sent ({len(response)} chars)")

        except Exception as e:
            error_msg = f"❌ Fel vid bearbetning: {str(e)}"
            say(error_msg)
            print(error_msg)

    def _remove_mention(self, text: str) -> str:
        """Remove @bot_name mention from message"""
        return re.sub(r'<@[A-Z0-9]+>', '', text).strip()

    def _format_for_slack(self, text: str) -> str:
        """Convert agent response to Slack mrkdwn format"""
        # For now, keep simple - Slack markdown is mostly compatible
        return text

    def start(self):
        """Start Socket Mode connection (WebSocket to Slack)"""
        handler = SocketModeHandler(
            self.app,
            os.getenv("SLACK_APP_TOKEN")
        )

        print("\n" + "="*60)
        print("🤖 Slack Chat Interface starting...")
        print("="*60)
        print(f"📡 Mode: Socket Mode (WebSocket)")
        print(f"🔒 Security: Single-user restriction enabled")
        print(f"👤 Allowed User ID: {self.allowed_user_id}")
        print("✓ Connected to Slack")
        print("\nBot is now listening for messages!")
        print("- Send DM to bot (only you can use it)")
        print("- @mention bot in channels (only you will get responses)")
        print("\nPress Ctrl+C to stop")
        print("="*60 + "\n")

        handler.start()

def main():
    """Entry point for Slack chat interface"""
    try:
        interface = SlackChatInterface()
        interface.start()
    except ValueError as e:
        print(f"\n❌ Configuration Error: {e}\n")
        exit(1)
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down Slack interface...")
```

### 4. Background Fetch Interface

**interfaces/fetch_and_analyze_cli.py** - Background job:
```python
"""CLI interface for background fetch and analysis"""

import asyncio
from rich.console import Console
from agents.analyzer import create_analyzer_client
from core.database import Database
from core.feed_fetcher import FeedFetcher

console = Console()

async def run():
    """Run background fetch and analysis"""
    db = Database()

    # Step 1: Fetch RSS articles
    console.print("[yellow]Fetching articles from RSS feeds...[/yellow]")
    fetcher = FeedFetcher(db=db)
    results = fetcher.fetch_all()
    console.print(f"[green]✓ Fetched {results['new_count']} new articles[/green]")

    # Step 2: Run analyzer agent
    console.print("\n[yellow]Starting analyzer agent...[/yellow]")
    async with await create_analyzer_client(db) as client:
        await client.query("Start autonomous analysis of all unanalyzed articles")
        # Collect response...

    console.print("[green]✓ Background task complete[/green]\n")

def main():
    """Entry point for CLI fetch & analyze interface"""
    try:
        asyncio.run(run())
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
```

### 5. Main Entry Point

**main.py** - Updated for interfaces:
```python
#!/usr/bin/env python3
"""News Reader - AI-powered RSS reader with multiple interfaces"""

import typer
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer(help="Intelligent RSS Reader - AI-powered news filtering")

@app.command()
def init():
    """Initialize the database and configuration."""
    from core.database import Database
    db = Database()
    db.init_database()
    typer.echo("✓ Database initialized")

@app.command()
def chat():
    """Launch interactive CLI chat interface."""
    from interfaces.chat_cli import main as chat_cli_main
    chat_cli_main()

@app.command()
def background():
    """Run background fetch and analysis (CLI interface)."""
    from interfaces.fetch_and_analyze_cli import main as fetch_cli_main
    fetch_cli_main()

@app.command()
def slack():
    """Launch Slack chat interface (Socket Mode)."""
    from interfaces.chat_slack import main as chat_slack_main
    chat_slack_main()

@app.command()
def cleanup(days: int = 30):
    """Clean up old articles from database."""
    from datetime import datetime, timedelta
    from core.database import Database

    db = Database()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM articles WHERE fetched_date < ?", (cutoff,))
        deleted = cursor.rowcount

    typer.echo(f"✓ Deleted {deleted} articles older than {days} days")

if __name__ == "__main__":
    app()
```

## Environment Configuration

### .env (with Slack security)
```bash
# Anthropic API
ANTHROPIC_API_KEY=sk-ant-your-api-key

# Slack Configuration (for chat_slack interface)
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-level-token
SLACK_SIGNING_SECRET=your-signing-secret

# CRITICAL SECURITY SETTING: Your Slack User ID
# Find your user ID: Click your profile in Slack → "Copy member ID"
# Or: https://www.workast.com/help/article/how-to-find-a-slack-user-id/
SLACK_ALLOWED_USER_ID=U01234ABCD
```

### .env.example (updated)
```bash
# Anthropic API
ANTHROPIC_API_KEY=sk-ant-your-api-key

# Slack Configuration (for chat_slack interface)
# Create Slack App at https://api.slack.com/apps
# 1. "Create New App" → "From scratch"
# 2. Enable Socket Mode (Settings → Socket Mode)
# 3. Subscribe to bot events: app_mention, message.im
# 4. Bot Token Scopes: chat:write, channels:history, app_mentions:read
# 5. Install App to Workspace
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-level-token
SLACK_SIGNING_SECRET=your-signing-secret

# SECURITY: Restrict bot to only your user ID
# Find your Slack User ID:
# 1. Click your profile in Slack
# 2. Select "View profile"
# 3. Click "More" (three dots) → "Copy member ID"
# Format: U01234ABCD (starts with U)
SLACK_ALLOWED_USER_ID=U01234ABCD
```

## Dependencies

### pyproject.toml (add)
```toml
dependencies = [
    # ... existing ...
    "slack-bolt>=1.26.0",  # Slack SDK with Socket Mode support
]
```

## Slack App Setup Guide

### Step 1: Create Internal App
1. Go to https://api.slack.com/apps
2. "Create New App" → "From scratch"
3. App Name: "News Bot (Private)"
4. Workspace: Your workspace
5. **IMPORTANT**: Choose **NOT** "Distribute to App Directory"

### Step 2: Enable Socket Mode
1. Settings → Socket Mode
2. Enable Socket Mode
3. Generate App-Level Token
   - Name: "news-bot-socket"
   - Scope: `connections:write`
   - Copy token → `SLACK_APP_TOKEN`

### Step 3: Configure Bot
1. OAuth & Permissions → Scopes → Bot Token Scopes:
   - `chat:write` - Send messages
   - `channels:history` - Read channel history
   - `app_mentions:read` - See @mentions
   - `im:history` - Read DM history

2. Event Subscriptions → Subscribe to Bot Events:
   - `app_mention` - When someone @mentions the bot
   - `message.im` - Direct messages

### Step 4: Install to Workspace
1. OAuth & Permissions → "Install to Workspace"
2. Copy "Bot User OAuth Token" → `SLACK_BOT_TOKEN`
3. Basic Information → Signing Secret → `SLACK_SIGNING_SECRET`

### Step 5: Find Your User ID

**Method 1: Via Slack UI (easiest)**
1. Click your profile in Slack (top right corner)
2. Select "View profile"
3. Click "More" (three dots) → "Copy member ID"
4. Paste in `.env` as `SLACK_ALLOWED_USER_ID`

**Method 2: Via Web URL**
When logged into Slack web, your profile URL contains your user ID:
```
https://app.slack.com/team/U01234ABCD
                          ^^^^^^^^^^^^ Your User ID
```

**Method 3: Via Bot (first time)**
```python
# Temporarily add in _handle_message to see your user ID
print(f"DEBUG - User ID: {event['user']}")
# Send a message to the bot → see your user ID in logs
# Add to .env and remove debug line
```

### Step 6: Test
```bash
python main.py slack
```

## Security Features

### 1. User ID Validation at Startup
- Bot's `__init__` checks that `SLACK_ALLOWED_USER_ID` exists in `.env`
- Throws ValueError if missing → bot won't start

### 2. User ID Check on Every Message
- `_is_authorized_user()` runs for ALL mentions and DMs
- Blocks immediately if user ID doesn't match
- Logs security attempts

### 3. Clear Error Messages
- Users get: "⛔ Denna bot är privat..."
- Console logs: "❌ Unauthorized access attempt by user: U98765XYZ"

### 4. Bot Ignores Its Own Messages
```python
if event.get("bot_id"):
    return  # Avoid loop
```

## Migration Plan

### Step 1: Create interfaces/ structure
- Create `interfaces/__init__.py`
- Create `interfaces/chat_cli.py` (move CLI logic from `agents/chat.py`)
- Create `interfaces/fetch_and_analyze_cli.py` (move from `agents/analyzer.py`)

### Step 2: Refactor agents/
- `agents/chat.py`: Export `create_chat_client()`, `CHAT_TOOLS`, system prompt
- `agents/analyzer.py`: Export `create_analyzer_client()`, `ANALYZER_TOOLS`
- Remove `main()` functions from agents - they move to interfaces

### Step 3: Create Slack interface
- Create `interfaces/chat_slack.py`
- Import and use `agents.chat.create_chat_client()`
- Implement Socket Mode WebSocket handler
- Add user ID security checks

### Step 4: Update main.py
- `chat` command → import `interfaces.chat_cli`
- `background` command → import `interfaces.fetch_and_analyze_cli`
- `slack` command → import `interfaces.chat_slack`

### Step 5: Test
- `python main.py chat` → Terminal chat (unchanged UX)
- `python main.py background` → Background job (unchanged)
- `python main.py slack` → Slack bot (new!)

## Usage

```bash
# CLI chat interface (terminal)
python main.py chat

# CLI background interface (scheduler)
python main.py background

# Slack chat interface (WebSocket)
python main.py slack
```

### Example: User Restriction in Action

**Only you can use the bot**:
```
# In Slack DM with bot:
You: visa olästa artiklar
Bot: [shows articles]

# If someone else tries:
Colleague: @NewsBot visa nyheter
Bot: ⛔ Denna bot är privat och endast tillgänglig för ägaren.
```

**Console output**:
```
🤖 Slack Chat Interface starting...
🔒 Bot restricted to user: U01234ABCD
✓ Connected to Slack

📨 Processing query: visa olästa artiklar...
✅ Response sent (2450 chars)

⚠️  Security: Blocked user U98765XYZ (allowed: U01234ABCD)
❌ Unauthorized access attempt by user: U98765XYZ
```

## Testing User Restriction

### Test 1: Authorized User (you)
1. Send DM to bot: "hej"
2. Expected: Bot responds
3. Console: `📨 Processing query: hej...`

### Test 2: Unauthorized User (colleague)
1. Ask colleague to send DM to bot
2. Expected: "⛔ Denna bot är privat..."
3. Console: `❌ Unauthorized access attempt by user: U98765XYZ`

## Benefits of This Architecture

✅ **Clear separation**: Agents = logic, Interfaces = I/O
✅ **Easy to add new interfaces**: Just create new file in `interfaces/`
✅ **Consistent naming**: `{what}_{service}.py`
✅ **Zero duplication**: Agents used by multiple interfaces
✅ **Easy to test**: Agents can be tested independent of interface
✅ **Scalable**: Add Discord, Telegram, API later
✅ **Secure**: User ID restriction protects private news from 34 colleagues

## Future Enhancements

- `chat_discord.py` - Discord bot
- `chat_api.py` - REST API endpoint
- `chat_telegram.py` - Telegram bot
- `summaries_slack.py` - Scheduled summaries to Slack channel
- Block Kit for interactive Slack elements (buttons for feedback)
- Threaded replies for long responses

## Security Summary

✅ **User ID validation** - Only your user ID allowed
✅ **Startup check** - Bot won't start without SLACK_ALLOWED_USER_ID
✅ **Runtime check** - Every message validated
✅ **Clear error messages** - Unauthorized users don't see your news
✅ **Audit logging** - All security attempts logged
✅ **Internal app** - Not distributed to App Directory

With this setup, your private news are 100% safe from your 34 colleagues! 🔒
