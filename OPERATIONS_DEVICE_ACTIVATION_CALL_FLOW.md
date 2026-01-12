# Operations Device Activation - Complete Call Scheduling Flow

**Date:** 2025-12-18
**Campaigns:** Device Activation - Medicaid & DTC/MA
**Purpose:** Comprehensive explanation of how scheduled calls work from file arrival to completion

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Phase 1: File Arrival & Processing](#phase-1-file-arrival--processing)
3. [Phase 2: Enrollment Creation](#phase-2-enrollment-creation)
4. [Phase 3: Scheduler Eligibility Check](#phase-3-scheduler-eligibility-check)
5. [Phase 4: Business Hours Validation](#phase-4-business-hours-validation)
6. [Phase 5: Batch Creation & Bland AI Submission](#phase-5-batch-creation--bland-ai-submission)
7. [Phase 6: Call Execution & Webhook Processing](#phase-6-call-execution--webhook-processing)
8. [Call Sequence Scenarios](#call-sequence-scenarios)
9. [Timeline Examples](#timeline-examples)

---

## Overview

### The Complete Journey

```
FILE UPLOAD → FILE PROCESSING → ENROLLMENT → ELIGIBILITY CHECK → BUSINESS HOURS CHECK → BATCH CREATION → BLAND AI CALL → WEBHOOK RESULT → NEXT ATTEMPT (if needed)
```

### Key Components

1. **Blob Trigger** - Detects CSV file upload
2. **File Processor** - Validates and processes CSV data
3. **Database ETL** - 5-phase pipeline (Extract → Load → Validate → Transform → Audit)
4. **Scheduler** - Runs every 15 minutes to find eligible members
5. **Eligibility Service** - Checks if member can be called
6. **Business Hours Validator** - Dual-timezone check (MG EST + Member timezone)
7. **Batch Orchestrator** - Creates batches and submits to Bland AI
8. **Bland AI** - Makes the actual phone call
9. **Webhook Processor** - Receives call result and updates database

---

## Phase 1: File Arrival & Processing

### Step 1.1: File Upload

**User Action:** Upload CSV file to Azure Blob Storage

**Container:** `fs-ops/landing`

**Filename Examples:**
- `MedicalGuardian_DeviceActivationMedicaid_20251218_DELTA.csv`
- `MedicalGuardian_DeviceActivationDTCMA_20251218_DELTA.csv`

**File Structure:**
```csv
partner_name,campaign_name_source,language_pref,salesforce_account_number,salesforce_account_id,member_first_name,member_last_name,member_phone_number,member_timezone,member_dob,member_email,member_address_street,member_address_city,member_address_state,member_address_zip,member_address_country,device_udi,device_name,member_brand,device_phone_number,campaign_parameters,monitoring_system_id,fall_detection,powersaver_mode,enrollment_status,unenrollment_reason
Medical Guardian,Device Activation - Medicaid,English,5743441,0016R00003PVck4QAD,Barbara,McDaniel,+18173137409,CST,1935-12-16,mcdanielbf@gmail.com,4424 Overton Crest St,Fort Worth,TX,76109,USA,457128490,MGMini,Medical Guardian,+17182887685,,a3lR3000000a9XpIAI,False,Standard,enrolled,
```

**Trigger Time:** < 10 seconds after upload

---

### Step 1.2: Blob Trigger Activation

**Function:** `operations_device_activation_file_processor`

**Location:** `functions/operations_device_activation_file_processor.py`

**What Happens:**
```python
@operations_device_activation_bp.blob_trigger(
    arg_name="blob",
    path="fs-ops/landing/{name}",
    connection="AzureWebJobsStorage"
)
def operations_device_activation_file_processor(blob: func.InputStream):
    # 1. Validate filename pattern
    if "Medicaid" in blob.name:
        campaign_id = "0F69659B-491B-40E2-88C3-ABC7D87385B2"
        campaign_name = "Device Activation - Medicaid"
    elif "DTCMA" in blob.name:
        campaign_id = "BA865458-60F9-4EBB-9FB5-D195B532CF5A"
        campaign_name = "Device Activation - DTC/MA"

    # 2. Process file using existing device activation logic
    result = process_device_activation_file_complete(
        blob_name=blob.name,
        blob_content=blob.read(),
        campaign_id=campaign_id,
        campaign_name=campaign_name
    )
```

**Logs:**
```
🔔 [OPS-DEVICE-ACTIVATION] Blob trigger fired for file: MedicalGuardian_DeviceActivationMedicaid_20251218_DELTA.csv
   📦 Blob size: 1024 bytes
   📂 Container: fs-ops/landing
✅ [OPS-DEVICE-ACTIVATION] Filename pattern validated successfully
📋 [OPS-DEVICE-ACTIVATION] Campaign: Device Activation - Medicaid
   🆔 Campaign ID: 0F69659B-491B-40E2-88C3-ABC7D87385B2
🚀 [OPS-DEVICE-ACTIVATION] Starting file processing...
```

---

### Step 1.3: 5-Phase ETL Pipeline

**Function:** `process_device_activation_file_complete()`

**Location:** `af_code/af_device_activation_logic.py`

#### Phase 1: Extract

**What Happens:**
1. Download CSV from blob storage
2. Read into pandas DataFrame
3. **Column Mapping (NEW for Operations):**

```python
# Detect member_ prefix columns (Operations campaigns)
column_mapping = {
    'member_first_name': 'first_name',
    'member_last_name': 'last_name',
    'member_phone_number': 'primary_phone',
    'member_timezone': 'timezone',
    'member_dob': 'dob',
    'member_email': 'email',
    'member_address_street': 'service_address',
    'member_address_city': 'city',
    'member_address_state': 'state',
    'member_address_zip': 'zip',
    'member_brand': 'brand'
}

# Rename columns
df.rename(columns=column_mapping, inplace=True)

# Special handling
if 'powersaver_mode' in df.columns:
    df['battery_status'] = df['powersaver_mode']  # Standard → Good, Powersaver → Low

if 'fall_detection' in df.columns:
    df['fall_detection_status'] = df['fall_detection']
```

**Result:** DataFrame with staging table column names

---

#### Phase 2: Load to Staging

**What Happens:**
1. Generate `file_batch_id` (UUID)
2. Add metadata columns (file_batch_id, campaign_id, org_id, created_ts)
3. Bulk insert into `engage360_stg.stg_device_activation_delta`

**Table:** `engage360_stg.stg_device_activation_delta`

**Key Columns:**
- `salesforce_account_number` (unique member ID)
- `salesforce_account_id` (Salesforce Account ID)
- `monitoring_system_id` (external system ID)
- `first_name`, `last_name`, `primary_phone`, `timezone`, `email`, `dob`
- `device_udi`, `device_name`, `brand`, `device_phone_number`
- `fall_detection_status`, `battery_status`
- `enrollment_status` (enrolled, unenrolled, updated)
- `processing_status` (STAGING, VALIDATING, TRANSFORMING, ERROR, COMPLETE)

**Example Row:**
```sql
file_batch_id: a1b2c3d4-e5f6-7890-abcd-ef1234567890
campaign_id: 0F69659B-491B-40E2-88C3-ABC7D87385B2
salesforce_account_number: 5743441
salesforce_account_id: 0016R00003PVck4QAD
first_name: Barbara
last_name: McDaniel
primary_phone: +18173137409
timezone: CST
device_udi: 457128490
device_phone_number: +17182887685
monitoring_system_id: a3lR3000000a9XpIAI
fall_detection_status: False
battery_status: Good (mapped from "Standard")
enrollment_status: enrolled
processing_status: STAGING
created_ts: 2025-12-18 10:00:00.000 +00:00
```

**Logs:**
```
📥 [DEVICE-ACTIVATION] Phase 2: Loading 1 rows to staging table...
✅ [DEVICE-ACTIVATION] Successfully loaded 1 rows to staging table
```

---

#### Phase 3: Validate

**What Happens:**
1. Phone number validation (E.164 format: +1XXXXXXXXXX)
2. Timezone validation (CST, EST, PST, MST, etc.)
3. Email validation (if provided)
4. Device validation (device_udi, device_phone_number)
5. Salesforce account number required
6. Enrollment status validation (enrolled, unenrolled, updated)

**Validation Rules:**
- Phone: Must start with '+', 11-15 digits
- Timezone: Must be valid pytz timezone
- Device phone: E.164 if device is callable
- Enrollment status: One of (enrolled, unenrolled, updated)

**If Validation Fails:**
```sql
UPDATE engage360_stg.stg_device_activation_delta
SET
    processing_status = 'ERROR',
    error_message = 'Invalid phone number: must be E.164 format',
    updated_ts = SYSDATETIMEOFFSET()
WHERE file_batch_id = 'a1b2c3d4-...' AND row_id = 1;
```

**If Validation Succeeds:**
```sql
UPDATE engage360_stg.stg_device_activation_delta
SET processing_status = 'VALIDATED'
WHERE file_batch_id = 'a1b2c3d4-...' AND processing_status = 'STAGING';
```

**Logs:**
```
🔍 [DEVICE-ACTIVATION] Phase 3: Validating 1 rows...
✅ [DEVICE-ACTIVATION] Validation complete: 1 passed, 0 failed
```

---

#### Phase 4: Transform & Load to Core Tables

**What Happens:**
1. **Upsert Members** (`engage360.members`)
2. **Upsert Devices** (`engage360.member_devices`)
3. **Upsert Member Identifiers** (`engage360.member_identifiers`)
4. **Process Enrollments** (based on enrollment_status)

##### 4.1: Upsert Members

**MERGE Logic:**
```sql
MERGE engage360.members AS tgt
USING (
    SELECT DISTINCT
        org_id,
        salesforce_account_number,
        salesforce_account_id,  -- NEW for Operations
        first_name,
        last_name,
        primary_phone,
        email,
        dob,
        timezone,
        language_pref,
        service_address,
        city,
        state,
        zip,
        'US' AS address_country  -- Default
    FROM engage360_stg.stg_device_activation_delta
    WHERE file_batch_id = 'a1b2c3d4-...'
      AND processing_status = 'VALIDATED'
) AS src
ON (tgt.org_id = src.org_id AND tgt.salesforce_account_number = src.salesforce_account_number)
WHEN MATCHED THEN
    UPDATE SET
        tgt.salesforce_account_id = ISNULL(src.salesforce_account_id, tgt.salesforce_account_id),
        tgt.first_name = ISNULL(src.first_name, tgt.first_name),
        tgt.last_name = ISNULL(src.last_name, tgt.last_name),
        tgt.primary_phone = ISNULL(src.primary_phone, tgt.primary_phone),
        tgt.email = ISNULL(src.email, tgt.email),
        tgt.timezone = ISNULL(src.timezone, tgt.timezone),
        tgt.updated_ts = SYSDATETIMEOFFSET()
WHEN NOT MATCHED THEN
    INSERT (member_id, org_id, salesforce_account_number, salesforce_account_id, first_name, last_name, primary_phone, email, dob, timezone, language_pref, address_street, address_city, address_state, address_zip, address_country, created_ts)
    VALUES (NEWID(), src.org_id, src.salesforce_account_number, src.salesforce_account_id, src.first_name, src.last_name, src.primary_phone, src.email, src.dob, src.timezone, src.language_pref, src.service_address, src.city, src.state, src.zip, src.address_country, SYSDATETIMEOFFSET());
```

**Result:**
- New member created OR existing member updated
- `member_id` (UUID) generated for new members
- Salesforce Account ID stored

**Logs:**
```
💾 [DEVICE-ACTIVATION] Phase 4.1: Upserting members...
✅ [DEVICE-ACTIVATION] Members upserted: 1 inserted, 0 updated
```

---

##### 4.2: Upsert Member Identifiers

**Purpose:** Store monitoring_system_id in separate table

**MERGE Logic:**
```sql
MERGE engage360.member_identifiers AS tgt
USING (
    SELECT
        m.member_id,
        'monitoring_system_id' AS id_type,
        stg.monitoring_system_id AS id_value
    FROM engage360_stg.stg_device_activation_delta stg
    JOIN engage360.members m
        ON m.salesforce_account_number = stg.salesforce_account_number
        AND m.org_id = stg.org_id
    WHERE stg.file_batch_id = 'a1b2c3d4-...'
      AND stg.processing_status = 'VALIDATED'
      AND stg.monitoring_system_id IS NOT NULL
) AS src
ON tgt.member_id = src.member_id AND tgt.id_type = src.id_type
WHEN MATCHED THEN
    UPDATE SET
        tgt.id_value = src.id_value,
        tgt.updated_ts = SYSDATETIMEOFFSET()
WHEN NOT MATCHED THEN
    INSERT (member_identifier_id, member_id, id_type, id_value, created_ts)
    VALUES (NEWID(), src.member_id, src.id_type, src.id_value, SYSDATETIMEOFFSET());
```

**Result:**
- monitoring_system_id stored in member_identifiers table
- Can have multiple identifier types per member

**Example Record:**
```
member_identifier_id: uuid-123
member_id: member-uuid-456
id_type: monitoring_system_id
id_value: a3lR3000000a9XpIAI
```

**Logs:**
```
💾 [DEVICE-ACTIVATION] Phase 4.2: Upserting member identifiers...
✅ [DEVICE-ACTIVATION] Member identifiers upserted: 1 records
```

---

##### 4.3: Upsert Devices

**MERGE Logic:**
```sql
MERGE engage360.member_devices AS tgt
USING (
    SELECT DISTINCT
        m.member_id,
        stg.device_udi,
        stg.device_name,
        stg.brand,
        stg.device_phone_number,
        stg.is_device_callable,
        stg.delivery_date,
        stg.fall_detection_status,
        stg.battery_status
    FROM engage360_stg.stg_device_activation_delta stg
    JOIN engage360.members m
        ON m.salesforce_account_number = stg.salesforce_account_number
        AND m.org_id = stg.org_id
    WHERE stg.file_batch_id = 'a1b2c3d4-...'
      AND stg.processing_status = 'VALIDATED'
) AS src
ON (tgt.member_id = src.member_id AND tgt.device_udi = src.device_udi)
WHEN MATCHED THEN
    UPDATE SET
        tgt.device_name = ISNULL(src.device_name, tgt.device_name),
        tgt.device_phone_number = ISNULL(src.device_phone_number, tgt.device_phone_number),
        tgt.fall_detection_status = ISNULL(src.fall_detection_status, tgt.fall_detection_status),
        tgt.battery_status = ISNULL(src.battery_status, tgt.battery_status),
        tgt.updated_ts = SYSDATETIMEOFFSET()
WHEN NOT MATCHED THEN
    INSERT (device_id, member_id, device_udi, device_name, brand, device_phone_number, is_device_callable, delivery_date, fall_detection_status, battery_status, created_ts)
    VALUES (NEWID(), src.member_id, src.device_udi, src.device_name, src.brand, src.device_phone_number, src.is_device_callable, src.delivery_date, src.fall_detection_status, src.battery_status, SYSDATETIMEOFFSET());
```

**Result:**
- Device record created or updated
- `device_id` (UUID) generated for new devices

**Logs:**
```
💾 [DEVICE-ACTIVATION] Phase 4.3: Upserting devices...
✅ [DEVICE-ACTIVATION] Devices upserted: 1 inserted, 0 updated
```

---

##### 4.4: Process Enrollments

**Based on enrollment_status column:**

###### Scenario A: enrollment_status = "enrolled"

**What Happens:**
1. Check if member already enrolled in campaign
2. If NOT enrolled → Create new enrollment
3. If enrolled as UNENROLLED → Reactivate (set status back to ENROLLED)
4. Calculate activation_start_date (delivery_date + 2 business days)
5. Calculate campaign_end_date (activation_start_date + 90 days)

**MERGE Logic:**
```sql
MERGE engage360.member_campaign_enrollments_enhanced AS tgt
USING (
    SELECT
        m.member_id,
        '0F69659B-491B-40E2-88C3-ABC7D87385B2' AS campaign_id,
        'ENROLLED' AS current_status,
        -- Calculate Day 2 (delivery_date + 2 business days)
        dbo.AddBusinessDays(md.delivery_date, 2) AS activation_start_date,
        -- Calculate 90-day end date
        DATEADD(DAY, 90, dbo.AddBusinessDays(md.delivery_date, 2)) AS campaign_end_date,
        'Medicaid' AS customer_type,
        0 AS device_activated,
        SYSDATETIMEOFFSET() AS enrollment_ts
    FROM engage360.members m
    JOIN engage360.member_devices md ON m.member_id = md.member_id
    WHERE m.salesforce_account_number = '5743441'
) AS src
ON tgt.member_id = src.member_id AND tgt.campaign_id = src.campaign_id
WHEN MATCHED AND tgt.current_status = 'UNENROLLED' THEN
    -- Reactivate
    UPDATE SET
        tgt.current_status = 'ENROLLED',
        tgt.device_activated = 0,
        tgt.updated_ts = SYSDATETIMEOFFSET()
WHEN NOT MATCHED THEN
    -- New enrollment
    INSERT (enrollment_id, member_id, campaign_id, current_status, enrollment_ts, activation_start_date, campaign_end_date, customer_type, device_activated, created_ts)
    VALUES (NEWID(), src.member_id, src.campaign_id, src.current_status, src.enrollment_ts, src.activation_start_date, src.campaign_end_date, src.customer_type, src.device_activated, SYSDATETIMEOFFSET());
```

**Example Result:**
```
enrollment_id: enrollment-uuid-789
member_id: member-uuid-456
campaign_id: 0F69659B-491B-40E2-88C3-ABC7D87385B2
current_status: ENROLLED
enrollment_ts: 2025-12-18 10:00:00.000 +00:00
activation_start_date: 2025-12-20 09:00:00.000 -06:00  (delivery_date + 2 business days)
campaign_end_date: 2026-03-20 09:00:00.000 -05:00  (activation_start_date + 90 days)
customer_type: Medicaid
device_activated: 0
```

**Logs:**
```
📝 [DEVICE-ACTIVATION] Processing ENROLLED members: 1 records
✅ [DEVICE-ACTIVATION] Enrollments created: 1 inserted, 0 reactivated
```

---

###### Scenario B: enrollment_status = "unenrolled"

**What Happens:**
1. Find existing enrollment
2. Update status to UNENROLLED
3. Log reason in member_enrollment_status_history

**UPDATE Logic:**
```sql
UPDATE engage360.member_campaign_enrollments_enhanced
SET
    current_status = 'UNENROLLED',
    unenrollment_reason = stg.unenrollment_reason,
    updated_ts = SYSDATETIMEOFFSET()
FROM engage360.member_campaign_enrollments_enhanced mce
JOIN engage360.members m ON mce.member_id = m.member_id
JOIN engage360_stg.stg_device_activation_delta stg
    ON m.salesforce_account_number = stg.salesforce_account_number
WHERE stg.file_batch_id = 'a1b2c3d4-...'
  AND stg.enrollment_status = 'unenrolled'
  AND mce.campaign_id = '0F69659B-491B-40E2-88C3-ABC7D87385B2';
```

**Logs:**
```
📝 [DEVICE-ACTIVATION] Processing UNENROLLED members: 1 records
✅ [DEVICE-ACTIVATION] Members unenrolled: 1 updated
```

---

###### Scenario C: enrollment_status = "updated"

**What Happens:**
1. Update member demographics (already done in member upsert)
2. Update device information (already done in device upsert)
3. No enrollment status change

**Logs:**
```
📝 [DEVICE-ACTIVATION] Processing UPDATED members: 1 records
✅ [DEVICE-ACTIVATION] Member information updated (no enrollment change)
```

---

#### Phase 5: Audit & Finalization

**What Happens:**
1. Mark staging records as COMPLETE
2. Move file from `landing/` to `processed/`
3. Log summary to Application Insights

**UPDATE Staging:**
```sql
UPDATE engage360_stg.stg_device_activation_delta
SET processing_status = 'COMPLETE'
WHERE file_batch_id = 'a1b2c3d4-...'
  AND processing_status = 'VALIDATED';
```

**File Movement:**
```
FROM: fs-ops/landing/MedicalGuardian_DeviceActivationMedicaid_20251218_DELTA.csv
TO:   fs-ops/processed/MedicalGuardian_DeviceActivationMedicaid_20251218_DELTA.csv
```

**Logs:**
```
✅ [DEVICE-ACTIVATION] Phase 5: All records processed successfully
📊 [DEVICE-ACTIVATION] Processing summary:
   - Total rows: 1
   - Successful: 1
   - Failed: 0
   - Members upserted: 1
   - Devices upserted: 1
   - Enrollments created: 1
✨ [OPS-DEVICE-ACTIVATION] File will be moved to fs-ops/processed/
✅ [OPS-DEVICE-ACTIVATION] File processing completed successfully
```

---

## Phase 2: Enrollment Creation

**Result of File Processing:**

Member Barbara McDaniel is now enrolled:

```
Table: engage360.member_campaign_enrollments_enhanced

enrollment_id: e1b2c3d4-5678-90ab-cdef-1234567890ab
member_id: m9876543-210f-edcb-a987-6543210fedcb
campaign_id: 0F69659B-491B-40E2-88C3-ABC7D87385B2  (Medicaid)
current_status: ENROLLED
enrollment_ts: 2025-12-18 10:00:00.000 +00:00
activation_start_date: 2025-12-20 09:00:00.000 -06:00  (Day 2: delivery + 2 business days)
campaign_end_date: 2026-03-20 09:00:00.000 -05:00  (Day 92: activation_start + 90 days)
customer_type: Medicaid
device_activated: 0
created_ts: 2025-12-18 10:00:00.000 +00:00
```

**Status:** Waiting for Day 2 (activation_start_date)

---

## Phase 3: Scheduler Eligibility Check

### When Does Scheduler Run?

**Timer Trigger:** Every 15 minutes

**Schedule:** `0 */15 * * * *` (Azure CRON format)

**Run Times:**
- 9:00 AM, 9:15 AM, 9:30 AM, 9:45 AM
- 10:00 AM, 10:15 AM, 10:30 AM, 10:45 AM
- ... every 15 minutes, 24/7

**Function:** `timer_device_activation`

**Location:** `functions/device_activation_scheduler.py`

---

### Step 3.1: Scheduler Wakes Up

**Trigger Time:** 2025-12-20 09:15:00 AM CST (Day 2, first check after activation_start_date)

**Logs:**
```
⏰ [TIMER] Device Activation Scheduler TRIGGERED
🕐 [TIMER] Current time (UTC): 2025-12-20 15:15:00.000 +00:00
```

**What Happens:**
```python
def timer_device_activation(timer: func.TimerRequest):
    # Initialize services
    config_manager = ConfigManager()
    db_service = DatabaseService(config_manager)
    eligibility_service = EligibilityService(db_service)
    batch_orchestrator = BatchOrchestrator(db_service, config_manager)

    # Execute main logic
    result = create_device_activation_batch(eligibility_service, batch_orchestrator)
```

---

### Step 3.2: Eligibility Query Execution

**Function:** `get_eligible_members()`

**Location:** `af_code/device_activation_scheduler/services/eligibility_service.py`

**SQL Query:** `ELIGIBLE_MEMBERS_QUERY` (lines 36-140)

**Key WHERE Clauses:**

```sql
WHERE
    -- 1. Campaign criteria
    (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
    AND c.status = 'Active'

    -- 2. Enrollment status
    AND e.current_status = 'ENROLLED'
    AND e.device_activated = 0

    -- 3. Time window
    AND SYSDATETIMEOFFSET() >= e.activation_start_date  -- Past Day 2
    AND SYSDATETIMEOFFSET() <= e.campaign_end_date      -- Within 90 days

    -- 4. Not in callback queue
    AND NOT EXISTS (
        SELECT 1 FROM engage360.outreach_callback_queue cq
        WHERE cq.enrollment_id = e.enrollment_id
        AND cq.status = 'PENDING'
    )

    -- 5. Call frequency logic
    AND (
        -- Call 1: No previous attempts
        NOT EXISTS (
            SELECT 1 FROM engage360.outreach_attempts oa
            WHERE oa.enrollment_id = e.enrollment_id
        )
        OR
        -- Call 2-3: 2 business days since last attempt
        (
            (SELECT COUNT(*) FROM engage360.outreach_attempts oa
             WHERE oa.enrollment_id = e.enrollment_id) BETWEEN 1 AND 2
            AND DATEDIFF(day,
                (SELECT MAX(call_start_ts) FROM engage360.outreach_attempts oa
                 WHERE oa.enrollment_id = e.enrollment_id),
                SYSDATETIMEOFFSET()) >= 2
        )
        OR
        -- Call 4: 5 business days since Call 3
        (
            (SELECT COUNT(*) FROM engage360.outreach_attempts oa
             WHERE oa.enrollment_id = e.enrollment_id) = 3
            AND DATEDIFF(day,
                (SELECT MAX(call_start_ts) FROM engage360.outreach_attempts oa
                 WHERE oa.enrollment_id = e.enrollment_id),
                SYSDATETIMEOFFSET()) >= 5
        )
        OR
        -- Call 5+: 7 calendar days since last attempt
        (
            (SELECT COUNT(*) FROM engage360.outreach_attempts oa
             WHERE oa.enrollment_id = e.enrollment_id) >= 4
            AND DATEDIFF(day,
                (SELECT MAX(call_start_ts) FROM engage360.outreach_attempts oa
                 WHERE oa.enrollment_id = e.enrollment_id),
                SYSDATETIMEOFFSET()) >= 7
        )
    )
```

**Query Result for Barbara McDaniel (Call 1):**

```
enrollment_id: e1b2c3d4-5678-90ab-cdef-1234567890ab
member_id: m9876543-210f-edcb-a987-6543210fedcb
campaign_id: 0F69659B-491B-40E2-88C3-ABC7D87385B2
first_name: Barbara
last_name: McDaniel
primary_phone: +18173137409
email: mcdanielbf@gmail.com
timezone: CST
language_pref: EN
device_udi: 457128490
device_name: MGMini
brand: Medical Guardian
device_phone_number: +17182887685
is_device_callable: 1
delivery_date: 2025-12-18
fall_detection_status: False
battery_status: Good
activation_start_date: 2025-12-20 09:00:00.000 -06:00
campaign_end_date: 2026-03-20 09:00:00.000 -05:00
customer_type: Medicaid
campaign_name: Device Activation - Medicaid
operating_tz: America/New_York
operating_start_time: 09:00:00
operating_end_time: 17:00:00
timezone_flag: member_tz
call_attempt_number: 1  (calculated: COUNT(*) from outreach_attempts + 1)
last_attempt_date: NULL  (no previous attempts)
last_disposition: NULL
```

**Logs:**
```
🔍 [ELIGIBILITY-SERVICE] Starting member eligibility query...
📊 [ELIGIBILITY-SERVICE] Found 1 potential members from database
📊 [ELIGIBILITY-SERVICE] Potential members by call attempt:
   Call 1: 1 members
```

---

## Phase 4: Business Hours Validation

### Step 4.1: Dual-Timezone Check

**Function:** `_filter_by_business_hours()`

**Location:** `af_code/device_activation_scheduler/services/eligibility_service.py` (lines 212-274)

**Validation Logic:**

```python
def _filter_by_business_hours(self, potential_members: List[Dict]) -> List[Dict]:
    """
    Validates BOTH:
    1. Medical Guardian operating hours (America/New_York, 9 AM - 5 PM)
    2. Member's local timezone (member.timezone, 9 AM - 5 PM)
    """
    eligible_members = []
    now_utc = datetime.now(pytz.UTC)

    for member in potential_members:
        member_timezone = member.get("timezone")  # "CST"

        # Convert to pytz timezone
        member_tz = pytz.timezone(member_timezone)  # America/Chicago

        # Use dual-timezone validation
        can_call, reason = can_make_call(now_utc, member_tz)

        if can_call:
            eligible_members.append(member)
            logger.info(f"✅ Member {member_id} eligible: {reason}")
        else:
            logger.info(f"⏰ Member {member_id} not eligible: {reason}")

    return eligible_members
```

---

### Step 4.2: Business Hours Utility

**Function:** `can_make_call()`

**Location:** `af_code/shared/business_hours_utils.py`

**Logic:**

```python
def can_make_call(now_utc: datetime, member_tz: pytz.timezone) -> Tuple[bool, str]:
    """
    Dual-timezone business hours validation

    Checks BOTH:
    1. Medical Guardian hours: 9 AM - 5 PM EST
    2. Member hours: 9 AM - 5 PM (member timezone)
    """
    # Convert to Medical Guardian timezone (EST)
    mg_tz = pytz.timezone('America/New_York')
    now_mg = now_utc.astimezone(mg_tz)
    mg_hour = now_mg.hour

    # Check MG hours: 9 AM - 5 PM EST
    if mg_hour < 9:
        return False, f"Before MG operating hours (current: {mg_hour}:00 EST)"
    if mg_hour >= 17:  # 5 PM
        return False, f"After MG operating hours (current: {mg_hour}:00 EST)"

    # Convert to member timezone
    now_member = now_utc.astimezone(member_tz)
    member_hour = now_member.hour

    # Check member hours: 9 AM - 5 PM
    if member_hour < 9:
        return False, f"Before member business hours (current: {member_hour}:00 {member_tz.zone})"
    if member_hour >= 17:  # 5 PM
        return False, f"After member business hours (current: {member_hour}:00 {member_tz.zone})"

    # Check day of week (Mon-Fri)
    if now_member.weekday() >= 5:  # Saturday=5, Sunday=6
        return False, "Weekend - no calls"

    return True, f"Within business hours (MG: {mg_hour}:00 EST, Member: {member_hour}:00 {member_tz.zone})"
```

---

### Step 4.3: Example Validation

**Current Time:** 2025-12-20 09:15:00 AM CST (Friday)

**Conversions:**
- UTC: 2025-12-20 15:15:00 +00:00
- EST (Medical Guardian): 2025-12-20 10:15:00 AM -05:00
- CST (Barbara's timezone): 2025-12-20 09:15:00 AM -06:00

**Validation Steps:**

1. **Check MG Hours (9 AM - 5 PM EST)**
   - Current MG time: 10:15 AM EST
   - ✅ Within range (9 AM - 5 PM)

2. **Check Member Hours (9 AM - 5 PM CST)**
   - Current member time: 09:15 AM CST
   - ✅ Within range (9 AM - 5 PM)

3. **Check Day of Week**
   - Friday (weekday = 4)
   - ✅ Not weekend

**Result:** ✅ Can make call

**Logs:**
```
⏰ [ELIGIBILITY-SERVICE] Validating business hours for 1 members...
⏰ [ELIGIBILITY-SERVICE] Checking member m9876543-... (timezone: CST, mode: member_tz)
✅ [ELIGIBILITY-SERVICE] Member m9876543-... eligible: Within business hours (MG: 10:00 EST, Member: 09:00 CST)
✅ [ELIGIBILITY-SERVICE] 1/1 members passed business hours validation
✅ [ELIGIBILITY-SERVICE] 1 members eligible after business hours validation
```

---

### Step 4.4: Counter-Examples (When Calls DON'T Happen)

#### Example 1: Too Early in Member Timezone

**Current Time:** 2025-12-20 08:45:00 AM CST

**Conversions:**
- UTC: 2025-12-20 14:45:00 +00:00
- EST (MG): 2025-12-20 09:45:00 AM -05:00 ✅
- CST (Member): 2025-12-20 08:45:00 AM -06:00 ❌

**Result:** ❌ Cannot call - Before member business hours

**Logs:**
```
⏰ [ELIGIBILITY-SERVICE] Member m9876543-... not eligible: Before member business hours (current: 08:00 CST)
```

---

#### Example 2: Too Late for MG

**Current Time:** 2025-12-20 04:15:00 PM EST

**Conversions:**
- UTC: 2025-12-20 21:15:00 +00:00
- EST (MG): 2025-12-20 04:15:00 PM -05:00 ❌
- CST (Member): 2025-12-20 03:15:00 PM -06:00 ✅

**Result:** ❌ Cannot call - After MG operating hours (5 PM cutoff)

**Logs:**
```
⏰ [ELIGIBILITY-SERVICE] Member m9876543-... not eligible: After MG operating hours (current: 16:00 EST)
```

---

#### Example 3: Weekend

**Current Time:** 2025-12-21 10:00:00 AM CST (Saturday)

**Result:** ❌ Cannot call - Weekend

**Logs:**
```
⏰ [ELIGIBILITY-SERVICE] Member m9876543-... not eligible: Weekend - no calls
```

---

## Phase 5: Batch Creation & Bland AI Submission

### Step 5.1: Batch Orchestrator Preparation

**Function:** `create_device_activation_batch()`

**Location:** `af_code/device_activation_scheduler/main_logic.py`

**Input:** List of 1 eligible member (Barbara McDaniel)

**What Happens:**
```python
def create_device_activation_batch(eligibility_service, batch_orchestrator, force=False):
    # 1. Get eligible members
    eligible_members = eligibility_service.get_eligible_members()

    if not eligible_members and not force:
        logger.info("ℹ️ No eligible members found")
        return {"success": True, "message": "No eligible members", "total_eligible": 0}

    # 2. Create batch
    result = batch_orchestrator.create_and_submit_batch(eligible_members)

    return result
```

---

### Step 5.2: Create Batch Record

**Function:** `create_and_submit_batch()`

**Location:** `af_code/device_activation_scheduler/services/batch_orchestrator.py`

**Step 1: Generate Batch ID**
```python
batch_id = str(uuid.uuid4())  # e.g., "b1234567-89ab-cdef-0123-456789abcdef"
campaign_id = eligible_members[0].get("campaign_id")  # "0F69659B-491B-40E2-88C3-ABC7D87385B2"
```

**Step 2: Insert Batch Record**
```sql
INSERT INTO engage360.outreach_batches (
    batch_id,
    campaign_id,
    batch_status,
    total_calls_intended,
    created_ts
) VALUES (
    'b1234567-89ab-cdef-0123-456789abcdef',
    '0F69659B-491B-40E2-88C3-ABC7D87385B2',
    'Pending',
    1,  -- Barbara McDaniel
    SYSDATETIMEOFFSET()
);
```

**Result:**
```
Table: engage360.outreach_batches

batch_id: b1234567-89ab-cdef-0123-456789abcdef
campaign_id: 0F69659B-491B-40E2-88C3-ABC7D87385B2
batch_status: Pending
total_calls_intended: 1
vendor_batch_id: NULL  (will be updated after Bland AI submission)
created_ts: 2025-12-20 15:15:00.000 +00:00
```

**Logs:**
```
📋 [BATCH-ORCH] Creating batch for 1 eligible members
📋 [BATCH-ORCH] Batch ID: b1234567-89ab-cdef-0123-456789abcdef
📋 [BATCH-ORCH] Campaign ID: 0F69659B-491B-40E2-88C3-ABC7D87385B2
```

---

### Step 5.3: Create Attempt Records

**Step 1: Generate Attempt IDs**
```python
for member in eligible_members:
    attempt_id = str(uuid.uuid4())  # e.g., "a7654321-dcba-9876-5432-10fedcba9876"
    enrollment_id = member.get("enrollment_id")
```

**Step 2: Insert Attempt Records**
```sql
INSERT INTO engage360.outreach_attempts (
    attempt_id,
    enrollment_id,
    batch_id,
    channel,
    attempt_ts,
    disposition,
    retry_seq
) VALUES (
    'a7654321-dcba-9876-5432-10fedcba9876',
    'e1b2c3d4-5678-90ab-cdef-1234567890ab',  -- Barbara's enrollment
    'b1234567-89ab-cdef-0123-456789abcdef',
    'Voice',
    SYSUTCDATETIME(),
    'Pending',
    0  -- First attempt in this sequence
);
```

**Result:**
```
Table: engage360.outreach_attempts

attempt_id: a7654321-dcba-9876-5432-10fedcba9876
enrollment_id: e1b2c3d4-5678-90ab-cdef-1234567890ab
batch_id: b1234567-89ab-cdef-0123-456789abcdef
channel: Voice
attempt_ts: 2025-12-20 15:15:00.000 +00:00
call_start_ts: NULL  (will be updated by webhook)
call_end_ts: NULL
disposition: Pending
retry_seq: 0
created_ts: 2025-12-20 15:15:00.000 +00:00
```

**Logs:**
```
📝 [BATCH-ORCH] Creating attempt records for 1 members
✅ [BATCH-ORCH] Attempt records created: 1 inserted
```

---

### Step 5.4: Fetch Bland AI Configuration

**Query:**
```sql
SELECT bland_parameters_global
FROM engage360.campaign_call_configs_enhanced
WHERE campaign_id = '0F69659B-491B-40E2-88C3-ABC7D87385B2'
  AND config_status = 'active';
```

**Result:**
```json
{
  "from": "+18336000078",
  "model": "base",
  "voice": "bc97a31e-b0b8-49e5-bcb8-393fcc6a86ea",
  "record": true,
  "endpoint": "https://api.bland.ai",
  "language": "auto",
  "pathway_id": "323f8d52-6e30-459c-9f71-e395b3c3ba69",
  "pathway_version": 0,
  "max_duration": 12,
  "background_track": "office",
  "voicemail_action": "leave_message",
  "voicemail_message": "Hi there, this is Grace calling from Medical Guardian. I'm trying to reach {{first_name}} {{last_name}} to assist with device activation. I'll try calling back later, goodbye!",
  "wait_for_greeting": false,
  "noise_cancellation": true,
  "answered_by_enabled": true,
  "block_interruptions": false,
  "interruption_threshold": 400,
  "sensitive_voicemail_detection": true,
  "use_batch": true,
  "timezone": "America/New_York",
  "webhook": "https://ioe-function-e2g7e6d4e6hme4ge.eastus2-01.azurewebsites.net/api/bland-ai-webhook?code=3IlwYsB3O4Ie8jcZegOouI_Fj1nf4N-5K_cGMJpmQBy8AzFuR9syPQ%3D%3D"
}
```

**Extract Values:**
```python
pathway_id = "323f8d52-6e30-459c-9f71-e395b3c3ba69"
voice = "bc97a31e-b0b8-49e5-bcb8-393fcc6a86ea"
```

**Logs:**
```
🎯 [BATCH-ORCH] Using Bland AI config: pathway_id=323f8d52-..., voice=bc97a31e-...
```

---

### Step 5.5: Build Bland AI Batch Payload

**Structure:**
```json
{
  "base_prompt": "default",
  "model": "base",
  "voice": "bc97a31e-b0b8-49e5-bcb8-393fcc6a86ea",
  "pathway_id": "323f8d52-6e30-459c-9f71-e395b3c3ba69",
  "pathway_version": 0,
  "max_duration": 12,
  "background_track": "office",
  "voicemail_action": "leave_message",
  "voicemail_message": "Hi there, this is Grace calling from Medical Guardian. I'm trying to reach {{first_name}} {{last_name}} to assist with device activation. I'll try calling back later, goodbye!",
  "wait_for_greeting": false,
  "noise_cancellation": true,
  "answered_by_enabled": true,
  "block_interruptions": false,
  "interruption_threshold": 400,
  "sensitive_voicemail_detection": true,
  "timezone": "America/New_York",
  "from": "+18336000078",
  "webhook": "https://ioe-function-e2g7e6d4e6hme4ge.eastus2-01.azurewebsites.net/api/bland-ai-webhook?code=3IlwYsB3O4Ie8jcZegOouI_Fj1nf4N-5K_cGMJpmQBy8AzFuR9syPQ%3D%3D",
  "calls": [
    {
      "phone_number": "+18173137409",
      "request_data": {
        "first_name": "Barbara",
        "last_name": "McDaniel",
        "primary_phone": "+18173137409",
        "email": "barbara.mcdaniel@example.com",
        "dob": "12-16-1935",
        "address_street": "4424 Overton Crest St",
        "address_city": "Fort Worth",
        "address_state": "TX",
        "address_zip": "76109",
        "member_brand": "Medical Guardian",
        "device_name": "MGMini",
        "fall_detection": "False",
        "powersaver_mode": "Standard",
        "monitoring_system_id": "MG457128490"
      },
      "metadata": {
        "batch_id": "b1234567-89ab-cdef-0123-456789abcdef",
        "campaign_id": "0F69659B-491B-40E2-88C3-ABC7D87385B2",
        "campaign_type": "Operations",
        "campaign_name": "Device Activation - Medicaid",
        "pathway_id": "323f8d52-6e30-459c-9f71-e395b3c3ba69",
        "attempt_id": "a7654321-dcba-9876-5432-10fedcba9876",
        "member_id": "m9876543-210f-edcb-a987-6543210fedcb",
        "enrollment_id": "e1b2c3d4-5678-90ab-cdef-1234567890ab",
        "salesforce_account_number": "5743441",
        "first_name": "Barbara",
        "last_name": "McDaniel",
        "primary_phone": "+18173137409",
        "timezone": "CST",
        "call_attempt_number": "1",
        "customer_type": "Medicaid"
      }
    }
  ]
}
```

**Key Fields Explanation:**

- **pathway_id**: Bland AI conversational flow for device activation
- **voice**: Grace's voice ID
- **phone_number**: Barbara's phone (+18173137409)
- **request_data**: Variables available in the conversation (name, address, device info)
- **metadata**: Our tracking info (attempt_id, member_id, campaign_id, etc.)
- **webhook**: Where Bland AI sends call results

---

### Step 5.6: Submit to Bland AI API

**API Endpoint:** `POST https://api.bland.ai/v2/batches/create`

**Headers:**
```
Authorization: <BLAND_AI_API_KEY>
encrypted_key: <TWILIO_ENCRYPTION_KEY>
Content-Type: application/json
```

**Request:**
```python
response = requests.post(
    "https://api.bland.ai/v2/batches/create",
    headers=headers,
    json=batch_payload
)
```

**Bland AI Response (Success):**
```json
{
  "status": "success",
  "batch_id": "bland-batch-xyz789",
  "calls_submitted": 1,
  "message": "Batch created successfully"
}
```

**Logs:**
```
🚀 [BATCH-ORCH] Submitting batch to Bland AI...
📡 [BATCH-ORCH] API Endpoint: https://api.bland.ai/v2/batches/create
📋 [BATCH-ORCH] Payload size: 1 calls
✅ [BATCH-ORCH] Batch submitted successfully
📋 [BATCH-ORCH] Bland AI batch_id: bland-batch-xyz789
```

---

### Step 5.7: Update Batch Record with vendor_batch_id

**UPDATE Query:**
```sql
UPDATE engage360.outreach_batches
SET
    vendor_batch_id = 'bland-batch-xyz789',
    batch_status = 'Submitted',
    updated_ts = SYSDATETIMEOFFSET()
WHERE batch_id = 'b1234567-89ab-cdef-0123-456789abcdef';
```

**Result:**
```
Table: engage360.outreach_batches

batch_id: b1234567-89ab-cdef-0123-456789abcdef
campaign_id: 0F69659B-491B-40E2-88C3-ABC7D87385B2
batch_status: Submitted  (changed from Pending)
total_calls_intended: 1
vendor_batch_id: bland-batch-xyz789  (added)
created_ts: 2025-12-20 15:15:00.000 +00:00
updated_ts: 2025-12-20 15:15:05.000 +00:00
```

**Final Scheduler Logs:**
```
✅ [BATCH-ORCH] Batch record updated with vendor_batch_id
✅ [TIMER] Device Activation batch creation SUCCEEDED
📊 [TIMER] Summary: 1 eligible, 1 batches created, 1 calls submitted
⏰ [TIMER] Device Activation Scheduler COMPLETED
```

---

## Phase 6: Call Execution & Webhook Processing

### Step 6.1: Bland AI Makes the Call

**Time:** 2025-12-20 09:20:00 AM CST (few minutes after batch submission)

**What Happens:**
1. Bland AI dials Barbara's phone: +18173137409
2. Caller ID shows: +18336000078 (Medical Guardian)
3. Call connects (or goes to voicemail)
4. Grace (AI voice) begins conversation using pathway_id: 323f8d52-...

**Call Flow (Successful Connection):**

```
Grace: "Hi, is this Barbara?"
Barbara: "Yes, this is Barbara."
Grace: "Hi Barbara, this is Grace calling from Medical Guardian. I'm reaching out to help you activate your new MGMini device. Do you have a few minutes to talk?"
Barbara: "Sure, I do."
Grace: "Great! I see your device was delivered on December 18th. Have you had a chance to unpack it yet?"
Barbara: "Yes, I have it here."
Grace: "Wonderful! Let's get it activated. First, can you press the button on the device for me?"
... [conversation continues following pathway logic] ...
Grace: "Perfect! Your device is now activated. Is there anything else I can help you with today?"
Barbara: "No, that's all. Thank you!"
Grace: "You're welcome, Barbara! Have a great day!"
```

**Call Duration:** 5 minutes 32 seconds

---

### Step 6.2: Bland AI Sends Webhook

**Time:** 2025-12-20 09:25:32 AM CST (immediately after call ends)

**Webhook Endpoint:** `POST https://ioe-function-e2g7e6d4e6hme4ge.eastus2-01.azurewebsites.net/api/bland-ai-webhook?code=...`

**Webhook Payload:**
```json
{
  "call_id": "bland-call-abc123",
  "batch_id": "bland-batch-xyz789",
  "to": "+18173137409",
  "from": "+18336000078",
  "status": "completed",
  "answered_by": "human",
  "call_length": 332,
  "recording_url": "https://storage.bland.ai/recordings/bland-call-abc123.mp3",
  "transcripts": [
    {
      "text": "Hi, is this Barbara?",
      "user": "assistant"
    },
    {
      "text": "Yes, this is Barbara.",
      "user": "user"
    }
    // ... full conversation transcript ...
  ],
  "analysis": {
    "call_successful": true,
    "summary": "Successfully activated member's MGMini device. Member confirmed device is working properly.",
    "disposition": "DEVICE_ACTIVATED"
  },
  "metadata": {
    "batch_id": "b1234567-89ab-cdef-0123-456789abcdef",
    "campaign_id": "0F69659B-491B-40E2-88C3-ABC7D87385B2",
    "campaign_type": "Operations",
    "campaign_name": "Device Activation - Medicaid",
    "pathway_id": "323f8d52-6e30-459c-9f71-e395b3c3ba69",
    "attempt_id": "a7654321-dcba-9876-5432-10fedcba9876",
    "member_id": "m9876543-210f-edcb-a987-6543210fedcb",
    "enrollment_id": "e1b2c3d4-5678-90ab-cdef-1234567890ab",
    "salesforce_account_number": "5743441",
    "first_name": "Barbara",
    "last_name": "McDaniel",
    "call_attempt_number": "1",
    "customer_type": "Medicaid"
  },
  "price": 0.08,
  "started_at": "2025-12-20T15:20:00.000Z",
  "completed_at": "2025-12-20T15:25:32.000Z"
}
```

---

### Step 6.3: Webhook Function Receives Payload

**Function:** `bland_ai_webhook`

**Location:** `functions/bland_ai_webhook.py`

**Trigger:** HTTP POST request from Bland AI

**Logs:**
```
🌐 [WEBHOOK] Bland AI webhook TRIGGERED
📨 [WEBHOOK] Received webhook for call_id: bland-call-abc123
📋 [WEBHOOK] Batch ID: bland-batch-xyz789
📋 [WEBHOOK] Status: completed
📋 [WEBHOOK] Disposition: DEVICE_ACTIVATED
```

---

### Step 6.4: Webhook Processing Steps

#### Step 1: Duplicate Detection

**Check if call_id already processed:**
```sql
SELECT call_id
FROM engage360.bland_call_logs
WHERE call_id = 'bland-call-abc123';
```

**Result:** Not found (first time receiving this call)

**Logs:**
```
🔍 [WEBHOOK] Checking for duplicate call_id...
✅ [WEBHOOK] Call is unique, proceeding with processing
```

---

#### Step 2: Insert Bland Call Log

**Table:** `engage360.bland_call_logs`

```sql
INSERT INTO engage360.bland_call_logs (
    call_id,
    batch_id,
    vendor_batch_id,
    from_number,
    to_number,
    call_status,
    answered_by,
    call_length,
    recording_url,
    transcript,
    analysis_summary,
    analysis_disposition,
    price,
    started_at,
    completed_at,
    metadata,
    created_ts
) VALUES (
    'bland-call-abc123',
    'b1234567-89ab-cdef-0123-456789abcdef',
    'bland-batch-xyz789',
    '+18336000078',
    '+18173137409',
    'completed',
    'human',
    332,
    'https://storage.bland.ai/recordings/bland-call-abc123.mp3',
    '[{"text":"Hi, is this Barbara?","user":"assistant"}...]',
    'Successfully activated member''s MGMini device. Member confirmed device is working properly.',
    'DEVICE_ACTIVATED',
    0.08,
    '2025-12-20 15:20:00.000 +00:00',
    '2025-12-20 15:25:32.000 +00:00',
    '{"campaign_id":"0F69659B-491B-40E2-88C3-ABC7D87385B2",...}',
    SYSDATETIMEOFFSET()
);
```

**Logs:**
```
💾 [WEBHOOK] Inserting call log record...
✅ [WEBHOOK] Call log inserted: bland-call-abc123
```

---

#### Step 3: Map Disposition to Internal Status

**Function:** `StatusMapper.map_disposition()`

**Location:** `af_code/bland_ai_webhook/services/status_mapper.py`

**Mapping Logic:**
```python
DISPOSITION_MAP = {
    "DEVICE_ACTIVATED": ("Completed", "Close"),
    "INTERESTED": ("Completed", "Follow_Up"),
    "NOT_INTERESTED": ("Completed", "Close"),
    "NO_ANSWER": ("NoAnswer", "Retry"),
    "VOICEMAIL": ("NoAnswer", "Retry"),
    "BUSY": ("Failed", "Retry"),
    "FAILED": ("Failed", "Retry"),
    "DO_NOT_CONTACT": ("OptOut", "Close"),
    # ... other dispositions
}

def map_disposition(bland_disposition: str) -> Tuple[str, str]:
    return DISPOSITION_MAP.get(bland_disposition, ("Failed", "Retry"))
```

**For "DEVICE_ACTIVATED":**
- Internal disposition: **"Completed"**
- Action: **"Close"**

**Logs:**
```
🔄 [WEBHOOK] Mapping disposition: DEVICE_ACTIVATED
✅ [WEBHOOK] Internal disposition: Completed, Action: Close
```

---

#### Step 4: Update Attempt Record

**Table:** `engage360.outreach_attempts`

```sql
UPDATE engage360.outreach_attempts
SET
    call_start_ts = '2025-12-20 15:20:00.000 +00:00',
    call_end_ts = '2025-12-20 15:25:32.000 +00:00',
    disposition = 'Completed',
    call_length = 332,
    recording_url = 'https://storage.bland.ai/recordings/bland-call-abc123.mp3',
    transcript = '[{"text":"Hi, is this Barbara?","user":"assistant"}...]',
    analysis_summary = 'Successfully activated member''s MGMini device...',
    updated_ts = SYSDATETIMEOFFSET()
WHERE attempt_id = 'a7654321-dcba-9876-5432-10fedcba9876';
```

**Result:**
```
Table: engage360.outreach_attempts

attempt_id: a7654321-dcba-9876-5432-10fedcba9876
enrollment_id: e1b2c3d4-5678-90ab-cdef-1234567890ab
batch_id: b1234567-89ab-cdef-0123-456789abcdef
channel: Voice
attempt_ts: 2025-12-20 15:15:00.000 +00:00
call_start_ts: 2025-12-20 15:20:00.000 +00:00  (updated)
call_end_ts: 2025-12-20 15:25:32.000 +00:00  (updated)
disposition: Completed  (updated from Pending)
call_length: 332  (updated)
recording_url: https://storage.bland.ai/recordings/...  (updated)
retry_seq: 0
```

**Logs:**
```
📝 [WEBHOOK] Updating attempt record...
✅ [WEBHOOK] Attempt updated: disposition=Completed
```

---

#### Step 5: Update Enrollment Status

**For Device Activation campaigns with disposition "DEVICE_ACTIVATED":**

**Table:** `engage360.member_campaign_enrollments_enhanced`

```sql
UPDATE engage360.member_campaign_enrollments_enhanced
SET
    current_status = 'COMPLETED',
    device_activated = 1,
    updated_ts = SYSDATETIMEOFFSET()
WHERE enrollment_id = 'e1b2c3d4-5678-90ab-cdef-1234567890ab';
```

**Result:**
```
Table: engage360.member_campaign_enrollments_enhanced

enrollment_id: e1b2c3d4-5678-90ab-cdef-1234567890ab
member_id: m9876543-210f-edcb-a987-6543210fedcb
campaign_id: 0F69659B-491B-40E2-88C3-ABC7D87385B2
current_status: COMPLETED  (changed from ENROLLED)
device_activated: 1  (changed from 0)
enrollment_ts: 2025-12-18 10:00:00.000 +00:00
activation_start_date: 2025-12-20 09:00:00.000 -06:00
campaign_end_date: 2026-03-20 09:00:00.000 -05:00
updated_ts: 2025-12-20 15:25:35.000 +00:00
```

**Logs:**
```
📝 [WEBHOOK] Updating enrollment status...
✅ [WEBHOOK] Enrollment updated: status=COMPLETED, device_activated=1
```

---

#### Step 6: Log Status History

**Table:** `engage360.member_enrollment_status_history`

```sql
INSERT INTO engage360.member_enrollment_status_history (
    history_id,
    enrollment_id,
    previous_status,
    new_status,
    change_reason,
    change_source,
    created_ts
) VALUES (
    NEWID(),
    'e1b2c3d4-5678-90ab-cdef-1234567890ab',
    'ENROLLED',
    'COMPLETED',
    'Device activated via Bland AI call - disposition: DEVICE_ACTIVATED',
    'bland_ai_webhook',
    SYSDATETIMEOFFSET()
);
```

**Logs:**
```
📝 [WEBHOOK] Logging status history...
✅ [WEBHOOK] Status history created
```

---

#### Step 7: Update Batch Status

**Check if all calls in batch completed:**
```sql
SELECT COUNT(*) as total,
       SUM(CASE WHEN disposition = 'Pending' THEN 1 ELSE 0 END) as pending
FROM engage360.outreach_attempts
WHERE batch_id = 'b1234567-89ab-cdef-0123-456789abcdef';
```

**Result:** total=1, pending=0 (all calls completed)

**UPDATE Batch:**
```sql
UPDATE engage360.outreach_batches
SET
    batch_status = 'Completed',
    updated_ts = SYSDATETIMEOFFSET()
WHERE batch_id = 'b1234567-89ab-cdef-0123-456789abcdef';
```

**Logs:**
```
📊 [WEBHOOK] Checking batch completion status...
✅ [WEBHOOK] All calls in batch completed
📝 [WEBHOOK] Updating batch status to Completed
```

---

### Step 6.5: Final Webhook Response

**HTTP Response to Bland AI:**
```json
{
  "success": true,
  "message": "Webhook processed successfully",
  "call_id": "bland-call-abc123",
  "attempt_id": "a7654321-dcba-9876-5432-10fedcba9876",
  "disposition": "Completed"
}
```

**Logs:**
```
✅ [WEBHOOK] Webhook processing COMPLETED
📋 [WEBHOOK] Call ID: bland-call-abc123
📋 [WEBHOOK] Disposition: Completed
📋 [WEBHOOK] Member: Barbara McDaniel
📋 [WEBHOOK] Device activated: YES
🎉 [WEBHOOK] Campaign goal achieved!
```

---

## Call Sequence Scenarios

### Scenario 1: Successful Call 1 (Device Activated)

**Timeline:**
- **Day 0 (Dec 18):** Device delivered, file uploaded
- **Day 2 (Dec 20, 9:15 AM):** Scheduler finds Barbara eligible, creates batch
- **Day 2 (Dec 20, 9:20 AM):** Bland AI calls Barbara
- **Day 2 (Dec 20, 9:25 AM):** Call completes, device activated

**Result:** ✅ Campaign complete, no more calls needed

**Database State:**
- enrollment_id: COMPLETED
- device_activated: 1
- Total attempts: 1

---

### Scenario 2: No Answer on Call 1, Success on Call 2

**Timeline:**

**Call 1 (Day 2):**
- **Day 0 (Dec 18):** Device delivered
- **Day 2 (Dec 20, 9:15 AM):** Scheduler creates batch
- **Day 2 (Dec 20, 9:20 AM):** Barbara doesn't answer
- **Webhook:** disposition = "NO_ANSWER", action = "Retry"

**Database State After Call 1:**
```
enrollment_id: ENROLLED  (no change)
device_activated: 0  (no change)
outreach_attempts: 1 record with disposition='NoAnswer'
```

**Call 2 (Day 4):**
- **Day 2 (Dec 20):** Call 1 - No Answer
- **Day 3 (Dec 21):** Weekend - No calls
- **Day 4 (Dec 23, 9:15 AM):** Scheduler runs, checks eligibility

**Eligibility Check:**
```sql
-- Check call frequency logic
SELECT COUNT(*) FROM engage360.outreach_attempts
WHERE enrollment_id = 'e1b2c3d4-...'
-- Result: 1 attempt

-- Check days since last attempt
SELECT DATEDIFF(day, MAX(call_start_ts), SYSDATETIMEOFFSET())
FROM engage360.outreach_attempts
WHERE enrollment_id = 'e1b2c3d4-...'
-- Result: 3 days (Dec 20 → Dec 23)

-- Eligibility: YES (1 attempt, 3 days >= 2 business days)
```

- **Day 4 (Dec 23, 9:20 AM):** Bland AI calls Barbara again
- **Day 4 (Dec 23, 9:25 AM):** Barbara answers, device activated

**Result:** ✅ Campaign complete after 2 attempts

**Database State:**
- enrollment_id: COMPLETED
- device_activated: 1
- Total attempts: 2

---

### Scenario 3: Multiple Attempts Until Success

**Timeline:**

**Call 1 (Day 2 - Dec 20):** No Answer
**Call 2 (Day 4 - Dec 23):** Voicemail
**Call 3 (Day 6 - Dec 27):** Busy
**Call 4 (Day 11 - Jan 3):** No Answer

**Eligibility Check for Call 4:**
```sql
-- 3 previous attempts
SELECT COUNT(*) FROM engage360.outreach_attempts
WHERE enrollment_id = 'e1b2c3d4-...'
-- Result: 3 attempts

-- Days since Call 3
SELECT DATEDIFF(day, MAX(call_start_ts), SYSDATETIMEOFFSET())
FROM engage360.outreach_attempts
WHERE enrollment_id = 'e1b2c3d4-...'
-- Result: 7 days (Dec 27 → Jan 3)

-- Frequency rule: Call 4 needs 5+ days since Call 3
-- Eligibility: YES (3 attempts, 7 days >= 5 business days)
```

**Call 5 (Day 18 - Jan 10):** Success - Device Activated

**Eligibility Check for Call 5:**
```sql
-- 4 previous attempts
SELECT COUNT(*) FROM engage360.outreach_attempts
WHERE enrollment_id = 'e1b2c3d4-...'
-- Result: 4 attempts

-- Days since Call 4
-- Result: 7 days (Jan 3 → Jan 10)

-- Frequency rule: Call 5+ needs 7+ calendar days
-- Eligibility: YES (4+ attempts, 7 days >= 7 days)
```

**Result:** ✅ Campaign complete after 5 attempts

---

### Scenario 4: Member Opts Out

**Timeline:**

**Call 1 (Day 2):** Member answers but requests no more calls

**Webhook Payload:**
```json
{
  "call_id": "bland-call-opt-out-123",
  "status": "completed",
  "analysis": {
    "disposition": "DO_NOT_CONTACT"
  }
}
```

**Webhook Processing:**
- Map disposition: "DO_NOT_CONTACT" → "OptOut"
- Update attempt: disposition = "OptOut"
- Update enrollment: current_status = "OPTED_OUT"

**Database State:**
```
enrollment_id: OPTED_OUT  (changed from ENROLLED)
device_activated: 0
outreach_attempts: 1 record with disposition='OptOut'
```

**Future Scheduler Runs:**
- Eligibility query filters out: `WHERE e.current_status = 'ENROLLED'`
- Member Barbara will NEVER appear in eligible list again
- No more calls will be made

**Result:** ❌ Campaign ended, member opted out

---

### Scenario 5: 90-Day Limit Reached Without Success

**Timeline:**

**Day 0 (Dec 18):** Device delivered
**Day 2-90:** Multiple calls (Call 1, 2, 3, 4, 5, 6... 13 calls total)
**Day 92 (March 20):** Campaign end date reached

**Final Call Attempt:**
- **Day 88 (March 16, 9:15 AM):** Scheduler runs
- **Eligibility Check:**

```sql
SELECT
    e.enrollment_id,
    e.campaign_end_date,
    SYSDATETIMEOFFSET() as now
FROM engage360.member_campaign_enrollments_enhanced e
WHERE e.enrollment_id = 'e1b2c3d4-...'

-- Result:
-- campaign_end_date: 2026-03-20 09:00:00.000 -05:00
-- now: 2026-03-16 15:00:00.000 +00:00
-- Eligibility: YES (still within 90-day window)
```

- **Day 88 (March 16, 9:20 AM):** Call 13 - No Answer

**Day 92 (March 20, 9:15 AM):** Scheduler runs
**Eligibility Check:**
```sql
-- Check time window
AND SYSDATETIMEOFFSET() <= e.campaign_end_date

-- Result: FALSE (now = March 20 15:00 UTC, end_date = March 20 14:00 UTC)
-- Eligibility: NO (outside 90-day window)
```

**Result:** ❌ Campaign ended, 90-day limit reached without activation

**Database State:**
```
enrollment_id: ENROLLED  (still enrolled, but no longer eligible)
device_activated: 0
outreach_attempts: 13 records, all unsuccessful
```

**Note:** You may want to manually update status to "EXPIRED" or "FAILED" for reporting purposes.

---

## Timeline Examples

### Example 1: Perfect Case (1 Call, Success)

```
Day 0 (Dec 18 Wed)
├─ 10:00 AM: Device delivered to Barbara
├─ 10:30 AM: CSV file uploaded to fs-ops/landing
├─ 10:30 AM: File processing starts
├─ 10:31 AM: Barbara enrolled (activation_start_date = Dec 20)
└─ 10:31 AM: File moved to fs-ops/processed

Day 1 (Dec 19 Thu)
└─ (No activity - waiting for Day 2)

Day 2 (Dec 20 Fri) - CALL DAY 1
├─ 09:00 AM CST: activation_start_date reached
├─ 09:15 AM CST: Scheduler wakes up
│  ├─ Eligibility query: Barbara found
│  ├─ Business hours check: PASS (9:15 AM CST, 10:15 AM EST)
│  └─ Call attempt #1 created
├─ 09:20 AM CST: Bland AI calls Barbara
├─ 09:25 AM CST: Barbara answers, device activated
├─ 09:25 AM CST: Webhook received
│  ├─ Disposition: DEVICE_ACTIVATED
│  ├─ Update attempt: Completed
│  ├─ Update enrollment: COMPLETED, device_activated=1
│  └─ Update batch: Completed
└─ ✅ CAMPAIGN COMPLETE

Day 3+ (Dec 21+)
└─ Scheduler runs every 15 min, but Barbara never appears (status=COMPLETED)
```

---

### Example 2: Typical Case (3 Calls, Success)

```
Day 0 (Dec 18 Wed)
├─ 10:00 AM: Device delivered
└─ 10:30 AM: Barbara enrolled

Day 2 (Dec 20 Fri) - CALL 1
├─ 09:15 AM: Scheduler finds Barbara
├─ 09:20 AM: Call 1 starts
├─ 09:21 AM: No answer (goes to voicemail)
├─ 09:21 AM: Webhook: NO_ANSWER, disposition=NoAnswer
└─ Status: ENROLLED (no change)

Day 3 (Dec 21 Sat)
└─ Weekend - No scheduler runs for member timezone checks

Day 4 (Dec 23 Mon) - CALL 2
├─ 09:15 AM: Scheduler finds Barbara
│  └─ Eligibility: 1 attempt, 3 days since last (>= 2 business days) ✅
├─ 09:20 AM: Call 2 starts
├─ 09:21 AM: Voicemail detected
├─ 09:21 AM: Webhook: VOICEMAIL, disposition=NoAnswer
└─ Status: ENROLLED (no change)

Day 6 (Dec 27 Fri) - CALL 3
├─ 09:15 AM: Scheduler finds Barbara
│  └─ Eligibility: 2 attempts, 4 days since last (>= 2 business days) ✅
├─ 09:20 AM: Call 3 starts
├─ 09:26 AM: Barbara answers, device activated
├─ 09:26 AM: Webhook: DEVICE_ACTIVATED, disposition=Completed
│  └─ Update: status=COMPLETED, device_activated=1
└─ ✅ CAMPAIGN COMPLETE

Day 7+ (Dec 28+)
└─ Barbara never appears in eligibility (status=COMPLETED)
```

---

### Example 3: Long Journey (Multiple Attempts, Weekly Calls)

```
Day 0 (Dec 18): Enrolled
Day 2 (Dec 20): Call 1 - No Answer
Day 4 (Dec 23): Call 2 - Voicemail
Day 6 (Dec 27): Call 3 - Busy

Day 11 (Jan 3): Call 4 - No Answer
  ├─ Eligibility: 3 attempts, 7 days since Call 3 (>= 5 business days) ✅
  └─ Frequency rule: Call 4 needs 5+ days

Day 18 (Jan 10): Call 5 - Voicemail
  ├─ Eligibility: 4 attempts, 7 days since Call 4 (>= 7 calendar days) ✅
  └─ Frequency rule: Call 5+ weekly (7 days)

Day 25 (Jan 17): Call 6 - No Answer
Day 32 (Jan 24): Call 7 - Voicemail
Day 39 (Jan 31): Call 8 - Busy
Day 46 (Feb 7): Call 9 - No Answer
Day 53 (Feb 14): Call 10 - Voicemail
Day 60 (Feb 21): Call 11 - No Answer
Day 67 (Feb 28): Call 12 - Voicemail

Day 74 (March 7): Call 13 - SUCCESS! Device Activated
  ├─ Eligibility: 12 attempts, 7 days since Call 12 ✅
  └─ ✅ CAMPAIGN COMPLETE (after 13 attempts over 74 days)

Total Duration: 74 days (within 90-day limit)
Total Attempts: 13 calls
Result: Success
```

---

## Summary Table

| Phase | Component | Key Activities | Database Tables | Duration |
|-------|-----------|----------------|-----------------|----------|
| **1. File Arrival** | Blob Trigger | Validate filename, extract campaign ID | - | < 10 seconds |
| **2. File Processing** | ETL Pipeline | Extract, validate, transform, load | `stg_device_activation_delta`, `members`, `member_devices`, `member_identifiers`, `member_campaign_enrollments_enhanced` | 1-2 minutes |
| **3. Enrollment** | Transform Phase | Calculate activation dates, create enrollment | `member_campaign_enrollments_enhanced` | Part of ETL |
| **4. Waiting Period** | - | Wait until Day 2 (activation_start_date) | - | 2 business days |
| **5. Scheduler Check** | Timer Trigger | Runs every 15 minutes to find eligible members | - | Every 15 min |
| **6. Eligibility** | EligibilityService | Query + business hours validation | `member_campaign_enrollments_enhanced`, `outreach_attempts`, `outreach_callback_queue` | 5-10 seconds |
| **7. Batch Creation** | BatchOrchestrator | Create batch & attempt records | `outreach_batches`, `outreach_attempts` | 2-3 seconds |
| **8. Bland AI Submission** | BlandAIClient | POST to Bland AI API | - | 1-2 seconds |
| **9. Call Execution** | Bland AI | Make actual phone call | - | 1-10 minutes |
| **10. Webhook** | Webhook Processor | Update attempt, enrollment, batch | `bland_call_logs`, `outreach_attempts`, `member_campaign_enrollments_enhanced`, `member_enrollment_status_history` | 1-2 seconds |
| **11. Retry Logic** | Scheduler | Check frequency rules for next attempt | `outreach_attempts` | Varies by attempt # |

---

## Key Takeaways

1. **File Upload Triggers Everything** - CSV file upload starts the entire workflow

2. **Day 2 is Critical** - First call happens 2 business days after device delivery

3. **Scheduler Runs Every 15 Minutes** - Constantly looking for eligible members

4. **Dual-Timezone Validation** - Must satisfy BOTH MG hours (9 AM-5PM EST) AND member hours (9 AM-5 PM local)

5. **Smart Frequency Logic** - Call frequency adjusts based on attempt number:
   - Calls 1-3: Every 2 business days
   - Call 4: 5 business days after Call 3
   - Calls 5+: Weekly (7 calendar days)

6. **90-Day Campaign Window** - Attempts stop after 90 days from activation_start_date

7. **Device Activation = Campaign Complete** - Once device activated, no more calls

8. **Webhook is Critical** - Updates database with call results and determines next steps

9. **Comprehensive Tracking** - Every call logged in 4 tables (batches, attempts, call_logs, history)

10. **Multiple Success Scenarios** - Can succeed on Call 1 or continue up to 90 days

---

**This comprehensive flow ensures every member gets persistent, respectful outreach to activate their device while respecting business hours and call frequency preferences.**
