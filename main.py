#!/usr/bin/env python3
"""
Intelligent RSS Reader CLI
AI-powered news reader with personalized filtering and summarization.
"""

import os
from datetime import datetime
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
    Launch interactive AI agent chat (25 tools).

    Provides full access to the news system via natural conversation.
    Can fetch articles, manage profile, give statistics, handle feedback, and more.

    Requires:
    - Claude Code CLI (local, for tooling/MCP)
    - Anthropic API key and credits (for LLM inference)
    Get API key from: https://console.anthropic.com/
    """
    try:
        from agents.chat import main as chat_main
        chat_main()
    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print("Make sure all dependencies are installed: pip install -r requirements.txt")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@app.command()
def background():
    """
    Run autonomous background analysis (6 tools only).

    This command is called by the scheduler every 30 minutes.
    Fetches RSS feeds and analyzes all unanalyzed articles via Claude Agent SDK.

    Requires Anthropic API credits for analysis.
    Manual usage: python main.py background
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        console.print(f"\n[bold blue]Background Fetch + Analysis[/bold blue] - {timestamp}\n")

        # 1. Fetch RSS feeds
        console.print("[bold]Step 1: Fetching RSS feeds...[/bold]")
        from core.feed_fetcher import FeedFetcher
        fetcher = FeedFetcher()
        result = fetcher.fetch_all()

        console.print("[green]✓[/green] Fetch complete!")
        console.print(f"  Sources checked: {result['total_sources']}")
        console.print(f"  Articles found: {result['total_fetched']}")
        console.print(f"  New articles: {result['total_new']}")

        errors: list[str] = result.get('errors', [])  # type: ignore[assignment]
        if errors:
            console.print("[yellow]Warnings:[/yellow]")
            for error in errors:
                console.print(f"  {error}")

        # 2. Check if analysis needed
        analyzer = ArticleManager()
        unanalyzed = analyzer.get_unanalyzed_articles()

        if not unanalyzed:
            console.print("\n[green]✓[/green] No unanalyzed articles found")
            console.print("\n[green]✓[/green] Background task complete\n")
            return

        console.print(f"\n[bold]Step 2: Analyzing {len(unanalyzed)} articles...[/bold]")
        console.print("[dim]Launching autonomous analyzer via Claude Agent SDK (uses API credits)[/dim]\n")

        # 3. Run autonomous analysis
        from agents.analyzer import main as analyzer_main
        analyzer_main()

        console.print("\n[green]✓[/green] Background fetch + analysis complete\n")

    except Exception as e:
        console.print(f"\n[red]Error during background task: {e}[/red]\n")
        import traceback
        traceback.print_exc()
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
