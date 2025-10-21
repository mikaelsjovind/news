"""User profile management and learning system."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.database import Database


class ProfileManager:
    """Manages and learns user's reading profile over time."""

    def __init__(self, db: Optional[Database] = None, config_path: str = "config.json"):
        self.db = db or Database()
        self.config_path = config_path
        self._init_default_topics()

    def _load_config(self) -> Dict:
        """Load config.json file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _init_default_topics(self):
        """Initialize profile with topics from config.json if empty."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("SELECT COUNT(*) as count FROM reader_profile")
            if cursor.fetchone()['count'] == 0:
                # Load topics from config.json
                config = self._load_config()
                user_interests = config.get('user_interests', {})
                topics = user_interests.get('topics', [])
                priorities = user_interests.get('priorities', {})

                # Map priority to weight
                high_priority = priorities.get('high', [])
                medium_priority = priorities.get('medium', [])
                low_priority = priorities.get('low', [])

                # Add topics with appropriate weights
                for topic in topics:
                    if topic in high_priority:
                        weight = 0.8
                    elif topic in medium_priority:
                        weight = 0.6
                    elif topic in low_priority:
                        weight = 0.5
                    else:
                        weight = 0.7  # Default for topics not in priority lists

                    _ = self.update_topic(topic, weight, "explicit")

    # ===== Profile Access =====

    def get_profile(self) -> Dict[str, Dict]:
        """Get the complete reader profile."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("""
                SELECT topic, weight, source, sample_count, last_updated
                FROM reader_profile
                ORDER BY weight DESC
            """)

            profile = {}
            for row in cursor.fetchall():
                profile[row['topic']] = {
                    'weight': row['weight'],
                    'source': row['source'],
                    'sample_count': row['sample_count'],
                    'last_updated': row['last_updated']
                }

            return profile

    def get_top_topics(self, limit: int = 10) -> List[Tuple[str, float]]:
        """Get top topics by weight."""
        profile = self.get_profile()
        sorted_topics = sorted(
            profile.items(),
            key=lambda x: x[1]['weight'],
            reverse=True
        )

        return [(topic, data['weight']) for topic, data in sorted_topics[:limit]]

    # ===== Topic Management =====

    def update_topic(self, topic: str, weight: float, source: str = "learned") -> bool:
        """Update or create a topic in the profile."""
        weight = max(0.0, min(1.0, weight))  # Clamp to 0-1

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("""
                INSERT INTO reader_profile (topic, weight, source, sample_count, last_updated)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(topic) DO UPDATE SET
                    weight = ?,
                    sample_count = sample_count + 1,
                    last_updated = ?
            """, (topic, weight, source, datetime.now().isoformat(),
                  weight, datetime.now().isoformat()))

            return True

    def adjust_topic_weight(self, topic: str, delta: float) -> Optional[float]:
        """Adjust topic weight by delta."""
        profile = self.get_profile()

        if topic not in profile:
            # Create new topic with base weight
            new_weight = 0.5 + delta
            _ = self.update_topic(topic, new_weight, "learned")
            return new_weight

        current_weight = profile[topic]['weight']
        new_weight = max(0.0, min(1.0, current_weight + delta))
        _ = self.update_topic(topic, new_weight, profile[topic]['source'])

        return new_weight

    def remove_topic(self, topic: str) -> bool:
        """
        Remove a topic from the profile.

        Args:
            topic: The topic to remove

        Returns:
            True if topic was removed, False if topic didn't exist
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("DELETE FROM reader_profile WHERE topic = ?", (topic,))
            deleted = cursor.rowcount > 0

        return deleted

    # ===== Topic Extraction =====

    def extract_topics_from_text(self, text: str, title: str = "") -> List[str]:
        """Extract potential topics from article text by matching against profile topics."""
        # Combine title and text
        full_text = f"{title} {text}".lower()

        # Get current profile topics
        profile = self.get_profile()

        # Build keyword mapping from actual profile topics
        # Each profile topic generates keywords by splitting on common words
        topic_keywords = {}
        for topic in profile.keys():
            # Split topic into keywords (e.g., "Claude och AI-utveckling" -> ["claude", "ai", "utveckling"])
            topic_lower = topic.lower()
            # Remove ONLY very common Swedish words that don't help matching
            # Keep words like "svensk", "politik", "teknik" as they are meaningful
            stop_words = {"och", "eller", "med", "för", "av", "på", "i", "samt", "en", "ett", "den", "det", "om"}
            keywords = [word for word in topic_lower.split() if word not in stop_words and len(word) > 2]
            topic_keywords[topic] = keywords

        # Match topics against text
        found_topics = []
        for topic, keywords in topic_keywords.items():
            # Topic matches if ANY of its keywords appear in text
            if any(kw in full_text for kw in keywords):
                found_topics.append(topic)

        return found_topics

    # ===== Learning from Feedback =====

    def learn_from_feedback(self, article_id: int, rating: int):
        """Learn from user feedback and adjust profile."""
        # Get article details
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            _ = cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
            row = cursor.fetchone()
            article = dict(row) if row else None

        if not article:
            return

        # Extract topics from article
        topics = self.extract_topics_from_text(
            article.get('content', ''),
            article.get('title', '')
        )

        if not topics:
            return

        # Adjust weights based on rating
        # rating 5 = +0.1, rating 4 = +0.05, rating 3 = 0, rating 2 = -0.05, rating 1 = -0.1
        delta_map = {5: 0.1, 4: 0.05, 3: 0.0, 2: -0.05, 1: -0.1}
        delta = delta_map.get(rating, 0.0)

        updates = []
        for topic in topics:
            new_weight = self.adjust_topic_weight(topic, delta)
            if new_weight is not None:
                updates.append((topic, new_weight))

        return updates

    # ===== Analysis & Insights =====

    def analyze_profile_evolution(self, days: int = 30) -> Dict[str, Any]:
        """Analyze how the profile has evolved over time."""
        # This would require historical tracking - simplified version
        profile = self.get_profile()

        explicit_topics = {k: v for k, v in profile.items() if v['source'] == 'explicit'}
        learned_topics = {k: v for k, v in profile.items() if v['source'] == 'learned'}

        return {
            'total_topics': len(profile),
            'explicit_count': len(explicit_topics),
            'learned_count': len(learned_topics),
            'top_topics': self.get_top_topics(5),
            'emerging_topics': [
                (topic, data['weight'])
                for topic, data in learned_topics.items()
                if data['weight'] >= 0.6
            ]
        }

