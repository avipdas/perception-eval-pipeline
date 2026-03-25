"""Database connection manager.

Creates a SQLite database file and provides sessions for reading/writing.
The default location is data/eval.db — a single portable file, no server needed.

To switch to Postgres later, just change the URL:
    db = DatabaseManager("postgresql://user:pw@localhost:5432/perception")
"""

from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from storage.schema import Base

DEFAULT_DB_PATH = Path("data/eval.db")


class DatabaseManager:
    """Connects to the database and provides sessions.

    Usage:
        db = DatabaseManager()           # SQLite at data/eval.db
        db.create_tables()               # creates tables if they don't exist
        with db.session() as s:
            s.add(some_row)              # auto-commits when the block ends
    """

    def __init__(self, url: str | None = None) -> None:
        if url is None:
            DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{DEFAULT_DB_PATH}"

        self.engine = create_engine(url)
        self._session_factory = sessionmaker(bind=self.engine)

    def create_tables(self) -> None:
        """Run CREATE TABLE IF NOT EXISTS for every table in schema.py."""
        Base.metadata.create_all(self.engine)

    def drop_tables(self) -> None:
        """Drop all tables. Destructive — only use for resets."""
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Yield a session that auto-commits on success, auto-rolls-back on error."""
        sess = self._session_factory()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()
