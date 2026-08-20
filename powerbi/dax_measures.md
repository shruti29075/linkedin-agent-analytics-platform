# Power BI DAX Measure Layer (Part 6)

This document contains production-grade, explicit DAX measures designed for the **LinkedIn Agent Analytics Platform**.
In accordance with Part 6 assessment requirements, all calculations are implemented via **explicit DAX measures** rather than implicit aggregations.

---

## 1. Core Outreach KPIs

### Total Invites Sent
```dax
Total Invites Sent = 
CALCULATE(
    COUNTROWS(fact_outreach_activity),
    fact_outreach_activity[event_type] = "INVITE_SENT"
)
```

### Total Invites Accepted
```dax
Total Invites Accepted = 
CALCULATE(
    COUNTROWS(fact_outreach_activity),
    fact_outreach_activity[event_type] = "INVITE_ACCEPTED"
)
```

### Acceptance Rate %
```dax
Acceptance Rate % = 
DIVIDE(
    [Total Invites Accepted],
    [Total Invites Sent],
    0
)
```

### Total Messages Sent
```dax
Total Messages Sent = 
CALCULATE(
    COUNTROWS(fact_outreach_activity),
    fact_outreach_activity[event_type] = "MESSAGE_SENT"
)
```

### Total Replies Received
```dax
Total Replies Received = 
CALCULATE(
    COUNTROWS(fact_outreach_activity),
    fact_outreach_activity[event_type] = "REPLY_RECEIVED"
)
```

### Reply Rate %
```dax
Reply Rate % = 
DIVIDE(
    [Total Replies Received],
    [Total Messages Sent],
    0
)
```

### Total Conversions
```dax
Total Conversions = 
CALCULATE(
    COUNTROWS(fact_outreach_activity),
    fact_outreach_activity[is_converted] = 1
)
```

### Overall Conversion Rate %
```dax
Overall Conversion Rate % = 
DIVIDE(
    [Total Conversions],
    [Total Invites Sent],
    0
)
```

---

## 2. Account Health & Limit Utilization

### Active Agents Count
```dax
Active Agents Count = 
CALCULATE(
    DISTINCTCOUNT(dim_agent[agent_sk]),
    dim_agent[status] = "ACTIVE",
    dim_agent[is_current] = 1
)
```

### Paused or Ghosted Agents Count
```dax
Paused or Ghosted Agents Count = 
CALCULATE(
    DISTINCTCOUNT(dim_agent[agent_sk]),
    dim_agent[status] IN {"PAUSED", "GHOSTED"},
    dim_agent[is_current] = 1
)
```

### Invite Capacity Utilization %
```dax
Invite Capacity Utilization % = 
VAR TotalSent = [Total Invites Sent]
VAR TotalCeiling = SUM(dim_agent[daily_invite_ceiling]) * DISTINCTCOUNT(dim_date[date_key])
RETURN
DIVIDE(TotalSent, TotalCeiling, 0)
```

### Message Capacity Utilization %
```dax
Message Capacity Utilization % = 
VAR TotalSent = [Total Messages Sent]
VAR TotalCeiling = SUM(dim_agent[daily_message_ceiling]) * DISTINCTCOUNT(dim_date[date_key])
RETURN
DIVIDE(TotalSent, TotalCeiling, 0)
```

---

## 3. Risk Intelligence & Statistical Anomalies

### Average Anomaly Z-Score
```dax
Average Anomaly Z-Score = 
AVERAGE(fact_daily_agent_metric[anomaly_score])
```

### Critical Risk Account Days
```dax
Critical Risk Account Days = 
CALCULATE(
    COUNTROWS(fact_daily_agent_metric),
    fact_daily_agent_metric[risk_level] = "CRITICAL"
)
```

### Warning Risk Account Days
```dax
Warning Risk Account Days = 
CALCULATE(
    COUNTROWS(fact_daily_agent_metric),
    fact_daily_agent_metric[risk_level] = "WARNING"
)
```

### Recommended Safe Invite Volume
```dax
Recommended Safe Invite Volume = 
SUM(fact_daily_agent_metric[recommended_invite_capacity])
```

### Throttled Capacity Variance %
```dax
Throttled Capacity Variance % = 
VAR Recommended = [Recommended Safe Invite Volume]
VAR Ceiling = SUM(dim_agent[daily_invite_ceiling]) * DISTINCTCOUNT(dim_date[date_key])
RETURN
DIVIDE(Ceiling - Recommended, Ceiling, 0)
```

---

## 4. Campaign ROI & Economics

### Total Campaign Budget
```dax
Total Campaign Budget = 
SUMX(
    dim_campaign,
    dim_campaign[daily_budget] * DISTINCTCOUNT(dim_date[date_key])
)
```

### Cost Per Invite ($)
```dax
Cost Per Invite = 
DIVIDE([Total Campaign Budget], [Total Invites Sent], 0)
```

### Cost Per Conversion ($)
```dax
Cost Per Conversion = 
DIVIDE([Total Campaign Budget], [Total Conversions], 0)
```

### Estimated Pipeline Value ($)
*(Assuming standard $5,000 enterprise deal value per meeting conversion)*
```dax
Estimated Pipeline Value = 
[Total Conversions] * 5000
```

### Campaign ROI Multiplier
```dax
Campaign ROI Multiplier = 
DIVIDE([Estimated Pipeline Value], [Total Campaign Budget], 0)
```

---

## 5. Power BI Relationships Guide

To connect the exported CSV files in Power BI Desktop Model View:

1. **`fact_outreach_activity`** $\to$ **`dim_agent`**: Join on `agent_sk` (Many-to-One `*:1`, Single direction)
2. **`fact_outreach_activity`** $\to$ **`dim_lead`**: Join on `lead_sk` (Many-to-One `*:1`, Single direction)
3. **`fact_outreach_activity`** $\to$ **`dim_campaign`**: Join on `campaign_sk` (Many-to-One `*:1`, Single direction)
4. **`fact_outreach_activity`** $\to$ **`dim_date`**: Join on `date_key` (Many-to-One `*:1`, Single direction)
5. **`fact_daily_agent_metric`** $\to$ **`dim_agent`**: Join on `agent_sk` (Many-to-One `*:1`, Single direction)
6. **`fact_daily_agent_metric`** $\to$ **`dim_date`**: Join on `date_key` (Many-to-One `*:1`, Single direction)
