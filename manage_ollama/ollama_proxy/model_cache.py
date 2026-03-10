import sqlite3
import time
import os
from contextlib import contextmanager

class ModelCache:
    """Persistent SQLite cache for model sizes (size_vram) per host."""

    def __init__(self, db_path=None):
        if db_path is None:
            # Default to a file in the same directory as this script
            db_path = os.path.join(os.path.dirname(__file__), 'model_cache.sqlite')

        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS model_cache (
                    host_url TEXT,
                    model_name TEXT,
                    size_vram_bytes INTEGER,
                    last_updated REAL,
                    PRIMARY KEY (host_url, model_name)
                )
            """)
            conn.commit()

    def update_model_size(self, host_url: str, model_name: str, size_vram: int):
        """Update the cached size for a model on a specific host."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO model_cache (host_url, model_name, size_vram_bytes, last_updated)
                VALUES (?, ?, ?, ?)
            """, (host_url, model_name, size_vram, time.time()))
            conn.commit()

    def get_model_size(self, host_url: str, model_name: str) -> int | None:
        """Get the cached size for a model on a specific host, or None if not found."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT size_vram_bytes FROM model_cache
                WHERE host_url = ? AND model_name = ?
            """, (host_url, model_name))
            row = cursor.fetchone()
            return row[0] if row else None

    def get_all_entries(self):
        """Return all entries in the cache."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT host_url, model_name, size_vram_bytes, last_updated FROM model_cache")
            return cursor.fetchall()

    def clear(self):
        """Clear all cached data."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM model_cache")
            conn.commit()
