"""Article management and analysis data access."""

import json
from typing import Any, Dict, List, Optional

from core.database import Database


class ArticleManager:
    """Manages articles, summaries, and deep analysis.

    Provides methods to query, filter, and manage articles.
    Does NOT make direct API calls - only data access.
    """

    def __init__(self, db: Optional[Database] = None, config_file: str = "config.json"):
        self.db = db or Database()
        self.config = self._load_config(config_file)

    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: {config_file} not found, using defaults")
            return {}
        except json.JSONDecodeError:
            print(f"Warning: {config_file} is not valid JSON, using defaults")
            return {}

    # ===== Article CRUD Operations =====

    def get_article(self, article_id: int) -> Optional[Dict[str, Any]]:
        """Get a single article by ID."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_articles(self,
                    limit: Optional[int] = None,
                    min_relevance: Optional[float] = None,
                    unread_only: bool = False,
                    source_name: Optional[str] = None,
                    since_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get articles with optional filters."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM articles WHERE 1=1"
            params = []

            if min_relevance is not None:
                query += " AND relevance_score >= ?"
                params.append(min_relevance)

            if unread_only:
                query += " AND is_read = 0"

            if source_name:
                query += " AND source_name = ?"
                params.append(source_name)

            if since_date:
                query += " AND published_date >= ?"
                params.append(since_date)

            query += " ORDER BY published_date DESC"

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            _ = cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def mark_as_read(self, article_id: int):
        """Mark an article as read."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("UPDATE articles SET is_read = 1 WHERE id = ?", (article_id,))

    def mark_all_as_read(self) -> int:
        """
        Mark all unread articles as read.

        Returns:
            Number of articles marked as read
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("UPDATE articles SET is_read = 1 WHERE is_read = 0")
            return cursor.rowcount

    def cleanup_old_articles(self, days: int = 30) -> int:
        """Remove articles older than specified days."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("""
                DELETE FROM articles
                WHERE date(fetched_date) < date('now', '-' || ? || ' days')
            """, (days,))
            return cursor.rowcount

    # ===== Advanced Query Operations =====

    def query_articles_advanced(self,
                               # Read status
                               read_status: str = "all",
                               # Pagination
                               limit: Optional[int] = None,
                               offset: int = 0,
                               # Sources
                               source: Optional[str] = None,
                               sources: Optional[List[str]] = None,
                               exclude_sources: Optional[List[str]] = None,
                               # Relevance
                               min_relevance: Optional[float] = None,
                               max_relevance: Optional[float] = None,
                               has_summary: Optional[bool] = None,
                               # Temporal
                               published_after: Optional[str] = None,
                               published_before: Optional[str] = None,
                               fetched_after: Optional[str] = None,
                               fetched_before: Optional[str] = None,
                               last_n_days: Optional[int] = None,
                               # Text search
                               search_query: Optional[str] = None,
                               search_in: str = "all",
                               exclude_query: Optional[str] = None,
                               # Feedback
                               with_feedback: Optional[bool] = None,
                               min_rating: Optional[float] = None,
                               controversial: Optional[bool] = None,
                               # Sorting
                               sort_by: str = "relevance_desc",
                               group_by: Optional[str] = None,
                               # Presentation
                               include_content: bool = False,
                               include_feedback: bool = False,
                               stats_only: bool = False) -> Dict[str, Any]:
        """
        Advanced article query with flexible filtering and sorting.

        All parameters are optional. Returns articles matching all specified criteria.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Build SELECT clause
            if stats_only:
                select_clause = "SELECT COUNT(*) as total_count"
            elif include_content:
                select_clause = "SELECT a.*"
            else:
                select_clause = "SELECT a.id, a.url, a.title, a.source_name, a.published_date, a.fetched_date, a.relevance_score, a.is_read, a.summary, a.created_at"

            # Base query
            query = f"{select_clause} FROM articles a"

            # Add joins for feedback queries
            if with_feedback is not None or min_rating is not None or controversial is not None or include_feedback:
                query += " LEFT JOIN feedback f ON a.id = f.article_id"

            # Build WHERE clause
            conditions = []
            params = []

            # Read status
            if read_status == "unread":
                conditions.append("a.is_read = 0")
            elif read_status == "read":
                conditions.append("a.is_read = 1")

            # Sources
            if source:
                conditions.append("LOWER(a.source_name) LIKE LOWER(?)")
                params.append(f"%{source}%")
            elif sources:
                placeholders = ','.join('?' * len(sources))
                conditions.append(f"a.source_name IN ({placeholders})")
                params.extend(sources)

            if exclude_sources:
                placeholders = ','.join('?' * len(exclude_sources))
                conditions.append(f"a.source_name NOT IN ({placeholders})")
                params.extend(exclude_sources)

            # Relevance
            if min_relevance is not None:
                conditions.append("a.relevance_score >= ?")
                params.append(min_relevance)

            if max_relevance is not None:
                conditions.append("a.relevance_score <= ?")
                params.append(max_relevance)

            if has_summary is not None:
                if has_summary:
                    conditions.append("a.summary IS NOT NULL")
                else:
                    conditions.append("a.summary IS NULL")

            # Temporal filters
            if last_n_days is not None:
                conditions.append("date(a.published_date) >= date('now', '-' || ? || ' days')")
                params.append(last_n_days)

            if published_after:
                conditions.append("a.published_date >= ?")
                params.append(published_after)

            if published_before:
                conditions.append("a.published_date <= ?")
                params.append(published_before)

            if fetched_after:
                conditions.append("a.fetched_date >= ?")
                params.append(fetched_after)

            if fetched_before:
                conditions.append("a.fetched_date <= ?")
                params.append(fetched_before)

            # Text search
            if search_query:
                search_conditions = []
                if search_in in ["all", "title"]:
                    search_conditions.append("a.title LIKE ?")
                    params.append(f"%{search_query}%")
                if search_in in ["all", "content"]:
                    search_conditions.append("a.content LIKE ?")
                    params.append(f"%{search_query}%")
                if search_in in ["all", "summary"]:
                    search_conditions.append("a.summary LIKE ?")
                    params.append(f"%{search_query}%")

                if search_conditions:
                    conditions.append(f"({' OR '.join(search_conditions)})")

            if exclude_query:
                conditions.append("(a.title NOT LIKE ? AND (a.content NOT LIKE ? OR a.content IS NULL))")
                params.extend([f"%{exclude_query}%", f"%{exclude_query}%"])

            # Feedback filters
            if with_feedback is not None:
                if with_feedback:
                    conditions.append("f.id IS NOT NULL")
                else:
                    conditions.append("f.id IS NULL")

            if min_rating is not None:
                conditions.append("f.rating >= ?")
                params.append(min_rating)

            if controversial is not None:
                # Controversial articles have mixed ratings (variance > threshold)
                # This requires a subquery
                if controversial:
                    conditions.append("""
                        a.id IN (
                            SELECT article_id
                            FROM feedback
                            GROUP BY article_id
                            HAVING COUNT(*) >= 3 AND
                                   (MAX(rating) - MIN(rating)) >= 3
                        )
                    """)

            # Apply WHERE clause
            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            # For stats only, return early
            if stats_only:
                _ = cursor.execute(query, params)
                result = cursor.fetchone()
                return {"total_count": result['total_count'] if result else 0}

            # GROUP BY (needed for feedback aggregation)
            if include_feedback or group_by == "article":
                query += " GROUP BY a.id"

            # ORDER BY
            sort_mapping = {
                "relevance_desc": "a.relevance_score DESC NULLS LAST",
                "relevance_asc": "a.relevance_score ASC NULLS LAST",
                "published_desc": "a.published_date DESC NULLS LAST",
                "published_asc": "a.published_date ASC NULLS LAST",
                "fetched_desc": "a.fetched_date DESC",
                "fetched_asc": "a.fetched_date ASC",
                "title": "a.title ASC",
                "source": "a.source_name ASC, a.published_date DESC"
            }

            order_clause = sort_mapping.get(sort_by, "a.published_date DESC")
            query += f" ORDER BY {order_clause}"

            # LIMIT and OFFSET
            if limit:
                query += " LIMIT ?"
                params.append(limit)

            if offset > 0:
                query += " OFFSET ?"
                params.append(offset)

            # Execute query
            _ = cursor.execute(query, params)
            articles = [dict(row) for row in cursor.fetchall()]

            # Add feedback if requested
            if include_feedback and articles:
                article_ids = [a['id'] for a in articles]
                placeholders = ','.join('?' * len(article_ids))
                _ = cursor.execute(f"""
                    SELECT article_id, rating, note, created_at
                    FROM feedback
                    WHERE article_id IN ({placeholders})
                    ORDER BY created_at DESC
                """, article_ids)

                feedback_by_article = {}
                for row in cursor.fetchall():
                    aid = row['article_id']
                    if aid not in feedback_by_article:
                        feedback_by_article[aid] = []
                    feedback_by_article[aid].append({
                        'rating': row['rating'],
                        'note': row['note'],
                        'created_at': row['created_at']
                    })

                for article in articles:
                    article['feedback'] = feedback_by_article.get(article['id'], [])

            # Group by source if requested
            if group_by == "source":
                grouped = {}
                for article in articles:
                    source = article['source_name']
                    if source not in grouped:
                        grouped[source] = []
                    grouped[source].append(article)
                return {"articles": articles, "grouped": grouped, "total": len(articles)}

            return {"articles": articles, "total": len(articles)}

    # ===== Analysis-Specific Queries =====

    def get_unanalyzed_articles(self) -> List[Dict[str, Any]]:
        """
        Get all articles that don't have summaries yet.

        Returns:
            List of unanalyzed articles
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("""
                SELECT * FROM articles
                WHERE summary IS NULL OR relevance_score IS NULL
                ORDER BY fetched_date DESC
            """)
            articles = [dict(row) for row in cursor.fetchall()]

        return articles

    def get_deep_analysis_prompt(self, article: Dict[str, Any], analysis_description: Optional[str] = None) -> Optional[str]:
        """
        Generate a prompt for deep article analysis.

        Returns:
            Prompt string for AI, or None if no analysis description available
        """
        source_name = article.get('source_name', '')

        # Get analysis description from sources.json via source manager
        if not analysis_description:
            from core.source_manager import SourceManager
            source_mgr = SourceManager()
            source_config = next((s for s in source_mgr.sources if s.get('name') == source_name), None)

            if source_config and source_config.get('deep_analysis'):
                analysis_description = source_config.get('analysis_description')

        if not analysis_description:
            return None

        # Simple, flexible prompt - let the model structure the output
        prompt = f"""Analysera denna artikel från {source_name}.

ARTIKEL:
Titel: {article.get('title', '')}
Innehåll: {article.get('content', '')[:10000]}

ANALYSINSTRUKTION:
{analysis_description}

Skriv din analys i tydlig, välstrukturerad markdown-format med rubriker och citat där det är relevant."""

        return prompt

    def save_deep_analysis(self, article_id: int, analysis_text: str) -> bool:
        """
        Save deep analysis for an article.

        Args:
            article_id: Article ID
            analysis_text: The deep analysis text (markdown format)

        Returns:
            True if saved successfully
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("""
                UPDATE articles
                SET deep_analysis = ?
                WHERE id = ?
            """, (analysis_text, article_id))
            return cursor.rowcount > 0

    def save_analysis(self, article_id: int, summary: str, relevance_score: float) -> bool:
        """
        Save article analysis (summary and relevance score).

        Args:
            article_id: Article ID
            summary: Article summary in Swedish
            relevance_score: Relevance score (0.0-1.0)

        Returns:
            True if saved successfully
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("""
                UPDATE articles
                SET summary = ?, relevance_score = ?
                WHERE id = ?
            """, (summary, relevance_score, article_id))
            return cursor.rowcount > 0
