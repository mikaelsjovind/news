#!/usr/bin/env python3
"""
Analyzer Agent - Autonomous article analysis agent.

This agent analyzes unread articles, generates summaries, assigns relevance scores,
and performs deep analysis for configured sources. Runs every 30 minutes via scheduler.

No base classes, no inheritance - just straightforward code.

Uses Claude Agent SDK which requires:
- Local Claude Code CLI (for tooling/MCP)
- Anthropic API key and credits (for LLM inference)
"""

import asyncio
import os

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)
from rich.console import Console

from agents.mcp_tools import TOOLS
from core.database import Database
from core.profile_manager import ProfileManager

console = Console()

# Tools available for analyzer agent (7 tools - minimal write access)
ANALYZER_TOOLS = [
    'get_articles',
    'get_article',
    'get_profile',
    'get_stats',
    'save_article_analysis',  # PRIMARY tool for saving analysis
    'trigger_deep_analysis',
    'save_deep_analysis'
]


def create_mcp_server():
    """Create MCP server with analyzer tools."""
    sdk_tools = []

    for tool_name in ANALYZER_TOOLS:
        tool_info = TOOLS[tool_name]

        def make_tool_wrapper(name, func, desc, params):
            input_schema = params if params else {}

            @tool(name, desc, input_schema)
            async def wrapper(args):
                console.print(f"[dim]🔧 {name}[/dim]")
                result = func(args)
                import json
                result_json = json.dumps(result, ensure_ascii=False, indent=2)
                return {
                    "content": [
                        {"type": "text", "text": result_json}
                    ]
                }
            return wrapper

        sdk_tools.append(make_tool_wrapper(
            tool_name,
            tool_info['function'],
            tool_info['description'],
            tool_info['parameters']
        ))

    return create_sdk_mcp_server(
        name="news_tools",
        version="1.0.0",
        tools=sdk_tools
    )


def get_system_prompt(profile: ProfileManager) -> str:
    """Get system prompt for analyzer agent."""
    profile_data = profile.get_profile()
    top_topics = profile.get_top_topics(5)
    topics_str = ", ".join([f"{topic} ({weight:.1f})" for topic, weight in top_topics])

    return f"""Du är en autonom artikel-analysagent.

ANVÄNDARENS PROFIL:
- Huvudintressen: {topics_str}
- Antal ämnen i profil: {len(profile_data)}

DIN UPPGIFT:
Analysera ALLA olästa artiklar i systemet. Detta är en autonom bakgrundsuppgift.

VIKTIGA VERKTYG:
- get_articles: Hämta artiklar för analys
- get_article: Hämta fullständig artikel för djupanalys
- get_profile: Hämta användarprofil
- get_stats: Hämta statistik
- save_article_analysis: Spara sammanfattning + relevanspoäng (PRIMÄRT VERKTYG!)
- trigger_deep_analysis: Hämta djupanalysprompt (steg 1/2)
- save_deep_analysis: Spara djupanalysresultat (steg 2/2)

ANALYSPROCESS:
1. Använd get_articles(read_status='unread', limit=1000) för att hämta ALLA olästa artiklar
2. För VARJE artikel:
   - Analysera för relevans (0.0-1.0) baserat på användarprofil
   - Skapa koncis svensk sammanfattning (2-3 meningar)
   - SPARA med save_article_analysis(article_id, summary, relevance_score)
3. För artiklar från källor med deep_analysis=true (t.ex. Cornucopia):
   - Anropa trigger_deep_analysis(article_id) → få prompt
   - Exekvera prompten (skapa djupanalys)
   - Anropa save_deep_analysis(article_id, analysis_text) → spara

VIKTIGT:
- Detta är en AUTONOM uppgift - ingen användarinteraktion
- Analysera ALLA artiklar, hoppa inte över några
- Var effektiv men noggrann
- Rapportera kort vad du gjorde när du är klar
- Använd svenska i alla analyser

När du är klar, ge en kort sammanfattning:
"Analyserade X artiklar: Y högrelevanta, Z medelrelevanta, W lågrelevanta. Djupanalyserade N artiklar."
"""


async def run_analysis():
    """Run autonomous analysis."""
    db = Database()
    profile = ProfileManager(db=db)

    console.print("[bold blue]Starting autonomous analysis...[/bold blue]")

    # Load model from config
    import json
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        model = config.get('claude_model', 'claude-haiku-4-5-20251001')
    except (FileNotFoundError, json.JSONDecodeError):
        model = 'claude-haiku-4-5-20251001'  # Default fallback

    # Create MCP server
    mcp_server = create_mcp_server()
    console.print(f"[green]✓[/green] Loaded {len(ANALYZER_TOOLS)} tools")

    # Setup options
    allowed_tools = [f"mcp__news_tools__{tool_name}" for tool_name in ANALYZER_TOOLS]

    # NVM-specific configuration
    subprocess_env = os.environ.copy()
    subprocess_env["PATH"] = f"/Users/mikaelsjovind/.nvm/versions/node/v22.15.1/bin:{subprocess_env.get('PATH', '')}"

    options = ClaudeAgentOptions(
        mcp_servers={"news_tools": mcp_server},
        allowed_tools=allowed_tools,
        system_prompt=get_system_prompt(profile),
        permission_mode='bypassPermissions',
        cli_path="/Users/mikaelsjovind/.nvm/versions/node/v22.15.1/bin/claude",
        env=subprocess_env,
        model=model
    )

    # Create client and run analysis
    async with ClaudeSDKClient(options=options) as client:
        # Send analysis task
        analysis_task = """Analysera alla olästa artiklar i systemet.

STEG-FÖR-STEG:
1. Hämta alla olästa artiklar med get_articles(read_status='unread', limit=1000)
2. För varje artikel:
   - Bedöm relevans (0.0-1.0) baserat på användarprofil
   - Skapa koncis svensk sammanfattning (2-3 meningar)
   - SPARA med save_article_analysis(article_id, summary, relevance_score)
3. Identifiera artiklar från källor med deep_analysis=true
4. För dessa artiklar:
   - Använd trigger_deep_analysis(article_id) för att få prompt
   - Exekvera prompten och skapa djupanalys
   - Spara med save_deep_analysis(article_id, analysis_text)

KRITISKT: Du MÅSTE använda save_article_analysis() för att spara varje artikels sammanfattning och relevanspoäng!

När du är klar, ge en sammanfattning av vad du gjorde.

BÖRJA NU!"""

        await client.query(analysis_task)

        # Collect response
        response_text = []
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text.append(block.text)
                        console.print(f"[cyan]Agent:[/cyan] {block.text}")

        final_response = "\n".join(response_text)
        console.print("\n[green]✓[/green] Analysis complete!")
        return final_response


def main():
    """Main entry point."""
    try:
        result = asyncio.run(run_analysis())
        console.print(f"\n[green]Analysis complete:[/green]\n{result}")
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Interrupted[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
