"""Database connection handling for Quay."""

import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from typing import Generator, Any
from ..config.settings import Config


class DatabaseConnection:
    """Manages database connections to Quay."""
    
    def __init__(self, config: Config):
        self.config = config
        self._connection = None
    
    def connect(self):
        """Establish database connection."""
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(
                self.config.database_uri,
                cursor_factory=psycopg2.extras.RealDictCursor
            )
        return self._connection
    
    @contextmanager
    def get_cursor(self) -> Generator[psycopg2.extras.RealDictCursor, None, None]:
        """Get a database cursor with automatic connection management."""
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                yield cursor
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.commit()
    
    def close(self):
        """Close database connection."""
        if self._connection and not self._connection.closed:
            self._connection.close()