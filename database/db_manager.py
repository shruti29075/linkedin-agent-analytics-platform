"""
Database Manager & Schema Migration Engine
Handles connection pooling, table initialization, and conformed date dimension population.
"""

import os
import sys
from datetime import date, timedelta
from typing import Optional

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import yaml

from pipeline.logger import get_logger

logger = get_logger("db_manager")


def load_config(config_path: str = None) -> dict:
    """Loads system YAML configuration."""
    if config_path is None:
        config_path = os.path.join(PROJECT_ROOT, "config", "config.yaml")
    if not os.path.exists(config_path):
        return {
            "database": {"connection_string": "sqlite:///database/warehouse.db"}
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_db_engine(custom_url: Optional[str] = None) -> Engine:
    """Creates and returns a SQLAlchemy engine."""
    config = load_config()
    db_url = custom_url or os.environ.get("DATABASE_URL") or config.get("database", {}).get("connection_string", "sqlite:///database/warehouse.db")
    
    # Handle SQLite paths safely (excluding in-memory indicators)
    if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:///:memory:"):
        rel_path = db_url.replace("sqlite:///", "")
        db_path = os.path.join(PROJECT_ROOT, rel_path) if not os.path.isabs(rel_path) else rel_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        db_url = f"sqlite:///{os.path.abspath(db_path)}"

    return create_engine(db_url, echo=False)


def init_database(schema_path: str = None, custom_url: Optional[str] = None) -> None:
    """
    Executes the DDL schema to create tables, indexes, and constraints.
    Populates conformed date dimension.
    """
    if schema_path is None:
        schema_path = os.path.join(PROJECT_ROOT, "database", "schema.sql")

    engine = get_db_engine(custom_url)
    
    with open(schema_path, "r", encoding="utf-8") as f:
        ddl_script = f.read()

    # Split and execute individual statements
    with engine.begin() as conn:
        for statement in ddl_script.split(";"):
            cleaned = statement.strip()
            if cleaned:
                conn.execute(text(cleaned))

    logger.info("database_schema_initialized", schema_file=schema_path)
    populate_date_dimension(engine, start_date=date(2025, 1, 1), end_date=date(2027, 12, 31))


def populate_date_dimension(engine: Engine, start_date: date, end_date: date) -> None:
    """
    Generates conformed date dimension records across the specified date range.
    Grain: 1 record per calendar day.
    """
    date_records = []
    current = start_date
    while current <= end_date:
        date_key = int(current.strftime("%Y%m%d"))
        day_of_week = current.isoweekday() # 1 = Monday, 7 = Sunday
        is_weekend = 1 if day_of_week in (6, 7) else 0
        
        date_records.append({
            "date_key": date_key,
            "full_date": current.isoformat(),
            "day_of_week": day_of_week,
            "day_name": current.strftime("%A"),
            "month_number": current.month,
            "month_name": current.strftime("%B"),
            "quarter": (current.month - 1) // 3 + 1,
            "year": current.year,
            "is_weekend": is_weekend
        })
        current += timedelta(days=1)

    insert_sql = text("""
        INSERT OR IGNORE INTO dim_date (
            date_key, full_date, day_of_week, day_name,
            month_number, month_name, quarter, year, is_weekend
        ) VALUES (
            :date_key, :full_date, :day_of_week, :day_name,
            :month_number, :month_name, :quarter, :year, :is_weekend
        )
    """)

    with engine.begin() as conn:
        conn.execute(insert_sql, date_records)

    logger.info("dim_date_populated", records_count=len(date_records), start=str(start_date), end=str(end_date))


if __name__ == "__main__":
    init_database()
    print("Database initialized successfully with Star Schema tables and dim_date records.")
