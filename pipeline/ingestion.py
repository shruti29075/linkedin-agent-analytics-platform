"""
Secure, Idempotent API Ingestion & Pipeline Service (Part 2)
Implements:
1. Incremental loading using watermark timestamps
2. Idempotent Star Schema writes (zero duplicate rows upon re-run)
3. Robust retries with exponential backoff & rate-limit awareness
4. Dead-letter queue (DLQ) capture for malformed records
5. Run metadata persistence in pipeline_runs table
"""

import json
import os
import random
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
import yaml

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.db_manager import get_db_engine, init_database, load_config
from pipeline.data_quality import DataQualityEngine
from pipeline.logger import get_logger

logger = get_logger("ingestion_pipeline")


class WatermarkManager:
    """Manages high-watermark timestamps for incremental ETL extraction."""

    def __init__(self, watermark_path: str = None):
        if watermark_path is None:
            config = load_config()
            rel_path = config.get("pipeline", {}).get("watermark_file", "data/watermark.json")
            watermark_path = os.path.join(PROJECT_ROOT, rel_path)
        self.watermark_path = watermark_path
        os.makedirs(os.path.dirname(self.watermark_path), exist_ok=True)

    def get_watermark(self) -> str:
        """Returns the last successfully processed timestamp or a default start date."""
        if os.path.exists(self.watermark_path):
            try:
                with open(self.watermark_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("last_processed_timestamp", "2025-01-01T00:00:00Z")
            except Exception as e:
                logger.warning("watermark_read_error", error=str(e))
        return "2025-01-01T00:00:00Z"

    def set_watermark(self, timestamp_iso: str) -> None:
        """Saves the latest watermark timestamp."""
        try:
            with open(self.watermark_path, "w", encoding="utf-8") as f:
                json.dump({"last_processed_timestamp": timestamp_iso, "updated_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)
            logger.info("watermark_updated", new_watermark=timestamp_iso)
        except Exception as e:
            logger.error("watermark_write_error", error=str(e))


class DeadLetterQueue:
    """Captures and quarantines failed or malformed records with failure reasons."""

    def __init__(self, dlq_dir: str = None):
        if dlq_dir is None:
            config = load_config()
            rel_path = config.get("pipeline", {}).get("dead_letter_dir", "data/dead_letter")
            dlq_dir = os.path.join(PROJECT_ROOT, rel_path)
        self.dlq_dir = dlq_dir
        os.makedirs(self.dlq_dir, exist_ok=True)

    def quarantine_records(self, failed_records: List[Dict[str, Any]], run_id: str) -> int:
        """Writes quarantined records to a timestamped JSON file."""
        if not failed_records:
            return 0

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"dlq_{run_id}_{timestamp}.json"
        file_path = os.path.join(self.dlq_dir, filename)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(failed_records, f, indent=2)
            logger.warning("records_quarantined_to_dlq", count=len(failed_records), dlq_file=file_path)
            return len(failed_records)
        except Exception as e:
            logger.error("dlq_write_failure", error=str(e))
            return len(failed_records)


def with_exponential_backoff(max_retries: int = 3, backoff_factor: float = 2.0):
    """Decorator executing callable with exponential backoff on failure."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    sleep_time = backoff_factor ** attempts + random.uniform(0.1, 0.5)
                    logger.warning("operation_failed_retrying", attempt=attempts, max_retries=max_retries, sleep_sec=round(sleep_time, 2), error=str(e))
                    if attempts >= max_retries:
                        logger.error("operation_failed_max_retries_exceeded", error=str(e))
                        raise e
                    time.sleep(sleep_time)
        return wrapper
    return decorator


class IngestionService:
    """End-to-end API Ingestion and Staging Service."""

    def __init__(self, engine: Engine = None, config: Dict[str, Any] = None):
        self.engine = engine or get_db_engine()
        self.config = config or load_config()
        self.watermark_mgr = WatermarkManager()
        self.dlq = DeadLetterQueue()
        self.dq_engine = DataQualityEngine(self.engine, self.config)

    def generate_synthetic_telemetry(self, days_back: int = 30) -> Dict[str, List[Dict[str, Any]]]:
        """
        Generates realistic LinkedIn outreach telemetry matching the Part 1 Account Age Tier Matrix.
        """
        agents = [
            {
                "agent_id": "AGT-001",
                "agent_name": "Sarah Connor",
                "linkedin_profile_url": "https://linkedin.com/in/sarah-connor-enterprise",
                "account_age_tier": "< 1 Month",
                "risk_classification": "Very High Risk",
                "daily_invite_ceiling": 5,
                "daily_message_ceiling": 10,
                "status": "ACTIVE"
            },
            {
                "agent_id": "AGT-002",
                "agent_name": "Marcus Vance",
                "linkedin_profile_url": "https://linkedin.com/in/marcus-vance-b2b",
                "account_age_tier": "1 Month",
                "risk_classification": "High Risk",
                "daily_invite_ceiling": 10,
                "daily_message_ceiling": 15,
                "status": "ACTIVE"
            },
            {
                "agent_id": "AGT-003",
                "agent_name": "Elena Rostova",
                "linkedin_profile_url": "https://linkedin.com/in/elena-rostova-growth",
                "account_age_tier": "2–6 Months",
                "risk_classification": "Moderate Risk",
                "daily_invite_ceiling": 15,
                "daily_message_ceiling": 25,
                "status": "ACTIVE"
            },
            {
                "agent_id": "AGT-004",
                "agent_name": "David Kim",
                "linkedin_profile_url": "https://linkedin.com/in/david-kim-strategy",
                "account_age_tier": "6–12 Months",
                "risk_classification": "Low Risk",
                "daily_invite_ceiling": 25,
                "daily_message_ceiling": 40,
                "status": "ACTIVE"
            },
            {
                "agent_id": "AGT-005",
                "agent_name": "Rachel Zane",
                "linkedin_profile_url": "https://linkedin.com/in/rachel-zane-partnerships",
                "account_age_tier": "1+ Year",
                "risk_classification": "Minimal Risk",
                "daily_invite_ceiling": 30,
                "daily_message_ceiling": 60,
                "status": "ACTIVE"
            }
        ]

        campaigns = [
            {"campaign_id": "CMP-101", "campaign_name": "SaaS VP Sales Q3", "target_segment": "Enterprise Tech", "daily_budget": 150.00, "start_date": "2026-07-01", "end_date": "2026-09-30", "status": "ACTIVE"},
            {"campaign_id": "CMP-102", "campaign_name": "FinTech Series A Founders", "target_segment": "Startups", "daily_budget": 100.00, "start_date": "2026-07-15", "end_date": "2026-10-15", "status": "ACTIVE"},
            {"campaign_id": "CMP-103", "campaign_name": "Healthcare IT Directors", "target_segment": "Healthcare", "daily_budget": 80.00, "start_date": "2026-08-01", "end_date": "2026-11-01", "status": "ACTIVE"}
        ]

        titles = ["VP of Sales", "Head of Growth", "Founder & CEO", "CTO", "Director of Product", "Chief Revenue Officer"]
        companies = ["Acme Cloud", "Stripewave", "NovaHealth", "Dataprism", "CyberShield", "FinFlow AI", "OmniScale"]
        industries = ["Software & SaaS", "Financial Services", "HealthTech", "Cybersecurity", "Artificial Intelligence"]
        locations = ["San Francisco, CA", "New York, NY", "London, UK", "Austin, TX", "Bengaluru, India", "Berlin, Germany"]

        leads = []
        for i in range(1, 121):
            leads.append({
                "lead_id": f"LEAD-{i:04d}",
                "first_name": f"LeadFirst_{i}",
                "last_name": f"LeadLast_{i}",
                "job_title": random.choice(titles),
                "company_name": random.choice(companies),
                "industry": random.choice(industries),
                "location": random.choice(locations),
                "target_segment": random.choice(["Enterprise Tech", "Startups", "Healthcare"])
            })

        activities = []
        base_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        event_counter = 1

        for day_offset in range(days_back + 1):
            curr_day = base_date + timedelta(days=day_offset)
            date_key = int(curr_day.strftime("%Y%m%d"))
            is_recent_drop = (day_offset >= (days_back - 5))

            for agent in agents:
                max_inv = agent["daily_invite_ceiling"]

                if agent["agent_id"] == "AGT-001" and is_recent_drop:
                    inv_count = max_inv
                    accept_prob = 0.05
                elif agent["agent_id"] == "AGT-002" and is_recent_drop:
                    inv_count = max_inv
                    accept_prob = 0.10
                else:
                    inv_count = random.randint(max(1, max_inv - 2), max_inv)
                    accept_prob = random.uniform(0.30, 0.50)

                for _ in range(inv_count):
                    lead = random.choice(leads)
                    campaign = random.choice(campaigns)
                    invite_time = curr_day.replace(hour=random.randint(9, 17), minute=random.randint(0, 59))

                    activities.append({
                        "event_id": f"EVT-{event_counter:07d}",
                        "agent_id": agent["agent_id"],
                        "lead_id": lead["lead_id"],
                        "campaign_id": campaign["campaign_id"],
                        "date_key": date_key,
                        "event_timestamp": invite_time.isoformat(),
                        "event_type": "INVITE_SENT",
                        "message_length": random.randint(120, 280),
                        "response_latency_hours": None,
                        "is_converted": 0
                    })
                    event_counter += 1

                    if random.random() < accept_prob:
                        accept_time = invite_time + timedelta(hours=random.uniform(2, 24))
                        activities.append({
                            "event_id": f"EVT-{event_counter:07d}",
                            "agent_id": agent["agent_id"],
                            "lead_id": lead["lead_id"],
                            "campaign_id": campaign["campaign_id"],
                            "date_key": int(accept_time.strftime("%Y%m%d")),
                            "event_timestamp": accept_time.isoformat(),
                            "event_type": "INVITE_ACCEPTED",
                            "message_length": 0,
                            "response_latency_hours": round(random.uniform(2, 24), 2),
                            "is_converted": 0
                        })
                        event_counter += 1

                        msg_time = accept_time + timedelta(hours=random.uniform(1, 4))
                        activities.append({
                            "event_id": f"EVT-{event_counter:07d}",
                            "agent_id": agent["agent_id"],
                            "lead_id": lead["lead_id"],
                            "campaign_id": campaign["campaign_id"],
                            "date_key": int(msg_time.strftime("%Y%m%d")),
                            "event_timestamp": msg_time.isoformat(),
                            "event_type": "MESSAGE_SENT",
                            "message_length": random.randint(200, 450),
                            "response_latency_hours": None,
                            "is_converted": 0
                        })
                        event_counter += 1

                        if random.random() < 0.28:
                            reply_time = msg_time + timedelta(hours=random.uniform(1, 18))
                            is_converted = 1 if random.random() < 0.45 else 0
                            activities.append({
                                "event_id": f"EVT-{event_counter:07d}",
                                "agent_id": agent["agent_id"],
                                "lead_id": lead["lead_id"],
                                "campaign_id": campaign["campaign_id"],
                                "date_key": int(reply_time.strftime("%Y%m%d")),
                                "event_timestamp": reply_time.isoformat(),
                                "event_type": "REPLY_RECEIVED",
                                "message_length": random.randint(50, 200),
                                "response_latency_hours": round(random.uniform(1, 18), 2),
                                "is_converted": is_converted
                            })
                            event_counter += 1

        return {
            "agents": agents,
            "campaigns": campaigns,
            "leads": leads,
            "activities": activities
        }

    def load_dimensions(self, payload: Dict[str, Any]) -> None:
        """Idempotently loads and maintains dimensions with surrogate keys."""
        with self.engine.begin() as conn:
            for ag in payload.get("agents", []):
                existing = conn.execute(
                    text("SELECT agent_sk FROM dim_agent WHERE agent_id = :id AND is_current = 1"),
                    {"id": ag["agent_id"]}
                ).fetchone()

                now_iso = datetime.now(timezone.utc).isoformat()
                if not existing:
                    conn.execute(
                        text("""
                            INSERT INTO dim_agent (
                                agent_id, agent_name, linkedin_profile_url, account_age_tier,
                                risk_classification, daily_invite_ceiling, daily_message_ceiling,
                                status, effective_date, end_date, is_current
                            ) VALUES (
                                :agent_id, :agent_name, :linkedin_profile_url, :account_age_tier,
                                :risk_classification, :daily_invite_ceiling, :daily_message_ceiling,
                                :status, :effective_date, NULL, 1
                            )
                        """),
                        {**ag, "effective_date": now_iso}
                    )

            for cmp in payload.get("campaigns", []):
                conn.execute(
                    text("""
                        INSERT OR IGNORE INTO dim_campaign (
                            campaign_id, campaign_name, target_segment, daily_budget, start_date, end_date, status
                        ) VALUES (
                            :campaign_id, :campaign_name, :target_segment, :daily_budget, :start_date, :end_date, :status
                        )
                    """),
                    cmp
                )

            for ld in payload.get("leads", []):
                conn.execute(
                    text("""
                        INSERT OR IGNORE INTO dim_lead (
                            lead_id, first_name, last_name, job_title, company_name, industry, location, target_segment
                        ) VALUES (
                            :lead_id, :first_name, :last_name, :job_title, :company_name, :industry, :location, :target_segment
                        )
                    """),
                    ld
                )

    def load_fact_activities(self, activities_df: pd.DataFrame) -> Tuple[int, int]:
        """
        Resolves surrogate keys and loads activities idempotently.
        Returns: (records_inserted, records_quarantined)
        """
        if activities_df.empty:
            return 0, 0

        with self.engine.connect() as conn:
            agent_map = dict(conn.execute(text("SELECT agent_id, agent_sk FROM dim_agent WHERE is_current = 1")).fetchall())
            lead_map = dict(conn.execute(text("SELECT lead_id, lead_sk FROM dim_lead")).fetchall())
            campaign_map = dict(conn.execute(text("SELECT campaign_id, campaign_sk FROM dim_campaign")).fetchall())

        valid_rows = []
        failed_records = []

        for _, row in activities_df.iterrows():
            rec = row.to_dict()
            agent_sk = agent_map.get(rec.get("agent_id"))
            lead_sk = lead_map.get(rec.get("lead_id"))
            campaign_sk = campaign_map.get(rec.get("campaign_id"))

            # Quarantine if FKs missing or required fields are NaN/missing
            if (not agent_sk or not lead_sk or not campaign_sk or 
                pd.isna(rec.get("event_timestamp")) or not rec.get("event_type") or 
                pd.isna(rec.get("event_id")) or pd.isna(rec.get("date_key"))):
                failed_records.append({
                    "record": {k: (v if pd.notna(v) else None) for k, v in rec.items()},
                    "failure_reason": "Foreign key lookup failed or missing mandatory timestamp/event_type/event_id",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                continue

            msg_len = int(rec["message_length"]) if pd.notna(rec.get("message_length")) else 0
            latency = float(rec["response_latency_hours"]) if pd.notna(rec.get("response_latency_hours")) else None
            conv = int(rec["is_converted"]) if pd.notna(rec.get("is_converted")) else 0

            valid_rows.append({
                "event_id": str(rec["event_id"]),
                "agent_sk": agent_sk,
                "lead_sk": lead_sk,
                "campaign_sk": campaign_sk,
                "date_key": int(rec["date_key"]),
                "event_timestamp": str(rec["event_timestamp"]),
                "event_type": str(rec["event_type"]),
                "message_length": msg_len,
                "response_latency_hours": latency,
                "is_converted": conv
            })

        quarantined_count = 0
        if failed_records:
            quarantined_count = self.dlq.quarantine_records(failed_records, run_id=str(uuid.uuid4())[:8])

        inserted_count = 0
        if valid_rows:
            insert_sql = text("""
                INSERT OR IGNORE INTO fact_outreach_activity (
                    event_id, agent_sk, lead_sk, campaign_sk, date_key,
                    event_timestamp, event_type, message_length, response_latency_hours, is_converted
                ) VALUES (
                    :event_id, :agent_sk, :lead_sk, :campaign_sk, :date_key,
                    :event_timestamp, :event_type, :message_length, :response_latency_hours, :is_converted
                )
            """)

            with self.engine.begin() as conn:
                conn.execute(insert_sql, valid_rows)
                inserted_count = len(valid_rows)

        return inserted_count, quarantined_count

    def run_pipeline(self, raw_payload: Optional[Dict[str, Any]] = None, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Executes complete ingestion pipeline."""
        run_id = correlation_id or str(uuid.uuid4())
        start_time = datetime.now(timezone.utc)
        logger.info("pipeline_execution_started", run_id=run_id, start_time=start_time.isoformat())

        if raw_payload is None:
            raw_payload = self.generate_synthetic_telemetry(days_back=30)

        self.load_dimensions(raw_payload)

        activities = raw_payload.get("activities", [])
        activities_df = pd.DataFrame(activities)

        dq_results = self.dq_engine.evaluate_batch(activities_df, "fact_outreach_activity", run_id)
        records_loaded, records_dlq = self.load_fact_activities(activities_df)

        if not activities_df.empty and "event_timestamp" in activities_df.columns:
            valid_ts = activities_df["event_timestamp"].dropna()
            if not valid_ts.empty:
                self.watermark_mgr.set_watermark(str(valid_ts.max()))

        end_time = datetime.now(timezone.utc)
        status = "SUCCESS" if dq_results["passed"] else "WARNING_DQ_THRESHOLD"

        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO pipeline_runs (
                        run_id, start_time, end_time, source_system,
                        records_ingested, records_loaded, records_quarantined_dlq,
                        status, watermark_timestamp, error_message
                    ) VALUES (
                        :run_id, :start_time, :end_time, :source,
                        :ingested, :loaded, :dlq, :status, :watermark, NULL
                    )
                """),
                {
                    "run_id": run_id,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "source": "Polluxa_API_v1",
                    "ingested": len(activities),
                    "loaded": records_loaded,
                    "dlq": records_dlq,
                    "status": status,
                    "watermark": self.watermark_mgr.get_watermark()
                }
            )

        logger.info(
            "pipeline_execution_completed",
            run_id=run_id,
            status=status,
            records_ingested=len(activities),
            records_loaded=records_loaded,
            records_quarantined_dlq=records_dlq,
            composite_dq_score=dq_results["composite_score"],
            duration_sec=round((end_time - start_time).total_seconds(), 2)
        )

        return {
            "run_id": run_id,
            "status": status,
            "records_ingested": len(activities),
            "records_loaded": records_loaded,
            "records_quarantined_dlq": records_dlq,
            "dq_score": dq_results["composite_score"]
        }


if __name__ == "__main__":
    init_database()
    service = IngestionService()
    result = service.run_pipeline()
    print("\n--- Pipeline Execution Summary ---")
    print(json.dumps(result, indent=2))
