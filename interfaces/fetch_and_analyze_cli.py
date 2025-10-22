#!/usr/bin/env python3
"""
CLI interface for background fetching and analysis.

This interface combines RSS feed fetching with autonomous article analysis.
Used by the scheduler (launchd) to run background tasks every 30 minutes.
"""

import asyncio

from rich.console import Console

from agents.analyzer import run_analysis
from core.feed_fetcher import FeedFetcher

console = Console()


def main():
    """Main entry point for background fetch and analyze."""
    console.print("[bold blue]Background Fetch & Analyze[/bold blue]\n")

    # Step 1: Fetch new articles from all RSS feeds
    console.print("[cyan]Step 1:[/cyan] Fetching articles from RSS feeds...")
    fetcher = FeedFetcher()
    new_count = fetcher.fetch_all()
    console.print(f"[green]✓[/green] Fetched {new_count} new articles\n")

    # Step 2: Run autonomous analysis
    console.print("[cyan]Step 2:[/cyan] Running autonomous analysis...")
    try:
        _ = asyncio.run(run_analysis())
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Interrupted[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error during analysis: {e}[/red]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
