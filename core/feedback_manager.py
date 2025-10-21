"""Feedback management and statistics."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.database import Database


class FeedbackManager:
    """Manages user feedback, ratings, and learning statistics."""

    def __init__(self, db: Optional[Database] = None, config_file: str = "config.json"):
        self.db = db or Database()
        self.config = self._load_config(config_file)

    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            return {}

    # ===== Feedback Operations =====

    def add_feedback(self, article_id: int, rating: int, note: Optional[str] = None) -> int:
        """Add user feedback for an article."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("""
                INSERT INTO feedback (article_id, rating, note, created_at)
                VALUES (?, ?, ?, ?)
            """, (article_id, rating, note, datetime.now().isoformat()))
            feedback_id: int = cursor.lastrowid or 0
            return feedback_id

    def get_article_feedback(self, article_id: int) -> List[Dict[str, Any]]:
        """Get all feedback for a specific article."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("""
                SELECT id, article_id, rating, note, created_at
                FROM feedback
                WHERE article_id = ?
                ORDER BY created_at DESC
            """, (article_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_feedback_stats(self) -> Dict[str, Any]:
        """Get feedback statistics for learning."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Get overall feedback stats
            _ = cursor.execute("""
                SELECT
                    COUNT(*) as total_feedback,
                    AVG(rating) as avg_rating,
                    SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END) as positive_count,
                    SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END) as negative_count
                FROM feedback
            """)
            stats = dict(cursor.fetchone())

            return stats

    def get_feedback_summary(self, limit: int) -> List[Dict[str, Any]]:
        """
        Get recent feedback with article details.

        Args:
            limit: Maximum number of feedback entries to return

        Returns:
            List of feedback dictionaries with article info
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("""
                SELECT a.title, a.source_name, f.rating, f.note, f.created_at
                FROM feedback f
                JOIN articles a ON f.article_id = a.id
                ORDER BY f.created_at DESC
                LIMIT ?
            """, (limit,))

            feedback_list = []
            for row in cursor.fetchall():
                feedback_list.append({
                    'title': row['title'],
                    'source': row['source_name'],
                    'rating': row['rating'],
                    'note': row['note'],
                    'date': row['created_at']
                })

        return feedback_list

    def get_source_preferences(self) -> List[Dict[str, Any]]:
        """
        Get source preferences by average rating.

        Returns:
            List of sources with average ratings and feedback counts
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("""
                SELECT
                    a.source_name,
                    AVG(f.rating) as avg_rating,
                    COUNT(*) as feedback_count
                FROM feedback f
                JOIN articles a ON f.article_id = a.id
                GROUP BY a.source_name
                HAVING feedback_count >= 2
                ORDER BY avg_rating DESC
            """)

            preferences = []
            for row in cursor.fetchall():
                preferences.append({
                    'source': row['source_name'],
                    'avg_rating': row['avg_rating'],
                    'feedback_count': row['feedback_count']
                })

        return preferences

    # ===== General Statistics =====

    def get_stats(self) -> Dict[str, Any]:
        """Get general statistics about articles and feedback."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Article stats
            _ = cursor.execute("""
                SELECT
                    COUNT(*) as total_articles,
                    SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) as unread_count,
                    SUM(CASE WHEN relevance_score >= 0.6 THEN 1 ELSE 0 END) as relevant_count
                FROM articles
            """)
            article_stats = dict(cursor.fetchone())

            # Feedback stats
            _ = cursor.execute("""
                SELECT
                    COUNT(*) as total_feedback,
                    AVG(rating) as avg_rating
                FROM feedback
            """)
            feedback_stats = dict(cursor.fetchone())

            # Source stats
            _ = cursor.execute("""
                SELECT
                    COUNT(DISTINCT source_name) as source_count
                FROM articles
            """)
            source_stats = dict(cursor.fetchone())

            # Articles by source
            _ = cursor.execute("""
                SELECT source_name, COUNT(*) as count
                FROM articles
                GROUP BY source_name
                ORDER BY count DESC
            """)
            articles_by_source = {row['source_name']: row['count'] for row in cursor.fetchall()}

            return {
                **article_stats,
                **feedback_stats,
                **source_stats,
                'articles_by_source': articles_by_source
            }

    # ===== Learning & AI Accuracy =====

    def get_learning_stats(self) -> Dict[str, Any]:
        """
        Get statistics about learning progress from feedback.

        Returns:
            Dictionary with learning statistics including AI accuracy
        """
        feedback_stats = self.get_feedback_stats()

        # Get source preferences from database
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("""
                SELECT
                    a.source_name,
                    AVG(f.rating) as avg_rating,
                    COUNT(*) as count
                FROM feedback f
                JOIN articles a ON f.article_id = a.id
                GROUP BY a.source_name
                HAVING count >= 2
                ORDER BY avg_rating DESC
            """)
            source_prefs = {row['source_name']: row['avg_rating'] for row in cursor.fetchall()}

        # Calculate AI accuracy (discrepancies between AI scores and user ratings)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("""
                SELECT COUNT(*) as total
                FROM feedback f
                JOIN articles a ON f.article_id = a.id
                WHERE a.relevance_score IS NOT NULL
            """)
            total_with_scores = cursor.fetchone()['total']

            _ = cursor.execute("""
                SELECT COUNT(*) as discrepancies
                FROM feedback f
                JOIN articles a ON f.article_id = a.id
                WHERE a.relevance_score IS NOT NULL
                AND ABS(a.relevance_score - (f.rating / 5.0)) > 0.3
            """)
            discrepancies = cursor.fetchone()['discrepancies']

        accuracy_rate = 1.0 if total_with_scores == 0 else 1 - (discrepancies / total_with_scores)

        return {
            "total_feedback_given": feedback_stats.get("total_feedback", 0),
            "average_rating": feedback_stats.get("avg_rating", 0),
            "positive_feedback": feedback_stats.get("positive_count", 0),
            "negative_feedback": feedback_stats.get("negative_count", 0),
            "current_threshold": self.get_relevance_threshold(),
            "source_preferences": source_prefs,
            "ai_accuracy": {
                "total_discrepancies": discrepancies,
                "accuracy_rate": accuracy_rate
            }
        }

    # ===== Configuration =====

    def get_relevance_threshold(self) -> float:
        """Get current relevance threshold from config."""
        return self.config.get("relevance_threshold", 0.6)

    def set_relevance_threshold(self, threshold: float, config_file: str = "config.json") -> bool:
        """
        Set relevance threshold in config file.

        Returns:
            True if successful
        """
        if not 0.0 <= threshold <= 1.0:
            return False

        try:
            # Reload config to ensure we have latest
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)

            config["relevance_threshold"] = threshold

            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            # Update instance config
            self.config["relevance_threshold"] = threshold
            return True
        except Exception as e:
            print(f"Error saving threshold: {e}")
            return False
