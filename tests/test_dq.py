"""
Data Quality Engine Unit Tests (Part 4)
"""

import os
import sys
import pandas as pd
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pipeline.data_quality import DataQualityEngine


@pytest.fixture
def dq_engine(test_db):
    engine, _ = test_db
    return DataQualityEngine(engine=engine)


def test_completeness_check(dq_engine):
    # Perfect data
    df_clean = pd.DataFrame([{"col1": "A", "col2": "B"}, {"col1": "C", "col2": "D"}])
    score, missing, _ = dq_engine.check_completeness(df_clean, ["col1", "col2"])
    assert score == 100.0
    assert missing == 0

    # Data with missing values
    df_dirty = pd.DataFrame([{"col1": None, "col2": "B"}, {"col1": "C", "col2": None}])
    score_dirty, missing_dirty, _ = dq_engine.check_completeness(df_dirty, ["col1", "col2"])
    assert score_dirty == 50.0
    assert missing_dirty == 2


def test_uniqueness_check(dq_engine):
    # Unique keys
    df_unique = pd.DataFrame([{"id": "1"}, {"id": "2"}, {"id": "3"}])
    score, dupes, _ = dq_engine.check_uniqueness(df_unique, "id")
    assert score == 100.0
    assert dupes == 0

    # Duplicate keys
    df_dupe = pd.DataFrame([{"id": "1"}, {"id": "1"}, {"id": "2"}])
    score_dupe, dupes_cnt, _ = dq_engine.check_uniqueness(df_dupe, "id")
    assert score_dupe < 100.0
    assert dupes_cnt == 2


def test_validity_check(dq_engine):
    # Valid event types
    df_valid = pd.DataFrame([{"event_type": "INVITE_SENT"}, {"event_type": "INVITE_ACCEPTED"}])
    score, invalid_cnt, _ = dq_engine.check_validity(df_valid)
    assert score == 100.0
    assert invalid_cnt == 0

    # Invalid event types
    df_invalid = pd.DataFrame([{"event_type": "INVITE_SENT"}, {"event_type": "HACK_ATTEMPT"}])
    score_inv, invalid_cnt_inv, _ = dq_engine.check_validity(df_invalid)
    assert score_inv == 50.0
    assert invalid_cnt_inv == 1
