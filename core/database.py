"""Low-level database connection and schema management.

This module provides ONLY:
- Database connection via context manager
- Schema initialization

All CRUD operations belong in feature-based managers.
"""

import sqlite3
from contextlib import contextmanager
from typing import Generator


class Database:
    """Minimal SQLite connection manager - connection and schema only."""

    def __init__(self, db_path: str = "news.db"):
        self.db_path = db_path
        self.init_database()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_database(self) -> None:
        """Initialize database schema."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Articles table
            _ = cursor.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT,
                    summary TEXT,
                    deep_analysis TEXT,
                    source_name TEXT NOT NULL,
                    published_date TEXT,
                    fetched_date TEXT NOT NULL,
                    relevance_score REAL,
                    is_read INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Feedback table
            _ = cursor.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL,
                    rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
                    note TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (article_id) REFERENCES articles (id)
                )
            """)

            # Reader profile table
            _ = cursor.execute("""
                CREATE TABLE IF NOT EXISTS reader_profile (
                    topic TEXT PRIMARY KEY,
                    weight REAL NOT NULL DEFAULT 0.5,
                    source TEXT NOT NULL DEFAULT 'learned',
                    sample_count INTEGER DEFAULT 0,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes
            _ = cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_published
                ON articles(published_date DESC)
            """)
            _ = cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_relevance
                ON articles(relevance_score DESC)
            """)
            _ = cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_articles_source
                ON articles(source_name)
            """)
