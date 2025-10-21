"""MCP tools for Agent SDK - provides agent with full system access."""

from datetime import datetime, timedelta
from typing import Any, Dict

from core.article_manager import ArticleManager
from core.database import Database
from core.feed_fetcher import FeedFetcher
from core.feedback_manager import FeedbackManager
from core.profile_manager import ProfileManager
from core.source_manager import SourceManager

# Initialize shared instances
db = Database()
source_mgr = SourceManager()
feed_fetcher = FeedFetcher(db=db)
article_mgr = ArticleManager(db=db)
profile_mgr = ProfileManager(db=db)
feedback_mgr = FeedbackManager(db=db)


# ============================================================================
# FEEDBACK & ANALYSIS TOOLS
# ============================================================================

def save_feedback_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Save user feedback for an article and learn from it."""
    article_id = int(args['article_id'])
    rating = int(args['rating'])
    note = args.get('note')

    if not 1 <= rating <= 5:
        return {"success": False, "error": "Rating must be between 1-5"}

    # Save feedback
    feedback_id = feedback_mgr.add_feedback(article_id, rating, note)
    article_mgr.mark_as_read(article_id)

    # Learn from feedback
    updates = profile_mgr.learn_from_feedback(article_id, rating)

    return {
        "success": True,
        "feedback_id": feedback_id,
        "profile_updates": updates or [],
        "message": f"Feedback saved with rating {rating}/5"
    }


def analyze_reading_patterns_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze user's reading patterns and habits."""
    days = args.get('days', 30)

    stats = feedback_mgr.get_stats()
    feedback_stats = feedback_mgr.get_feedback_stats()
    profile_analysis = profile_mgr.analyze_profile_evolution(days)

    return {
        "total_articles": stats['total_articles'],
        "unread_articles": stats['unread_articles'],
        "total_feedback": feedback_stats.get('total_feedback', 0),
        "average_rating": feedback_stats.get('avg_rating', 0),
        "profile_topics": profile_analysis['total_topics'],
        "top_interests": profile_analysis['top_topics'],
        "articles_by_source": stats['articles_by_source']
    }


def get_feedback_summary_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get summary of all feedback given."""
    limit: int = int(args.get('limit', 50))

    feedback_list = feedback_mgr.get_feedback_summary(limit)

    return {
        "feedback": feedback_list,
        "count": len(feedback_list)
    }


def compare_ai_vs_user_rating_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Compare AI's relevance score with user's rating."""
    article_id = int(args['article_id'])

    article = article_mgr.get_article(article_id)
    if not article:
        return {"success": False, "error": "Article not found"}

    feedback_list = feedback_mgr.get_article_feedback(article_id)
    if not feedback_list:
        return {"success": False, "error": "No feedback for this article"}

    ai_score = article.get('relevance_score', 0)
    user_rating = feedback_list[0]['rating'] / 5.0  # Normalize to 0-1

    difference = abs(ai_score - user_rating)

    return {
        "article_title": article['title'],
        "ai_relevance": ai_score,
        "user_rating_normalized": user_rating,
        "user_rating_raw": feedback_list[0]['rating'],
        "difference": difference,
        "alignment": "good" if difference < 0.2 else "moderate" if difference < 0.4 else "poor"
    }


# ============================================================================
# ARTICLE MANAGEMENT TOOLS
# ============================================================================

def fetch_articles_from_feed_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch new articles from RSS feeds to database.

    Note: Articles will need to be analyzed separately via agent.
    The analyze parameter is deprecated since analyzer no longer makes direct API calls.
    """
    result = feed_fetcher.fetch_all()

    # Return info about unanalyzed articles
    unanalyzed = article_mgr.get_unanalyzed_articles()
    result['unanalyzed_count'] = len(unanalyzed)

    return result


def mark_article_read_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Mark an article as read."""
    article_id = int(args['article_id'])

    article = article_mgr.get_article(article_id)
    if not article:
        return {"success": False, "error": "Article not found"}

    article_mgr.mark_as_read(article_id)

    return {
        "success": True,
        "article_id": article_id,
        "title": article['title']
    }


def mark_articles_read_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Mark multiple articles as read."""
    article_ids = args.get('article_ids', [])

    if not article_ids:
        return {"success": False, "error": "article_ids is required"}

    marked_count = 0
    for article_id in article_ids:
        article_mgr.mark_as_read(int(article_id))
        marked_count += 1

    return {
        "success": True,
        "marked_count": marked_count,
        "article_ids": article_ids
    }


def get_articles_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get articles with flexible filtering. NEVER marks as read automatically.

    Use mark_articles_read() afterward if user wants to mark them as read.
    """
    try:
        read_status = args.get('read_status', 'all')
        source = args.get('source')
        min_relevance = args.get('min_relevance')
        time_filter = args.get('time_filter')
        fetched_since = args.get('fetched_since')
        published_since = args.get('published_since')
        limit = args.get('limit')  # Agent MUST specify limit explicitly
        offset = args.get('offset', 0)
        sort_by = args.get('sort_by', 'relevance_desc')
        grouped = args.get('grouped', False)

        # Convert time_filter to timestamp
        if time_filter:
            hours_map = {'last_24h': 24, 'last_week': 168, 'last_month': 720}
            hours = hours_map.get(time_filter, 24)
            fetched_since = (datetime.now() - timedelta(hours=hours)).isoformat()

        # Query database
        result = article_mgr.query_articles_advanced(
            read_status=read_status,
            source=source,
            min_relevance=min_relevance,
            fetched_after=fetched_since,
            published_after=published_since,
            limit=limit,
            offset=offset,
            sort_by=sort_by
        )

        # Ensure we have articles list
        articles = result.get('articles', [])

        # Group by tiers if requested
        if grouped:
            high_relevance = []
            medium_relevance = []
            low_relevance = []

            for article in articles:
                score = article.get('relevance_score', 0)
                article_with_hint = dict(article)

                # Deep analysis boost
                has_deep = bool(article.get('deep_analysis'))
                if has_deep:
                    score = max(score, 0.75)
                    article_with_hint['has_deep_analysis'] = True
                else:
                    article_with_hint['has_deep_analysis'] = False

                if score >= 0.7:
                    article_with_hint['presentation_hint'] = 'full'
                    article_with_hint['tier'] = 'high'
                    high_relevance.append(article_with_hint)
                elif score >= 0.4:
                    article_with_hint['presentation_hint'] = 'compact'
                    article_with_hint['tier'] = 'medium'
                    medium_relevance.append(article_with_hint)
                else:
                    article_with_hint['presentation_hint'] = 'minimal'
                    article_with_hint['tier'] = 'low'
                    low_relevance.append(article_with_hint)

            # Consistent return format: always include 'articles' key
            return {
                "success": True,
                "articles": articles,  # Full list for compatibility
                "articles_by_tier": {
                    "high_relevance": high_relevance,
                    "medium_relevance": medium_relevance,
                    "low_relevance": low_relevance
                },
                "tier_counts": {
                    "high": len(high_relevance),
                    "medium": len(medium_relevance),
                    "low": len(low_relevance)
                },
                "total": len(articles),
                "grouped": True
            }

        # Non-grouped response - add success flag for consistency
        return {
            "success": True,
            "articles": articles,
            "total": len(articles),
            "grouped": False
        }

    except Exception as e:
        # Return error info for debugging
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "articles": [],
            "total": 0
        }


def search_articles_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for articles by text query (search intent).

    Search in title, content, or summary for specific terms.
    """
    query = args.get('query')
    if not query:
        return {"articles": [], "count": 0, "error": "query parameter is required"}

    search_in = args.get('search_in', 'all')
    min_relevance = args.get('min_relevance')
    limit = args.get('limit')  # Agent MUST specify limit explicitly

    result = article_mgr.query_articles_advanced(
        search_query=query,
        search_in=search_in,
        min_relevance=min_relevance,
        limit=limit,
        sort_by='relevance_desc'
    )

    return result


def get_article_details_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get full details of a specific article including deep analysis if available."""
    article_id = int(args['article_id'])
    include_deep = args.get('include_deep_analysis', True)

    article = article_mgr.get_article(article_id)
    if not article:
        return {"success": False, "error": "Article not found"}

    feedback = feedback_mgr.get_article_feedback(article_id)

    result = {
        "success": True,
        "article": dict(article),
        "feedback": [dict(f) for f in feedback]
    }

    # Include deep_analysis if present (as markdown text)
    if include_deep and article.get('deep_analysis'):
        result['deep_analysis'] = article['deep_analysis']

    return result


def trigger_deep_analysis_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get deep analysis prompt for a specific article.

    Works for ANY article - uses source-specific prompt if available,
    otherwise generates a fallback prompt based on user's interests.

    Returns the article info and prompt for the agent to execute.
    """
    article_id = int(args['article_id'])

    article = article_mgr.get_article(article_id)
    if not article:
        return {
            "success": False,
            "article_id": article_id,
            "error": "Article not found"
        }

    prompt, is_fallback = article_mgr.get_deep_analysis_prompt(article)

    if not prompt:
        return {
            "success": False,
            "article_id": article_id,
            "error": "Failed to generate analysis prompt"
        }

    # Build response message
    if is_fallback:
        message = "Deep analysis prompt generated based on user's interests (no source-specific configuration found). Execute this prompt and save result with save_deep_analysis()."
    else:
        message = "Deep analysis prompt generated using source-specific configuration. Execute this prompt and save result with save_deep_analysis()."

    return {
        "success": True,
        "article_id": article_id,
        "title": article.get('title', ''),
        "source": article.get('source_name', ''),
        "prompt": prompt,
        "is_fallback": is_fallback,
        "message": message
        }


def save_deep_analysis_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save deep analysis result for an article.

    Use after executing the prompt from trigger_deep_analysis().
    """
    try:
        article_id = int(args['article_id'])
        analysis_text = args.get('analysis_text', '').strip()

        if not analysis_text:
            return {
                "success": False,
                "error": "analysis_text is required and cannot be empty"
            }

        # Verify article exists
        article = article_mgr.get_article(article_id)
        if not article:
            return {
                "success": False,
                "error": f"Article {article_id} not found"
            }

        # Save the analysis
        saved = article_mgr.save_deep_analysis(article_id, analysis_text)

        if not saved:
            return {
                "success": False,
                "error": f"Failed to save analysis for article {article_id}"
            }

        return {
            "success": True,
            "article_id": article_id,
            "title": article.get('title', ''),
            "message": f"Deep analysis saved for article {article_id}",
            "analysis_length": len(analysis_text)
        }

    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


def save_article_analysis_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save analysis results (summary and relevance score) for an article.

    This is the primary tool for saving article analysis performed by the analyzer agent.
    """
    try:
        article_id = int(args['article_id'])
        summary = args.get('summary', '').strip()
        relevance_score = float(args['relevance_score'])

        if not summary:
            return {
                "success": False,
                "error": "summary is required and cannot be empty"
            }

        if not 0.0 <= relevance_score <= 1.0:
            return {
                "success": False,
                "error": "relevance_score must be between 0.0 and 1.0"
            }

        # Verify article exists
        article = article_mgr.get_article(article_id)
        if not article:
            return {
                "success": False,
                "error": f"Article {article_id} not found"
            }

        # Save the analysis
        saved = article_mgr.save_analysis(article_id, summary, relevance_score)

        if not saved:
            return {
                "success": False,
                "error": f"Failed to save analysis for article {article_id}"
            }

        return {
            "success": True,
            "article_id": article_id,
            "title": article.get('title', ''),
            "relevance_score": relevance_score,
            "message": f"Analysis saved for article {article_id}"
        }

    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


def mark_all_read_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mark ALL unread articles as read in bulk (bulk update intent).

    Simple zero-parameter operation that marks every unread article as read.
    Use when user has read articles externally or wants to clear all unread.
    """
    count = article_mgr.mark_all_as_read()

    return {
        "success": True,
        "marked_count": count,
        "message": f"Marked {count} unread articles as read"
    }


# ============================================================================
# PROFILE & PREFERENCES TOOLS
# ============================================================================

def update_reader_profile_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Update reader profile with topic weights."""
    updates = args['updates']  # Dict of {topic: weight}

    results = []
    for topic, weight in updates.items():
        success = profile_mgr.update_topic(topic, float(weight), "agent_updated")
        results.append({
            'topic': topic,
            'weight': weight,
            'success': success
        })

    return {
        "success": True,
        "updates": results
    }


def get_reader_profile_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get current reader profile."""
    profile = profile_mgr.get_profile()

    return {
        "profile": profile,
        "top_topics": profile_mgr.get_top_topics(10)
    }


def add_interest_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Add a new interest/topic to profile."""
    topic = args['topic']
    priority = args.get('priority', 'medium')

    # Map priority to weight
    weight_map = {'high': 0.8, 'medium': 0.6, 'low': 0.4}
    weight = weight_map.get(priority, 0.6)

    success = profile_mgr.update_topic(topic, weight, "explicit")

    return {
        "success": success,
        "topic": topic,
        "weight": weight,
        "priority": priority
    }


def remove_interest_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Remove an interest from profile."""
    topic = args['topic']

    deleted = profile_mgr.remove_topic(topic)

    return {
        "success": deleted,
        "topic": topic
    }


def adjust_relevance_threshold_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Adjust the relevance threshold for articles."""
    new_threshold = float(args['threshold'])

    if not 0.0 <= new_threshold <= 1.0:
        return {"success": False, "error": "Threshold must be between 0.0 and 1.0"}

    old_threshold = feedback_mgr.get_relevance_threshold()
    success = feedback_mgr.set_relevance_threshold(new_threshold)

    return {
        "success": success,
        "old_threshold": old_threshold,
        "new_threshold": new_threshold
    }


# ============================================================================
# STATISTICS & INSIGHTS TOOLS
# ============================================================================

def get_reading_stats_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get comprehensive reading statistics."""
    try:
        stats = feedback_mgr.get_stats()
        learning_stats = feedback_mgr.get_learning_stats()

        return {
            "success": True,
            **stats,
            "learning": learning_stats
        }
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


def get_source_preferences_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get preferences by RSS source."""
    preferences = feedback_mgr.get_source_preferences()

    return {
        "source_preferences": preferences
    }


def identify_trending_topics_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Identify trending topics from recent articles."""
    days = args.get('days', 7)
    since_date = (datetime.now() - timedelta(days=days)).isoformat()

    articles = article_mgr.get_articles(since_date=since_date, limit=None)

    # Extract topics from recent articles
    topic_count = {}
    for article in articles:
        topics = profile_mgr.extract_topics_from_text(
            article.get('content', ''),
            article.get('title', '')
        )
        for topic in topics:
            topic_count[topic] = topic_count.get(topic, 0) + 1

    trending = sorted(topic_count.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "trending_topics": [
            {"topic": topic, "count": count}
            for topic, count in trending
        ],
        "period_days": days
    }


def suggest_new_sources_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Suggest new RSS sources based on interests."""
    top_topics = profile_mgr.get_top_topics(5)

    # Predefined suggestions based on topics
    suggestions_map = {
        'ai': [
            {"name": "The Gradient", "url": "https://thegradient.pub/rss/"},
            {"name": "AI News", "url": "https://artificialintelligence-news.com/feed/"}
        ],
        'apple': [
            {"name": "9to5Mac", "url": "https://9to5mac.com/feed/"},
            {"name": "AppleInsider", "url": "https://appleinsider.com/rss/news/"}
        ],
        'tesla': [
            {"name": "Electrek Tesla", "url": "https://electrek.co/guides/tesla/feed/"}
        ],
        'politik': [
            {"name": "Altinget", "url": "https://www.altinget.se/rss/"}
        ]
    }

    suggestions = []
    for topic, weight in top_topics[:3]:
        topic_lower = topic.lower()
        for key, sources in suggestions_map.items():
            if key in topic_lower:
                suggestions.extend(sources)

    # Remove duplicates
    seen = set()
    unique_suggestions = []
    for s in suggestions:
        if s['url'] not in seen:
            seen.add(s['url'])
            unique_suggestions.append(s)

    return {
        "suggestions": unique_suggestions[:5],
        "based_on_topics": [t for t, _ in top_topics[:3]]
    }


# ============================================================================
# SOURCE MANAGEMENT TOOLS
# ============================================================================

def list_sources_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all available RSS sources (discovery intent).

    Simple listing of all RSS feeds in the system.
    """
    sources = source_mgr.list_sources()
    include_stats = args.get('include_stats', False)

    if include_stats:
        # Enhance with article counts per source
        with db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("""
                SELECT source_name, COUNT(*) as count
                FROM articles
                GROUP BY source_name
            """)
            stats_map = {row['source_name']: row['count'] for row in cursor.fetchall()}

        # Add stats to sources
        for source in sources:
            source['article_count'] = stats_map.get(source['name'], 0)

    return {
        "success": True,
        "sources": sources,
        "count": len(sources)
    }


def add_source_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a new RSS feed source (creation intent).

    Adds a new RSS source to the system's source list.
    """
    name = args.get('name')
    url = args.get('url')

    if not name or not url:
        return {"success": False, "error": "Both name and url are required"}

    success = source_mgr.add_source(name, url)

    return {
        "success": success,
        "name": name,
        "url": url,
        "message": f"Source '{name}' added successfully" if success else f"Failed to add source '{name}'"
    }


def remove_source_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove an RSS source by name (deletion intent).

    Removes a source from the system using case-insensitive partial matching.
    """
    name = args.get('name')

    if not name:
        return {"success": False, "error": "name parameter is required"}

    success = source_mgr.remove_source(name)

    return {
        "success": success,
        "name": name,
        "message": f"Source '{name}' removed successfully" if success else f"Source '{name}' not found"
    }


def validate_feed_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate an RSS feed URL (validation intent).

    Tests if a feed URL is valid and fetchable before adding it to the system.
    """
    url = args.get('url')

    if not url:
        return {"success": False, "error": "url parameter is required"}

    try:
        import feedparser
        feed = feedparser.parse(url)

        is_valid = not feed.bozo
        feed_title: str = getattr(feed.feed, 'title', 'Unknown')

        return {
            "success": is_valid,
            "url": url,
            "feed_title": feed_title,
            "entries_found": len(feed.entries),
            "error": str(feed.bozo_exception) if feed.bozo else None,
            "message": f"Valid RSS feed with {len(feed.entries)} entries" if is_valid else "Invalid RSS feed"
        }
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "error": str(e),
            "message": f"Failed to validate feed: {str(e)}"
        }


# ============================================================================
# TOOL REGISTRY
# ============================================================================

TOOLS = {
    # Feedback & Analysis
    "save_feedback": {
        "function": save_feedback_tool,
        "description": "Save user rating (1-5) for an article and trigger profile learning from the feedback",
        "parameters": {
            "type": "object",
            "properties": {
                "article_id": {"type": "integer", "description": "Article ID"},
                "rating": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Rating from 1-5"},
                "note": {"type": "string", "description": "Optional note about the rating"}
            },
            "required": ["article_id", "rating"]
        }
    },
    "analyze_reading_patterns": {
        "function": analyze_reading_patterns_tool,
        "description": "Analyze user's reading habits, patterns, and topic evolution over specified time period",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days to analyze", "default": 30}
            }
        }
    },
    "get_feedback_summary": {
        "function": get_feedback_summary_tool,
        "description": "List recent feedback history with ratings and notes",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "How many feedbacks to return"}
            },
            "required": ["limit"]
        }
    },
    "compare_ai_vs_user": {
        "function": compare_ai_vs_user_rating_tool,
        "description": "Compare AI's relevance prediction with user's actual rating for a specific article",
        "parameters": {
            "type": "object",
            "properties": {
                "article_id": {"type": "integer", "description": "Article ID"}
            },
            "required": ["article_id"]
        }
    },

    # Article Management
    "fetch_articles_from_feed": {
        "function": fetch_articles_from_feed_tool,
        "description": "Import new articles from external RSS feeds into database and optionally analyze them",
        "parameters": {
            "type": "object",
            "properties": {
                "analyze": {"type": "boolean", "description": "Whether to analyze articles", "default": True}
            }
        }
    },
    "mark_read": {
        "function": mark_article_read_tool,
        "description": "Mark specific article as read",
        "parameters": {
            "type": "object",
            "properties": {
                "article_id": {"type": "integer", "description": "Article ID"}
            },
            "required": ["article_id"]
        }
    },
    "mark_articles_read": {
        "function": mark_articles_read_tool,
        "description": "Mark multiple articles as read. Use after showing articles to user and they confirm they want to mark them as read.",
        "parameters": {
            "type": "object",
            "properties": {
                "article_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of article IDs to mark as read"
                }
            },
            "required": ["article_ids"]
        }
    },
    "get_articles": {
        "function": get_articles_tool,
        "description": "Get articles with flexible filtering. NEVER marks as read automatically - use mark_articles_read() afterward if user wants that. Supports grouped mode where ALL matching articles are organized into 3 presentation tiers by relevance (not filtered!). IMPORTANT: You MUST specify limit explicitly based on intent: use 1000 for 'show all', 50 for sampling, 10 for quick preview.",
        "parameters": {
            "type": "object",
            "properties": {
                "read_status": {"type": "string", "enum": ["all", "read", "unread"], "description": "Filter by read status", "default": "all"},
                "source": {"type": "string", "description": "Partial source name (case-insensitive)"},
                "min_relevance": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "Minimum relevance score"},
                "time_filter": {"type": "string", "enum": ["last_24h", "last_week", "last_month"], "description": "Time filter"},
                "fetched_since": {"type": "string", "description": "ISO timestamp for fetched after"},
                "published_since": {"type": "string", "description": "ISO timestamp for published after"},
                "limit": {"type": "integer", "description": "Max articles to return (1000 for all, 50 for sample, 10 for preview)"},
                "offset": {"type": "integer", "description": "Offset for pagination", "default": 0},
                "sort_by": {"type": "string", "enum": ["relevance_desc", "date_desc", "date_asc"], "description": "Sort order", "default": "relevance_desc"},
                "grouped": {"type": "boolean", "description": "Group by relevance tiers", "default": False}
            },
            "required": ["limit"]
        }
    },
    "search_articles": {
        "function": search_articles_tool,
        "description": "Search for articles by text query in title, content, or summary",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term"},
                "search_in": {"type": "string", "enum": ["title", "content", "summary", "all"], "description": "Where to search", "default": "all"},
                "min_relevance": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "Minimum relevance score"},
                "limit": {"type": "integer", "description": "Max results (50 for thorough, 20 for quick)"}
            },
            "required": ["query", "limit"]
        }
    },
    "get_article": {
        "function": get_article_details_tool,
        "description": "Retrieve complete details for a single article by ID including content, feedback, and deep_analysis if available",
        "parameters": {
            "type": "object",
            "properties": {
                "article_id": {"type": "integer", "description": "Article ID"},
                "include_deep_analysis": {"type": "boolean", "description": "Include deep analysis", "default": True}
            },
            "required": ["article_id"]
        }
    },
    "trigger_deep_analysis": {
        "function": trigger_deep_analysis_tool,
        "description": "Get deep analysis prompt for ANY article (step 1 of 2). Works for all articles - uses source-specific analysis prompt if configured in sources.json (e.g., Cornucopia for Lars Wilderäng's analyses), otherwise generates a prompt based on user's interests. Returns a prompt that the agent should execute and then save with save_deep_analysis().",
        "parameters": {
            "type": "object",
            "properties": {
                "article_id": {"type": "integer", "description": "Article ID to analyze"}
            },
            "required": ["article_id"]
        }
    },
    "save_deep_analysis": {
        "function": save_deep_analysis_tool,
        "description": "Save deep analysis result for an article (step 2 of 2). Use after executing the prompt from trigger_deep_analysis(). Stores the analysis in the database.",
        "parameters": {
            "type": "object",
            "properties": {
                "article_id": {"type": "integer", "description": "Article ID"},
                "analysis_text": {"type": "string", "description": "The deep analysis text in markdown format"}
            },
            "required": ["article_id", "analysis_text"]
        }
    },
    "save_article_analysis": {
        "function": save_article_analysis_tool,
        "description": "Save article analysis (summary + relevance score). PRIMARY TOOL for analyzer agent to save analysis results. Use for every article analyzed.",
        "parameters": {
            "type": "object",
            "properties": {
                "article_id": {"type": "integer", "description": "Article ID to save analysis for"},
                "summary": {"type": "string", "description": "Swedish summary of the article (2-3 sentences)"},
                "relevance_score": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "Relevance score based on user profile (0.0-1.0)"}
            },
            "required": ["article_id", "summary", "relevance_score"]
        }
    },
    "mark_all_read": {
        "function": mark_all_read_tool,
        "description": "Mark ALL unread articles as read in one operation. Simple, zero-parameter tool. Use when user says 'mark all as read' or 'clear all unread' or has read articles externally.",
        "parameters": {}
    },

    # Profile & Preferences
    "update_profile": {
        "function": update_reader_profile_tool,
        "description": "Batch update weights for multiple existing topics at once (use when rebalancing multiple topic priorities)",
        "parameters": {
            "type": "object",
            "properties": {
                "updates": {
                    "type": "object",
                    "description": "Dictionary of topic to weight mappings",
                    "additionalProperties": {"type": "number"}
                }
            },
            "required": ["updates"]
        }
    },
    "get_profile": {
        "function": get_reader_profile_tool,
        "description": "Retrieve user's current interest profile including all topics, weights, and top interests",
        "parameters": {}
    },
    "add_interest": {
        "function": add_interest_tool,
        "description": "Add a single new interest/topic to profile with priority level (use when discovering new interest)",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic name"},
                "priority": {"type": "string", "enum": ["high", "medium", "low"], "description": "Priority level", "default": "medium"}
            },
            "required": ["topic"]
        }
    },
    "remove_interest": {
        "function": remove_interest_tool,
        "description": "Remove a specific interest/topic from profile permanently",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic name to remove"}
            },
            "required": ["topic"]
        }
    },
    "adjust_threshold": {
        "function": adjust_relevance_threshold_tool,
        "description": "Configure the minimum relevance score threshold for filtering articles (0.0-1.0)",
        "parameters": {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "Relevance threshold"}
            },
            "required": ["threshold"]
        }
    },

    # Statistics & Insights
    "get_stats": {
        "function": get_reading_stats_tool,
        "description": "Get overview of reading statistics: total articles, unread count, feedback summary, and learning progress",
        "parameters": {}
    },
    "get_source_prefs": {
        "function": get_source_preferences_tool,
        "description": "Analyze and compare RSS sources by user ratings to identify highest/lowest quality sources",
        "parameters": {}
    },
    "trending_topics": {
        "function": identify_trending_topics_tool,
        "description": "Discover trending topics from recently published articles over specified time period",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Number of days", "default": 7}
            }
        }
    },
    "suggest_sources": {
        "function": suggest_new_sources_tool,
        "description": "Get personalized RSS source recommendations based on current interest profile",
        "parameters": {}
    },

    # Source Management
    "list_sources": {
        "function": list_sources_tool,
        "description": "List all available RSS sources. IMPORTANT: Use this FIRST when user mentions a specific source name (e.g., 'SVT Inrikes') to discover exact source names before filtering articles",
        "parameters": {
            "type": "object",
            "properties": {
                "include_stats": {"type": "boolean", "description": "Include article counts per source", "default": False}
            }
        }
    },
    "add_source": {
        "function": add_source_tool,
        "description": "Add a new RSS feed source to the system",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Display name for the source"},
                "url": {"type": "string", "description": "RSS feed URL"}
            },
            "required": ["name", "url"]
        }
    },
    "remove_source": {
        "function": remove_source_tool,
        "description": "Remove an RSS source by name (case-insensitive partial matching supported)",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Source name to remove"}
            },
            "required": ["name"]
        }
    },
    "validate_feed": {
        "function": validate_feed_tool,
        "description": "Test if an RSS feed URL is valid and fetchable before adding it to the system",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "RSS feed URL to validate"}
            },
            "required": ["url"]
        }
    }
}
