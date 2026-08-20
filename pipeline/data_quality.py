"""
Data Quality & Automation Engine (Part 4)
Implements automated checks across 5 core dimensions:
1. Completeness (Missing values)
2. Uniqueness (Duplicate records)
3. Validity (Domain value rules and data types)
4. Timeliness (Date boundary checks)
5. Referential Integrity (Foreign key validity)

Calculates weighted composite DQ score and persists audit history to dq_audit_log.
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.db_manager import get_db_engine, load_config
from pipeline.logger import get_logger

logger = get_logger("data_quality")


class DataQualityEngine:
    """Automated Data Quality Validator and Composite Scorer."""

    def __init__(self, engine: Engine = None, config: Dict[str, Any] = None):
        self.engine = engine or get_db_engine()
        self.config = config or load_config()
        self.dq_config = self.config.get("data_quality", {})
        self.pass_threshold = self.dq_config.get("pass_threshold_score", 95.0)
        self.weights = self.dq_config.get("dimension_weights", {
            "completeness": 0.25,
            "uniqueness": 0.25,
            "validity": 0.20,
            "referential_integrity": 0.20,
            "timeliness": 0.10,
        })
        self.allowed_events = self.dq_config.get("allowed_event_types", [
            "INVITE_SENT", "INVITE_ACCEPTED", "MESSAGE_SENT", "REPLY_RECEIVED", "CONNECTION_WITHDRAWN"
        ])

    def check_completeness(self, df: pd.DataFrame, required_columns: List[str]) -> Tuple[float, int, Dict[str, int]]:
        """
        Dimension 1: Completeness
        Measures proportion of non-null values across mandatory attributes.
        """
        if df.empty:
            return 100.0, 0, {}

        total_cells = len(df) * len(required_columns)
        null_counts = {}
        total_missing = 0

        for col in required_columns:
            if col in df.columns:
                missing = int(df[col].isna().sum())
                null_counts[col] = missing
                total_missing += missing
            else:
                null_counts[col] = len(df)
                total_missing += len(df)

        score = max(0.0, 100.0 * (1.0 - (total_missing / max(1, total_cells))))
        return round(score, 2), total_missing, null_counts

    def check_uniqueness(self, df: pd.DataFrame, key_column: str) -> Tuple[float, int, List[str]]:
        """
        Dimension 2: Uniqueness
        Checks for duplicate natural keys / event IDs.
        """
        if df.empty or key_column not in df.columns:
            return 100.0, 0, []

        duplicates = df[df.duplicated(subset=[key_column], keep=False)]
        duplicate_count = len(duplicates)
        score = max(0.0, 100.0 * (1.0 - (duplicate_count / max(1, len(df)))))
        duplicate_samples = duplicates[key_column].astype(str).unique().tolist()[:5]
        return round(score, 2), duplicate_count, duplicate_samples

    def check_validity(self, df: pd.DataFrame) -> Tuple[float, int, Dict[str, Any]]:
        """
        Dimension 3: Validity
        Checks that categorical values match expected domain definitions (e.g. event types).
        """
        if df.empty or "event_type" not in df.columns:
            return 100.0, 0, {}

        invalid_mask = ~df["event_type"].isin(self.allowed_events)
        invalid_count = int(invalid_mask.sum())
        score = max(0.0, 100.0 * (1.0 - (invalid_count / max(1, len(df)))))
        invalid_types = df.loc[invalid_mask, "event_type"].unique().tolist()
        return round(score, 2), invalid_count, {"invalid_event_types": invalid_types}

    def check_timeliness(self, df: pd.DataFrame, timestamp_col: str = "event_timestamp") -> Tuple[float, int, Dict[str, Any]]:
        """
        Dimension 4: Timeliness
        Ensures timestamps are in the past and within realistic operational boundaries (e.g. >= 2024).
        """
        if df.empty or timestamp_col not in df.columns:
            return 100.0, 0, {}

        now = pd.Timestamp.now(tz="UTC")
        min_allowed = pd.Timestamp("2024-01-01", tz="UTC")

        # Convert to datetime with UTC
        parsed_dates = pd.to_datetime(df[timestamp_col], errors="coerce", utc=True)
        future_events = (parsed_dates > now).sum()
        stale_events = (parsed_dates < min_allowed).sum()
        invalid_dates = parsed_dates.isna().sum()

        failed_count = int(future_events + stale_events + invalid_dates)
        score = max(0.0, 100.0 * (1.0 - (failed_count / max(1, len(df)))))
        return round(score, 2), failed_count, {
            "future_events": int(future_events),
            "stale_events": int(stale_events),
            "unparseable_dates": int(invalid_dates)
        }

    def check_referential_integrity(self, df: pd.DataFrame) -> Tuple[float, int, Dict[str, Any]]:
        """
        Dimension 5: Referential Integrity
        Verifies foreign keys resolve against parent dimension tables.
        """
        if df.empty:
            return 100.0, 0, {}

        failed_count = 0
        details = {}

        with self.engine.connect() as conn:
            # Check agent_id exists in dim_agent
            if "agent_id" in df.columns:
                valid_agents = set(r[0] for r in conn.execute(text("SELECT DISTINCT agent_id FROM dim_agent")).fetchall())
                missing_agents = df[~df["agent_id"].isin(valid_agents)]["agent_id"].unique().tolist()
                if missing_agents:
                    failed_count += len(missing_agents)
                    details["unresolved_agent_ids"] = missing_agents[:5]

            # Check campaign_id exists in dim_campaign
            if "campaign_id" in df.columns:
                valid_campaigns = set(r[0] for r in conn.execute(text("SELECT DISTINCT campaign_id FROM dim_campaign")).fetchall())
                missing_campaigns = df[~df["campaign_id"].isin(valid_campaigns)]["campaign_id"].unique().tolist()
                if missing_campaigns:
                    failed_count += len(missing_campaigns)
                    details["unresolved_campaign_ids"] = missing_campaigns[:5]

        score = max(0.0, 100.0 * (1.0 - (failed_count / max(1, len(df)))))
        return round(score, 2), failed_count, details

    def evaluate_batch(self, df: pd.DataFrame, table_name: str, pipeline_run_id: str) -> Dict[str, Any]:
        """
        Runs full 5-dimension assessment on a data batch, calculates composite score,
        and logs results to dq_audit_log table.
        """
        required_cols = ["event_id", "agent_id", "lead_id", "campaign_id", "event_timestamp", "event_type"]
        
        comp_score, comp_fails, comp_det = self.check_completeness(df, required_cols)
        uniq_score, uniq_fails, uniq_det = self.check_uniqueness(df, "event_id")
        val_score, val_fails, val_det = self.check_validity(df)
        time_score, time_fails, time_det = self.check_timeliness(df, "event_timestamp")
        ref_score, ref_fails, ref_det = self.check_referential_integrity(df)

        composite_score = round(
            (comp_score * self.weights["completeness"]) +
            (uniq_score * self.weights["uniqueness"]) +
            (val_score * self.weights["validity"]) +
            (ref_score * self.weights["referential_integrity"]) +
            (time_score * self.weights["timeliness"]),
            2
        )

        passed = 1 if composite_score >= self.pass_threshold else 0

        audit_entries = [
            ("COMPLETENESS", len(df), comp_fails, comp_score, json.dumps(comp_det)),
            ("UNIQUENESS", len(df), uniq_fails, uniq_score, json.dumps(uniq_det)),
            ("VALIDITY", len(df), val_fails, val_score, json.dumps(val_det)),
            ("TIMELINESS", len(df), time_fails, time_score, json.dumps(time_det)),
            ("REFERENTIAL_INTEGRITY", len(df), ref_fails, ref_score, json.dumps(ref_det)),
        ]

        # Insert audit results to dq_audit_log table
        insert_sql = text("""
            INSERT INTO dq_audit_log (
                pipeline_run_id, check_timestamp, table_name, dimension,
                records_evaluated, records_failed, dimension_score,
                composite_score, passed, details
            ) VALUES (
                :run_id, :ts, :table, :dim, :eval_cnt, :fail_cnt, :dim_score, :comp_score, :passed, :det
            )
        """)

        with self.engine.begin() as conn:
            for dim, evaluated, failed, dim_score, det_str in audit_entries:
                conn.execute(insert_sql, {
                    "run_id": pipeline_run_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "table": table_name,
                    "dim": dim,
                    "eval_cnt": evaluated,
                    "fail_cnt": failed,
                    "dim_score": dim_score,
                    "comp_score": composite_score,
                    "passed": passed,
                    "det": det_str
                })

        logger.info(
            "data_quality_evaluated",
            table=table_name,
            composite_score=composite_score,
            passed=bool(passed),
            threshold=self.pass_threshold
        )

        return {
            "composite_score": composite_score,
            "passed": bool(passed),
            "dimension_scores": {
                "completeness": comp_score,
                "uniqueness": uniq_score,
                "validity": val_score,
                "timeliness": time_score,
                "referential_integrity": ref_score,
            },
            "records_evaluated": len(df)
        }
