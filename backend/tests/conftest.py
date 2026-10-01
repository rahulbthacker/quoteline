from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets its own SQLite file; nothing touches backend/var."""
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    db.init_db()
    from app.services import quote_table

    monkeypatch.setattr(quote_table, "SNAPSHOT_DIR", tmp_path / "snapshots")
    yield
    engine.dispose()
