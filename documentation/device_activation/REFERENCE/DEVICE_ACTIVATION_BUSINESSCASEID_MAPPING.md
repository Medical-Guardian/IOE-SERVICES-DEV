# Device Activation - BusinessCaseID Mapping

**Date:** 2025-12-24
**Version:** 1.0
**Purpose:** Central reference for all Device Activation BusinessCaseIDs

---

## Table of Contents

1. [BusinessCaseID Definitions](#businesscaseid-definitions)
2. [Complete File Cross-Reference Table](#complete-file-cross-reference-table)
3. [BusinessCaseID Usage in Code](#businesscaseid-usage-in-code)
4. [Quick Reference Guide](#quick-reference-guide)

---

## BusinessCaseID Definitions

### BC-DA-001: Device Activation - Core Orchestration System

**Purpose:** Main orchestration and function registration for Device Activation bot

**Scope:**
- Timer trigger execution (every 15 minutes)
- HTTP trigger for manual batch creation
- Service initialization pattern
- Main orchestration logic coordinating EligibilityService, BatchOrchestrator, and CallbackScheduler

**Components:**
- Azure Function blueprints and triggers
- Service initialization and dependency injection
- Orchestration flow control
- Error handling and logging

**Files:**
- `functions/device_activation_scheduler.py` (~100 lines) - Timer + HTTP trigger registration
- `af_code/device_activation_scheduler/main_logic.py` (~100 lines) - Main orchestration function
- `af_code/device_activation_scheduler/__init__.py` - Module initialization

**Key Functions:**
- `timer_device_activation()` - Timer trigger (runs every 15 min)
- `http_device_activation()` - HTTP trigger (manual execution)
- `create_device_activation_batch()` - Main orchestration function

**Related Documentation:**
- [Complete Architecture](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md#1-system-overview)
- [Scheduler Internals](../ARCHITECTURE/DEVICE_ACTIVATION_SCHEDULER_INTERNALS.md#1-scheduler-triggers)

**Related Code (Cross-References):**
- Uses: `EligibilityService`, `BatchOrchestrator`, `CallbackScheduler`
- Called by: Azure Functions runtime (timer/HTTP triggers)

---

### BC-DA-002: Device Activation - File Processing & ETL Pipeline

**Purpose:** Complete CSV ingestion, validation, staging, and core table updates for device activation data

**Scope:**
- 5-phase ETL pipeline architecture:
  - **Phase 1 - Extract:** CSV download from blob storage, Pandera schema validation
  - **Phase 2 - Load to Staging:** Row-by-row INSERT into stg_device_activation_delta with 10% error threshold
  - **Phase 3 - Validate:** SQL cleansing functions, org_id lookup, timezone mapping
  - **Phase 4 - Transform:** MERGE members/member_devices tables, INSERT member_campaign_enrollments_enhanced
  - **Phase 5 - Audit:** Audit trail creation, blob movement to processed/ or error/ folders
- Blob trigger detection for CSV files
- Comprehensive validation rules (E.164 phone, email, timezone, device status, customer type)
- Business day calculations for activation_start_date

**Components:**
- Azure Blob Storage integration
- Pandera schema validation
- SQL MERGE operations
- Error handling with retry logic
- File movement and archival
- Validation error logging

**Files:**
- `af_code/af_device_activation_logic.py` (2,104 lines) - Complete 5-phase ETL pipeline
- `functions/device_activation_file_processor.py` (~91 lines) - Blob trigger for fs-device-activation container
- `functions/operations_device_activation_file_processor.py` (~100 lines) - Blob trigger for fs-ops container
- `af_code/device_activation_scheduler/services/__init__.py` - Service module initialization

**Key Functions:**
- `process_device_activation_file_complete()` - Main ETL orchestrator
- `extract()` - Phase 1: CSV download and Pandera validation
- `load_to_staging()` - Phase 2: Staging table INSERT with error threshold
- `validate_data()` - Phase 3: SQL cleansing and validation
- `transform_and_load_core()` - Phase 4: MERGE/INSERT to core tables
- `audit_and_log()` - Phase 5: Audit trail and file movement
- Validation utilities: `standardize_phone()`, `validate_email()`, `map_timezone_to_iana()`, etc.

**Database Tables:**
- **Staging:** `stg_device_activation_delta` (ioe_stg schema)
- **Core:** `members`, `member_devices`, `member_campaign_enrollments_enhanced` (ioe schema)

**Related Documentation:**
- [Complete Architecture](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md#3-file-processing-flow)
- [Database Operations](../ARCHITECTURE/DEVICE_ACTIVATION_DATABASE_OPERATIONS.md#2-staging-etl-flow)
- [CSV Reference](DEVICE_ACTIVATION_CSV_REFERENCE.md)
- [Data Specification](DEVICE_ACTIVATION_DATA_SPECIFICATION.md)

**Related Code (Cross-References):**
- Uses: Azure Blob Storage SDK, pymssql, pandas, Pandera
- Calls: DatabaseService, ConfigManager
- Creates data for: BC-DA-003 (eligibility queries use enrollments created here)

---

### BC-DA-003: Device Activation - Eligibility & Scheduling Logic

**Purpose:** Determine which members are eligible for Device Activation calls based on complex business rules

**Scope:**
- Complex SQL eligibility query (200+ lines) with dual CTE structure (RegularCalls + CallbackCalls)
- Call 1-4 eligibility rules: BUSINESS day frequency (2 days for Calls 2-3, 5 days for Call 4), max 4 attempts, no 90-day limit
- Call 5+ eligibility rules: Weekly (7 CALENDAR days) frequency, unlimited attempts, 90-day window
- Callback priority processing (callbacks processed before regular calls)
- Dual-timezone business hours validation (MG operating hours EST + Member local timezone)
- Exclusion logic for pending batches and callback queue members

**Components:**
- EligibilityService class
- Multi-CTE SQL query with complex date arithmetic
- Business hours filtering logic
- Timezone conversion utilities integration
- Member eligibility result model

**Files:**
- `af_code/device_activation_scheduler/services/eligibility_service.py` (414 lines) - Core eligibility logic

**Key Methods:**
- `get_eligible_members()` - Main eligibility determination method
- `_filter_by_business_hours()` - Dual-timezone business hours check

**Database Query Highlights:**
```sql
WITH RegularCalls AS (
    -- Call 1-4: DATEDIFF(HOUR, last_attempt, NOW) >= 24 AND attempt_count < 4
    -- Call 5+: DATEDIFF(DAY, last_attempt, NOW) >= 7 AND NOW < call_5_timestamp + 90 days
),
CallbackCalls AS (
    -- Members with pending callbacks (bypass regular frequency rules)
)
SELECT * FROM RegularCalls UNION ALL SELECT * FROM CallbackCalls
```

**Business Rules:**
1. **Call 1:** No previous attempts, activation_start_date reached
2. **Calls 2-3:** 2 BUSINESS days between attempts, max 3 total attempts
3. **Call 4:** 5 BUSINESS days after Call 3, exactly 3 previous attempts
4. **Call 5+:** 7 CALENDAR days frequency, 90-day window starting from call_5_timestamp
5. **Callbacks:** Scheduled time reached, within 24 CALENDAR hours OR <3 attempts

**Related Documentation:**
- [Complete Architecture](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md#4-scheduler-architecture)
- [Scheduler Internals](../ARCHITECTURE/DEVICE_ACTIVATION_SCHEDULER_INTERNALS.md#2-eligibilityservice-deep-dive)
- [SQL Query Reference](DEVICE_ACTIVATION_SQL_QUERY_REFERENCE.md#1-eligibility-queries)
- [Call Sequence Diagrams](../FLOWS/DEVICE_ACTIVATION_CALL_SEQUENCE.md)

**Related Code (Cross-References):**
- Uses: DatabaseService, business_hours_utils
- Called by: BC-DA-001 (main_logic.py orchestration)
- Provides data to: BC-DA-004 (BatchOrchestrator)

---

### BC-DA-004: Device Activation - Batch Orchestration & Bland AI Integration

**Purpose:** Create batches, submit to Bland AI, and track via 3-phase database pattern

**Scope:**
- 3-phase database tracking pattern (Pending → Submitted → Completed):
  - **Phase 1:** Create batch record (status='Pending') BEFORE Bland AI call
  - **Phase 2:** Create attempt records (disposition='Pending') BEFORE Bland AI call
  - **Phase 3:** Update batch with vendor_batch_id (status='Submitted') AFTER Bland AI response
- Batch splitting (max 100 members per batch per Bland AI limitation)
- Bland AI payload building (18+ parameters, 13-field metadata structure)
- Call 5 timestamp tracking (triggers 90-day window)
- Error handling and rollback logic

**Components:**
- BatchOrchestrator class
- Bland AI client integration
- Database transaction management
- BatchRequest model building
- Retry and error recovery

**Files:**
- `af_code/device_activation_scheduler/services/batch_orchestrator.py` (809 lines) - Batch orchestration logic

**Key Methods:**
- `create_and_submit_batches()` - Main batch creation and submission
- `_submit_single_batch()` - Submit one batch (up to 100 members)
- `_build_batch_request()` - Build BatchRequest model for Bland AI
- `_create_outreach_batch()` - Phase 1: INSERT batch record
- `_create_outreach_attempts()` - Phase 2: INSERT attempt records
- `_update_batch_with_vendor_id()` - Phase 3: UPDATE with Bland AI vendor_batch_id
- `_update_call_5_enrollments()` - Set call_5_timestamp for Call 5+ logic
- `_mark_batch_failed()` - Error handling and rollback

**Database Tables:**
- `outreach_batches` - Batch tracking
- `outreach_attempts` - Individual call attempts
- `member_campaign_enrollments_enhanced` - call_5_timestamp updates

**Bland AI Integration:**
- BatchRequest model: campaign_id, calls[], pathway_id, voice_id, bland_parameters_global
- Metadata: 13 fields including member_id, enrollment_id, campaign_id, attempt_id, etc.
- 3-header pattern: Authorization, Twilio, encrypted_key

**Related Documentation:**
- [Complete Architecture](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md#7-bland-ai-integration)
- [Scheduler Internals](../ARCHITECTURE/DEVICE_ACTIVATION_SCHEDULER_INTERNALS.md#3-batchorchestrator-deep-dive)
- [Bland AI Integration](../ARCHITECTURE/DEVICE_ACTIVATION_BLAND_AI_INTEGRATION.md)
- [Database Operations](../ARCHITECTURE/DEVICE_ACTIVATION_DATABASE_OPERATIONS.md#4-batch-creation-pattern)

**Related Code (Cross-References):**
- Uses: DatabaseService, BlandAIClient, BlandParametersValidator
- Called by: BC-DA-001 (main_logic.py orchestration)
- Receives data from: BC-DA-003 (eligible members)
- Triggers: BC-DA-006 (Call 5 timestamp logic)

---

### BC-DA-005: Device Activation - Callback Scheduling & Queue Management

**Purpose:** Manage callback queue for members requesting scheduled callbacks

**Scope:**
- Callback queue processing loop
- Business hours validation for callbacks
- Rescheduling logic (next business day at operating_start_time)
- Timeout detection and handling (24 hours OR 3 attempts, whichever comes first)
- Callback attempt tracking
- Integration with BatchOrchestrator for callback batch submission

**Components:**
- CallbackScheduler class
- Business hours validation
- Timeout detection logic
- Callback rescheduling algorithm
- Queue status management

**Files:**
- `af_code/device_activation_scheduler/services/callback_scheduler.py` (566 lines) - Callback scheduling logic

**Key Methods:**
- `get_pending_callbacks()` - SQL query for pending callbacks
- `process_callbacks()` - Main callback processing loop
- `_validate_callback_business_hours()` - Dual-timezone business hours check
- `_reschedule_callback()` - Reschedule to next business day 9 AM
- `_handle_callback_timeouts()` - Detect and mark timeouts
- `increment_callback_attempt()` - Increment attempt counter
- `mark_callback_completed()` - Mark callback as completed
- `mark_callback_failed()` - Mark callback as failed

**Database Tables:**
- `outreach_callback_queue` - Callback scheduling queue

**Business Rules:**
1. **Priority:** Callbacks processed before regular calls (added to top of eligible member list)
2. **Timeout:** 24 hours OR 3 attempts, whichever comes first
3. **Rescheduling:** Next business day at operating_start_time (e.g., 9:00 AM EST)
4. **Business Hours:** Dual-timezone validation (MG EST + Member timezone)

**Related Documentation:**
- [Complete Architecture](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md#4-scheduler-architecture)
- [Scheduler Internals](../ARCHITECTURE/DEVICE_ACTIVATION_SCHEDULER_INTERNALS.md#4-callbackscheduler-deep-dive)
- [Callback Guide](../GUIDES/CALLBACK_SCHEDULER_DETAILED_GUIDE.md)
- [State Machines](../FLOWS/DEVICE_ACTIVATION_STATE_MACHINES.md#4-callback-status-state-machine)

**Related Code (Cross-References):**
- Uses: DatabaseService, business_hours_utils, timezone_utils
- Called by: BC-DA-001 (main_logic.py orchestration)
- Calls: BC-DA-004 (BatchOrchestrator for callback batch submission)

---

### BC-DA-006: Device Activation - Call Frequency & Sequencing Logic

**Purpose:** Implement call frequency rules that differ between Calls 1-4 and Call 5+

**Scope:**
- **Calls 1-4 Frequency:** BUSINESS day frequency (2 days for Calls 2-3, 5 days for Call 4), max 4 attempts, NO 90-day limit
- **Call 5+ Frequency:** 7 CALENDAR days frequency (includes weekends/holidays in count), calls ONLY on business days, unlimited attempts, 90-day window
- **Business Days:** Monday-Friday, excluding US federal holidays - **FILTERED IN PYTHON** (uses `get_business_days_between()` for Calls 1-4, `is_business_day()` for Call 5+)
- **Calendar Days:** All days including weekends and holidays (uses `DATEDIFF(day, ...)` in SQL for frequency calculation)
- **90-Day Window Logic:** Starts from call_5_timestamp (NOT activation_start_date)
- **Call 5 Timestamp Tracking:** Set when Call 5 is created, triggers campaign_end_date calculation
- **Campaign End Date Calculation:** call_5_timestamp + 90 days
- **Defense in Depth:** Call 5+ business day validation happens in TWO places (eligibility filter + business hours filter)

**Components:**
- Eligibility query frequency logic (Python `get_business_days_between()` for Calls 1-4, SQL DATEDIFF for Call 5+ frequency)
- Explicit business day validation for Call 5+ (Python `is_business_day()` for current day check)
- Call 5 timestamp update logic
- Campaign end date calculation
- Attempt count tracking
- Python `holidays` library for US federal holidays (NOT database table)
- Defense in depth: Business day validation in eligibility filter AND business hours filter

**Files:**
- `af_code/device_activation_scheduler/services/eligibility_service.py` - Frequency rules in SQL query + explicit Call 5+ business day validation (lines 680-695)
- `af_code/device_activation_scheduler/services/batch_orchestrator.py` - call_5_timestamp update
- `af_code/shared/business_hours_utils.py` - Business day utilities (`is_business_day()`, `get_business_days_between()`)
- `tests/test_device_activation_call_5_business_days.py` (377 lines) - Comprehensive test suite for Call 5+ business day validation (10 test cases)
- `database/create_business_days_function.sql` - Business days calculation function (DEPRECATED - now using Python)
- `database/create_us_federal_holidays_table.sql` - Holidays table (DEPRECATED - now using Python `holidays` library)

**Key Logic Blocks:**

**In eligibility_service.py (SQL + Python):**

⚠️ **NOTE: Business day filtering for Calls 2-4 now happens in PYTHON, not SQL.**
See: `eligibility_service.py:666-730` (uses `get_business_days_between()` function)

**SQL Frequency Calculation:**
```sql
-- Calls 2-3: 2 BUSINESS days since last attempt (FILTERED IN PYTHON)
(SELECT COUNT(*) FROM outreach_attempts WHERE enrollment_id = e.enrollment_id) BETWEEN 1 AND 2
-- Business day check removed from SQL - now filtered in Python code

-- Call 4: 5 BUSINESS days since Call 3 (FILTERED IN PYTHON)
(SELECT COUNT(*) FROM outreach_attempts WHERE enrollment_id = e.enrollment_id) = 3
-- Business day check removed from SQL - now filtered in Python code

-- Call 5+: 7 CALENDAR days since last attempt (frequency only, call timing checked in Python)
(SELECT COUNT(*) FROM outreach_attempts WHERE enrollment_id = e.enrollment_id) >= 4
AND DATEDIFF(DAY, MAX(attempt_ts), SYSDATETIMEOFFSET()) >= 7
AND (call_5_timestamp IS NULL OR SYSDATETIMEOFFSET() < DATEADD(DAY, 90, call_5_timestamp))
```

**Python Business Day Validation for Call 5+ (eligibility_service.py:680-695):**
```python
# Call 5+: Check current day is a business day (no frequency calculation needed)
# Frequency uses 7 CALENDAR days (SQL), but calls only on business days
if call_attempt_number >= 5:
    # Check if TODAY is a business day (excludes weekends and federal holidays)
    if is_business_day(now_utc):
        logger.debug(
            f"✅ [ELIGIBILITY-SERVICE] Member {member.get('member_id')} Call {call_attempt_number}: "
            f"Current day is a business day - ELIGIBLE"
        )
        business_day_filtered_members.append(member)
    else:
        logger.debug(
            f"❌ [ELIGIBILITY-SERVICE] Member {member.get('member_id')} Call {call_attempt_number}: "
            f"Current day is NOT a business day (weekend or holiday) - SKIPPED"
        )
    continue
```

**In batch_orchestrator.py (Python):**
```python
def _update_call_5_enrollments(self, eligible_members: List[Dict]) -> None:
    """
    Update call_5_timestamp for members on their 5th call attempt

    Sets:
    - call_5_timestamp = SYSDATETIMEOFFSET()
    - campaign_end_date = call_5_timestamp + 90 days

    BusinessCaseID: BC-DA-006
    """
```

**Business Rules:**
1. **Call 1:** First attempt, activation_start_date reached
2. **Call 2:** 2 BUSINESS days after Call 1, no success yet
3. **Call 3:** 2 BUSINESS days after Call 2, no success yet
4. **Call 4:** 5 BUSINESS days after Call 3, no success yet
5. **Call 5:** 7 CALENDAR days after Call 4 (frequency), calls ONLY on business days (timing), sets call_5_timestamp and 90-day window
6. **Call 6+:** Weekly (every 7 CALENDAR days frequency), calls ONLY on business days (timing), until call_5_timestamp + 90 days

**Key Distinction:**
- **Calls 1-4:** Use BUSINESS days for both frequency AND timing (Monday-Friday, no holidays) - gives members more time in real calendar
- **Call 5+:** Use CALENDAR days for frequency (includes weekends/holidays), but calls ONLY on business days (Monday-Friday, no holidays)

**Critical Clarification (Call 5+):**
- **Frequency Calculation (SQL):** `DATEDIFF(day, ...) >= 7` - counts ALL days (calendar days)
- **Call Timing (Python):** `is_business_day(now_utc)` - filters out weekends/holidays
- **Example:** If Call 5 attempted on Monday, 7 calendar days = next Monday (eligible). If next Monday is a holiday, call skipped until next business day (Tuesday).

**Related Documentation:**
- [Complete Architecture](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md#5-call-sequencing-logic)
- [Call Sequence Diagrams](../FLOWS/DEVICE_ACTIVATION_CALL_SEQUENCE.md)
- [Database Operations](../ARCHITECTURE/DEVICE_ACTIVATION_DATABASE_OPERATIONS.md#6-call-5-timestamp-logic)

**Related Code (Cross-References):**
- Implemented in: BC-DA-003 (eligibility query), BC-DA-004 (call_5_timestamp update)
- Affects: Eligibility determination, campaign end date calculation

---

### BC-DA-007: Device Activation - Campaign Closure (90-Day Auto-Unenroll)

**Purpose:** Automatically unenroll Device Activation members when their 90-day campaign window expires

**Scope:**
- Hourly timer trigger to check for expired campaigns
- Query enrollments past campaign_end_date
- Update enrollment status from 'Active' to 'UNENROLLED'
- Insert status change history for audit trail
- Distributed locking to prevent concurrent executions
- HTTP endpoint for manual testing

**Components:**
- Timer trigger (hourly)
- HTTP trigger (manual execution)
- Campaign Closure Service
- Distributed locking mechanism
- Database transaction management

**Files:**
- `functions/device_activation_campaign_closure.py` (~200 lines) - Timer + HTTP triggers
- `af_code/device_activation_scheduler/services/campaign_closure_service.py` (~300+ lines) - Closure logic

**Key Functions:**
- `timer_device_activation_campaign_closure()` - Timer trigger (runs every hour)
- `http_device_activation_campaign_closure()` - HTTP trigger (manual execution)
- `process_expired_enrollments()` - Main closure logic

**Eligibility Criteria:**
- enrollment_status = 'Active' (only active members)
- campaign_id IN (Medicaid, DTC/MA campaigns)
- campaign_end_date IS NOT NULL (only members with Call 5+)
- campaign_end_date < CURRENT_DATE (90-day window expired)

**Database Operations:**
1. SELECT eligible enrollments (past campaign_end_date)
2. UPDATE `member_campaign_enrollments_enhanced` SET enrollment_status = 'UNENROLLED'
3. INSERT `member_enrollment_status_history` with reason='90-day window expired'
4. Distributed locking via `system_locks` table

**Related Documentation:**
- [Complete Architecture](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md#3-1-5-campaign-closure)
- [Data Flow Diagrams](../FLOWS/DEVICE_ACTIVATION_DATA_FLOW.md#diagram-5-campaign-closure-flow)
- [Operations Call Flow](../../OPERATIONS_DEVICE_ACTIVATION_CALL_FLOW.md#phase-7-campaign-closure)

**Related Code (Cross-References):**
- Uses: DatabaseService, ConfigManager
- Updates data created by: BC-DA-002 (enrollments), BC-DA-004 (call_5_timestamp)
- Prevents data access by: BC-DA-003 (unenrolled members excluded from eligibility)

---

### BC-102: Webhook Processing (Shared Across All Campaigns)

**Purpose:** Process Bland AI webhook responses and update database with call results (shared by DTC, Partner, and Device Activation campaigns)

**Scope:**
- Webhook payload parsing and validation
- Duplicate call detection (idempotency)
- Disposition mapping (Bland AI → Internal status)
- Database status updates (attempts, enrollments, callbacks)
- Callback queue creation for callback requests
- Audit trail logging

**Components:**
- Webhook handler function
- Data validator
- Duplicate detector
- Status mapper
- Database orchestrator
- Callback queue manager

**Files:**
- `af_code/bland_ai_webhook/bland_ai_webhook.py` - Webhook HTTP endpoint
- `af_code/bland_ai_webhook/services/data_validator.py` - Payload validation
- `af_code/bland_ai_webhook/services/duplicate_detector.py` - Duplicate call detection
- `af_code/bland_ai_webhook/services/status_mapper.py` - Disposition mapping (BC-102)
- `af_code/bland_ai_webhook/services/database_orchestrator.py` - Database updates

**Disposition Mapping:**
- `INTERESTED` → Completed + Follow_Up
- `NOT_INTERESTED` → Completed + Close
- `CALL_BACK_SCHEDULED` → Completed + Scheduled (INSERT callback_queue)
- `DO_NOT_CONTACT` → OptOut + Close
- `NOT_QUALIFIED` → Completed + Close
- `CANCELED` → Failed + Retry
- `FAILED` → Failed + Retry
- `NO_ANSWER` → NoAnswer
- `BUSY` → Busy
- `VOICEMAIL` → VoicemailLeft

**Database Updates:**
1. UPDATE `outreach_attempts` SET disposition, call_duration, etc.
2. UPDATE `member_campaign_enrollments_enhanced` SET current_status (if opt-out or completion)
3. INSERT `outreach_callback_queue` (if callback requested)
4. INSERT `bland_call_logs` (audit trail)

**Campaign-Specific Behavior:**
- **DTC Campaigns:** Updates enrollment status based on disposition
- **Partner Campaigns:** Skips enrollment status updates (all members remain 'Active')
- **Device Activation:** Updates enrollment status, creates Call 5 timestamp for 90-day window

**Related Documentation:**
- [Webhook Testing Guide](../../WEBHOOK_TESTING_GUIDE.md)
- [Complete Architecture](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md#3-1-3-webhook-processor)

**Related Code (Cross-References):**
- Uses: DatabaseService, ConfigManager
- Receives data from: Bland AI API (POST webhook)
- Updates data created by: BC-DA-004 (Device Activation attempts/batches), BC-109 (DTC batches), BC-113 (Partner batches)
- Creates data for: BC-DA-005 (Device Activation callbacks), BC-103 (DTC callbacks), BC-114 (Partner callbacks)

---

### BC-DA-008: Device Activation - Operations Campaigns (Medicaid + DTC/MA)

**Purpose:** Handle hardcoded campaign ID routing for Medicaid and DTC/MA operations campaigns

**Scope:**
- Dual-campaign file processing with hardcoded campaign IDs
- Filename-based campaign determination
- Campaign-specific configuration handling
- Blob trigger for fs-ops container (operations files)

**Components:**
- Operations blob trigger
- Campaign ID mapping logic
- File routing based on filename pattern

**Files:**
- `functions/operations_device_activation_file_processor.py` (~100 lines) - Operations blob trigger

**Campaign ID Mapping:**
- **Medicaid:** `0F69659B-491B-40E2-88C3-ABC7D87385B2`
  - Filename pattern: `MedicalGuardian_DeviceActivationMedicaid_YYYYMMDD_DELTA.csv`
- **DTC/MA:** `BA865458-60F9-4EBB-9FB5-D195B532CF5A`
  - Filename pattern: `MedicalGuardian_DeviceActivationDTCMA_YYYYMMDD_DELTA.csv`

**Key Differences from Standard Device Activation:**
- Uses explicit campaign_id instead of campaign discovery from CSV
- Processes files in fs-ops container instead of fs-device-activation
- Requires different CSV field structure (26 fields vs 24 fields)

**Related Documentation:**
- [Complete Architecture](../ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md#3-file-processing-flow)
- [CSV Reference](DEVICE_ACTIVATION_CSV_REFERENCE.md#operations-campaign-csv-format)

**Related Code (Cross-References):**
- Uses: BC-DA-002 (af_device_activation_logic.py for ETL processing)
- Calls: Same ETL pipeline but with hardcoded campaign_id

---

## Complete File Cross-Reference Table

| File Path | BusinessCaseID(s) | Purpose | Lines | Key Functions/Classes |
|-----------|------------------|---------|-------|---------------------|
| **Core Scheduler** |||||
| `functions/device_activation_scheduler.py` | BC-DA-001 | Function registration (timer + HTTP triggers) | ~100 | `timer_device_activation()`, `http_device_activation()` |
| `af_code/device_activation_scheduler/main_logic.py` | BC-DA-001 | Main orchestration logic | ~100 | `create_device_activation_batch()` |
| `af_code/device_activation_scheduler/__init__.py` | BC-DA-001 | Module initialization | ~10 | N/A |
| **Scheduler Services** |||||
| `af_code/device_activation_scheduler/services/eligibility_service.py` | BC-DA-003, BC-DA-006 | Eligibility determination, call frequency logic | 414 | `EligibilityService`, `get_eligible_members()`, `_filter_by_business_hours()` |
| `af_code/device_activation_scheduler/services/batch_orchestrator.py` | BC-DA-004, BC-DA-006 | Batch creation, Bland AI submission, Call 5 timestamp | 809 | `BatchOrchestrator`, `create_and_submit_batches()`, `_update_call_5_enrollments()` |
| `af_code/device_activation_scheduler/services/callback_scheduler.py` | BC-DA-005 | Callback queue processing, rescheduling | 566 | `CallbackScheduler`, `process_callbacks()`, `_reschedule_callback()` |
| `af_code/device_activation_scheduler/services/__init__.py` | BC-DA-003, BC-DA-004, BC-DA-005 | Services module initialization | ~10 | N/A |
| **File Processors** |||||
| `af_code/af_device_activation_logic.py` | BC-DA-002 | Complete 5-phase ETL pipeline | 2,104 | `process_device_activation_file_complete()`, `extract()`, `load_to_staging()`, `validate_data()`, `transform_and_load_core()`, `audit_and_log()` |
| `functions/device_activation_file_processor.py` | BC-DA-002 | Blob trigger (fs-device-activation container) | ~91 | `device_activation_file_processor()` |
| `functions/operations_device_activation_file_processor.py` | BC-DA-002, BC-DA-008 | Blob trigger (fs-ops) for Medicaid/DTC-MA | ~100 | `operations_device_activation_file_processor()` |
| **Shared Utilities** |||||
| `af_code/shared/business_hours_utils.py` | BC-DA-003, BC-DA-005 | Dual-timezone business hours validation | ~200 | `can_make_call()`, `get_next_business_day()` |
| `af_code/shared/bland_ai_client.py` | BC-DA-004 | Bland AI API client (3-header pattern) | ~300 | `BlandAIClient`, `submit_batch_calls()` |
| `af_code/shared/bland_parameters_validator.py` | BC-DA-004 | Bland AI parameter validation | ~150 | `BlandParametersValidator`, `validate()` |
| `af_code/shared/timezone_utils.py` | BC-DA-003, BC-DA-005 | Timezone conversion utilities | ~100 | `TimezoneConverter`, `to_pytz()`, `get_us_timezones_pytz()` |
| **Campaign Closure (90-Day Auto-Unenroll)** |||||
| `functions/device_activation_campaign_closure.py` | BC-DA-007 | Timer + HTTP triggers for campaign closure | ~200 | `timer_device_activation_campaign_closure()`, `http_device_activation_campaign_closure()` |
| `af_code/device_activation_scheduler/services/campaign_closure_service.py` | BC-DA-007 | Campaign closure logic, distributed locking | ~300 | `CampaignClosureService`, `process_expired_enrollments()` |
| **Webhook Processing (Shared)** |||||
| `af_code/bland_ai_webhook/bland_ai_webhook.py` | BC-102 | Webhook HTTP endpoint (DTC/Partner/Device Activation) | ~200 | `bland_ai_webhook()` |
| `af_code/bland_ai_webhook/services/data_validator.py` | BC-102 | Webhook payload validation | ~150 | `DataValidator`, `validate_webhook_data()` |
| `af_code/bland_ai_webhook/services/duplicate_detector.py` | BC-102 | Duplicate call detection | ~100 | `DuplicateDetector`, `is_duplicate_call()` |
| `af_code/bland_ai_webhook/services/status_mapper.py` | BC-102 | Disposition mapping | ~200 | `StatusMapper`, `map_disposition()` |
| `af_code/bland_ai_webhook/services/database_orchestrator.py` | BC-102 | Database updates from webhook | ~800 | `DatabaseOrchestrator`, `process_webhook()` |
| **Database/Config Services** |||||
| `af_code/bland_ai_webhook/services/config_manager.py` | All | Azure Key Vault integration | ~150 | `ConfigManager`, `get_config()`, `get_db_connection_string()` |
| `af_code/bland_ai_webhook/services/database_service.py` | All | Database connection management | ~200 | `DatabaseService`, `execute_query()`, `execute_transaction()` |

**Total Files:** 24
**Total Lines of Code:** ~7,000+

---

## BusinessCaseID Usage in Code

### Module Docstring Example

```python
"""
Device Activation Batch Orchestrator

BusinessCaseID: BC-DA-004 (Batch Orchestration), BC-DA-006 (Call Frequency Logic)
Created: 2025-12-07
Updated: 2025-12-24 - Added comprehensive documentation

This service orchestrates batch call submissions to Bland AI for Device Activation campaigns.

ARCHITECTURE:
------------
Implements 3-phase database tracking pattern (following DTC intro call pattern):

Phase 1: Create batch record (status='Pending') BEFORE Bland AI call
  - INSERT into outreach_batches with generated batch_id
  - Allows transaction rollback if Phase 2 or Phase 3 fails

Phase 2: Create attempt records (disposition='Pending') BEFORE Bland AI call
  - INSERT into outreach_attempts for each member in batch
  - Links attempts to batch_id from Phase 1
  - Captures member/campaign/enrollment context

Phase 3: Update batch with vendor_batch_id (status='Submitted') AFTER Bland AI response
  - UPDATE outreach_batches with Bland AI's vendor_batch_id
  - Changes status to 'Submitted' to indicate successful submission
  - Webhook processor uses vendor_batch_id to match call results

RELATED DOCUMENTATION:
---------------------
- Complete Architecture: documentation/device_activation/ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md
- Database Operations: documentation/device_activation/ARCHITECTURE/DEVICE_ACTIVATION_DATABASE_OPERATIONS.md
- Bland AI Integration: documentation/device_activation/ARCHITECTURE/DEVICE_ACTIVATION_BLAND_AI_INTEGRATION.md

RELATED CODE:
------------
- DTC Pattern: af_code/af_dtc_intro_call/services/blandai_service.py
- Eligibility Service: af_code/device_activation_scheduler/services/eligibility_service.py
- Bland AI Client: af_code/shared/bland_ai_client.py
"""
```

### Class Docstring Example

```python
class BatchOrchestrator:
    """
    Service to orchestrate batch call submissions to Bland AI for Device Activation

    Implements 3-phase database tracking (following DTC pattern):
    - Phase 1: Create batch record (status='Pending') BEFORE Bland AI call
    - Phase 2: Create attempt records (disposition='Pending') BEFORE Bland AI call
    - Phase 3: Update batch with vendor_batch_id (status='Submitted') AFTER Bland AI response

    BusinessCaseID: BC-DA-004, BC-DA-006

    Attributes:
        db_service (DatabaseService): Database operations service
        config_manager (ConfigManager): Azure Key Vault configuration
        bland_client (BlandAIClient): Bland AI API client
        enabled (bool): Whether batch orchestrator is enabled

    Example:
        >>> config_manager = ConfigManager()
        >>> db_service = DatabaseService(config_manager)
        >>> orchestrator = BatchOrchestrator(db_service, config_manager)
        >>> result = orchestrator.create_and_submit_batches(eligible_members)
        >>> print(result['batches_created'])
        3
    """
```

### Function Docstring Example

```python
def create_and_submit_batches(self, eligible_members: List[Dict]) -> Dict[str, Any]:
    """
    Create batches and submit to Bland AI

    Splits members into batches of 100 (Bland AI limit) and submits each batch
    using 3-phase database tracking pattern.

    BusinessCaseID: BC-DA-004, BC-DA-006

    Args:
        eligible_members (List[Dict]): List of eligible members from EligibilityService
            Each dict contains: enrollment_id, member_id, campaign_id, phone, etc.

    Returns:
        Dict[str, Any]: Result dictionary containing:
            - success (bool): Whether all batches submitted successfully
            - batches_created (int): Number of batches created
            - calls_submitted (int): Total calls submitted to Bland AI
            - error (str): Error message if failed (only if success=False)

    Raises:
        DatabaseError: If batch/attempt creation fails
        BlandAPIError: If Bland AI submission fails

    Example:
        >>> eligible_members = [
        ...     {"enrollment_id": "abc-123", "member_id": "mem-001", ...},
        ...     # ... 150 more members ...
        ... ]
        >>> result = orchestrator.create_and_submit_batches(eligible_members)
        >>> result
        {'success': True, 'batches_created': 2, 'calls_submitted': 151, 'error': None}

    Notes:
        - Batches are split at 100 members max (Bland AI limitation)
        - For Call 5+, updates call_5_timestamp in enrollments table
        - Uses transaction rollback for failures
    """
```

### Inline Comment Example

```python
# Purpose: Calculate which call attempt this is (used for Call 1-4 vs Call 5+ logic)
# BusinessCaseID: BC-DA-006
call_attempt_number = ISNULL((
    SELECT COUNT(*)
    FROM ioe.outreach_attempts oa
    WHERE oa.enrollment_id = e.enrollment_id
), 0) + 1

# Purpose: 90-day window logic (only applies to Call 5+)
# Starts from call_5_timestamp, NOT activation_start_date
# BusinessCaseID: BC-DA-006
AND (
    e.call_5_timestamp IS NULL  -- Call 5 hasn't been made yet
    OR SYSDATETIMEOFFSET() < DATEADD(DAY, 90, e.call_5_timestamp)  -- Within 90-day window
)
```

---

## Quick Reference Guide

### Find BusinessCaseID by Feature

| Feature/Component | BusinessCaseID |
|------------------|---------------|
| Timer trigger (15 min scheduler) | BC-DA-001 |
| HTTP trigger (manual batch creation) | BC-DA-001 |
| CSV file processing | BC-DA-002 |
| 5-phase ETL pipeline | BC-DA-002 |
| Blob triggers (fs-device-activation, fs-ops) | BC-DA-002, BC-DA-008 |
| Eligibility SQL query | BC-DA-003 |
| Business hours validation | BC-DA-003, BC-DA-005 |
| Call 1-4 frequency (BUSINESS days: 2-5 days) | BC-DA-006 |
| Call 5+ frequency (CALENDAR days: weekly, 90-day window) | BC-DA-006 |
| Batch creation (3-phase tracking) | BC-DA-004 |
| Bland AI submission | BC-DA-004 |
| Call 5 timestamp logic | BC-DA-006 |
| Callback queue processing | BC-DA-005 |
| Callback rescheduling | BC-DA-005 |
| Webhook processing | BC-DA-007 |
| Disposition mapping | BC-DA-007 |
| Medicaid campaign | BC-DA-008 |
| DTC/MA campaign | BC-DA-008 |

### Find BusinessCaseID by File

| File | Primary BC | Secondary BC |
|------|-----------|--------------|
| `main_logic.py` | BC-DA-001 | - |
| `device_activation_scheduler.py` | BC-DA-001 | - |
| `af_device_activation_logic.py` | BC-DA-002 | - |
| `device_activation_file_processor.py` | BC-DA-002 | - |
| `operations_device_activation_file_processor.py` | BC-DA-002 | BC-DA-008 |
| `eligibility_service.py` | BC-DA-003 | BC-DA-006 |
| `batch_orchestrator.py` | BC-DA-004 | BC-DA-006 |
| `callback_scheduler.py` | BC-DA-005 | - |
| `status_mapper.py` | BC-DA-007 | - |
| `database_orchestrator.py` (webhook) | BC-DA-007 | - |

### Find Files by BusinessCaseID

| BusinessCaseID | File Count | Primary Files |
|---------------|-----------|--------------|
| BC-DA-001 | 3 | main_logic.py, device_activation_scheduler.py, __init__.py |
| BC-DA-002 | 4 | af_device_activation_logic.py, device_activation_file_processor.py, operations_device_activation_file_processor.py, __init__.py |
| BC-DA-003 | 2 | eligibility_service.py, __init__.py |
| BC-DA-004 | 2 | batch_orchestrator.py, __init__.py |
| BC-DA-005 | 2 | callback_scheduler.py, __init__.py |
| BC-DA-006 | 2 | eligibility_service.py (SQL), batch_orchestrator.py (call_5_timestamp) |
| BC-DA-007 | 5 | bland_ai_webhook.py, data_validator.py, duplicate_detector.py, status_mapper.py, database_orchestrator.py |
| BC-DA-008 | 1 | operations_device_activation_file_processor.py |

---

## Change Log

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-12-24 | 1.0 | Initial creation with BC-DA-001 through BC-DA-008 | Claude Code |

---

**Last Updated:** 2025-12-24
**Next Review:** Q1 2026 (or when new business cases added)
