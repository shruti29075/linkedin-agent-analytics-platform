"""
Power BI Data Exporter & Feed Generator (Part 6)
Exports all Star Schema warehouse tables to clean CSV/Parquet feeds for direct ingestion into Power BI.
"""

import os
import sys
import pandas as pd
from sqlalchemy import text

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.db_manager import get_db_engine
from pipeline.logger import get_logger

logger = get_logger("powerbi_export")


def export_warehouse_tables(output_dir: str = None) -> None:
    """Exports all dimension and fact tables to CSV files for Power BI Desktop."""
    if output_dir is None:
        output_dir = os.path.join(PROJECT_ROOT, "powerbi", "data_exports")
    os.makedirs(output_dir, exist_ok=True)

    engine = get_db_engine()
    tables = [
        "dim_agent",
        "dim_lead",
        "dim_campaign",
        "dim_date",
        "fact_outreach_activity",
        "fact_daily_agent_metric",
        "dq_audit_log",
        "pipeline_runs"
    ]

    with engine.connect() as conn:
        for tbl in tables:
            df = pd.read_sql(text(f"SELECT * FROM {tbl}"), conn)
            csv_path = os.path.join(output_dir, f"{tbl}.csv")
            df.to_csv(csv_path, index=False)
            logger.info("table_exported_for_powerbi", table=tbl, rows=len(df), path=csv_path)

    print(f"\n[OK] All 8 tables successfully exported to {output_dir}")


if __name__ == "__main__":
    export_warehouse_tables()
