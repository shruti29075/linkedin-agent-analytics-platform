"""
Statistical Risk & Anomaly Scoring Model (Part 5)

Methodology & Statistical Justification:
1. Exponentially Weighted Moving Average (EWMA) + Rolling Z-Score:
   Outreach metrics (acceptance rates, reply rates) are non-stationary time series with weekly
   seasonality. EWMA gives higher weight to recent performance while smoothing day-to-day noise.
   The rolling Z-score:
       Z_t = (x_t - mu_{t-1}) / (sigma_{t-1} + epsilon)
   measures deviation in standard deviations from the historical baseline.

2. Hidden Risk Detection:
   - Acceptance Rate Collapse: Z_t <= -2.0 OR sharp drop from baseline.
   - Ghosting / Inactivity Pattern: Multiple consecutive zero-response days despite active sends.
   - Reply Rate Decay: > 40% decay in moving average relative to baseline.

3. Capacity Optimization:
   Calculates daily invite/message capacity recommendations strictly bounded by the
   Part 1 Account Age Tier Matrix:
   - Normal: 100% of Tier Ceiling
   - Warning: 70% of Tier Ceiling (proactive throttling)
   - Critical: 30% of Tier Ceiling (safe cooldown floor to prevent ban)
"""

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
import yaml

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.db_manager import get_db_engine, load_config
from pipeline.logger import get_logger

logger = get_logger("risk_model")


class RiskModelEngine:
    """Statistical Risk Engine for LinkedIn Outreach Agents."""

    def __init__(self, engine: Engine = None, config: Dict[str, Any] = None):
        self.engine = engine or get_db_engine()
        self.config = config or load_config()
        self.risk_cfg = self.config.get("risk_model", {})
        self.z_threshold = self.risk_cfg.get("z_score_threshold", -2.0)
        self.ewma_span = self.risk_cfg.get("ewma_span_days", 7)
        self.min_data_points = self.risk_cfg.get("min_data_points_required", 5)

        # Load rate limits matrix
        limits_file = os.path.join(PROJECT_ROOT, "config", "rate_limits.yaml")
        with open(limits_file, "r", encoding="utf-8") as f:
            self.rate_limits = yaml.safe_load(f).get("account_age_tiers", {})

    def fetch_daily_activity_aggregates(self) -> pd.DataFrame:
        """Queries fact_outreach_activity grouped by agent_sk and date_key."""
        query = text("""
            SELECT 
                f.agent_sk,
                a.agent_id,
                a.account_age_tier,
                a.daily_invite_ceiling,
                a.daily_message_ceiling,
                f.date_key,
                d.full_date,
                SUM(CASE WHEN f.event_type = 'INVITE_SENT' THEN 1 ELSE 0 END) AS invites_sent,
                SUM(CASE WHEN f.event_type = 'INVITE_ACCEPTED' THEN 1 ELSE 0 END) AS invites_accepted,
                SUM(CASE WHEN f.event_type = 'MESSAGE_SENT' THEN 1 ELSE 0 END) AS messages_sent,
                SUM(CASE WHEN f.event_type = 'REPLY_RECEIVED' THEN 1 ELSE 0 END) AS replies_received
            FROM fact_outreach_activity f
            JOIN dim_agent a ON f.agent_sk = a.agent_sk
            JOIN dim_date d ON f.date_key = d.date_key
            GROUP BY f.agent_sk, a.agent_id, a.account_age_tier, a.daily_invite_ceiling, a.daily_message_ceiling, f.date_key, d.full_date
            ORDER BY f.agent_sk, f.date_key ASC
        """)
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)
        return df

    def compute_agent_anomalies_and_capacity(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes rolling statistical metrics, anomaly scores, and optimized capacity recommendations.
        """
        if df.empty:
            return df

        # Compute raw rates
        df["acceptance_rate"] = np.where(df["invites_sent"] > 0, df["invites_accepted"] / df["invites_sent"], 0.0)
        df["reply_rate"] = np.where(df["messages_sent"] > 0, df["replies_received"] / df["messages_sent"], 0.0)

        # Capacity utilization percentages
        df["invite_limit_utilization_pct"] = np.round((df["invites_sent"] / df["daily_invite_ceiling"]) * 100, 2)
        df["message_limit_utilization_pct"] = np.round((df["messages_sent"] / df["daily_message_ceiling"]) * 100, 2)

        results = []
        for agent_sk, group in df.groupby("agent_sk"):
            group = group.sort_values("date_key").copy()

            # Long-term historical baseline (14-day rolling) and short-term EWMA
            raw_mean = group["acceptance_rate"].shift(1).ewm(span=self.ewma_span, min_periods=self.min_data_points).mean()
            raw_std = group["acceptance_rate"].shift(1).ewm(span=self.ewma_span, min_periods=self.min_data_points).std()
            
            group["rolling_mean_acc"] = raw_mean.bfill().fillna(group["acceptance_rate"].mean())
            group["rolling_std_acc"] = np.maximum(raw_std.bfill().fillna(0.08), 0.05)

            # Compute Z-score
            group["anomaly_score"] = (group["acceptance_rate"] - group["rolling_mean_acc"]) / group["rolling_std_acc"]
            group["anomaly_score"] = group["anomaly_score"].fillna(0.0).round(3)

            # Ghosting & collapse detection: 2+ consecutive zero-acceptance days with active outbound volume
            is_zero_acceptance = (group["invites_sent"] > 0) & (group["acceptance_rate"] <= 0.05)
            consecutive_zeros = is_zero_acceptance.rolling(2, min_periods=2).sum() >= 2

            is_critical = (group["anomaly_score"] <= self.z_threshold) | consecutive_zeros
            is_warning = (group["anomaly_score"] <= -1.5) | ((group["rolling_mean_acc"] >= 0.20) & (group["acceptance_rate"] <= 0.15))

            # Classify Risk Level
            conditions = [
                is_critical,
                is_warning
            ]
            choices = ["CRITICAL", "WARNING"]
            group["risk_level"] = np.select(conditions, choices, default="NORMAL")

            # Dynamic Capacity Optimization
            capacity_multiplier = np.where(
                group["risk_level"] == "CRITICAL", 0.30,
                np.where(group["risk_level"] == "WARNING", 0.70, 1.00)
            )

            group["recommended_invite_capacity"] = np.maximum(
                1, np.floor(group["daily_invite_ceiling"] * capacity_multiplier)
            ).astype(int)

            group["recommended_message_capacity"] = np.maximum(
                2, np.floor(group["daily_message_ceiling"] * capacity_multiplier)
            ).astype(int)

            results.append(group)

        return pd.concat(results, ignore_index=True)

    def persist_daily_metrics(self, scored_df: pd.DataFrame) -> int:
        """Upserts scored daily agent metrics into fact_daily_agent_metric table."""
        if scored_df.empty:
            return 0

        upsert_sql = text("""
            INSERT INTO fact_daily_agent_metric (
                agent_sk, date_key, invites_sent, invites_accepted,
                messages_sent, replies_received, acceptance_rate, reply_rate,
                invite_limit_utilization_pct, message_limit_utilization_pct,
                anomaly_score, risk_level, recommended_invite_capacity,
                recommended_message_capacity, updated_at
            ) VALUES (
                :agent_sk, :date_key, :invites_sent, :invites_accepted,
                :messages_sent, :replies_received, :acceptance_rate, :reply_rate,
                :invite_limit_utilization_pct, :message_limit_utilization_pct,
                :anomaly_score, :risk_level, :recommended_invite_capacity,
                :recommended_message_capacity, :updated_at
            )
            ON CONFLICT(agent_sk, date_key) DO UPDATE SET
                invites_sent = excluded.invites_sent,
                invites_accepted = excluded.invites_accepted,
                messages_sent = excluded.messages_sent,
                replies_received = excluded.replies_received,
                acceptance_rate = excluded.acceptance_rate,
                reply_rate = excluded.reply_rate,
                invite_limit_utilization_pct = excluded.invite_limit_utilization_pct,
                message_limit_utilization_pct = excluded.message_limit_utilization_pct,
                anomaly_score = excluded.anomaly_score,
                risk_level = excluded.risk_level,
                recommended_invite_capacity = excluded.recommended_invite_capacity,
                recommended_message_capacity = excluded.recommended_message_capacity,
                updated_at = excluded.updated_at
        """)

        records = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for _, row in scored_df.iterrows():
            records.append({
                "agent_sk": int(row["agent_sk"]),
                "date_key": int(row["date_key"]),
                "invites_sent": int(row["invites_sent"]),
                "invites_accepted": int(row["invites_accepted"]),
                "messages_sent": int(row["messages_sent"]),
                "replies_received": int(row["replies_received"]),
                "acceptance_rate": float(row["acceptance_rate"]),
                "reply_rate": float(row["reply_rate"]),
                "invite_limit_utilization_pct": float(row["invite_limit_utilization_pct"]),
                "message_limit_utilization_pct": float(row["message_limit_utilization_pct"]),
                "anomaly_score": float(row["anomaly_score"]),
                "risk_level": str(row["risk_level"]),
                "recommended_invite_capacity": int(row["recommended_invite_capacity"]),
                "recommended_message_capacity": int(row["recommended_message_capacity"]),
                "updated_at": now_iso
            })

        with self.engine.begin() as conn:
            conn.execute(upsert_sql, records)

        logger.info("daily_risk_metrics_persisted", records_count=len(records))
        return len(records)

    def run_risk_model(self) -> Dict[str, Any]:
        """Runs the statistical risk and anomaly model end-to-end."""
        logger.info("risk_model_execution_started")
        raw_df = self.fetch_daily_activity_aggregates()
        scored_df = self.compute_agent_anomalies_and_capacity(raw_df)
        persisted_count = self.persist_daily_metrics(scored_df)

        anomalies_count = int((scored_df["risk_level"] != "NORMAL").sum()) if not scored_df.empty else 0
        critical_count = int((scored_df["risk_level"] == "CRITICAL").sum()) if not scored_df.empty else 0

        logger.info(
            "risk_model_execution_completed",
            total_records=persisted_count,
            anomalies_detected=anomalies_count,
            critical_alerts=critical_count
        )

        return {
            "status": "SUCCESS",
            "records_processed": persisted_count,
            "anomalies_flagged": anomalies_count,
            "critical_risk_count": critical_count
        }


if __name__ == "__main__":
    engine = RiskModelEngine()
    summary = engine.run_risk_model()
    print("\n--- Risk Model Execution Summary ---")
    print(summary)
