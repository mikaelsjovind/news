#!/usr/bin/env python3
"""
CLI interface for the chat agent.

This is a thin wrapper around the chat agent that provides
an interactive command-line interface for user conversations.
"""

import asyncio

from agents.chat import run_chat


def main():
    """Main entry point for CLI chat interface."""
    try:
        asyncio.run(run_chat())
    except KeyboardInterrupt:
        print("\n\nAvslutad")
    except Exception as e:
        print(f"\nFel: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
