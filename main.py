#!/usr/bin/env python3
"""
Intelligent RSS Reader CLI
AI-powered news reader with personalized filtering and summarization.
"""

import os
from typing import Annotated, Any

import typer
from rich.console import Console

from core.article_manager import ArticleManager
from core.database import Database

app = typer.Typer(help="Intelligent RSS Reader - AI-powered news filtering")
console = Console()


@app.command()
def init() -> None:
    """Initialize the database and configuration."""
    console.print("\n[bold blue]Initializing RSS Reader...[/bold blue]\n")

    _ = Database()  # Initialize database (side effect)
    console.print("[green]✓[/green] Database initialized")

    # Check for .env file
    if not os.path.exists(".env"):
        console.print("[yellow]![/yellow] No .env file found")
        console.print("  Copy .env.example to .env and add your Anthropic API key")
        console.print("  Get your key from: https://console.anthropic.com/")
    else:
        console.print("[green]✓[/green] .env file found")

    # Check for config
    if not os.path.exists("config.json"):
        console.print("[yellow]![/yellow] No config.json found, creating default...")
        # Create default config.json
        import json
        default_config: dict[str, Any] = {
            "database_path": "news.db",
            "max_articles_per_source": 50,
            "fetch_interval_hours": 24,
            "claude_model": "claude-sonnet-4-5-20250929",
            "max_tokens_per_summary": 200,
            "relevance_threshold": 0.6,
            "user_interests": {
                "description": "",
                "topics": [],
                "priorities": {
                    "high": [],
                    "medium": [],
                    "low": []
                }
            }
        }
        with open("config.json", 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        console.print("[green]✓[/green] Created default config.json")
    else:
        console.print("[green]✓[/green] config.json found")

    console.print("\n[bold green]Setup complete![/bold green]")
    console.print("\nNext steps:")
    console.print("  1. Start chat agent: [cyan]python main.py chat[/cyan]")
    console.print("  2. Install scheduler: [cyan]./install_scheduler.sh[/cyan]")
    console.print("\nThe chat agent handles everything: reading, feedback, sources, and configuration.")


@app.command()
def cleanup(
    days: Annotated[int, typer.Option(help="Remove articles older than N days")] = 30
) -> None:
    """Clean up old articles from database."""
    article_mgr = ArticleManager()

    confirm = typer.confirm(f"Remove articles older than {days} days?")
    if not confirm:
        console.print("Cancelled")
        return

    count = article_mgr.cleanup_old_articles(days)
    console.print(f"\n[green]✓[/green] Removed {count} old articles")


@app.command()
def chat():
    """
    Launch interactive AI agent chat (CLI interface).

    Provides full access to the news system via natural conversation.
    Can fetch articles, manage profile, give statistics, handle feedback, and more.

    Requires:
    - Claude Code CLI (local, for tooling/MCP)
    - Anthropic API key and credits (for LLM inference)
    Get API key from: https://console.anthropic.com/
    """
    try:
        from interfaces.chat_cli import main as chat_cli_main
        chat_cli_main()
    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("Make sure all dependencies are installed: pip install -e .")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@app.command()
def background():
    """
    Run autonomous background fetch and analysis.

    This command is called by the scheduler every 30 minutes.
    Fetches RSS feeds and analyzes all unanalyzed articles via Claude Agent SDK.

    Requires Anthropic API credits for analysis.
    Manual usage: python main.py background
    """
    try:
        from interfaces.fetch_and_analyze_cli import main as background_main
        background_main()
    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("Make sure all dependencies are installed: pip install -e .")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@app.command()
def slack():
    """
    Launch Slack bot interface.

    Connects to your Slack workspace via Socket Mode (WebSocket).
    Allows you to interact with the chat agent via Slack messages.

    SECURITY: Only the user specified in SLACK_ALLOWED_USER_ID can use the bot.

    Requires:
    - SLACK_BOT_TOKEN in .env (xoxb-...)
    - SLACK_APP_TOKEN in .env (xapp-...)
    - SLACK_ALLOWED_USER_ID in .env (your Slack user ID)
    - Anthropic API key and credits
    """
    try:
        import asyncio

        from interfaces.chat_slack import main as slack_main
        asyncio.run(slack_main())
    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("Make sure slack-bolt is installed: pip install -e .")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


if __name__ == "__main__":
    app()
