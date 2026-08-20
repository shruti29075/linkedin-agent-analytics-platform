-- ============================================================================
-- End-to-End LinkedIn Agent Analytics Platform
-- Star Schema Database DDL (Part 3)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Date Dimension (Conformed Dimension)
-- Grain: One record per calendar date
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_date (
    date_key INTEGER PRIMARY KEY, -- Format: YYYYMMDD (e.g., 20260819)
    full_date DATE NOT NULL UNIQUE,
    day_of_week INTEGER NOT NULL, -- 1 = Monday, 7 = Sunday
    day_name VARCHAR(10) NOT NULL,
    month_number INTEGER NOT NULL,
    month_name VARCHAR(10) NOT NULL,
    quarter INTEGER NOT NULL,
    year INTEGER NOT NULL,
    is_weekend INTEGER NOT NULL DEFAULT 0 -- 1 = True, 0 = False
);

-- ----------------------------------------------------------------------------
-- 2. Agent Dimension (SCD Type 2 Enabled)
-- Grain: One record per agent version / status change
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_agent (
    agent_sk INTEGER PRIMARY KEY AUTOINCREMENT, -- Surrogate Key
    agent_id VARCHAR(64) NOT NULL,              -- Natural Key
    agent_name VARCHAR(128) NOT NULL,
    linkedin_profile_url VARCHAR(255),
    account_age_tier VARCHAR(32) NOT NULL,      -- '< 1 Month', '1 Month', '2–6 Months', '6–12 Months', '1+ Year'
    risk_classification VARCHAR(32) NOT NULL,   -- 'Very High Risk', 'High Risk', 'Moderate Risk', 'Low Risk', 'Minimal Risk'
    daily_invite_ceiling INTEGER NOT NULL,      -- Hard limit from Part 1 SOP matrix
    daily_message_ceiling INTEGER NOT NULL,     -- Hard limit from Part 1 SOP matrix
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', -- 'ACTIVE', 'PAUSED', 'GHOSTED'
    effective_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP,
    is_current INTEGER NOT NULL DEFAULT 1       -- 1 = Current record, 0 = Historical record
);

-- ----------------------------------------------------------------------------
-- 3. Lead Dimension
-- Grain: One record per target prospect / lead
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_lead (
    lead_sk INTEGER PRIMARY KEY AUTOINCREMENT,  -- Surrogate Key
    lead_id VARCHAR(64) NOT NULL UNIQUE,        -- Natural Key
    first_name VARCHAR(64),
    last_name VARCHAR(64),
    job_title VARCHAR(128),
    company_name VARCHAR(128),
    industry VARCHAR(64),
    location VARCHAR(128),
    target_segment VARCHAR(64),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 4. Campaign Dimension
-- Grain: One record per outreach campaign
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_campaign (
    campaign_sk INTEGER PRIMARY KEY AUTOINCREMENT, -- Surrogate Key
    campaign_id VARCHAR(64) NOT NULL UNIQUE,       -- Natural Key
    campaign_name VARCHAR(128) NOT NULL,
    target_segment VARCHAR(64),
    daily_budget DECIMAL(10, 2) DEFAULT 0.00,
    start_date DATE NOT NULL,
    end_date DATE,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE'   -- 'ACTIVE', 'COMPLETED', 'PAUSED'
);

-- ----------------------------------------------------------------------------
-- 5. Fact Outreach Activity (Transactional Fact)
-- Grain: One record per individual outreach event / interaction
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_outreach_activity (
    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id VARCHAR(64) NOT NULL UNIQUE,       -- Natural Key for Idempotency
    agent_sk INTEGER NOT NULL,
    lead_sk INTEGER NOT NULL,
    campaign_sk INTEGER NOT NULL,
    date_key INTEGER NOT NULL,
    event_timestamp TIMESTAMP NOT NULL,
    event_type VARCHAR(32) NOT NULL,            -- 'INVITE_SENT', 'INVITE_ACCEPTED', 'MESSAGE_SENT', 'REPLY_RECEIVED', 'CONNECTION_WITHDRAWN'
    message_length INTEGER DEFAULT 0,
    response_latency_hours DECIMAL(8, 2) DEFAULT NULL,
    is_converted INTEGER NOT NULL DEFAULT 0,    -- 1 if lead booked meeting / replied positively
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_sk) REFERENCES dim_agent(agent_sk),
    FOREIGN KEY (lead_sk) REFERENCES dim_lead(lead_sk),
    FOREIGN KEY (campaign_sk) REFERENCES dim_campaign(campaign_sk),
    FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
);

-- ----------------------------------------------------------------------------
-- 6. Fact Daily Agent Metric (Periodic Snapshot Fact)
-- Grain: One record per agent per calendar day
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_daily_agent_metric (
    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_sk INTEGER NOT NULL,
    date_key INTEGER NOT NULL,
    invites_sent INTEGER NOT NULL DEFAULT 0,
    invites_accepted INTEGER NOT NULL DEFAULT 0,
    messages_sent INTEGER NOT NULL DEFAULT 0,
    replies_received INTEGER NOT NULL DEFAULT 0,
    acceptance_rate DECIMAL(5, 4) DEFAULT 0.0000,
    reply_rate DECIMAL(5, 4) DEFAULT 0.0000,
    invite_limit_utilization_pct DECIMAL(5, 2) DEFAULT 0.00,
    message_limit_utilization_pct DECIMAL(5, 2) DEFAULT 0.00,
    anomaly_score DECIMAL(6, 3) DEFAULT 0.000,    -- Output from Part 5 Risk Model
    risk_level VARCHAR(32) NOT NULL DEFAULT 'NORMAL', -- 'NORMAL', 'WARNING', 'CRITICAL'
    recommended_invite_capacity INTEGER NOT NULL, -- Part 5 optimization result
    recommended_message_capacity INTEGER NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent_sk, date_key),
    FOREIGN KEY (agent_sk) REFERENCES dim_agent(agent_sk),
    FOREIGN KEY (date_key) REFERENCES dim_date(date_key)
);

-- ----------------------------------------------------------------------------
-- 7. Data Quality Audit Log (Observability & Governance)
-- Grain: One record per data quality dimension check per pipeline run
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dq_audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_run_id VARCHAR(64) NOT NULL,
    check_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    table_name VARCHAR(64) NOT NULL,
    dimension VARCHAR(32) NOT NULL,              -- 'COMPLETENESS', 'UNIQUENESS', 'VALIDITY', 'TIMELINESS', 'REFERENTIAL_INTEGRITY'
    records_evaluated INTEGER NOT NULL,
    records_failed INTEGER NOT NULL,
    dimension_score DECIMAL(5, 2) NOT NULL,      -- 0.00 to 100.00
    composite_score DECIMAL(5, 2) NOT NULL,      -- Overall run score
    passed INTEGER NOT NULL DEFAULT 1,           -- 1 = Pass, 0 = Fail
    details TEXT
);

-- ----------------------------------------------------------------------------
-- 8. Pipeline Execution Metadata (Run Tracking & Idempotency)
-- Grain: One record per ETL execution
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id VARCHAR(64) PRIMARY KEY,             -- Correlation UUID
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    source_system VARCHAR(64) NOT NULL,
    records_ingested INTEGER NOT NULL DEFAULT 0,
    records_loaded INTEGER NOT NULL DEFAULT 0,
    records_quarantined_dlq INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL,                 -- 'SUCCESS', 'FAILED', 'PARTIAL'
    watermark_timestamp TIMESTAMP,
    error_message TEXT
);

-- ----------------------------------------------------------------------------
-- Indexes for Performance
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_activity_agent_date ON fact_outreach_activity(agent_sk, date_key);
CREATE INDEX IF NOT EXISTS idx_activity_event_type ON fact_outreach_activity(event_type);
CREATE INDEX IF NOT EXISTS idx_daily_agent_date ON fact_daily_agent_metric(agent_sk, date_key);
CREATE INDEX IF NOT EXISTS idx_agent_id_current ON dim_agent(agent_id, is_current);
