#!/usr/bin/env python3
"""
Slack interface for the chat agent.

This interface provides a Slack bot that connects to your workspace
and allows you to interact with the chat agent via Slack messages.

SECURITY: Only the user specified in SLACK_ALLOWED_USER_ID can use the bot.
This is critical since there are 35 people in the workspace but the bot
accesses personal news data that should remain private.

Uses Socket Mode (WebSocket) - no public URL required.
"""

import asyncio
import logging
import os
import re

from claude_agent_sdk import AssistantMessage, TextBlock
from dotenv import load_dotenv
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp

from agents.chat import create_chat_client

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def format_for_slack(text: str) -> str:
    """
    Convert markdown-style formatting to Slack mrkdwn format.

    Conversions:
    - [text](url) → <url|text>
    - **bold** → *bold*
    - ## Header → *Header*
    """
    # Convert markdown links [text](url) to Slack format <url|text>
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<\2|\1>', text)

    # Convert **bold** to *bold* (Slack uses single asterisks)
    text = re.sub(r'\*\*([^*]+)\*\*', r'*\1*', text)

    # Convert ## headers to *bold* (Slack doesn't have native headers in messages)
    text = re.sub(r'^##\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)
    text = re.sub(r'^#\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)

    return text

# Load environment variables
_ = load_dotenv()

# Initialize Slack app
app = AsyncApp(token=os.environ.get("SLACK_BOT_TOKEN"))

# Security: Only this user can access the bot
ALLOWED_USER_ID = os.environ.get("SLACK_ALLOWED_USER_ID")

# Store active agent clients per user (in case we expand access later)
active_clients = {}


def is_user_authorized(user_id: str) -> bool:
    """Check if user is authorized to use the bot."""
    if not ALLOWED_USER_ID:
        logger.error("SLACK_ALLOWED_USER_ID not set in environment")
        return False
    return user_id == ALLOWED_USER_ID


@app.event("app_mention")
async def handle_mention(event, say):
    """Handle @mentions of the bot."""
    user_id = event["user"]
    text = event["text"]
    channel = event["channel"]

    # Security check
    if not is_user_authorized(user_id):
        logger.warning(f"Unauthorized access attempt by user {user_id}")
        await say(
            "❌ Tyvärr, denna bot är privat och endast tillgänglig för en specifik användare.\n\n"
            "Om du tror detta är ett fel, kontakta bot-ägaren.",
            thread_ts=event.get("ts")
        )
        return

    # Remove bot mention from text
    message = text.split('>', 1)[1].strip() if '>' in text else text.strip()

    if not message:
        await say(
            "Hej! Jag är din nyhetsassistent. Ställ mig en fråga om dina nyheter!",
            thread_ts=event.get("ts")
        )
        return

    try:
        # Get or create client for this user
        if user_id not in active_clients:
            logger.info(f"Creating new agent client for user {user_id}")
            active_clients[user_id] = create_chat_client()

        client = active_clients[user_id]

        # Send "thinking" indicator
        thinking_msg = await say("🤔 Tänker...", thread_ts=event.get("ts"))

        # Get response from agent
        async with client:
            await client.query(message)

            response_text = []
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            response_text.append(block.text)

            response = "\n".join(response_text)

        # Format response for Slack (convert markdown links, etc.)
        formatted_response = format_for_slack(response)

        # Delete thinking message and send actual response
        _ = await app.client.chat_delete(
            channel=channel,
            ts=thinking_msg["ts"]
        )
        await say(formatted_response, thread_ts=event.get("ts"))

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        await say(
            f"❌ Ett fel uppstod: {str(e)}\n\n"
            f"Försök igen eller kontakta administratören om problemet kvarstår.",
            thread_ts=event.get("ts")
        )


@app.event("message")
async def handle_message(event, say):
    """Handle direct messages to the bot."""
    # Ignore bot messages and threaded messages (handled by mentions)
    if event.get("subtype") or event.get("thread_ts"):
        return

    user_id = event["user"]
    text = event["text"]
    channel = event["channel"]

    # Security check
    if not is_user_authorized(user_id):
        logger.warning(f"Unauthorized DM attempt by user {user_id}")
        await say(
            "❌ Tyvärr, denna bot är privat och endast tillgänglig för en specifik användare.\n\n"
            "Om du tror detta är ett fel, kontakta bot-ägaren."
        )
        return

    try:
        # Get or create client for this user
        if user_id not in active_clients:
            logger.info(f"Creating new agent client for user {user_id}")
            active_clients[user_id] = create_chat_client()

        client = active_clients[user_id]

        # Send "thinking" indicator
        thinking_msg = await say("🤔 Tänker...")

        # Get response from agent
        async with client:
            await client.query(text)

            response_text = []
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            response_text.append(block.text)

            response = "\n".join(response_text)

        # Format response for Slack (convert markdown links, etc.)
        formatted_response = format_for_slack(response)

        # Delete thinking message and send actual response
        _ = await app.client.chat_delete(
            channel=channel,
            ts=thinking_msg["ts"]
        )
        await say(formatted_response)

    except Exception as e:
        logger.error(f"Error processing DM: {e}", exc_info=True)
        await say(
            f"❌ Ett fel uppstod: {str(e)}\n\n"
            f"Försök igen eller kontakta administratören om problemet kvarstår."
        )


async def main():
    """Start the Slack bot."""
    # Validate configuration
    if not os.environ.get("SLACK_BOT_TOKEN"):
        logger.error("SLACK_BOT_TOKEN not found in environment")
        print("\n❌ Error: SLACK_BOT_TOKEN not found")
        print("\nPlease add to your .env file:")
        print("  SLACK_BOT_TOKEN=xoxb-...")
        return

    if not os.environ.get("SLACK_APP_TOKEN"):
        logger.error("SLACK_APP_TOKEN not found in environment")
        print("\n❌ Error: SLACK_APP_TOKEN not found")
        print("\nPlease add to your .env file:")
        print("  SLACK_APP_TOKEN=xapp-...")
        return

    if not ALLOWED_USER_ID:
        logger.error("SLACK_ALLOWED_USER_ID not found in environment")
        print("\n❌ Error: SLACK_ALLOWED_USER_ID not found")
        print("\nPlease add to your .env file:")
        print("  SLACK_ALLOWED_USER_ID=U1234567890")
        print("\nTo find your user ID:")
        print("  1. In Slack, click your profile picture")
        print("  2. Select 'Profile'")
        print("  3. Click '...' (More)")
        print("  4. Select 'Copy member ID'")
        return

    logger.info("Starting Slack bot...")
    logger.info(f"Authorized user: {ALLOWED_USER_ID}")

    print("\n🤖 Slack News Bot Starting...")
    print(f"✓ Authorized user: {ALLOWED_USER_ID}")
    print("✓ Connecting to Slack via Socket Mode...")

    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    await handler.start_async()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        print("\n\n👋 Bot stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
