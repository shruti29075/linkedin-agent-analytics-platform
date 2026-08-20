"""
Master CLI Entry Point: LinkedIn Agent Analytics Platform
Orchestrates database migrations, data ingestion, DQ validation, risk modeling, and Power BI feed generation.
"""

import argparse
import json
import os
import sys
import uuid

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.db_manager import init_database
from models.risk_model import RiskModelEngine
from pipeline.ingestion import IngestionService
from pipeline.logger import get_logger
from powerbi.export_data import export_warehouse_tables

logger = get_logger("main_cli")


def main():
    parser = argparse.ArgumentParser(
        description="End-to-End LinkedIn Agent Analytics Platform CLI"
    )
    parser.add_argument("--init-db", action="store_true", help="Initialize database schema and date dimension")
    parser.add_argument("--ingest", action="store_true", help="Run incremental ingestion and data quality checks")
    parser.add_argument("--risk-model", action="store_true", help="Run statistical anomaly and capacity risk model")
    parser.add_argument("--export", action="store_true", help="Export Star Schema tables for Power BI")
    parser.add_argument("--run-all", action="store_true", help="Execute complete end-to-end analytics workflow")
    parser.add_argument("--days", type=int, default=30, help="Days of historical telemetry to generate/ingest (default: 30)")

    args = parser.parse_args()

    # Default to --run-all if no specific action given
    if not (args.init_db or args.ingest or args.risk_model or args.export or args.run_all):
        args.run_all = True

    correlation_id = str(uuid.uuid4())
    print("=" * 80)
    print(" LINKEDIN AGENT ANALYTICS PLATFORM")
    print(f" Correlation ID: {correlation_id}")
    print("=" * 80)

    # 1. Initialize Database
    if args.init_db or args.run_all:
        print("\n[1/4] Initializing Database & Star Schema...")
        init_database()
        print("  -> Star Schema tables and conformed dim_date generated.")

    # 2. Ingestion & Data Quality
    if args.ingest or args.run_all:
        print(f"\n[2/4] Running Ingestion Pipeline & Data Quality Checks ({args.days} days)...")
        service = IngestionService()
        telemetry = service.generate_synthetic_telemetry(days_back=args.days)
        result = service.run_pipeline(raw_payload=telemetry, correlation_id=correlation_id)
        print(f"  -> Ingested: {result['records_ingested']} events")
        print(f"  -> Loaded into Warehouse: {result['records_loaded']} records")
        print(f"  -> Quarantined to DLQ: {result['records_quarantined_dlq']} records")
        print(f"  -> Composite Data Quality Score: {result['dq_score']}% (Status: {result['status']})")

    # 3. Statistical Risk Model
    if args.risk_model or args.run_all:
        print("\n[3/4] Running Statistical Anomaly & Risk Model...")
        risk_engine = RiskModelEngine()
        risk_summary = risk_engine.run_risk_model()
        print(f"  -> Daily Agent Metric Records Scored: {risk_summary['records_processed']}")
        print(f"  -> Anomalies Flagged: {risk_summary['anomalies_flagged']}")
        print(f"  -> Critical Risk Accounts Throttled: {risk_summary['critical_risk_count']}")

    # 4. Power BI Exports
    if args.export or args.run_all:
        print("\n[4/4] Exporting Clean Dimensional Feeds for Power BI...")
        export_warehouse_tables()
        print("  -> CSV data feeds exported to powerbi/data_exports/")

    print("\n" + "=" * 80)
    print(" [SUCCESS] WORKFLOW COMPLETED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    main()
