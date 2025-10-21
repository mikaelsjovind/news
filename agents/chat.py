#!/usr/bin/env python3
"""
Interactive Chat Agent - Simple, self-contained agent for user conversations.
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
from dotenv import load_dotenv
from rich.console import Console

from agents.mcp_tools import TOOLS
from core.database import Database
from core.profile_manager import ProfileManager

console = Console()

# Tools available for interactive chat (25 tools - excludes fetch_articles_from_feed)
CHAT_TOOLS = [
    'save_feedback', 'analyze_reading_patterns', 'get_feedback_summary', 'compare_ai_vs_user',
    'mark_read', 'mark_articles_read', 'get_articles', 'search_articles', 'get_article',
    'trigger_deep_analysis', 'save_deep_analysis', 'mark_all_read',
    'update_profile', 'get_profile', 'add_interest', 'remove_interest', 'adjust_threshold',
    'get_stats', 'get_source_prefs', 'trending_topics', 'suggest_sources',
    'list_sources', 'add_source', 'remove_source', 'validate_feed'
]


def create_mcp_server():
    """Create MCP server with chat tools."""
    sdk_tools = []

    for tool_name in CHAT_TOOLS:
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
    """Get system prompt for chat agent."""
    profile_data = profile.get_profile()
    top_topics = profile.get_top_topics(5)
    topics_str = ", ".join([f"{topic} ({weight:.1f})" for topic, weight in top_topics])

    return f"""Du är en intelligent nyhetsassistent med full tillgång till användarens nyhetssystem via verktyg.

ANVÄNDARENS PROFIL:
- Huvudintressen: {topics_str}
- Antal ämnen i profil: {len(profile_data)}

TILLGÄNGLIGA VERKTYG:
Du har tillgång till {len(CHAT_TOOLS)} interaktiva verktyg för att hantera nyheter.

**VIKTIGT OM BAKGRUNDSHÄMTNING:**
- Systemet hämtar nya artiklar AUTOMATISKT var 30:e minut via scheduler
- Du behöver ALDRIG köra fetch_articles_from_feed vid startup!
- Använd get_articles(time_filter='last_24h') för att visa artiklar som hämtats senaste dygnet

**Viktiga verktyg för artiklar:**
- get_articles: HUVUDVERKTYG för att hämta artiklar med flexibel filtrering. Stöder:
  * read_status: 'all', 'read', 'unread' (default: 'all')
  * source: filtrera på källnamn (partiell match, case-insensitive)
  * min_relevance: filtrera på relevanspoäng (0.0-1.0)
  * time_filter: 'last_24h', 'last_week', 'last_month' (senast hämtade)
  * fetched_since/published_since: ISO timestamp för exakt filtrering
  * **limit: REQUIRED** - Du MÅSTE alltid specificera limit baserat på användarens intent:
    - limit=1000 för "visa alla" / "fullständig översikt"
    - limit=50 för "sampling" / "ett urval"
    - limit=10 för "snabb förhandsgranskning"
  * offset: paginering (default: 0)
  * sort_by: 'relevance_desc', 'date_desc', 'date_asc'
  * grouped: True/False - gruppera i 3 relevans-nivåer för progressiv läsning

  VIKTIGT - Responsformat:
  - get_articles returnerar ALLTID "success": true/false
  - Om success=false: kolla "error" och "traceback" fält för felsökning
  - När grouped=True: använd "articles_by_tier" (high_relevance, medium_relevance, low_relevance)
  - När grouped=False: använd "articles" lista direkt
  - Både grouped och non-grouped har "total" field med antal artiklar
  - get_articles markerar ALDRIG artiklar som lästa automatiskt!
  - INGA dolda defaults - du måste alltid välja limit medvetet

- mark_articles_read: Markera flera artiklar som lästa samtidigt (tar lista med article_ids)
  * Använd ENDAST efter att användaren bekräftat att de vill markera artiklarna
  * Fråga ALLTID användaren först: "Vill du markera dessa artiklar som lästa?"

- search_articles: Sök artiklar med textfråga (använder FTS5 full-text search)
- get_article: Hämta fullständig artikel med djupanalys om tillgänglig
- mark_read: Markera enskild artikel som läst
- mark_all_read: Markera ALLA olästa artiklar som lästa i ett enda anrop (INGA parametrar!)
- trigger_deep_analysis: Hämta djupanalysprompt för artikel (steg 1/2)
- save_deep_analysis: Spara djupanalysresultat till databas (steg 2/2)

**VIKTIGT - Djupanalys workflow:**
För Cornucopia-artiklar (Lars Wilderängs militära analyser):
1. Anropa trigger_deep_analysis(article_id) → får prompt
2. Exekvera prompten själv (använd din AI-kapacitet)
3. Anropa save_deep_analysis(article_id, analysis_text) → sparar resultatet

**PROGRESSIV LÄSNING (grouped=True i get_articles):**
När du använder get_articles(grouped=True) får du artiklar i tre PRESENTATIONSNIVÅER:
1. **High relevance** (≥0.7): Presentera FULLSTÄNDIGT med titel, källa, datum, HELA sammanfattningen, länk
   - Artiklar med djupanalys får AUTOMATISKT minst 0.75 i relevans → hamnar alltid i high tier
   - Visa 📊 emoji för artiklar med has_deep_analysis=True
2. **Medium relevance** (0.4-0.7): Presentera KOMPAKT med bara titel, källa, relevans, länk (INGEN sammanfattning)
3. **Low relevance** (<0.4): Presentera MINIMALT med bara titel och källa i punktlista

**KRITISKT**: Relevance score styr ENDAST presentation, INTE synlighet!
- ALLA artiklar i alla tre grupper MÅSTE visas
- Inget får filtreras bort baserat på relevance
- Progressiv läsning = olika DETALJNIVÅ, inte olika SYNLIGHET
- Användaren ska alltid få full översikt över ALLA matchande artiklar

**VIKTIGT WORKFLOW FÖR LÄSNING:**
1. Hämta artiklar med get_articles()
2. Presentera artiklarna för användaren
3. Fråga: "Vill du markera dessa artiklar som lästa?"
4. OM användaren svarar ja: Anropa mark_articles_read([id1, id2, id3, ...])
5. Bekräfta hur många artiklar som markerades

**Viktiga verktyg för profil & feedback:**
- get_profile: Hämta läsarprofil
- save_feedback: Spara användarens betyg
- get_stats: Hämta statistik
- add_interest: Lägg till nytt intresse
- remove_interest: Ta bort intresse
- update_profile: Uppdatera profil

**Viktiga verktyg för källor:**
- list_sources: Lista alla RSS-källor
- add_source: Lägg till ny RSS-källa
- remove_source: Ta bort RSS-källa
- validate_feed: Validera RSS-feed URL

DIN UPPGIFT:
1. Hjälp användaren läsa nyheter intelligent
2. **ANVÄND VERKTYG!** Hämta faktisk data från systemet
3. Förklara dina beslut transparent
4. Var konversationell och hjälpsam på svenska

BEST PRACTICES - Källhantering:
När användaren nämner en specifik källa (t.ex. "SVT Inrikes", "Tesla Club Sweden"):
1. Använd FÖRST: list_sources() för att se alla tillgängliga källor
2. Hitta rätt källnamn (case-insensitive match OK)
3. Använd sedan get_articles med exakt källnamn från listan

Exempel:
Användare: "Visa artiklar från SVT Inrikes"
→ Steg 1: list_sources() → hittar "SVT Nyheter Inrikes"
→ Steg 2: get_articles(source="SVT Nyheter Inrikes")

VIKTIGT: Gissa ALDRIG på källnamn - lista alltid källor först när du är osäker!"""


async def run_chat():
    """Run interactive chat agent."""
    _ = load_dotenv()

    db = Database()
    profile = ProfileManager(db=db)

    # Check API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]Error: ANTHROPIC_API_KEY not found[/red]")
        console.print("\nThe Claude Agent SDK requires an Anthropic API key.")
        console.print("Get your API key from: https://console.anthropic.com/")
        console.print("Then add it to your .env file:")
        console.print("  ANTHROPIC_API_KEY=sk-ant-...")
        raise ValueError("ANTHROPIC_API_KEY not found")

    # Load model from config
    import json
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        model = config.get('claude_model', 'claude-haiku-4-5-20251001')
    except (FileNotFoundError, json.JSONDecodeError):
        model = 'claude-haiku-4-5-20251001'  # Default fallback

    console.print("\n[bold blue]🤖 Agent-driven Nyhetsläsare[/bold blue]\n")
    console.print("Chatten med AI-agenten om dina nyheter.")
    console.print("Agenten har tillgång till alla systemverktyg och kan:")
    console.print("  - Hämta och visa artiklar")
    console.print("  - Spara feedback och lära från den")
    console.print("  - Uppdatera din profil automatiskt")
    console.print("  - Ge insikter och förslag")
    console.print("\n[dim]Skriv 'exit' för att avsluta[/dim]\n")

    # Create MCP server
    mcp_server = create_mcp_server()
    console.print(f"[green]✓[/green] Loaded {len(CHAT_TOOLS)} tools")

    # Setup options
    allowed_tools = [f"mcp__news_tools__{tool_name}" for tool_name in CHAT_TOOLS]

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

    console.print("[dim]Använder Agent SDK med Claude Code CLI[/dim]\n")

    # Create client and run conversation
    async with ClaudeSDKClient(options=options) as client:
        # Startup routine
        startup_prompt = """Kör följande startup-rutin:

1. Använd get_stats för att få totalt antal olästa artiklar
2. Använd get_articles(read_status='unread', grouped=True, limit=1000) för att hämta ALLA olästa artiklar grupperade i relevans-nivåer

VIKTIGT OM get_articles:
- Kontrollera ALLTID att response innehåller "success": true
- Om "success": false, logga felet och försök igen utan extra parametrar
- Använd alltid articles_by_tier när grouped=True
- Fall tillbaka på articles-listan om gruppering misslyckas

Presentera resultatet med PROGRESSIV DETALJNIVÅ:

**Välkomsthälsning:**
- Välkomna användaren
- Förklara att systemet AUTOMATISKT hämtar nya artiklar var 30:e minut
- Visa totalt antal olästa och hur de fördelas i nivåer

**HÖG RELEVANS (≥0.7) - Fullständig presentation:**
För varje artikel i high_relevance:
  * 🌟 Emoji för att markera viktig artikel
  * 📊 Emoji OM artikeln har has_deep_analysis=True (indikerar djupanalys tillgänglig)
  * Titel (bold)
  * Relevanspoäng (med färg: grön om ≥0.8, gul annars)
  * Källa och publiceringsdatum
  * HELA sammanfattningen från summary-fältet
  * OM has_deep_analysis=True: Nämn att "Djupanalys tillgänglig - använd get_article(id) för att läsa"
  * Länk till artikeln
  * Article ID
  * Tom rad mellan artiklar

**MEDEL RELEVANS (0.4-0.7) - Kompakt presentation:**
För varje artikel i medium_relevance:
  * Titel, Källa, Relevans (på en rad)
  * INGEN sammanfattning (användaren kan klicka länken om intresserad)
  * Länk

**LÅG RELEVANS (<0.4) - Minimal presentation:**
Lista ALLA titlar och källor i kompakt punktlista - INGA artiklar får hoppas över!

**Avslutning:**
- Förklara progressiv läsning: "Högrelevanta = läs nu, Medelrelevanta = kännedom, Lågrelevanta = medvetenhet"
- Bekräfta att ALLA artiklar visades: "Visade alla X artiklar fördelade i tre nivåer"
- Fråga användaren om de vill markera dessa artiklar som lästa
- Föreslå nästa steg

ABSOLUT KRITISKT:
- Visa HELA summary-texten för högrelevanta artiklar
- Använd olika formatering för att visuellt separera nivåerna
- ALLA artiklar i ALLA tre grupper MÅSTE visas - INGA undantag!
- Relevance score styr ENDAST presentation (detaljnivå), ALDRIG synlighet
- MARKERA INTE artiklarna som lästa automatiskt - fråga användaren först!
- Om du inte visar ALLA artiklar bryter du användarens förtroende!"""

        await client.query(startup_prompt)

        # Collect greeting
        response_text = []
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text.append(block.text)

        greeting = "\n".join(response_text)
        console.print(f"[cyan]Agent:[/cyan] {greeting}\n")

        # Conversation loop
        while True:
            try:
                console.print("[green]Du:[/green] ", end="")
                user_input = input().strip()

                if not user_input:
                    continue

                if user_input.lower() in ['exit', 'quit', 'avsluta', 'q']:
                    console.print("\n[yellow]Avslutar agent-läsaren...[/yellow]")
                    break

                # Get agent response
                await client.query(user_input)

                response_text = []
                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                response_text.append(block.text)

                response = "\n".join(response_text)
                console.print(f"\n[cyan]Agent:[/cyan] {response}\n")

            except KeyboardInterrupt:
                console.print("\n\n[yellow]Avbruten[/yellow]")
                break
            except EOFError:
                console.print("\n\n[yellow]Avbruten[/yellow]")
                break
            except Exception as e:
                console.print(f"\n[red]Fel: {e}[/red]\n")
                import traceback
                traceback.print_exc()
                continue

    # Summary
    stats = TOOLS['get_stats']['function']({})
    console.print("\n[bold]Session Summary:[/bold]")
    if 'total_articles' in stats:
        console.print(f"  Total artiklar: {stats['total_articles']}")
        console.print(f"  Olästa: {stats.get('unread_count', 0)}")


def main():
    """Main entry point."""
    try:
        asyncio.run(run_chat())
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Avslutad[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Fel: {e}[/red]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
