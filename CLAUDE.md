# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **AI-powered RSS news reader** that uses **Claude Agent SDK** (requires Anthropic API credits) for all article analysis. The system features two specialized agents (chat and background) that interact with 25 MCP tools to provide personalized news filtering and summarization.

**Note**: While the SDK uses local Claude Code CLI for tooling/MCP (free), it still makes API calls to Anthropic for LLM inference (consumes credits).

**Key Architecture Principle**: Simple, flat, self-contained. No inheritance, no base classes, no complex layers.

## Quick Development Commands

### Setup
```bash
# First time setup
python3 -m venv venv
source venv/bin/activate

# Install project dependencies
pip install -e .

# Install development tools (optional)
pip install -e ".[dev]"

# Initialize database
python main.py init

# Add API key to .env
cp .env.example .env
# Edit .env and add ANTHROPIC_API_KEY
```

### Common Commands
```bash
# Launch interactive chat agent (24 tools)
# The chat agent handles ALL user interactions: reading, feedback, sources, stats
python main.py chat

# Run background fetch + analysis (5 tools)
# Called automatically by scheduler every 30 minutes
python main.py background

# Clean up old articles (maintenance)
python main.py cleanup
```

### Scheduler
```bash
# Install background service (runs every 30 minutes)
./install_scheduler.sh

# Uninstall background service
./uninstall_scheduler.sh
```

### Code Quality
```bash
# Run Ruff linter to check for code quality issues
ruff check .

# Automatically fix issues that can be safely fixed
ruff check . --fix

# Check specific file
ruff check agents/chat.py

# Format code (if needed)
ruff format .

# Run Basedpyright type checker
basedpyright .

# Check specific file
basedpyright main.py

# Run both linter and type checker
ruff check . && basedpyright .
```

**IMPORTANT for Claude Code:**
- ALWAYS run `ruff check . && basedpyright .` before committing changes
- Fix ALL errors and warnings reported by both tools
- Use `ruff check . --fix` to auto-fix simple issues
- Basedpyright configuration is in `pyproject.toml` under `[tool.basedpyright]`

## Architecture Deep Dive

### Core Principle: Zero Direct API Calls in `core/`

The `core/` directory contains **business logic only** - it makes ZERO direct API calls to Anthropic. All AI interactions happen via Claude Agent SDK through agents.

**Critical distinction**:
- `core/` modules - **Feature-based managers** for data access (NO API calls)
- `agents/chat.py` & `agents/analyzer.py` - Execute AI analysis via Claude Agent SDK (uses Anthropic API)

### Directory Structure

```
news/
├── core/                     # Business logic (NO API calls!)
│   ├── database.py           # Low-level DB connection + schema
│   ├── source_manager.py     # RSS source configuration management
│   ├── feed_fetcher.py       # RSS feed fetching and parsing
│   ├── article_manager.py    # Article CRUD + analysis queries
│   ├── profile_manager.py    # User profile + learning
│   └── feedback_manager.py   # Feedback + statistics
│
├── agents/                   # Two simple agents
│   ├── chat.py              # Interactive agent (24 tools)
│   ├── analyzer.py          # Analyzer agent (5 tools)
│   └── mcp_tools.py         # 25 MCP tool definitions
│
└── main.py                  # Minimal CLI (4 commands: init, chat, background, cleanup)
```

**Feature-Based Managers**:
- **SourceManager**: RSS sources configuration (add/remove/list sources.json) (implements own SQL)
- **FeedFetcher**: RSS feed fetching and parsing using feedparser (implements own SQL)
- **ArticleManager**: Article CRUD, querying, filtering, deep analysis prompts (implements own SQL)
- **ProfileManager**: Topic management, weight adjustment, learning from feedback (implements own SQL)
- **FeedbackManager**: User ratings, statistics, AI accuracy tracking (implements own SQL)
- **Database**: **Connection and schema ONLY** - NO CRUD methods, just `get_connection()` and `init_database()`

### The Two Agents

**Chat Agent** (`agents/chat.py`):
- **Purpose**: Interactive conversations with user
- **Tools**: 24 tools (all except `fetch_articles_from_feed`)
- **System prompt**: Swedish, conversational, helpful
- **Key features**:
  - Progressive reading with grouped articles
  - Natural language article filtering
  - Profile management and feedback
  - Source management

**Analyzer Agent** (`agents/analyzer.py`):
- **Purpose**: Autonomous article analysis
- **Tools**: 5 read-only tools (`get_articles`, `get_article`, `get_profile`, `get_stats`, `trigger_deep_analysis`)
- **System prompt**: Autonomous task completion
- **Key features**:
  - Analyzes ALL unanalyzed articles
  - Generates summaries and relevance scores
  - Executes deep analysis for configured sources
  - Runs every 30 minutes via scheduler

**Why separate agents?**
- **Safety**: Analyzer agent can't modify sources or profile
- **Clarity**: Each agent has a clear, focused purpose
- **Tool isolation**: Prevents autonomous agent from making destructive changes

### The 26 MCP Tools

Defined in `agents/mcp_tools.py` as a simple dictionary with **JSON Schema parameter definitions**:

```python
TOOLS = {
    'get_articles': {
        'function': get_articles_tool,
        'description': '...',
        'parameters': {
            'type': 'object',
            'properties': {
                'limit': {'type': 'integer', 'description': 'Max articles'},
                'read_status': {'type': 'string', 'enum': ['all', 'read', 'unread']},
                # ... more parameters
            },
            'required': ['limit']
        }
    },
    # ... 25 more tools
}
```

**CRITICAL - Parameter Format Requirements**:
- **MUST use JSON Schema format** - Not Python types (`int`, `str`, `bool`, `list`, `dict`)
- **Required structure**: `{"type": "object", "properties": {...}, "required": [...]}`
- **Python boolean values**: Use `True`/`False` (not `true`/`false`)
- **Proper types**: `"integer"`, `"string"`, `"boolean"`, `"number"`, `"array"`, `"object"`
- **Validation**: Add `minimum`, `maximum`, `enum`, `default` as needed

**Example - Correct vs Incorrect**:
```python
# ❌ WRONG - Python types (will fail in Claude Agent SDK)
"parameters": {
    "article_id": int,
    "rating": int
}

# ✅ CORRECT - JSON Schema
"parameters": {
    "type": "object",
    "properties": {
        "article_id": {"type": "integer", "description": "Article ID"},
        "rating": {"type": "integer", "minimum": 1, "maximum": 5}
    },
    "required": ["article_id", "rating"]
}
```

**Tool Categories** (26 tools total):
1. **Feedback & Analysis** (4): `save_feedback`, `analyze_reading_patterns`, `get_feedback_summary`, `compare_ai_vs_user`
2. **Article Management** (8): `mark_read`, `mark_articles_read`, `get_articles`, `search_articles`, `get_article`, `trigger_deep_analysis`, `save_deep_analysis`, `mark_all_read`
3. **Profile & Preferences** (5): `update_profile`, `get_profile`, `add_interest`, `remove_interest`, `adjust_threshold`
4. **Statistics & Insights** (4): `get_stats`, `get_source_prefs`, `trending_topics`, `suggest_sources`
5. **Source Management** (4): `list_sources`, `add_source`, `remove_source`, `validate_feed`
6. **RSS Fetching** (1): `fetch_articles_from_feed` (not used by chat agent)

**Note**: Each tool is a simple function that takes a dict of args and returns a dict result. No classes, no inheritance.

### Data Flow

```
1. RSS Fetching
   └─> FeedFetcher.fetch_all() fetches feeds from sources configured by SourceManager
   └─> Saves raw articles to database (no analysis yet)

2. Background Analysis (every 30 minutes via launchd)
   └─> main.py background command runs FeedFetcher first
   └─> Then launches agents/analyzer.py via Claude Agent SDK
   └─> Analyzes ALL unanalyzed articles autonomously (uses Anthropic API credits)
   └─> ArticleManager provides article queries (NO API calls)
   └─> ProfileManager provides user interests for scoring
   └─> Results saved to database

3. Interactive Reading
   └─> agents/chat.py provides conversational interface
   └─> User gives feedback via save_feedback tool (FeedbackManager)
   └─> ProfileManager learns from feedback
   └─> Analysis improves over time
```

### Database Schema

**SQLite database** (`news.db`) with 3 tables:

1. **articles** - Stores fetched articles
   - `id`, `url`, `title`, `content`, `summary`, `deep_analysis`
   - `source_name`, `published_date`, `fetched_date`
   - `relevance_score`, `is_read`

2. **feedback** - User ratings
   - `id`, `article_id`, `rating` (1-5), `note`, `created_at`

3. **reader_profile** - Interest topics
   - `topic`, `weight` (0.0-1.0), `source`, `sample_count`
   - `last_updated`, `created_at`

**Important indexes**:
- `idx_articles_published` - Fast date sorting
- `idx_articles_relevance` - Fast relevance filtering
- `idx_articles_source` - Fast source filtering

### Learning System

The system learns from user feedback through `ProfileManager`:

1. **Explicit topics**: Loaded from `config.json` on first run
2. **Topic extraction**: Matches article text against profile topics
3. **Weight adjustment**:
   - Rating 5 = +0.1 weight
   - Rating 4 = +0.05
   - Rating 3 = 0 (neutral)
   - Rating 2 = -0.05
   - Rating 1 = -0.1

**Key insight**: The system doesn't use ML - it uses simple weight adjustments to improve relevance scoring over time.

### Deep Analysis

Some sources can be configured for deep analysis in `sources.json`:

```json
{
  "name": "Cornucopia",
  "url": "https://cornucopia.se/feed/",
  "deep_analysis": true,
  "analysis_description": "Extract Lars Wilderängs personal analyses..."
}
```

When deep analysis is enabled:
1. Background agent detects articles from configured sources
2. Uses `trigger_deep_analysis` tool
3. Generates analysis based on `analysis_description`
4. Saves to `articles.deep_analysis` column

## Critical Implementation Details

### Agent SDK Configuration

Both agents use this pattern for NVM-based Node.js:

```python
subprocess_env = os.environ.copy()
subprocess_env["PATH"] = f"/Users/mikaelsjovind/.nvm/versions/node/v22.15.1/bin:{subprocess_env.get('PATH', '')}"

options = ClaudeAgentOptions(
    mcp_servers={"news_tools": mcp_server},
    allowed_tools=allowed_tools,
    system_prompt=get_system_prompt(profile),
    permission_mode='bypassPermissions',
    cli_path="/Users/mikaelsjovind/.nvm/versions/node/v22.15.1/bin/claude",
    env=subprocess_env
)
```

**Why this matters**: The system uses a specific Node.js version via NVM. If you modify agent code, preserve this configuration.

### Progressive Reading in Chat Agent

The chat agent uses a sophisticated startup routine with grouped articles:

```python
get_articles(read_status='unread', grouped=True, limit=1000)
```

This returns articles in three presentation levels:
- **High relevance** (≥0.7): Full summary, all details
- **Medium relevance** (0.4-0.7): Compact title/source/link
- **Low relevance** (<0.4): Minimal list

**Critical rule**: ALL articles must be shown. Relevance controls PRESENTATION, not VISIBILITY.

### Manager Responsibilities

Each manager has a clear, focused responsibility:

**SourceManager** (`core/source_manager.py`):
- Load sources from `sources.json`
- Add/remove/list RSS sources
- Pure configuration management (NO fetching)

**FeedFetcher** (`core/feed_fetcher.py`):
- Fetch RSS feeds using feedparser
- Parse and clean feed content
- Save raw articles to database

**ArticleManager** (`core/article_manager.py`):
- Article CRUD operations
- Advanced querying and filtering
- Get unanalyzed articles for background agent
- Generate deep analysis prompts

**ProfileManager** (`core/profile_manager.py`):
- Load/save user topics and weights
- Extract topics from article text
- Learn from feedback (adjust weights)
- Format interests for AI prompts

**FeedbackManager** (`core/feedback_manager.py`):
- Save user ratings
- Get feedback statistics
- Calculate AI accuracy
- Format feedback context for prompts

**Never call Anthropic API directly** - managers only provide data access and prompts for agents to execute.

## Configuration Files

### config.json
```json
{
  "database_path": "news.db",
  "max_articles_per_source": 50,
  "fetch_interval_hours": 24,
  "claude_model": "claude-sonnet-4-5-20250929",
  "max_tokens_per_summary": 200,
  "relevance_threshold": 0.6,
  "user_interests": {
    "description": "User interest description",
    "topics": ["AI", "Tesla", "Swedish politics"],
    "priorities": {
      "high": ["AI", "Tesla"],
      "medium": ["Swedish politics"],
      "low": []
    }
  }
}
```

**Note**: Topics here are migrated to `reader_profile` table on first run, then weights are learned from feedback.

### sources.json
```json
[
  {
    "name": "Source Name",
    "url": "https://example.com/rss",
    "article_count": 50
  },
  {
    "name": "Special Source",
    "url": "https://special.com/rss",
    "deep_analysis": true,
    "analysis_description": "Analysis instructions..."
  }
]
```

## Testing Workflow

No formal test suite currently. Manual testing workflow:

1. **Test chat agent**: `python main.py chat` → All user interactions (reading, feedback, sources, stats)
2. **Test background**: `python main.py background` → Fetch + analysis in one command
3. **Check database**: `sqlite3 news.db "SELECT COUNT(*) FROM articles"`
4. **Test cleanup**: `python main.py cleanup --days 30`

## Common Development Patterns

### Adding a New MCP Tool

**IMPORTANT**: All MCP tools MUST use JSON Schema format for parameters (not Python types).

1. Add function to `agents/mcp_tools.py`:
```python
def my_new_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Tool description."""
    try:
        # Extract and validate parameters
        param1 = args.get('param1')
        param2 = args.get('param2', 'default_value')

        # Implementation
        result = do_something(param1, param2)

        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
```

2. Add to TOOLS dictionary with **JSON Schema parameters**:
```python
TOOLS = {
    'my_new_tool': {
        'function': my_new_tool,
        'description': 'Clear description for AI agent to understand when to use this',
        'parameters': {
            'type': 'object',
            'properties': {
                'param1': {
                    'type': 'string',  # Use 'integer', 'boolean', 'number', 'array', 'object'
                    'description': 'What this parameter does',
                    'enum': ['option1', 'option2']  # Optional: restrict to specific values
                },
                'param2': {
                    'type': 'integer',
                    'description': 'Another parameter',
                    'minimum': 0,
                    'maximum': 100,
                    'default': 50  # Optional default value
                },
                'items_list': {
                    'type': 'array',
                    'items': {'type': 'integer'},  # Type of array elements
                    'description': 'List of IDs'
                }
            },
            'required': ['param1']  # List required parameters
        }
    }
}
```

**Common Mistakes to Avoid**:
```python
# ❌ WRONG - Python types (will fail!)
'parameters': {
    'param1': str,
    'param2': int
}

# ❌ WRONG - lowercase boolean (Python syntax error!)
'default': false

# ✅ CORRECT - JSON Schema with Python booleans
'parameters': {
    'type': 'object',
    'properties': {
        'param1': {'type': 'string'},
        'param2': {'type': 'boolean', 'default': False}  # Use False, not false
    }
}
```

3. Add to appropriate agent's tool list:
   - Chat agent: Add to `CHAT_TOOLS` in `agents/chat.py`
   - Analyzer agent: Add to `ANALYZER_TOOLS` in `agents/analyzer.py`

4. Update system prompt if needed to explain the new tool's purpose

5. Test the tool works:
```python
from agents.mcp_tools import TOOLS
result = TOOLS['my_new_tool']['function']({'param1': 'test'})
print(result)
```

### Adding Core Business Logic

1. Add method to appropriate manager in `core/`:
   - **SourceManager**: For RSS source configuration (sources.json)
   - **FeedFetcher**: For RSS fetching and parsing
   - **ArticleManager**: For article operations
   - **ProfileManager**: For profile/topic operations
   - **FeedbackManager**: For feedback/statistics
2. **Never import `anthropic`** - only generate prompts or return data
3. Return data dictionaries, not API responses
4. Use Database context manager pattern:
```python
with self.db.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute(...)
    return [dict(row) for row in cursor.fetchall()]
```

**Example - Adding new article query to ArticleManager**:
```python
def get_trending_articles(self, days: int = 7) -> List[Dict[str, Any]]:
    """Get trending articles from last N days."""
    since_date = (datetime.now() - timedelta(days=days)).isoformat()
    return self.db.get_articles(since_date=since_date, limit=50)
```

### Modifying Agent Behavior

1. Edit system prompt in `get_system_prompt()` function
2. Test with `python main.py chat` or `python main.py background`
3. **Never modify tool isolation** - chat gets 24, analyzer gets 5

## Troubleshooting

### "Claude Code not found"
- Verify: `claude --version`
- Check NVM path in agent files matches your installation

### "No articles showing"
- Run: `python main.py chat` and ask "show me stats"
- Run: `python main.py background` to fetch and analyze
- Verify sources.json has valid URLs

### "Agent doesn't respond"
- Check .env has ANTHROPIC_API_KEY
- Verify Claude CLI works: `claude --version`
- Check Python version: `python --version` (must be 3.10+)

### Database locked errors
- Close any SQLite connections
- Check no other processes are accessing news.db
- Use context manager pattern in code

## Important Constraints

1. **Python 3.10+** required (claude-agent-sdk requirement)
2. **Node.js** required for Claude Code CLI
3. **Swedish language** - All prompts and summaries are in Swedish
4. **SQLite** - Database is local, no migrations needed
5. **Flat architecture** - No inheritance, no base classes

## Language and Style

- **Prompts**: Always Swedish, conversational
- **Code**: English comments and variable names
- **User output**: Swedish (via Rich library)
- **Logs**: English for debugging

## When Making Changes

1. **Preserve agent isolation** - Don't give analyzer agent destructive tools
2. **Keep core/ pure** - No API calls, only business logic
3. **Maintain flat structure** - No base classes, no inheritance
4. **Test both agents** - Changes affect chat and analyzer differently
5. **Update system prompts** - If tool behavior changes, update prompts
6. **Run code quality checks** - ALWAYS run `ruff check . --fix && basedpyright .` before committing
7. **Fix all errors and warnings** - Both Ruff and Basedpyright must report zero errors/warnings
8. **JSON Schema-format in MCP-tools** - Use proper JSON Schema, not Python types

## Code Quality Standards

### Using Ruff (Python Linter)

**When to run Ruff:**
- Before making significant changes to understand current code quality
- After making changes to catch new issues
- Before committing code to ensure clean, consistent code

**Common workflow:**
```bash
# Check for issues
ruff check .

# Auto-fix safe issues
ruff check . --fix

# Check specific file
ruff check agents/chat.py --fix
```

**What Ruff catches:**
- Unused imports (F401)
- Unused variables (F841)
- F-strings without placeholders (F541)
- Import ordering issues
- Code style inconsistencies

**Claude's responsibilities:**
- Run `ruff check .` when asked to check code quality
- Use `ruff check . --fix` to automatically fix simple issues
- Report remaining issues that need manual attention
- Update code to follow Ruff's recommendations

### Using Basedpyright (Type Checker)

**When to run Basedpyright:**
- After making code changes to catch type errors
- Before committing to ensure type safety
- When adding new functions or modifying signatures

**Common workflow:**
```bash
# Check entire project
basedpyright .

# Check specific file
basedpyright main.py

# Check and run both tools
ruff check . --fix && basedpyright .
```

**What Basedpyright catches:**
- Type annotation errors
- Unused function call results (reportUnusedCallResult)
- Mutable defaults in function parameters (reportCallInDefaultInitializer)
- `Any` types that should be more specific (reportAny as warning)
- Missing type annotations

**Configuration:** Located in `pyproject.toml` under `[tool.basedpyright]`
- Type checking mode: "standard" (balanced strictness)
- Python version: 3.10
- Includes: `core/`, `agents/`, `main.py`
- Key rules: Errors for unused call results and mutable defaults, warnings for `Any` types

**Claude's responsibilities:**
- Run `basedpyright .` after making changes to check for type errors
- Fix ALL errors in files you modify (0 errors required for changed files)
- Fix ALL warnings in files you modify (0 warnings required for changed files)
- Add proper type annotations using `typing.Annotated`, `dict[str, Any]`, etc.
- Use `# type: ignore[rule-code]` ONLY when absolutely necessary with a comment explaining why

**Current status:**
- `main.py`: ✅ 0 errors, 0 warnings
- Rest of codebase: Type annotations being added incrementally
- Goal: Gradually improve type coverage across all modules