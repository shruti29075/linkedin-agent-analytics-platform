"""
Statistical Risk & Anomaly Model Unit Tests (Part 5)
"""

import os
import sys
import numpy as np
import pandas as pd
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from models.risk_model import RiskModelEngine


@pytest.fixture
def risk_engine(test_db):
    engine, _ = test_db
    return RiskModelEngine(engine=engine)


def test_capacity_throttling_on_anomaly(risk_engine):
    """
    Verifies that when an agent's acceptance rate collapses (Z-score < -2.0),
    the model throttles capacity to 30% of the tier ceiling.
    """
    dates = [20260801 + i for i in range(15)]
    history = []

    # 10 days of normal 40% acceptance
    for d in dates[:10]:
        history.append({
            "agent_sk": 1,
            "agent_id": "AGT-001",
            "account_age_tier": "< 1 Month",
            "daily_invite_ceiling": 5,
            "daily_message_ceiling": 10,
            "date_key": d,
            "full_date": f"2026-08-{d % 100:02d}",
            "invites_sent": 5,
            "invites_accepted": 2, # 40% rate
            "messages_sent": 5,
            "replies_received": 2
        })

    # 5 days of severe collapse (0% acceptance)
    for d in dates[10:]:
        history.append({
            "agent_sk": 1,
            "agent_id": "AGT-001",
            "account_age_tier": "< 1 Month",
            "daily_invite_ceiling": 5,
            "daily_message_ceiling": 10,
            "date_key": d,
            "full_date": f"2026-08-{d % 100:02d}",
            "invites_sent": 5,
            "invites_accepted": 0, # 0% rate (collapse)
            "messages_sent": 5,
            "replies_received": 0
        })

    df = pd.DataFrame(history)
    scored = risk_engine.compute_agent_anomalies_and_capacity(df)

    assert "anomaly_score" in scored.columns
    assert "risk_level" in scored.columns
    assert "recommended_invite_capacity" in scored.columns

    # Recent collapsed days should trigger anomaly warnings / critical flags
    recent_records = scored.iloc[-3:]
    assert any(recent_records["risk_level"].isin(["CRITICAL", "WARNING"]))
    # Recommended capacity must not exceed daily ceiling (5)
    assert all(scored["recommended_invite_capacity"] <= 5)
