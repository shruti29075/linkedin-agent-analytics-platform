# Enterprise Data Dictionary: LinkedIn Agent Analytics Platform

This data dictionary documents the Star Schema dimensional model, table grains, surrogate keys, slowly changing dimension strategies, and business definitions for all warehouse entities.

---

## 1. Dimensional Model Overview

```
                      +-------------------+
                      |     dim_date      |
                      +-------------------+
                               | 1
                               |
                               | *
+-------------------+ *      +--------------------------+      * +--------------------+
|     dim_agent     |--------|  fact_outreach_activity  |--------|     dim_campaign   |
+-------------------+ 1      +--------------------------+ 1      +--------------------+
         | 1                           | *
         |                             |
         | *                           | 1
+--------------------------+ +-------------------+
| fact_daily_agent_metric  | |     dim_lead      |
+--------------------------+ +-------------------+
```

---

## 2. Table Specifications

### 2.1 `dim_agent` (Agent Dimension)
- **Business Description**: Stores configuration, risk tier, and status for automated LinkedIn sales agents.
- **Grain**: One row per agent version (SCD Type 2 enabled to capture status and capacity changes over time).
- **Primary Key**: `agent_sk` (Surrogate Key, Auto-incremented Integer)
- **Natural Key**: `agent_id` (System UUID/String)

| Column Name | Data Type | Nullable | Description & Business Rules |
| :--- | :--- | :--- | :--- |
| `agent_sk` | INTEGER | NO | Surrogate primary key. |
| `agent_id` | VARCHAR(64) | NO | Natural identifier assigned by Polluxa system. |
| `agent_name` | VARCHAR(128) | NO | Display name / LinkedIn profile alias. |
| `linkedin_profile_url` | VARCHAR(255) | YES | URL of the connected LinkedIn account. |
| `account_age_tier` | VARCHAR(32) | NO | Declared profile age tier: `< 1 Month`, `1 Month`, `2–6 Months`, `6–12 Months`, `1+ Year`. |
| `risk_classification` | VARCHAR(32) | NO | Risk level: `Very High Risk`, `High Risk`, `Moderate Risk`, `Low Risk`, `Minimal Risk`. |
| `daily_invite_ceiling` | INTEGER | NO | Maximum allowed daily invitations from Part 1 SOP matrix. |
| `daily_message_ceiling` | INTEGER | NO | Maximum allowed daily messages from Part 1 SOP matrix. |
| `status` | VARCHAR(32) | NO | Operational status: `ACTIVE`, `PAUSED`, `GHOSTED`. |
| `effective_date` | TIMESTAMP | NO | Start timestamp of this version (SCD Type 2). |
| `end_date` | TIMESTAMP | YES | Expiry timestamp of this version (NULL if current). |
| `is_current` | INTEGER | NO | 1 if active current version, 0 if historical. |

---

### 2.2 `dim_lead` (Lead Dimension)
- **Business Description**: Stores target prospects and recipients of outreach.
- **Grain**: One row per unique LinkedIn lead.
- **Primary Key**: `lead_sk` (Surrogate Key, Auto-incremented Integer)
- **Natural Key**: `lead_id` (Unique String)

| Column Name | Data Type | Nullable | Description & Business Rules |
| :--- | :--- | :--- | :--- |
| `lead_sk` | INTEGER | NO | Surrogate primary key. |
| `lead_id` | VARCHAR(64) | NO | Natural identifier from LinkedIn or CRM. |
| `first_name` | VARCHAR(64) | YES | Lead first name. |
| `last_name` | VARCHAR(64) | YES | Lead last name. |
| `job_title` | VARCHAR(128) | YES | Current professional title (e.g., 'VP of Sales'). |
| `company_name` | VARCHAR(128) | YES | Current employer / organization. |
| `industry` | VARCHAR(64) | YES | Industry sector (e.g., 'SaaS', 'FinTech'). |
| `location` | VARCHAR(128) | YES | Geographic location. |
| `target_segment` | VARCHAR(64) | YES | Market segment (e.g., 'Enterprise', 'SMB'). |
| `created_at` | TIMESTAMP | NO | Timestamp when record was created in staging. |

---

### 2.3 `dim_campaign` (Campaign Dimension)
- **Business Description**: Defines outreach initiatives, ICP targeting, and budget allocations.
- **Grain**: One row per marketing/sales campaign.
- **Primary Key**: `campaign_sk` (Surrogate Key)
- **Natural Key**: `campaign_id` (Unique String)

| Column Name | Data Type | Nullable | Description & Business Rules |
| :--- | :--- | :--- | :--- |
| `campaign_sk` | INTEGER | NO | Surrogate primary key. |
| `campaign_id` | VARCHAR(64) | NO | Unique campaign code. |
| `campaign_name` | VARCHAR(128) | NO | Human-readable campaign title. |
| `target_segment` | VARCHAR(64) | YES | Target audience segment. |
| `daily_budget` | DECIMAL(10,2) | NO | Daily allocated outreach budget in USD. |
| `start_date` | DATE | NO | Campaign launch date. |
| `end_date` | DATE | YES | Campaign scheduled conclusion date. |
| `status` | VARCHAR(32) | NO | Status: `ACTIVE`, `COMPLETED`, `PAUSED`. |

---

### 2.4 `dim_date` (Conformed Date Dimension)
- **Business Description**: Standard enterprise calendar dimension enabling time intelligence.
- **Grain**: One row per calendar day.
- **Primary Key**: `date_key` (Format: `YYYYMMDD`)

| Column Name | Data Type | Nullable | Description & Business Rules |
| :--- | :--- | :--- | :--- |
| `date_key` | INTEGER | NO | Smart integer key (e.g., 20260819). |
| `full_date` | DATE | NO | ISO standard date (`YYYY-MM-DD`). |
| `day_of_week` | INTEGER | NO | 1 (Monday) through 7 (Sunday). |
| `day_name` | VARCHAR(10) | NO | Monday, Tuesday, Wednesday, etc. |
| `month_number` | INTEGER | NO | 1 through 12. |
| `month_name` | VARCHAR(10) | NO | January, February, etc. |
| `quarter` | INTEGER | NO | 1, 2, 3, or 4. |
| `year` | INTEGER | NO | 4-digit calendar year. |
| `is_weekend` | INTEGER | NO | Flag: 1 for Saturday/Sunday, 0 for weekdays. |

---

### 2.5 `fact_outreach_activity` (Transactional Fact Table)
- **Business Description**: Captures every individual touchpoint and event executed by an agent.
- **Grain**: One row per discrete event (invite, accept, message, reply, withdrawal).
- **Primary Key**: `activity_id` (Surrogate Key)
- **Natural Key**: `event_id` (Enforces idempotency)

| Column Name | Data Type | Nullable | Description & Business Rules |
| :--- | :--- | :--- | :--- |
| `activity_id` | INTEGER | NO | Auto-incrementing surrogate key. |
| `event_id` | VARCHAR(64) | NO | Unique event ID from API source. |
| `agent_sk` | INTEGER | NO | FK referencing `dim_agent(agent_sk)`. |
| `lead_sk` | INTEGER | NO | FK referencing `dim_lead(lead_sk)`. |
| `campaign_sk` | INTEGER | NO | FK referencing `dim_campaign(campaign_sk)`. |
| `date_key` | INTEGER | NO | FK referencing `dim_date(date_key)`. |
| `event_timestamp`| TIMESTAMP | NO | Exact UTC timestamp of the outreach event. |
| `event_type` | VARCHAR(32) | NO | `INVITE_SENT`, `INVITE_ACCEPTED`, `MESSAGE_SENT`, `REPLY_RECEIVED`, `CONNECTION_WITHDRAWN`. |
| `message_length`| INTEGER | NO | Character count of message sent or received. |
| `response_latency_hours`| DECIMAL(8,2)| YES | Hours elapsed between preceding message and reply. |
| `is_converted` | INTEGER | NO | 1 if event resulted in conversion/meeting, 0 otherwise. |
| `created_at` | TIMESTAMP | NO | Timestamp of warehouse insertion. |

---

### 2.6 `fact_daily_agent_metric` (Periodic Snapshot Fact Table)
- **Business Description**: Aggregates daily agent performance, capacity utilization, and statistical risk scores.
- **Grain**: One row per agent per calendar day.
- **Primary Key**: `metric_id` (Surrogate Key)
- **Unique Constraint**: (`agent_sk`, `date_key`)

| Column Name | Data Type | Nullable | Description & Business Rules |
| :--- | :--- | :--- | :--- |
| `metric_id` | INTEGER | NO | Auto-incrementing surrogate key. |
| `agent_sk` | INTEGER | NO | FK referencing `dim_agent(agent_sk)`. |
| `date_key` | INTEGER | NO | FK referencing `dim_date(date_key)`. |
| `invites_sent` | INTEGER | NO | Count of connection invites sent today. |
| `invites_accepted`| INTEGER | NO | Count of invites accepted today. |
| `messages_sent`| INTEGER | NO | Count of direct messages sent today. |
| `replies_received`| INTEGER | NO | Count of prospect replies received today. |
| `acceptance_rate`| DECIMAL(5,4)| NO | `invites_accepted / NULLIF(invites_sent, 0)`. |
| `reply_rate` | DECIMAL(5,4)| NO | `replies_received / NULLIF(messages_sent, 0)`. |
| `invite_limit_utilization_pct` | DECIMAL(5,2) | NO | `(invites_sent / daily_invite_ceiling) * 100`. |
| `message_limit_utilization_pct`| DECIMAL(5,2) | NO | `(messages_sent / daily_message_ceiling) * 100`. |
| `anomaly_score`| DECIMAL(6,3)| NO | Statistical Z-score deviation from Part 5 model. |
| `risk_level` | VARCHAR(32) | NO | `NORMAL` (Z > -1.5), `WARNING` (-2.0 <= Z <= -1.5), `CRITICAL` (Z < -2.0). |
| `recommended_invite_capacity` | INTEGER | NO | Optimized safe invite volume for next day. |
| `recommended_message_capacity`| INTEGER | NO | Optimized safe message volume for next day. |
| `updated_at` | TIMESTAMP | NO | Last calculation timestamp. |

---

### 2.7 `dq_audit_log` (Data Quality Audit Log)
- **Business Description**: Tracks quality score metrics across the 5 core dimensions for every pipeline run.
- **Grain**: One row per dimension check per pipeline execution.

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| `audit_id` | INTEGER | Auto-incrementing primary key. |
| `pipeline_run_id` | VARCHAR(64) | Correlation ID linking check to ETL run. |
| `check_timestamp` | TIMESTAMP | Execution timestamp. |
| `table_name` | VARCHAR(64) | Name of table checked. |
| `dimension` | VARCHAR(32) | `COMPLETENESS`, `UNIQUENESS`, `VALIDITY`, `TIMELINESS`, `REFERENTIAL_INTEGRITY`. |
| `records_evaluated` | INTEGER | Total records inspected. |
| `records_failed` | INTEGER | Number of records violating rule. |
| `dimension_score` | DECIMAL(5,2) | Percentage score (0.00 to 100.00). |
| `composite_score` | DECIMAL(5,2) | Weighted overall score across all 5 dimensions. |
| `passed` | INTEGER | 1 if composite score >= pass threshold (95.0), else 0. |
| `details` | TEXT | Specific violation breakdown JSON. |

---

### 2.8 `pipeline_runs` (Pipeline Execution Metadata)
- **Business Description**: Audit ledger of all batch ingestion runs for observability, SLA tracking, and idempotency.
- **Grain**: One row per pipeline execution.

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| `run_id` | VARCHAR(64) | UUID correlation ID. |
| `start_time` | TIMESTAMP | Pipeline start timestamp. |
| `end_time` | TIMESTAMP | Pipeline finish timestamp. |
| `source_system` | VARCHAR(64) | Name of ingestion source (`Polluxa_API_v1`). |
| `records_ingested` | INTEGER | Raw records fetched from source. |
| `records_loaded` | INTEGER | Valid records loaded into warehouse. |
| `records_quarantined_dlq` | INTEGER | Invalid/malformed records routed to DLQ. |
| `status` | VARCHAR(32) | Execution status: `SUCCESS`, `FAILED`, `PARTIAL`. |
| `watermark_timestamp` | TIMESTAMP | High watermark timestamp recorded for incremental loads. |
| `error_message` | TEXT | Exception details if failed. |
