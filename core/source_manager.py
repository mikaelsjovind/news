"""RSS source management."""

import json
from typing import Any, Dict, List


class SourceManager:
    """Manages RSS sources configuration."""

    def __init__(self, sources_file: str = "sources.json"):
        self.sources_file = sources_file
        self.sources = self._load_sources()

    def _load_sources(self) -> List[Dict[str, Any]]:
        """Load RSS sources from JSON file."""
        try:
            with open(self.sources_file, 'r', encoding='utf-8') as f:
                loaded_data: Any = json.load(f)
                sources: List[Dict[str, Any]] = loaded_data
                return sources
        except FileNotFoundError:
            print(f"Error: {self.sources_file} not found")
            return []
        except json.JSONDecodeError:
            print(f"Error: {self.sources_file} is not valid JSON")
            return []

    def add_source(self, name: str, url: str) -> bool:
        """Add a new RSS source."""
        try:
            # Check if source already exists
            for source in self.sources:
                if source['url'] == url:
                    print(f"Source with URL {url} already exists")
                    return False

            # Add to sources list
            self.sources.append({'name': name, 'url': url})

            # Save to file
            with open(self.sources_file, 'w', encoding='utf-8') as f:
                json.dump(self.sources, f, indent=2, ensure_ascii=False)

            print(f"Added source: {name}")
            return True

        except Exception as e:
            print(f"Error adding source: {e}")
            return False

    def remove_source(self, name: str) -> bool:
        """Remove an RSS source by name."""
        try:
            original_count = len(self.sources)
            self.sources = [s for s in self.sources if s['name'] != name]

            if len(self.sources) == original_count:
                print(f"Source '{name}' not found")
                return False

            # Save to file
            with open(self.sources_file, 'w', encoding='utf-8') as f:
                json.dump(self.sources, f, indent=2, ensure_ascii=False)

            print(f"Removed source: {name}")
            return True

        except Exception as e:
            print(f"Error removing source: {e}")
            return False

    def list_sources(self) -> List[Dict[str, Any]]:
        """List all RSS sources."""
        return self.sources
