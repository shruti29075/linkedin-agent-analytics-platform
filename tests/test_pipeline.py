"""
Pipeline Ingestion & Idempotency Tests (Part 2 & Part 8)
"""

import os
import sys
import pytest
from sqlalchemy import text

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pipeline.ingestion import IngestionService, WatermarkManager


def test_idempotent_ingestion(test_db):
    """
    Verifies that running the pipeline twice on the same data does NOT duplicate records.
    """
    engine, _ = test_db
    service = IngestionService(engine=engine)

    # 1. First run with synthetic data
    sample_payload = service.generate_synthetic_telemetry(days_back=3)
    res1 = service.run_pipeline(raw_payload=sample_payload, correlation_id="test-run-1")
    assert res1["status"] in ("SUCCESS", "WARNING_DQ_THRESHOLD")

    with engine.connect() as conn:
        count_after_first_run = conn.execute(text("SELECT COUNT(*) FROM fact_outreach_activity")).scalar()
    
    assert count_after_first_run > 0

    # 2. Second run with EXACT SAME payload
    res2 = service.run_pipeline(raw_payload=sample_payload, correlation_id="test-run-2")

    with engine.connect() as conn:
        count_after_second_run = conn.execute(text("SELECT COUNT(*) FROM fact_outreach_activity")).scalar()

    # Total records in warehouse MUST remain exactly identical (zero duplicate rows)
    assert count_after_second_run == count_after_first_run, "Idempotency failed: duplicate rows were inserted!"


def test_watermark_persistence(tmp_path):
    """Verifies that high-watermark updates and persists correctly."""
    wm_file = str(tmp_path / "test_watermark.json")
    wm_mgr = WatermarkManager(watermark_path=wm_file)

    assert wm_mgr.get_watermark() == "2025-01-01T00:00:00Z"

    test_ts = "2026-08-19T12:00:00Z"
    wm_mgr.set_watermark(test_ts)
    assert wm_mgr.get_watermark() == test_ts
