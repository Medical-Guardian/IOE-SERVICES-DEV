# Engage360 Schema - Complete Table Usage Reference

**Comprehensive documentation of all 65 engage360 tables with usage details**

---

## Table of Contents

1. [Tables Actively Used (24)](#tables-actively-used)
2. [Tables Not Referenced (42)](#tables-not-referenced)
3. [Quick Reference Summary](#quick-reference-summary)
4. [Workflow Patterns](#workflow-patterns)

---

## Tables Actively Used

### Core Campaign & Member Tables

#### 1. **engage360.campaigns_enhanced**
**What it does:** Master campaign definition table storing all campaign configuration, scheduling rules, and operating parameters.
**Where used:** Partner Campaign Scheduler (campaign_qualifier.py), DTC Logic, Batch Sync Coordinator
**Files:** 6 Python files, 6 Markdown files
**Operations:** SELECT (campaign qualification, validation)
**Key columns:** campaign_id, org_id, name, campaign_type, status, contact_pref, call_days_of_week, operating_start_time, operating_end_time, operating_tz, scheduling_mode, frequency_value, frequency_unit, timezone_flag, max_care_gaps_per_member, audience_file_batch

---

#### 2. **engage360.campaign_call_configs_enhanced**
**What it does:** Stores Bland AI-specific configuration parameters (pathway_id, voice_id, webhook_url) for each campaign.
**Where used:** Partner Campaign Scheduler (campaign_qualifier.py), DTC Intro Call (config.py), Bland AI Webhook (config.py)
**Files:** 5 Python files, 2 Markdown files
**Operations:** SELECT (LEFT JOIN with campaigns_enhanced), Filter: config_status = 'active'
**Key columns:** config_id, campaign_id, call_type_id, config_status, bland_parameters_global (JSON with 18+ Bland AI parameters)

---

#### 3. **engage360.members**
**What it does:** Master member/patient table containing demographics, contact information, and care gap flags for outreach.
**Where used:** Member Eligibility Service (member_eligibility.py), DTC Logic (af_partner_logic.py), Batch Orchestrator
**Files:** 8 Python files, 5 Markdown files
**Operations:** SELECT (eligibility checks), INSERT/MERGE (CSV uploads)
**Key columns:** member_id, org_id, salesforce_account_number, first_name, last_name, primary_phone, timezone, Channel, language_pref, dob, gender, address_street, address_city, address_state, address_zip, 30+ care_gap_import_flags

---

#### 4. **engage360.member_campaign_enrollments_enhanced**
**What it does:** Junction table linking members to campaigns with enrollment status and attempt tracking for eligibility.
**Where used:** Member Eligibility (eligibility checks), Webhook Handler (status updates), DTC Logic (enrollment creation)
**Files:** 10+ Python files, 6 Markdown files
**Operations:** SELECT (eligibility), INSERT/MERGE (CSV processing), UPDATE (webhook status changes)
**Key columns:** enrollment_id, member_id, campaign_id, current_status ('OPTED_OUT', 'PENDING', 'ENROLLED', 'UNENROLLED'), last_attempt_ts, preferred_window, member_care_gap_parameters

---

#### 5. **engage360.orgs**
**What it does:** Organization/partner master table storing partner metadata and contact information.
**Where used:** DTC Logic (partner validation), Campaign Qualifier (org metadata lookup)
**Files:** 4 Python files, 3 Markdown files
**Operations:** SELECT (partner validation), LEFT JOIN (campaign queries)
**Key columns:** org_id, org_name, org_type, partner_contact_name

---

### Outreach Tracking Tables

#### 6. **engage360.outreach_batches**
**What it does:** Batch-level tracking for Bland AI call submissions with status, size, and reconciliation metadata.
**Where used:** All outreach functions (DTC, Partner Scheduler, Batch Sync, Status Tracker)
**Files:** 11+ Python files, 7 Markdown files
**Operations:** INSERT (batch creation), UPDATE (status updates, reconciliation), SELECT (stale batch detection)
**Key columns:** batch_id, campaign_id, vendor_batch_id, batch_size, batch_status ('Submitted', 'In Progress', 'Completed', 'Failed'), submitted_ts, total_calls_completed, total_calls_failed, last_status_check_ts, api_reconciled

---

#### 7. **engage360.outreach_attempts**
**What it does:** Individual call attempt records (one per member per call) with disposition and outcome tracking.
**Where used:** Member Eligibility (frequency checks), Webhook Handler (disposition updates), All outreach functions
**Files:** 10+ Python files, 6 Markdown files
**Operations:** INSERT (attempt creation), UPDATE (webhook updates with call results), SELECT (frequency protection queries)
**Key columns:** attempt_id, enrollment_id, batch_id, vendor_session_id, disposition ('Completed', 'Pending', 'Failed', 'NoAnswer'), duration_sec, response_summary, next_action, attempt_ts, status_updated_ts

---

#### 8. **engage360.bland_call_logs**
**What it does:** Primary call log table storing complete Bland AI call data for audit trail. As of 2025-01-03, raw webhook JSON moved to separate bland_raw_response table for optimization.
**Where used:** Bland AI Webhook Handler (database_orchestrator.py)
**Files:** 3 Python files, 3 Markdown files
**Operations:** INSERT (every webhook call creates one record)
**Key columns:** call_log_id, from_number, price, end_at, status, call_id, summary, analysis, batch_id, metadata, transcripts, recording_url, disposition_tag, raw_bland_response (NULL after 2025-01-03) (32 fields total)
**Note:** New records insert NULL for raw_bland_response; raw webhook JSON now stored in bland_raw_response table.

---

#### 9. **engage360.bland_raw_response**
**What it does:** Stores complete raw Bland AI webhook JSON payloads separately from bland_call_logs to optimize main table size. Contains full audit trail of original webhook responses.
**Where used:** Bland AI Webhook Handler (database_orchestrator.py)
**Files:** 1 Python file
**Operations:** INSERT (one record per webhook call, atomic transaction with bland_call_logs)
**Key columns:** raw_response_id, call_id (FK to bland_call_logs), raw_response (NVARCHAR(MAX) JSON payload 5-50KB), created_at
**Purpose:** Separation of large JSON blobs from main call logs table for improved query performance and storage optimization.
**Relationship:** 1:1 with bland_call_logs via call_id (foreign key with CASCADE DELETE)

---

### Member Related Tables

#### 10. **engage360.member_devices**
**What it does:** Device information table storing Medical Guardian device phone numbers and callability status for members.
**Where used:** Member Eligibility (device phone lookup), DTC Logic (device data insertion)
**Files:** 4 Python files, 3 Markdown files
**Operations:** LEFT JOIN (eligibility queries with is_device_callable filter), INSERT/MERGE (CSV processing)
**Key columns:** device_id, member_id, device_phone_number, is_device_callable, device_udi, device_name

---

#### 11. **engage360.member_enrollment_status_history**
**What it does:** Audit log table tracking all enrollment status transitions with timestamp, source, and duration for compliance.
**Where used:** DTC Logic (status change logging), Webhook Handler (call outcome status changes)
**Files:** 3 Python files, 4 Markdown files
**Operations:** INSERT (every status change creates history record), SELECT (check existing history)
**Key columns:** history_id, member_id, campaign_id, previous_status, new_status, change_timestamp, change_source ('CSV_PROCESSING', 'WEBHOOK', 'MANUAL'), change_details, duration_since_last_change_hours

---

### Partner Campaign Tables

#### 12. **engage360.partner_file_processing_log**
**What it does:** File-level tracking table for partner campaign CSV uploads with processing status and row counts.
**Where used:** Partner Logic (af_partner_logic.py)
**Files:** 1 Python file
**Operations:** INSERT (processing start), UPDATE (processing end with final status and counts)
**Key columns:** file_processing_id, file_name, original_file_path, final_file_path, file_size_bytes, partner_name, campaign_name_source, processing_status, processing_start_time, processing_end_time, total_rows_in_file, valid_rows_count, invalid_rows_count, warning_rows_count

---

#### 13. **engage360.partner_row_validation_results**
**What it does:** Row-level validation summary table for partner campaign CSV files with error counts and validation status.
**Where used:** Partner Logic (af_partner_logic.py)
**Files:** 1 Python file
**Operations:** INSERT (one record per CSV row)
**Key columns:** result_id, file_processing_id, row_number, validation_status ('Valid', 'Invalid', 'Warning'), total_errors_count, total_warnings_count, partner_name, campaign_name_source, salesforce_account_number, active_care_gaps (JSON), healthcare_member_id

---

#### 14. **engage360.partner_validation_error_details_file**
**What it does:** File-level validation error details table for schema, filename, and structural errors.
**Where used:** Partner Logic (af_partner_logic.py)
**Files:** 1 Python file
**Operations:** INSERT (one record per file-level error)
**Key columns:** error_id, file_processing_id, error_category, error_type, error_field, error_message, error_value, expected_value, severity

---

#### 15. **engage360.partner_validation_error_details_row**
**What it does:** Row-level validation error details table tracking field-specific validation failures with severity levels.
**Where used:** Partner Logic (af_partner_logic.py)
**Files:** 1 Python file
**Operations:** INSERT (one record per row-level error)
**Key columns:** error_id, file_processing_id, row_number, error_category, error_type, error_field, error_message, error_value, expected_value, severity ('Error', 'Warning', 'Info')

---

#### 16. **engage360.partner_file_care_gap_stats**
**What it does:** Care gap statistics aggregation table tracking distribution of care gaps in uploaded partner campaign files.
**Where used:** Partner Logic (af_partner_logic.py)
**Files:** 1 Python file
**Operations:** INSERT (one record per care gap per file)
**Key columns:** stats_id, file_processing_id, care_gap_name, active_member_count, total_member_count

---

### Reference Tables

#### 17. **engage360.care_gaps**
**What it does:** Master reference table for valid care gap flags mapping import flags to completion flags.
**Where used:** Partner Logic (af_partner_logic.py - CareGapsValidator), Batch Orchestrator (care_gap_mapper.py)
**Files:** 2 Python files, 1 Markdown file
**Operations:** SELECT (load active care gaps on initialization for validation)
**Key columns:** care_gap_id, csv_import_flag_name, completion_flag_name, care_gap_name, priority, is_active

---

### System Tables

#### 18. **engage360.system_locks**
**What it does:** Distributed locking table preventing concurrent operations for timer-triggered functions (batch reconciliation).
**Where used:** Batch Sync Coordinator (batch_sync_coordinator.py)
**Files:** 2 Python files, 2 Markdown files
**Operations:** INSERT (acquire lock), DELETE (release lock or clean expired locks), SELECT (check lock existence)
**Key columns:** lock_id, lock_name, lock_expiry, locked_by, created_ts

---

#### 19. **engage360.error_log**
**What it does:** General error logging table for fallback error tracking across all functions.
**Where used:** Bland AI Webhook config (utils/config.py)
**Files:** 1 Python file
**Operations:** Referenced as constant (ERROR_LOG_TABLE = "engage360.error_log"), not actively used
**Key columns:** error_id, error_timestamp, error_source, error_message, error_details

---

### Analysis Tables

#### 20. **engage360.analysis_queue_status**
**What it does:** Analysis job submission tracking table for Service Bus queue status (call transcripts/summaries analysis).
**Where used:** Bland AI Webhook (database_orchestrator.py)
**Files:** 3 Python files, 1 Markdown file
**Operations:** INSERT (log queue submission), UPDATE (update status to PENDING or FAILED)
**Key columns:** queue_status_id, call_log_id, analysis_type, processing_status ('SUBMITTING', 'PENDING', 'FAILED'), queue_message_id, submitted_ts

---

### Staging Tables (Documentation Only)

#### 21. **engage360.dtc_staging_dev**
**What it does:** Staging table for DTC CSV uploads before processing into members and enrollments tables.
**Where used:** CSV Testing Guide documentation
**Files:** 1 Markdown file (CSV_TESTING_GUIDE.md)
**Operations:** Documentation reference only (not in active Python code)
**Key columns:** Referenced in docs but no active usage

---

#### 22. **engage360.bland_sms_communications**
**What it does:** SMS tracking table for Bland AI SMS communications (potential future use).
**Where used:** Referenced in documentation
**Files:** Documentation only
**Operations:** Not implemented in current codebase
**Key columns:** Unknown (not actively used)

---

#### 23. **engage360.attempt_audit_log**
**What it does:** Call attempt auditing table for detailed attempt logging (not currently implemented).
**Where used:** Referenced in documentation
**Files:** Documentation only
**Operations:** Not implemented in current codebase
**Key columns:** Unknown (not actively used)

---

#### 24. **engage360.behavioral_readiness**
**What it does:** Member behavioral readiness scoring table for contact prioritization (not currently implemented).
**Where used:** Referenced in documentation
**Files:** Documentation only
**Operations:** Not implemented in current codebase
**Key columns:** Unknown (not actively used)

---

## Tables Not Referenced

The following 42 tables exist in the engage360 schema but have **NO references** in the IOE-functions codebase. They may be:
- Used by other systems (BI tools, external APIs)
- Deprecated legacy tables
- Planned for future implementation
- Part of other Azure Functions not in this repository

### Analysis & AI Tables (14 tables)

#### 25. **engage360.action_execution_log**
**Status:** Not referenced in codebase
**Purpose:** Likely tracks AI agent action execution history

#### 26. **engage360.action_items**
**Status:** Not referenced in codebase
**Purpose:** Likely stores AI-generated action items from calls

#### 27. **engage360.agent_execution_log**
**Status:** Not referenced in codebase
**Purpose:** Likely tracks AI agent execution lifecycle

#### 28. **engage360.ai_decisions**
**Status:** Not referenced in codebase
**Purpose:** Likely logs AI decision-making process and rationale

#### 29. **engage360.ai_execution_context**
**Status:** Not referenced in codebase
**Purpose:** Likely stores AI agent execution context and state

#### 30. **engage360.analysis_alerts**
**Status:** Not referenced in codebase
**Purpose:** Likely stores alerts generated from call analysis

#### 31. **engage360.analysis_templates**
**Status:** Not referenced in codebase
**Purpose:** Likely stores templates for analysis processing

#### 32. **engage360.analysis_types**
**Status:** Not referenced in codebase
**Purpose:** Likely reference table for analysis type definitions

#### 33. **engage360.call_analysis_results**
**Status:** Not referenced in codebase
**Purpose:** Likely stores structured analysis results from calls

#### 34. **engage360.call_summaries**
**Status:** Not referenced in codebase
**Purpose:** Likely stores AI-generated call summaries

#### 35. **engage360.call_transcripts**
**Status:** Not referenced in codebase
**Purpose:** Likely stores full call transcripts (may use bland_call_logs instead)

#### 36. **engage360.compliance_findings**
**Status:** Not referenced in codebase
**Purpose:** Likely tracks compliance issues found in call analysis

#### 37. **engage360.sentiment_analysis**
**Status:** Not referenced in codebase
**Purpose:** Likely stores sentiment scores from call analysis

#### 38. **engage360.summary_processing_queue**
**Status:** Not referenced in codebase
**Purpose:** Likely queue table for summary processing jobs

---

### Conversation Analysis Tables (7 tables)

#### 39. **engage360.conversation_dynamics**
**Status:** Not referenced in codebase
**Purpose:** Likely tracks conversation flow patterns and dynamics

#### 40. **engage360.emotion_timeline**
**Status:** Not referenced in codebase
**Purpose:** Likely tracks emotional states throughout calls

#### 41. **engage360.empathy_rapport_analysis**
**Status:** Not referenced in codebase
**Purpose:** Likely analyzes empathy and rapport building in calls

#### 42. **engage360.healthcare_entities**
**Status:** Not referenced in codebase
**Purpose:** Likely extracts healthcare-specific entities (conditions, medications)

#### 43. **engage360.intent_analysis**
**Status:** Not referenced in codebase
**Purpose:** Likely tracks user intent classification from calls

#### 44. **engage360.risk_stratification_findings**
**Status:** Not referenced in codebase
**Purpose:** Likely stores health risk stratification results

#### 45. **engage360.topic_analysis**
**Status:** Not referenced in codebase
**Purpose:** Likely tracks topics discussed in calls

---

### Campaign Management Tables (9 tables)

#### 46. **engage360.campaign_agent_executions**
**Status:** Not referenced in codebase
**Purpose:** Likely tracks AI agent executions per campaign

#### 47. **engage360.campaign_analysis_config**
**Status:** Not referenced in codebase
**Purpose:** Likely stores analysis configuration per campaign

#### 48. **engage360.campaign_creation_requests**
**Status:** Not referenced in codebase
**Purpose:** Likely tracks campaign creation workflow requests

#### 49. **engage360.campaign_custom_metrics**
**Status:** Not referenced in codebase
**Purpose:** Likely stores custom KPIs per campaign

#### 50. **engage360.campaign_policies**
**Status:** Not referenced in codebase
**Purpose:** Likely stores campaign-specific policies (may overlap with campaigns_enhanced)

#### 51. **engage360.campaign_status_log**
**Status:** Not referenced in codebase
**Purpose:** Likely audit log for campaign status changes

#### 52. **engage360.campaigns_enhanced_history**
**Status:** Not referenced in codebase
**Purpose:** Likely historical changes to campaigns_enhanced table

#### 53. **engage360.campaigns_policies**
**Status:** Not referenced in codebase
**Purpose:** Likely junction table for campaign-policy relationships

#### 54. **engage360.event_to_campaign_cfg**
**Status:** Not referenced in codebase
**Purpose:** Likely maps trigger events to campaign configurations

---

### Member & Analytics Tables (6 tables)

#### 55. **engage360.analytics_daily_snapshot**
**Status:** Not referenced in codebase
**Purpose:** Likely daily rollup of analytics metrics

#### 56. **engage360.member_identifiers**
**Status:** Not referenced in codebase
**Purpose:** Likely stores alternate member identifiers (MRN, external IDs)

#### 57. **engage360.member_ingestion_batches**
**Status:** Not referenced in codebase
**Purpose:** Likely tracks member data import batches

#### 58. **engage360.member_ingestion_errors**
**Status:** Not referenced in codebase
**Purpose:** Likely logs errors during member data imports

#### 59. **engage360.wellness_health_ratings**
**Status:** Not referenced in codebase
**Purpose:** Likely stores wellness scores and health ratings

#### 60. **engage360.call_types**
**Status:** Not referenced in codebase
**Purpose:** Likely reference table for call type definitions

---

### Execution & Workflow Tables (6 tables)

#### 61. **engage360.executed_actions**
**Status:** Not referenced in codebase
**Purpose:** Likely tracks completed AI agent actions

#### 62. **engage360.kb_playbooks**
**Status:** Not referenced in codebase
**Purpose:** Likely stores knowledge base playbooks for agents

#### 63. **engage360.retry_policy**
**Status:** Not referenced in codebase
**Purpose:** Likely stores retry configuration per campaign/call type

#### 64. **engage360.template_analysis_mapping**
**Status:** Not referenced in codebase
**Purpose:** Likely maps analysis templates to campaigns

#### 65. **engage360.tool_call_audit**
**Status:** Not referenced in codebase
**Purpose:** Likely tracks AI agent tool/function calls

#### 66. **engage360.trigger_event_log**
**Status:** Not referenced in codebase
**Purpose:** Likely logs events that trigger campaigns or actions

---

## Quick Reference Summary

### By Usage Frequency

| Table | References | Primary Use |
|-------|-----------|-------------|
| outreach_batches | 18 | Batch tracking and reconciliation |
| member_campaign_enrollments_enhanced | 15 | Enrollment status and eligibility |
| outreach_attempts | 12 | Call attempt tracking |
| members | 10 | Member demographics |
| campaigns_enhanced | 9 | Campaign configuration |
| bland_call_logs | 6 | Call audit trail (raw JSON moved to bland_raw_response) |
| campaign_call_configs_enhanced | 5 | Bland AI parameters |
| member_devices | 4 | Device phone numbers |
| orgs | 4 | Partner metadata |
| partner_file_processing_log | 3 | File upload tracking |
| member_enrollment_status_history | 3 | Status change audit |
| analysis_queue_status | 3 | Analysis job tracking |
| system_locks | 2 | Distributed locking |
| care_gaps | 2 | Care gap validation |
| bland_raw_response | 1 | Raw webhook JSON storage (NEW: 2025-01-03) |
| partner_row_validation_results | 1 | Row validation |
| partner_validation_error_details_file | 1 | File-level errors |
| partner_validation_error_details_row | 1 | Row-level errors |
| partner_file_care_gap_stats | 1 | Care gap analytics |
| error_log | 1 | General errors |

### By Function Area

**Campaign Management (3 tables)**
- campaigns_enhanced
- campaign_call_configs_enhanced
- orgs

**Member Management (4 tables)**
- members
- member_devices
- member_campaign_enrollments_enhanced
- member_enrollment_status_history

**Outreach Tracking (4 tables)**
- outreach_batches
- outreach_attempts
- bland_call_logs
- bland_raw_response (NEW: 2025-01-03)

**Partner Campaign Processing (4 tables)**
- partner_file_processing_log
- partner_row_validation_results
- partner_validation_error_details_file
- partner_validation_error_details_row

**Reference Data (1 table)**
- care_gaps

**System (2 tables)**
- system_locks
- error_log

**Analysis (1 table)**
- analysis_queue_status

---

## Workflow Patterns

### DTC (Direct-to-Consumer) Workflow
```
CSV Upload
    ↓
[members] ← MERGE member data
    ↓
[member_devices] ← MERGE device data
    ↓
[member_campaign_enrollments_enhanced] ← MERGE enrollment
    ↓
[outreach_batches] ← INSERT new batch
    ↓
[outreach_attempts] ← INSERT attempts (one per member)
    ↓
Bland AI API Call
    ↓
[bland_call_logs] ← INSERT call metadata (atomic transaction)
    ↓
[bland_raw_response] ← INSERT raw webhook JSON (atomic transaction)
    ↓
[outreach_attempts] ← UPDATE disposition
    ↓
[member_campaign_enrollments_enhanced] ← UPDATE status
    ↓
[member_enrollment_status_history] ← INSERT status change
```

### Partner Campaign Workflow
```
CSV Upload
    ↓
[partner_file_processing_log] ← INSERT file record
    ↓
Validation
    ↓
[partner_row_validation_results] ← INSERT row results
[partner_validation_error_details_row] ← INSERT errors
[partner_validation_error_details_file] ← INSERT file errors
    ↓
[partner_file_care_gap_stats] ← INSERT care gap stats
    ↓
Campaign Qualification
    ↓
[campaigns_enhanced] ← SELECT qualified campaigns
[campaign_call_configs_enhanced] ← JOIN config
    ↓
Member Eligibility
    ↓
[member_campaign_enrollments_enhanced] ← SELECT active enrollments
[members] ← JOIN demographics
[member_devices] ← JOIN device data
[care_gaps] ← JOIN care gap mappings
    ↓
[outreach_batches] ← INSERT batch
[outreach_attempts] ← INSERT attempts
    ↓
Bland AI Submission (same as DTC from here)
```

### Batch Reconciliation Workflow
```
Timer Trigger (every 5 minutes)
    ↓
[system_locks] ← DELETE expired locks
    ↓
[system_locks] ← INSERT new lock (prevent concurrent runs)
    ↓
[outreach_batches] ← SELECT stale batches
    ↓
Call Bland AI Batch API
    ↓
[outreach_batches] ← UPDATE status, counts
    ↓
[system_locks] ← DELETE lock (release)
```

---

## File Location Reference

### Python Files Using engage360 Tables

**Partner Campaign Scheduler:**
- `/af_code/partner_campaign_scheduler/services/campaign_qualifier.py` - campaigns_enhanced, campaign_call_configs_enhanced, orgs
- `/af_code/partner_campaign_scheduler/services/member_eligibility.py` - member_campaign_enrollments_enhanced, members, member_devices, outreach_attempts
- `/af_code/partner_campaign_scheduler/services/batch_orchestrator.py` - care_gaps
- `/af_code/partner_campaign_scheduler/services/database_tracker.py` - outreach_batches, outreach_attempts

**DTC Functions:**
- `/af_code/af_dtc_intro_call/utils/config.py` - campaign_call_configs_enhanced
- `/af_code/af_partner_logic.py` - members, member_devices, member_campaign_enrollments_enhanced, orgs, care_gaps, partner_* tables

**Bland AI Webhook:**
- `/af_code/bland_ai_webhook/services/database_orchestrator.py` - bland_call_logs, analysis_queue_status, outreach_attempts, member_campaign_enrollments_enhanced, member_enrollment_status_history
- `/af_code/bland_ai_webhook/utils/config.py` - error_log, campaign_call_configs_enhanced

**Batch Reconciliation:**
- `/af_code/batch_reconciliation/services/batch_sync_coordinator.py` - system_locks, outreach_batches

---

## Notes

**Tables with High Write Volume:**
- outreach_attempts (one insert per member per call)
- bland_call_logs (one insert per webhook)
- member_enrollment_status_history (one insert per status change)

**Tables with Lock Contention Risk:**
- system_locks (frequent INSERT/DELETE during reconciliation)
- outreach_batches (concurrent updates from webhook and reconciliation)

**Tables Requiring Indexes:**
- member_campaign_enrollments_enhanced (member_id, campaign_id, current_status)
- outreach_attempts (enrollment_id, batch_id, disposition, attempt_ts)
- outreach_batches (campaign_id, vendor_batch_id, batch_status, last_status_check_ts)
- members (org_id, salesforce_account_number, file_batch)

**Tables with JSON Columns:**
- campaign_call_configs_enhanced (bland_parameters_global)
- partner_row_validation_results (active_care_gaps)
- bland_call_logs (raw_bland_response - NULL after 2025-01-03)
- bland_raw_response (raw_response - full webhook JSON payload)

---

**Document Version:** 1.1
**Last Updated:** 2025-01-03
**Total Tables Documented:** 65
**Tables Actively Used:** 24
**Tables Not Referenced:** 42
**Recent Changes:** Added bland_raw_response table for webhook JSON storage optimization
