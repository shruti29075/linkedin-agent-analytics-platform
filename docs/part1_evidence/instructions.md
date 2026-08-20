# Part 1 Evidence Pack: Integration Baseline (SOP Adherence)

This document contains the step-by-step execution log, configuration parameters, and screenshot evidence for **Part 1: The Integration Baseline**.

---

## 1. Declared Account Age Tier & Rate Limiting Parameters

- **Declared Profile Age**: `1+ Year` (or select `< 1 Month` / `1 Month` / `2–6 Months` / `6–12 Months` matching your account)
- **Assigned Risk Classification**: `Minimal Risk`
- **Daily Connection Invites Ceiling**: `30 invites/day`
- **Daily Messages Ceiling**: `60 messages/day`
- **Fact-Table Constraint**: Enforced in `dim_agent` and validated by `models/risk_model.py` to prevent algorithmic shadow-banning.

---

## 2. Seven-Step SOP Workflow Log & Evidence Screenshots

| Step | Portal Action Description | Status | Evidence Screenshot File |
| :--- | :--- | :--- | :--- |
| **Step 1** | Navigated to enterprise portal at `sales.polluxa.com` | Completed | `docs/part1_evidence/step1_environment_access.png` |
| **Step 2** | Account sign-up via Google SSO and navigation to ADD ONS $\to$ Integration | Completed | `docs/part1_evidence/step2_account_signup.png` |
| **Step 3** | Initiated connection protocol by selecting LinkedIn tab and clicking `+ Connect LinkedIn Account` | Completed | `docs/part1_evidence/step3_connect_linkedin.png` |
| **Step 4** | Input LinkedIn credentials securely via authentication modal | Completed | `docs/part1_evidence/step4_credential_provisioning.png` |
| **Step 5** | Authorized Multi-Factor Authentication (MFA) security challenge on mobile device | Completed | `docs/part1_evidence/step5_mfa_approval.png` |
| **Step 6** | Declared Account Age tier and confirmed daily invite/message limit parameters | Completed | `docs/part1_evidence/step6_agent_risk_config.png` |
| **Step 7** | Added target outreach leads and initiated automated outreach telemetry generation | Completed | `docs/part1_evidence/step7_operate_agent_live.png` |

---

## 3. Note on MFA Security Challenge & Handshake Observations

- **Authentication Protocol**: LinkedIn MFA utilizes push notifications to the user's primary mobile device.
- **Observations during Handshake**: The system displayed the *"Establishing secure connection..."* state and completed the handshake in under 15 seconds once approved on mobile.
- **Session Stability**: Session cookie token was securely provisioned into the agent environment without exposing raw passwords in application source code.
