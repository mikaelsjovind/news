"""RSS feed fetching and parsing."""

import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

import feedparser

from core.database import Database
from core.source_manager import SourceManager


class FeedFetcher:
    """Fetches and parses RSS feeds."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.source_mgr = SourceManager()

    def _normalize_url(self, url: str) -> str:
        """Normalize URL by removing query parameters and fragments.

        This prevents duplicates when feeds include dynamic tokens or tracking params.
        Example: https://example.com/article?token=123 -> https://example.com/article
        """
        if not url:
            return url

        try:
            parsed = urlparse(url)
            # Reconstruct URL without query params and fragment
            normalized = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                '',  # params (empty)
                '',  # query (empty)
                ''   # fragment (empty)
            ))
            return normalized
        except Exception:
            # If parsing fails, return original URL
            return url

    def _parse_date(self, date_str: Optional[Any]) -> Optional[str]:
        """Parse and normalize date from feed."""
        if not date_str:
            return None

        try:
            # feedparser provides a time_struct
            if hasattr(date_str, 'tm_year'):
                time_tuple: time.struct_time = date_str
                dt = datetime(*time_tuple[:6])
                return dt.isoformat()
            return str(date_str)
        except Exception:
            return None

    def _clean_content(self, entry: Any) -> str:
        """Extract clean content from feed entry."""
        # Try different content fields in order of preference
        if hasattr(entry, 'content') and entry.content:
            return entry.content[0].value if isinstance(entry.content, list) else entry.content

        if hasattr(entry, 'summary') and entry.summary:
            return entry.summary

        if hasattr(entry, 'description') and entry.description:
            return entry.description

        return ""

    def fetch_feed(self, source: Dict[str, str], max_articles: int = 50) -> List[Dict[str, Any]]:
        """Fetch and parse a single RSS feed."""
        name = source.get('name', 'Unknown')
        url = source.get('url')

        if not url:
            print(f"Warning: Source '{name}' has no URL")
            return []

        try:
            print(f"Fetching {name}...")
            feed = feedparser.parse(url)

            if feed.bozo:
                print(f"Warning: Feed parsing error for {name}: {feed.bozo_exception}")

            articles = []
            for entry in feed.entries[:max_articles]:
                raw_url: str = str(entry.get('link', ''))
                article = {
                    'url': self._normalize_url(raw_url),
                    'title': entry.get('title', 'No title'),
                    'content': self._clean_content(entry),
                    'source_name': name,
                    'published_date': self._parse_date(entry.get('published_parsed'))
                }

                if article['url']:
                    articles.append(article)

            print(f"  Found {len(articles)} articles from {name}")
            return articles

        except Exception as e:
            print(f"Error fetching {name}: {e}")
            return []

    def fetch_all(self, max_articles_per_source: int = 50) -> Dict[str, Any]:
        """Fetch all RSS feeds and save to database."""
        sources = self.source_mgr.list_sources()
        print(f"\nFetching from {len(sources)} sources...")

        total_fetched = 0
        total_new = 0
        errors = []

        for source in sources:
            try:
                articles = self.fetch_feed(source, max_articles_per_source)
                total_fetched += len(articles)

                # Save to database
                for article in articles:
                    with self.db.get_connection() as conn:
                        cursor = conn.cursor()
                        try:
                            _ = cursor.execute("""
                                INSERT INTO articles
                                (url, title, content, source_name, published_date, fetched_date)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (article['url'], article['title'], article['content'],
                                  article['source_name'], article['published_date'],
                                  datetime.now().isoformat()))
                            total_new += 1
                        except sqlite3.IntegrityError:
                            # Article already exists (duplicate URL)
                            pass

            except Exception as e:
                error_msg = f"Error processing {source.get('name', 'unknown')}: {e}"
                errors.append(error_msg)
                print(f"  {error_msg}")

        result = {
            'total_fetched': total_fetched,
            'total_new': total_new,
            'total_sources': len(sources),
            'errors': errors,
            'timestamp': datetime.now().isoformat()
        }

        print("\nFetch complete!")
        print(f"  Total articles found: {total_fetched}")
        print(f"  New articles saved: {total_new}")
        print(f"  Duplicates skipped: {total_fetched - total_new}")

        if errors:
            print(f"  Errors: {len(errors)}")

        return result
