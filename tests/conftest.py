"""
Shared Pytest Fixtures for Database and Pipeline Testing
"""

import os
import sys
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.db_manager import get_db_engine, init_database


@pytest.fixture(scope="session")
def test_db(tmp_path_factory):
    """Creates an isolated session-scoped temporary SQLite database for fast test execution."""
    tmp_dir = tmp_path_factory.mktemp("db")
    db_file = tmp_dir / "test_warehouse.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    init_database(custom_url=db_url)
    engine = get_db_engine(db_url)
    yield engine, db_url
