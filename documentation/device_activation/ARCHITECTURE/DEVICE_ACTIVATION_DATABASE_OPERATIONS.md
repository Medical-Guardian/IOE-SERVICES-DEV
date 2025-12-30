# Device Activation - Database Operations Reference

**Date:** 2025-12-24
**Version:** 1.0
**BusinessCaseID:** BC-DA-002 (File Processing), BC-DA-003 (Eligibility), BC-DA-004 (Batch Creation), BC-DA-007 (Webhook Processing)
**Purpose:** Comprehensive reference for all database operations, SQL patterns, and data lifecycle in Device Activation

---

## Table of Contents

1. [Database Tables Overview](#1-database-tables-overview)
2. [File Processing Operations (5-Phase ETL)](#2-file-processing-operations-5-phase-etl)
3. [Scheduler Operations](#3-scheduler-operations)
4. [Batch Creation & Tracking](#4-batch-creation--tracking)
5. [Webhook Processing Operations](#5-webhook-processing-operations)
6. [Callback Queue Management](#6-callback-queue-management)
7. [Status Transitions & Audit Trail](#7-status-transitions--audit-trail)
8. [Transaction Management](#8-transaction-management)
9. [Index Requirements & Performance](#9-index-requirements--performance)
10. [Data Retention & Cleanup](#10-data-retention--cleanup)

---

## 1. Database Tables Overview

### 1.1 Table Summary

| Table | Schema | Type | Rows (Est.) | Retention | Primary Use |
|-------|--------|------|-------------|-----------|-------------|
| members | engage360 | Core | 100K+ | Permanent | Master member data |
| member_devices | engage360 | Core | 100K+ | Permanent | Device information |
| campaigns_enhanced | engage360 | Core | 10 | Permanent | Campaign configuration |
| campaign_call_configs_enhanced | engage360 | Core | 10 | Permanent | Bland AI config |
| member_campaign_enrollments_enhanced | engage360 | Core | 50K+ | Permanent | Enrollment tracking |
| outreach_batches | engage360 | Core | 5K+/month | 90 days | Batch-level tracking |
| outreach_attempts | engage360 | Core | 500K+/month | 90 days | Call attempt tracking |
| outreach_callback_queue | engage360 | Core | 100-1K | 7 days | Callback requests |
| bland_call_logs | engage360 | Audit | 500K+/month | 1 year | Complete webhook audit |
| stg_device_activation_delta | engage360_stg | Staging | 0-10K | 1 day | Temporary CSV staging |

### 1.2 Table Relationships

```
members (1) ──┬─→ (N) member_devices
              └─→ (N) member_campaign_enrollments_enhanced
                         │
                         ├─→ (N) outreach_batches
                         ├─→ (N) outreach_attempts
                         └─→ (N) outreach_callback_queue

campaigns_enhanced (1) ──┬─→ (N) member_campaign_enrollments_enhanced
                         └─→ (N) campaign_call_configs_enhanced

outreach_batches (1) ───→ (N) outreach_attempts

outreach_attempts (1) ──→ (0..1) bland_call_logs
```

### 1.3 Data Flow

```
CSV File → stg_device_activation_delta (staging)
                    ↓
        members + member_devices (MERGE)
                    ↓
    member_campaign_enrollments_enhanced (INSERT)
                    ↓
        outreach_batches → outreach_attempts (3-phase tracking)
                    ↓
            bland_call_logs (webhook audit)
```

---

## 2. File Processing Operations (5-Phase ETL)

### 2.1 Phase 1: Extract (No Database Operations)

Pandas DataFrame operations only - no database writes in this phase.

### 2.2 Phase 2: Load to Staging

**Purpose:** Insert raw CSV data into staging table for validation

**Table:** `engage360_stg.stg_device_activation_delta`

**Operation Type:** Row-by-row INSERT

**Error Handling:** 10% error threshold (>10% errors → ROLLBACK entire transaction)

**SQL Pattern:**

```sql
-- INSERT single row into staging
INSERT INTO engage360_stg.stg_device_activation_delta (
    -- Member fields
    member_id,
    first_name,
    last_name,
    primary_phone,
    email,
    dob,
    timezone,
    language_pref,
    address_street,
    address_city,
    address_state,
    address_zip,
    member_brand,
    salesforce_account_number,

    -- Device fields
    device_id,
    device_name,
    brand,
    device_phone_number,
    is_device_callable,
    fall_detection,
    powersaver_mode,

    -- Enrollment fields
    delivery_date,
    campaign_id,

    -- Metadata fields
    file_id,
    processing_status,
    validation_status,
    created_at
)
VALUES (
    %s, %s, %s, %s, %s,  -- Member: member_id, first_name, last_name, primary_phone, email
    %s, %s, %s, %s, %s,  -- Member: dob, timezone, language_pref, address_street, address_city
    %s, %s, %s, %s,      -- Member: address_state, address_zip, member_brand, sf_account_number
    %s, %s, %s, %s, %s,  -- Device: device_id, device_name, brand, device_phone, is_callable
    %s, %s,              -- Device: fall_detection, powersaver_mode
    %s, %s,              -- Enrollment: delivery_date, campaign_id
    %s, 'Staged', NULL, SYSDATETIMEOFFSET()  -- Metadata: file_id, status, validation, timestamp
);
```

**Python Code Pattern:**

```python
def load_to_staging(df: pd.DataFrame, file_id: str, db_service: DatabaseService) -> Dict:
    """
    Load DataFrame to staging table with error threshold

    BusinessCaseID: BC-DA-002
    """
    total_rows = len(df)
    error_count = 0
    staged_count = 0

    for idx, row in df.iterrows():
        try:
            # Build parameters tuple (23 values + file_id)
            params = (
                row['member_id'], row['first_name'], row['last_name'],
                row['primary_phone'], row['email'], row['dob'],
                row['timezone'], row['language_pref'],
                row['address_street'], row['address_city'],
                row['address_state'], row['address_zip'],
                row['member_brand'], row['salesforce_account_number'],
                row['device_id'], row['device_name'], row['brand'],
                row['device_phone_number'], row['is_device_callable'],
                row['fall_detection'], row['powersaver_mode'],
                row['delivery_date'], row['campaign_id'],
                file_id
            )

            # Execute INSERT
            db_service.execute_query(insert_staging_query, params, fetch_results=False)
            staged_count += 1

        except Exception as e:
            logger.error(f"Row {idx} staging error: {e}")
            error_count += 1

            # Check error threshold
            error_rate = error_count / total_rows
            if error_rate > 0.10:  # 10% threshold
                logger.error(f"Error threshold exceeded: {error_rate:.2%}")
                raise Exception(f"Staging error threshold exceeded: {error_count}/{total_rows} rows failed")

    return {
        'total_rows': total_rows,
        'staged_count': staged_count,
        'error_count': error_count
    }
```

**Error Scenarios:**

| Error Type | Handling | Example |
|------------|----------|---------|
| Duplicate primary key | Log, increment error_count | Same device_id in multiple rows |
| Data type mismatch | Log, increment error_count | Non-date value in delivery_date |
| NULL constraint violation | Log, increment error_count | NULL in member_id (NOT NULL field) |
| Error threshold exceeded | ROLLBACK transaction, abort file | >10% of rows failed |

### 2.3 Phase 3: Validate

**Purpose:** Cleanse and validate staged data using SQL UPDATE statements

**Table:** `engage360_stg.stg_device_activation_delta`

**Operation Type:** Batch UPDATE (all rows for file_id)

**Error Handling:** 50% validation threshold (>50% invalid → ROLLBACK)

**SQL Operations:**

**3.3.1 Proper Case Names:**

```sql
-- Clean first_name and last_name to proper case
UPDATE engage360_stg.stg_device_activation_delta
SET first_name_clean = UPPER(LEFT(first_name, 1)) + LOWER(SUBSTRING(first_name, 2, LEN(first_name))),
    last_name_clean = UPPER(LEFT(last_name, 1)) + LOWER(SUBSTRING(last_name, 2, LEN(last_name)))
WHERE file_id = %s;

-- Example: 'JOHN' → 'John', 'mary' → 'Mary', 'McDONALD' → 'Mcdonald'
```

**3.3.2 Standardize Phone Numbers:**

```sql
-- Convert phone numbers to E.164 format (+1XXXXXXXXXX)
UPDATE engage360_stg.stg_device_activation_delta
SET primary_phone_clean = '+1' + REPLACE(REPLACE(REPLACE(REPLACE(primary_phone, '-', ''), '(', ''), ')', ''), ' ', '')
WHERE file_id = %s
  AND LEN(REPLACE(REPLACE(REPLACE(REPLACE(primary_phone, '-', ''), '(', ''), ')', ''), ' ', '')) = 10;

-- Example: '555-123-4567' → '+15551234567'
-- Example: '(555) 123-4567' → '+15551234567'

-- Validate E.164 format (must start with +1 and be 12 characters)
UPDATE engage360_stg.stg_device_activation_delta
SET validation_status = 'Invalid',
    validation_error = CONCAT(ISNULL(validation_error, ''), '; Invalid phone format')
WHERE file_id = %s
  AND (primary_phone_clean IS NULL OR LEN(primary_phone_clean) != 12 OR LEFT(primary_phone_clean, 2) != '+1');
```

**3.3.3 Validate Email Addresses:**

```sql
-- Simple email validation (contains @ and . after @)
UPDATE engage360_stg.stg_device_activation_delta
SET email_clean = LOWER(LTRIM(RTRIM(email)))
WHERE file_id = %s
  AND email LIKE '%@%.%';

-- Mark invalid emails
UPDATE engage360_stg.stg_device_activation_delta
SET validation_status = 'Invalid',
    validation_error = CONCAT(ISNULL(validation_error, ''), '; Invalid email format')
WHERE file_id = %s
  AND email IS NOT NULL
  AND email_clean IS NULL;
```

**3.3.4 Map Timezone Names:**

```sql
-- Map common timezone abbreviations to IANA format
UPDATE engage360_stg.stg_device_activation_delta
SET timezone_clean = CASE
    WHEN timezone IN ('Eastern', 'EST', 'ET', 'E') THEN 'America/New_York'
    WHEN timezone IN ('Central', 'CST', 'CT', 'C') THEN 'America/Chicago'
    WHEN timezone IN ('Mountain', 'MST', 'MT', 'M') THEN 'America/Denver'
    WHEN timezone IN ('Pacific', 'PST', 'PT', 'P') THEN 'America/Los_Angeles'
    WHEN timezone LIKE 'America/%' THEN timezone  -- Already IANA format
    ELSE NULL
END
WHERE file_id = %s;

-- Mark invalid timezones
UPDATE engage360_stg.stg_device_activation_delta
SET validation_status = 'Invalid',
    validation_error = CONCAT(ISNULL(validation_error, ''), '; Invalid timezone')
WHERE file_id = %s
  AND timezone_clean IS NULL;
```

**3.3.5 Validate Device Fields:**

```sql
-- Convert fall_detection and powersaver_mode to BIT
UPDATE engage360_stg.stg_device_activation_delta
SET fall_detection_clean = CASE
        WHEN fall_detection IN ('Yes', 'Y', '1', 'True', 'T') THEN 1
        WHEN fall_detection IN ('No', 'N', '0', 'False', 'F') THEN 0
        ELSE NULL
    END,
    powersaver_mode_clean = CASE
        WHEN powersaver_mode IN ('Yes', 'Y', '1', 'True', 'T', 'Battery Saver') THEN 1
        WHEN powersaver_mode IN ('No', 'N', '0', 'False', 'F') THEN 0
        ELSE NULL
    END
WHERE file_id = %s;
```

**3.3.6 Check Validation Threshold:**

```sql
-- Count invalid rows
SELECT COUNT(*) AS invalid_count
FROM engage360_stg.stg_device_activation_delta
WHERE file_id = %s
  AND validation_status = 'Invalid';

-- If invalid_count / total_count > 0.50 → ROLLBACK
```

**3.3.7 Mark Valid Rows:**

```sql
-- Mark rows that passed all validation
UPDATE engage360_stg.stg_device_activation_delta
SET validation_status = 'Valid',
    processing_status = 'Validated'
WHERE file_id = %s
  AND validation_status IS NULL;  -- Not marked Invalid
```

### 2.4 Phase 4: Transform & Load Core

**Purpose:** MERGE/INSERT data into core production tables

**Tables:** `members`, `member_devices`, `member_campaign_enrollments_enhanced`

**Operation Type:** MERGE (UPSERT) for members/devices, INSERT for enrollments

**4.4.1 MERGE Members Table:**

```sql
-- MERGE validated staging data into core members table
MERGE engage360.members AS target
USING (
    -- Source: Validated rows from staging (DISTINCT to handle duplicates within file)
    SELECT DISTINCT
        member_id,
        first_name_clean AS first_name,
        last_name_clean AS last_name,
        primary_phone_clean AS primary_phone,
        email_clean AS email,
        dob,
        timezone_clean AS timezone,
        language_pref,
        address_street,
        address_city,
        address_state,
        address_zip,
        member_brand,
        salesforce_account_number
    FROM engage360_stg.stg_device_activation_delta
    WHERE file_id = %s
      AND processing_status = 'Validated'
      AND validation_status = 'Valid'
) AS source
ON target.member_id = source.member_id

-- MATCHED: Member exists, update with latest data
WHEN MATCHED THEN
    UPDATE SET
        first_name = source.first_name,
        last_name = source.last_name,
        primary_phone = source.primary_phone,
        email = source.email,
        dob = source.dob,
        timezone = source.timezone,
        language_pref = source.language_pref,
        address_street = source.address_street,
        address_city = source.address_city,
        address_state = source.address_state,
        address_zip = source.address_zip,
        member_brand = source.member_brand,
        salesforce_account_number = source.salesforce_account_number,
        updated_at = SYSDATETIMEOFFSET()

-- NOT MATCHED: New member, insert
WHEN NOT MATCHED THEN
    INSERT (
        member_id, first_name, last_name, primary_phone, email,
        dob, timezone, language_pref, address_street, address_city,
        address_state, address_zip, member_brand, salesforce_account_number,
        created_at, updated_at
    )
    VALUES (
        source.member_id, source.first_name, source.last_name, source.primary_phone, source.email,
        source.dob, source.timezone, source.language_pref, source.address_street, source.address_city,
        source.address_state, source.address_zip, source.member_brand, source.salesforce_account_number,
        SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET()
    );
```

**MERGE Strategy:**
- **UPDATE existing:** Keeps member_id, updates all other fields
- **INSERT new:** Creates new member record with current timestamp
- **Handles duplicates:** DISTINCT in source prevents duplicate INSERT attempts

**4.4.2 MERGE Member Devices Table:**

```sql
-- MERGE validated staging data into core member_devices table
MERGE engage360.member_devices AS target
USING (
    SELECT DISTINCT
        device_id,
        member_id,
        device_name,
        brand,
        device_phone_number,
        is_device_callable,
        fall_detection_clean AS fall_detection,
        powersaver_mode_clean AS powersaver_mode
    FROM engage360_stg.stg_device_activation_delta
    WHERE file_id = %s
      AND processing_status = 'Validated'
      AND validation_status = 'Valid'
) AS source
ON target.device_id = source.device_id

-- MATCHED: Device exists, update
WHEN MATCHED THEN
    UPDATE SET
        member_id = source.member_id,  -- Allow device reassignment
        device_name = source.device_name,
        brand = source.brand,
        device_phone_number = source.device_phone_number,
        is_device_callable = source.is_device_callable,
        fall_detection = source.fall_detection,
        powersaver_mode = source.powersaver_mode,
        updated_at = SYSDATETIMEOFFSET()

-- NOT MATCHED: New device, insert
WHEN NOT MATCHED THEN
    INSERT (
        device_id, member_id, device_name, brand, device_phone_number,
        is_device_callable, fall_detection, powersaver_mode,
        created_at, updated_at
    )
    VALUES (
        source.device_id, source.member_id, source.device_name, source.brand, source.device_phone_number,
        source.is_device_callable, source.fall_detection, source.powersaver_mode,
        SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET()
    );
```

**4.4.3 INSERT Enrollments (with activation_start_date calculation):**

```sql
-- INSERT new enrollments (always INSERT, never UPDATE)
-- Calculate activation_start_date using business day function
INSERT INTO engage360.member_campaign_enrollments_enhanced (
    enrollment_id,
    member_id,
    campaign_id,
    current_status,
    activation_start_date,
    campaign_end_date,
    call_5_timestamp,
    device_activated,
    created_at,
    updated_at
)
SELECT
    NEWID() AS enrollment_id,
    member_id,
    campaign_id,
    'ENROLLED' AS current_status,

    -- Calculate activation_start_date: delivery_date + 2 business days
    -- Uses helper function to skip weekends and holidays
    dbo.AddBusinessDays(CAST(delivery_date AS DATE), 2) AS activation_start_date,

    NULL AS campaign_end_date,  -- Set later when Call 5 created
    NULL AS call_5_timestamp,   -- Set later when Call 5 created
    0 AS device_activated,
    SYSDATETIMEOFFSET() AS created_at,
    SYSDATETIMEOFFSET() AS updated_at
FROM (
    SELECT DISTINCT
        member_id,
        campaign_id,
        delivery_date
    FROM engage360_stg.stg_device_activation_delta
    WHERE file_id = %s
      AND processing_status = 'Validated'
      AND validation_status = 'Valid'
) AS source

-- Prevent duplicate enrollments (member can only be enrolled once per campaign)
WHERE NOT EXISTS (
    SELECT 1
    FROM engage360.member_campaign_enrollments_enhanced e
    WHERE e.member_id = source.member_id
      AND e.campaign_id = source.campaign_id
      AND e.current_status IN ('ENROLLED', 'PENDING')  -- Active enrollments only
);
```

**Business Day Calculation Function:**

```sql
CREATE FUNCTION dbo.AddBusinessDays (
    @StartDate DATE,
    @NumberOfDays INT
)
RETURNS DATE
AS
BEGIN
    DECLARE @EndDate DATE = @StartDate;
    DECLARE @DaysAdded INT = 0;

    WHILE @DaysAdded < @NumberOfDays
    BEGIN
        -- Add one day
        SET @EndDate = DATEADD(DAY, 1, @EndDate);

        -- Check if it's a business day (Monday-Friday, not a holiday)
        IF DATEPART(WEEKDAY, @EndDate) NOT IN (1, 7)  -- Not Sunday (1) or Saturday (7)
        BEGIN
            -- Check if not a company holiday
            IF NOT EXISTS (
                SELECT 1
                FROM engage360.company_holidays
                WHERE holiday_date = @EndDate
            )
            BEGIN
                SET @DaysAdded = @DaysAdded + 1;
            END
        END
    END

    RETURN @EndDate;
END;
```

**Example Calculation:**
- Delivery date: Friday Jan 1, 2025
- +1 business day: Monday Jan 4 (skip Sat Jan 2, Sun Jan 3)
- +2 business days: Tuesday Jan 5 (if Jan 4 is not a holiday)
- activation_start_date: Tuesday Jan 5, 2025

### 2.5 Phase 5: Audit & Log

**Purpose:** Create audit trail and mark staging rows as processed

**5.5.1 Update Staging Status:**

```sql
-- Mark all rows as completed
UPDATE engage360_stg.stg_device_activation_delta
SET processing_status = 'Completed',
    processed_at = SYSDATETIMEOFFSET()
WHERE file_id = %s
  AND processing_status = 'Validated';
```

**5.5.2 Insert File Processing Log:**

```sql
INSERT INTO engage360.file_processing_log (
    log_id,
    file_name,
    file_id,
    blob_container,
    processing_status,
    rows_total,
    rows_staged,
    rows_validated,
    rows_loaded,
    errors_staging,
    errors_validation,
    phase_completed,
    started_at,
    completed_at,
    duration_seconds,
    created_at
)
VALUES (
    NEWID(),
    %s,  -- file_name
    %s,  -- file_id
    'fs-device-activation',
    'Completed',
    %s,  -- rows_total
    %s,  -- rows_staged
    %s,  -- rows_validated
    %s,  -- rows_loaded
    %s,  -- errors_staging
    %s,  -- errors_validation
    'Phase 5: Audit',
    %s,  -- started_at
    SYSDATETIMEOFFSET(),
    DATEDIFF(SECOND, %s, SYSDATETIMEOFFSET()),
    SYSDATETIMEOFFSET()
);
```

---

## 3. Scheduler Operations

### 3.1 Campaign Qualification Query

**Purpose:** Validate campaign is active and configured for Device Activation

**BusinessCaseID:** BC-DA-001

```sql
SELECT
    c.campaign_id,
    c.name AS campaign_name,
    c.campaign_type,
    c.campaign_status,
    c.operating_tz,
    c.operating_start_time,
    c.operating_end_time,
    c.timezone_flag,
    c.start_ts,
    c.end_ts,
    cc.pathway_id,
    cc.voice_id,
    cc.bland_parameters_global,
    cc.config_status
FROM engage360.campaigns_enhanced c
LEFT JOIN engage360.campaign_call_configs_enhanced cc
    ON c.campaign_id = cc.campaign_id
    AND cc.config_status = 'active'
WHERE c.campaign_id = %s
  AND c.campaign_status = 'Active'
  AND c.campaign_type IN ('Device Activation', 'Operations');
```

**Expected Result:** 1 row (campaign exists and is active)

**Error Handling:**
- 0 rows → Campaign not found or inactive, skip execution
- Multiple rows → Use first active configuration

### 3.2 Eligibility Query

See [DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md Section 12.1](DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md#121-eligibility-query-complete) for the complete 200+ line eligibility query.

**Key Points:**
- Uses CTE (Common Table Expressions) for RegularCalls and CallbackCalls
- Implements Call 1-4 logic (BUSINESS day frequency: 2 days for Calls 2-3, 5 days for Call 4)
- Implements Call 5+ logic (7 CALENDAR days frequency, 90-day window)
- ⚠️ **Business day filtering for Calls 1-4 now happens in PYTHON** (af_code/shared/business_hours_utils.py)
- Uses `DATEDIFF(day, ...)` for Call 5+ calendar days
- Excludes members in pending batches or callback queue
- Returns member, device, campaign, and configuration data

**Business Days vs Calendar Days:**
- **Calls 1-4:** BUSINESS days (Monday-Friday, excluding US federal holidays) - **FILTERED IN PYTHON** (eligibility_service.py:666-730)
- **Call 5+:** CALENDAR days (all days, including weekends and holidays) - filtered in SQL

**Performance:**
- Typical execution time: 2-5 seconds for 10K enrollments
- Returns 0-1000 rows depending on time of day and campaign size
- Requires indexes on enrollment status, activation_start_date, attempt timestamps
- Business day filtering in Python adds ~50-100ms per 1000 rows (faster than SQL function)

### 3.3 Business Days Calculation Function

⚠️ **DEPRECATED - NO LONGER USED IN CODEBASE**

This SQL function has been replaced by Python implementation. This section is kept for reference only.

**Current Implementation:**
- Python function: `get_business_days_between()` in `af_code/shared/business_hours_utils.py`
- Used in: `af_code/device_activation_scheduler/services/eligibility_service.py` (lines 666-730)
- Holiday detection: Python `holidays` library (NOT database table)

---

**Function:** `dbo.GetBusinessDaysBetween(@StartDate, @EndDate)` *(DEPRECATED)*

**Purpose:** Calculate business days between two dates (excludes weekends and US federal holidays)

**BusinessCaseID:** BC-DA-006

**Parameters:**
- `@StartDate` (DATETIMEOFFSET): Start date/time (inclusive)
- `@EndDate` (DATETIMEOFFSET): End date/time (exclusive)

**Returns:** INT (number of business days)

**Definition:** *(For reference only - DO NOT deploy)*
```sql
CREATE FUNCTION dbo.GetBusinessDaysBetween(
    @StartDate DATETIMEOFFSET,
    @EndDate DATETIMEOFFSET
)
RETURNS INT
AS
BEGIN
    DECLARE @BusinessDays INT = 0;
    DECLARE @CurrentDate DATE = CAST(@StartDate AS DATE);
    DECLARE @EndDateOnly DATE = CAST(@EndDate AS DATE);
    DECLARE @DayOfWeek INT;

    -- Loop through each day from StartDate to EndDate
    WHILE @CurrentDate < @EndDateOnly
    BEGIN
        SET @DayOfWeek = DATEPART(WEEKDAY, @CurrentDate);

        -- Check if weekday (Monday=2 through Friday=6)
        IF @DayOfWeek BETWEEN 2 AND 6
        BEGIN
            -- Check if NOT a federal holiday
            IF NOT EXISTS (
                SELECT 1 FROM dbo.USFederalHolidays
                WHERE holiday_date = @CurrentDate
                  AND is_observed = 1
            )
            BEGIN
                SET @BusinessDays = @BusinessDays + 1;
            END
        END

        SET @CurrentDate = DATEADD(DAY, 1, @CurrentDate);
    END

    RETURN @BusinessDays;
END;
```

**Usage in Eligibility Query:** *(DEPRECATED - For reference only)*

⚠️ **These SQL queries are NO LONGER USED. Business day filtering now happens in Python.**

```sql
-- ⚠️ DEPRECATED: Business day filtering now in Python (eligibility_service.py:666-730)

-- Calls 2-3: 2 BUSINESS days since last attempt (OLD SQL APPROACH - NOT USED)
AND dbo.GetBusinessDaysBetween(
    (SELECT MAX(attempt_ts) FROM engage360.outreach_attempts
     WHERE enrollment_id = e.enrollment_id),
    SYSDATETIMEOFFSET()
) >= 2

-- Call 4: 5 BUSINESS days since Call 3 (OLD SQL APPROACH - NOT USED)
AND dbo.GetBusinessDaysBetween(
    (SELECT MAX(attempt_ts) FROM engage360.outreach_attempts
     WHERE enrollment_id = e.enrollment_id),
    SYSDATETIMEOFFSET()
) >= 5
```

**Holidays Table:** `dbo.USFederalHolidays`
- Contains US federal holidays (2024-2027)
- Includes observed holidays (when holiday falls on weekend)
- Updated annually
- See `database/create_us_federal_holidays_table.sql`

---

## 4. Batch Creation & Tracking

### 4.1 3-Phase Tracking Pattern

Device Activation uses **3-phase tracking** to ensure database consistency even if Bland AI submission fails:

**Phase 1:** Create batch record (status='Pending') BEFORE Bland AI submission
**Phase 2:** Create attempt records (disposition='Pending') BEFORE Bland AI submission
**Phase 3:** Update vendor_batch_id (status='Submitted') AFTER Bland AI success

**Benefits:**
- Transaction can be rolled back if submission fails
- Complete audit trail from creation to completion
- Enables reconciliation of batch vs attempt status
- Clear state transitions for troubleshooting

### 4.2 Phase 1: Create Batch

**Purpose:** Generate batch_id and create batch record BEFORE submitting to Bland AI

**BusinessCaseID:** BC-DA-004

```sql
INSERT INTO engage360.outreach_batches (
    batch_id,
    campaign_id,
    batch_status,
    batch_size,
    batch_name,
    created_at,
    updated_at
)
VALUES (
    %s,  -- Generated UUID (Python: str(uuid.uuid4()))
    %s,  -- Campaign ID
    'Pending',
    %s,  -- Number of members in batch (1-100)
    %s,  -- Descriptive name: "Device Activation Batch 2025-01-15 14:30"
    SYSDATETIMEOFFSET(),
    SYSDATETIMEOFFSET()
);
```

**Python Code:**

```python
def _create_outreach_batch(self, campaign_id: str, batch_size: int) -> str:
    """
    Phase 1: Create batch record

    BusinessCaseID: BC-DA-004
    """
    batch_id = str(uuid.uuid4())
    batch_name = f"Device Activation Batch {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    query = """
        INSERT INTO engage360.outreach_batches (
            batch_id, campaign_id, batch_status, batch_size, batch_name,
            created_at, updated_at
        )
        VALUES (%s, %s, 'Pending', %s, %s, SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET());
    """
    params = (batch_id, campaign_id, batch_size, batch_name)

    self.db_service.execute_query(query, params, fetch_results=False)
    logger.info(f"✅ Phase 1: Created batch {batch_id} (size={batch_size})")

    return batch_id
```

### 4.3 Phase 2: Create Attempts

**Purpose:** Create attempt records for each member BEFORE Bland AI submission

**BusinessCaseID:** BC-DA-004

```sql
-- Create one attempt per member in batch
INSERT INTO engage360.outreach_attempts (
    attempt_id,
    enrollment_id,
    batch_id,
    disposition,
    attempt_ts,
    created_at,
    updated_at
)
VALUES (
    %s,  -- Generated UUID
    %s,  -- Enrollment ID (from eligible members)
    %s,  -- Batch ID from Phase 1
    'Pending',
    SYSDATETIMEOFFSET(),
    SYSDATETIMEOFFSET(),
    SYSDATETIMEOFFSET()
);
```

**Python Code:**

```python
def _create_outreach_attempts(self, batch_id: str, members: List[Dict]) -> List[str]:
    """
    Phase 2: Create attempt records

    BusinessCaseID: BC-DA-004
    """
    attempt_ids = []
    queries = []

    for member in members:
        attempt_id = str(uuid.uuid4())
        attempt_ids.append(attempt_id)

        query = """
            INSERT INTO engage360.outreach_attempts (
                attempt_id, enrollment_id, batch_id, disposition,
                attempt_ts, created_at, updated_at
            )
            VALUES (%s, %s, %s, 'Pending', SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET(), SYSDATETIMEOFFSET());
        """
        params = (attempt_id, member['enrollment_id'], batch_id)
        queries.append((query, params))

    # Execute all INSERTs in single transaction
    self.db_service.execute_transaction(queries)
    logger.info(f"✅ Phase 2: Created {len(attempt_ids)} attempt records")

    return attempt_ids
```

### 4.4 Phase 3: Update Batch with Vendor ID

**Purpose:** Store Bland AI's vendor_batch_id AFTER successful submission

**BusinessCaseID:** BC-DA-004

```sql
UPDATE engage360.outreach_batches
SET vendor_batch_id = %s,  -- From Bland AI response
    batch_status = 'Submitted',
    submitted_at = SYSDATETIMEOFFSET(),
    updated_at = SYSDATETIMEOFFSET()
WHERE batch_id = %s
  AND batch_status = 'Pending';  -- Safety check
```

**Python Code:**

```python
def _update_batch_with_vendor_id(self, batch_id: str, vendor_batch_id: str):
    """
    Phase 3: Update batch with Bland AI vendor_batch_id

    BusinessCaseID: BC-DA-004
    """
    query = """
        UPDATE engage360.outreach_batches
        SET vendor_batch_id = %s,
            batch_status = 'Submitted',
            submitted_at = SYSDATETIMEOFFSET(),
            updated_at = SYSDATETIMEOFFSET()
        WHERE batch_id = %s
          AND batch_status = 'Pending';
    """
    params = (vendor_batch_id, batch_id)

    self.db_service.execute_query(query, params, fetch_results=False)
    logger.info(f"✅ Phase 3: Updated batch {batch_id} with vendor_batch_id {vendor_batch_id}")
```

### 4.5 Call 5 Timestamp Update

**Purpose:** Set call_5_timestamp and calculate campaign_end_date when Call 5 is created

**BusinessCaseID:** BC-DA-006

**Trigger:** After Phase 3 completes, if call_attempt_number = 5

```sql
-- Update enrollment with Call 5 timestamp and 90-day campaign end date
UPDATE engage360.member_campaign_enrollments_enhanced
SET call_5_timestamp = SYSDATETIMEOFFSET(),
    campaign_end_date = CAST(DATEADD(DAY, 90, SYSDATETIMEOFFSET()) AS DATE),
    updated_at = SYSDATETIMEOFFSET()
WHERE enrollment_id IN (
    -- Get enrollments for members in this batch where this is their 5th attempt
    SELECT DISTINCT oa.enrollment_id
    FROM engage360.outreach_attempts oa
    WHERE oa.batch_id = %s
      AND (
          SELECT COUNT(*)
          FROM engage360.outreach_attempts oa2
          WHERE oa2.enrollment_id = oa.enrollment_id
      ) = 5  -- Including the attempt just created in Phase 2
)
  AND call_5_timestamp IS NULL;  -- Only set once
```

**Calculation Details:**
- **call_5_timestamp:** Current timestamp when Call 5 batch is created
- **campaign_end_date:** call_5_timestamp + 90 calendar days (DATE only, no time)
- **Timezone:** Stored as DATETIMEOFFSET (timezone-aware)

**Example:**
- Call 5 created: Jan 15, 2025 14:30:00-05:00 (EST)
- call_5_timestamp: 2025-01-15 14:30:00-05:00
- campaign_end_date: 2025-04-15 (DATE only)
- Eligibility check: `SYSDATETIMEOFFSET() < DATEADD(DAY, 90, call_5_timestamp)`

---

## 5. Webhook Processing Operations

### 5.1 Duplicate Detection

**Purpose:** Prevent processing same call_id multiple times (Bland AI may retry webhooks)

**BusinessCaseID:** BC-DA-007

```sql
-- Check if call_id already processed
SELECT COUNT(*)
FROM engage360.bland_call_logs
WHERE call_id = %s;
```

**Logic:**
- If count > 0 → Duplicate, return 200 OK but skip processing
- If count = 0 → New call, proceed with processing

### 5.2 Update Attempt Disposition

**Purpose:** Update attempt record with call result from webhook

**BusinessCaseID:** BC-DA-007

```sql
UPDATE engage360.outreach_attempts
SET disposition = %s,          -- Internal disposition (Completed, NoAnswer, etc.)
    completed_at = %s,         -- Bland AI completed_at timestamp
    call_length = %s,          -- Duration in seconds
    recording_url = %s,        -- Bland AI recording URL
    updated_at = SYSDATETIMEOFFSET()
WHERE attempt_id = %s          -- From webhook metadata.attempt_id
  AND disposition = 'Pending';  -- Safety check (prevent duplicate updates)
```

**Parameters:**
- disposition: Mapped from Bland AI disposition via StatusMapper
- completed_at: Parsed from webhook payload
- call_length: Duration in seconds
- recording_url: URL to call recording (for quality assurance)
- attempt_id: Extracted from webhook metadata

### 5.3 Update Enrollment Status (Opt-Outs)

**Purpose:** Update enrollment status if member opted out

**BusinessCaseID:** BC-DA-007

**Trigger:** Webhook disposition = 'DO_NOT_CONTACT'

```sql
UPDATE engage360.member_campaign_enrollments_enhanced
SET current_status = 'OPTED_OUT',
    updated_at = SYSDATETIMEOFFSET()
WHERE enrollment_id = %s       -- From webhook metadata.enrollment_id
  AND current_status = 'ENROLLED';  -- Only update if currently enrolled
```

**Note:** Device Activation only updates enrollment status for opt-outs. Other dispositions (INTERESTED, NOT_INTERESTED, etc.) do NOT change enrollment status.

### 5.4 Insert Callback Queue

**Purpose:** Create callback request if member requested callback

**BusinessCaseID:** BC-DA-007, BC-DA-005

**Trigger:** Webhook disposition = 'CALL_BACK_SCHEDULED'

```sql
INSERT INTO engage360.outreach_callback_queue (
    callback_id,
    enrollment_id,
    scheduled_callback_time,
    requested_time_text,
    status,
    attempt_count,
    created_at,
    updated_at
)
VALUES (
    %s,  -- Generated UUID
    %s,  -- From webhook metadata.enrollment_id
    %s,  -- Parsed from transcript or default to current_time + 2 hours
    %s,  -- Raw text from transcript (e.g., "in 2 hours")
    'Pending',
    0,
    SYSDATETIMEOFFSET(),
    SYSDATETIMEOFFSET()
);
```

**scheduled_callback_time Calculation:**
1. Parse transcript for member-requested time
   - "in 2 hours" → current_time + 2 hours
   - "tomorrow at 10 AM" → tomorrow 10:00 in member's timezone
   - "this afternoon" → today 2:00 PM in member's timezone
2. If no specific time found → default to current_time + 2 hours
3. Convert to DATETIMEOFFSET (timezone-aware)

### 5.5 Insert Bland Call Logs (Audit Trail)

**Purpose:** Store complete webhook payload for audit trail

**BusinessCaseID:** BC-DA-007

```sql
INSERT INTO engage360.bland_call_logs (
    log_id,
    call_id,
    batch_id,
    from_number,
    to_number,
    call_length,
    disposition,
    recording_url,
    transcript,
    analysis,
    metadata,
    webhook_received_at,
    created_at
)
VALUES (
    %s,  -- Generated UUID
    %s,  -- Bland AI call_id
    %s,  -- Bland AI batch_id (vendor_batch_id)
    %s,  -- From number (caller ID)
    %s,  -- To number (member phone)
    %s,  -- Call duration in seconds
    %s,  -- Bland AI disposition (raw, not mapped)
    %s,  -- Recording URL
    %s,  -- Full transcript (TEXT or NVARCHAR(MAX))
    %s,  -- Analysis JSON (sentiment, summary, etc.)
    %s,  -- Complete metadata JSON (all webhook fields)
    SYSDATETIMEOFFSET(),
    SYSDATETIMEOFFSET()
);
```

**Data Types:**
- transcript: TEXT (unlimited length)
- analysis: NVARCHAR(MAX) (JSON format)
- metadata: NVARCHAR(MAX) (JSON format - complete webhook payload)

**Purpose of Storing Complete Payload:**
- Audit trail for compliance
- Troubleshooting (can replay webhook processing)
- Post-call analysis (sentiment, keywords, etc.)
- Quality assurance (review call transcripts)

### 5.6 Insert Status History

**Purpose:** Log enrollment status changes for audit trail

**BusinessCaseID:** BC-DA-007

**Trigger:** Enrollment status changes (e.g., ENROLLED → OPTED_OUT)

```sql
INSERT INTO engage360.member_enrollment_status_history (
    history_id,
    enrollment_id,
    previous_status,
    new_status,
    changed_by,
    change_reason,
    metadata,
    changed_at,
    created_at
)
VALUES (
    %s,  -- Generated UUID
    %s,  -- Enrollment ID
    %s,  -- Previous status (e.g., 'ENROLLED')
    %s,  -- New status (e.g., 'OPTED_OUT')
    'Bland AI Webhook',
    %s,  -- Change reason (e.g., 'Member requested DO_NOT_CONTACT')
    %s,  -- Metadata JSON (call_id, disposition, etc.)
    SYSDATETIMEOFFSET(),
    SYSDATETIMEOFFSET()
);
```

### 5.7 Atomic Transaction Pattern

**All webhook updates occur in single transaction:**

```python
def process_webhook(self, webhook_data: Dict):
    """
    Process Bland AI webhook with atomic database updates

    BusinessCaseID: BC-DA-007
    """
    queries = []

    # Query 1: UPDATE attempt
    queries.append(self._build_update_attempt(webhook_data))

    # Query 2: UPDATE enrollment (if opt-out)
    if internal_disposition == 'OptedOut':
        queries.append(self._build_update_enrollment(webhook_data))

    # Query 3: INSERT callback (if requested)
    if internal_disposition == 'CallbackScheduled':
        queries.append(self._build_insert_callback_queue(webhook_data))

    # Query 4: INSERT call log (always)
    queries.append(self._build_insert_bland_call_logs(webhook_data))

    # Query 5: INSERT status history (if status changed)
    if internal_disposition == 'OptedOut':
        queries.append(self._build_insert_status_history(webhook_data))

    # Execute all queries atomically (all or nothing)
    self.db_service.execute_transaction(queries)
```

**Transaction Guarantees:**
- All queries succeed → COMMIT
- Any query fails → ROLLBACK all changes
- Database remains consistent even if webhook processing fails

---

## 6. Callback Queue Management

### 6.1 Get Pending Callbacks

**Purpose:** Retrieve callbacks ready to be processed

**BusinessCaseID:** BC-DA-005

```sql
SELECT
    ocq.callback_id,
    ocq.enrollment_id,
    ocq.scheduled_callback_time,
    ocq.attempt_count,
    ocq.created_at,

    -- Member info
    m.member_id,
    m.first_name,
    m.last_name,
    m.primary_phone,
    m.timezone,

    -- Enrollment info
    e.campaign_id,
    e.activation_start_date,

    -- Campaign info
    c.operating_tz,
    c.operating_start_time,
    c.operating_end_time,
    c.timezone_flag

FROM engage360.outreach_callback_queue ocq
INNER JOIN engage360.member_campaign_enrollments_enhanced e
    ON ocq.enrollment_id = e.enrollment_id
INNER JOIN engage360.members m
    ON e.member_id = m.member_id
INNER JOIN engage360.campaigns_enhanced c
    ON e.campaign_id = c.campaign_id

WHERE ocq.status = 'Pending'
  AND ocq.scheduled_callback_time <= SYSDATETIMEOFFSET()  -- Time reached
  AND (
      -- Not timed out (24 hours OR 3 attempts)
      DATEDIFF(HOUR, ocq.created_at, SYSDATETIMEOFFSET()) < 24
      AND ocq.attempt_count < 3
  )
  AND e.current_status = 'ENROLLED'  -- Enrollment still active

ORDER BY ocq.scheduled_callback_time ASC;  -- Process oldest first
```

### 6.2 Reschedule Callback

**Purpose:** Reschedule callback to next business day if business hours validation fails

**BusinessCaseID:** BC-DA-005

```sql
UPDATE engage360.outreach_callback_queue
SET scheduled_callback_time = %s,  -- Next business day at operating_start_time (e.g., 9:00 AM)
    attempt_count = attempt_count + 1,
    last_rescheduled_at = SYSDATETIMEOFFSET(),
    updated_at = SYSDATETIMEOFFSET()
WHERE callback_id = %s
  AND status = 'Pending';
```

**Rescheduling Logic (Python):**

```python
def _calculate_next_business_day_time(self, operating_tz: str, operating_start_time: time) -> datetime:
    """
    Calculate next business day at operating_start_time

    BusinessCaseID: BC-DA-005
    """
    tz = TimezoneConverter.to_pytz(operating_tz)
    now = datetime.now(pytz.UTC).astimezone(tz)
    next_day = now.date() + timedelta(days=1)

    # Skip weekends
    while next_day.weekday() >= 5:  # Saturday=5, Sunday=6
        next_day += timedelta(days=1)

    # Skip holidays (check company_holidays table)
    while self._is_holiday(next_day):
        next_day += timedelta(days=1)
        # Re-check for weekends after skipping holiday
        while next_day.weekday() >= 5:
            next_day += timedelta(days=1)

    # Combine date + time
    next_datetime = datetime.combine(next_day, operating_start_time)
    next_datetime_aware = tz.localize(next_datetime)

    return next_datetime_aware
```

### 6.3 Handle Callback Timeouts

**Purpose:** Mark callbacks as timed out if 24h elapsed OR 3 attempts reached

**BusinessCaseID:** BC-DA-005

```sql
UPDATE engage360.outreach_callback_queue
SET status = 'Timeout',
    timeout_reason = CASE
        WHEN DATEDIFF(HOUR, created_at, SYSDATETIMEOFFSET()) >= 24 THEN '24-hour timeout'
        WHEN attempt_count >= 3 THEN '3-attempt timeout'
        ELSE 'Unknown timeout'
    END,
    updated_at = SYSDATETIMEOFFSET()
WHERE status = 'Pending'
  AND (
      DATEDIFF(HOUR, created_at, SYSDATETIMEOFFSET()) >= 24  -- 24-hour timeout
      OR attempt_count >= 3                                   -- 3-attempt timeout
  );
```

**Timeout Conditions (OR logic):**
- **24-Hour Timeout:** Callback created more than 24 hours ago
- **3-Attempt Timeout:** Callback rescheduled 3 times (attempt_count >= 3)
- **Either condition** triggers timeout (not both required)

### 6.4 Mark Callback Completed

**Purpose:** Mark callback as completed after successful submission to Bland AI

**BusinessCaseID:** BC-DA-005

```sql
UPDATE engage360.outreach_callback_queue
SET status = 'Completed',
    completed_at = SYSDATETIMEOFFSET(),
    updated_at = SYSDATETIMEOFFSET()
WHERE callback_id = %s
  AND status = 'Pending';
```

---

## 7. Status Transitions & Audit Trail

### 7.1 Enrollment Status Transitions

**Valid States:** ENROLLED, COMPLETED, OPTED_OUT, UNENROLLED

**Allowed Transitions:**
- ENROLLED → COMPLETED (device activated OR campaign ended)
- ENROLLED → OPTED_OUT (member requested DO_NOT_CONTACT)
- ENROLLED → UNENROLLED (manual unenrollment)
- (No transitions FROM terminal states)

**Update Query:**

```sql
UPDATE engage360.member_campaign_enrollments_enhanced
SET current_status = %s,  -- New status
    updated_at = SYSDATETIMEOFFSET()
WHERE enrollment_id = %s
  AND current_status = %s;  -- Safety check: only update from expected previous status
```

### 7.2 Batch Status Transitions

**Valid States:** Pending, Submitted, Completed, Failed, Cancelled

**Allowed Transitions:**
- Pending → Submitted (Phase 3 after Bland AI success)
- Pending → Failed (Bland AI submission error)
- Submitted → Completed (Reconciler detects all attempts done)
- Submitted → Failed (Bland AI batch-level error)
- Submitted → Cancelled (manual cancellation)

**Update Query (Reconciler):**

```sql
-- Mark batch as Completed when all attempts have final dispositions
UPDATE engage360.outreach_batches
SET batch_status = 'Completed',
    completed_at = SYSDATETIMEOFFSET(),
    updated_at = SYSDATETIMEOFFSET()
WHERE batch_id IN (
    -- Find batches where all attempts are no longer Pending
    SELECT b.batch_id
    FROM engage360.outreach_batches b
    WHERE b.batch_status = 'Submitted'
      AND NOT EXISTS (
          SELECT 1
          FROM engage360.outreach_attempts oa
          WHERE oa.batch_id = b.batch_id
            AND oa.disposition = 'Pending'
      )
);
```

### 7.3 Attempt Disposition Transitions

**Valid States:** Pending, Completed, Failed, NoAnswer, Busy, VoicemailLeft, OptedOut, CallbackScheduled

**Transition:** Pending → (Any terminal state)

**Terminal States:** All states except Pending (no further transitions)

**Update Query (Webhook):**

```sql
UPDATE engage360.outreach_attempts
SET disposition = %s,
    completed_at = SYSDATETIMEOFFSET(),
    updated_at = SYSDATETIMEOFFSET()
WHERE attempt_id = %s
  AND disposition = 'Pending';
```

### 7.4 Callback Status Transitions

**Valid States:** Pending, Completed, Timeout

**Allowed Transitions:**
- Pending → Completed (business hours valid, submitted to Bland AI)
- Pending → Timeout (24h elapsed OR 3 attempts)
- Pending → Pending (rescheduled, attempt_count incremented)

**Transition Queries:** See Section 6 (Callback Queue Management)

---

## 8. Transaction Management

### 8.1 Transaction Patterns

Device Activation uses **DatabaseService.execute_transaction()** for all multi-query operations.

**Pattern:**

```python
def execute_transaction(queries: List[Tuple[str, Tuple]]) -> bool:
    """
    Execute multiple queries in single atomic transaction

    Args:
        queries: List of (query_string, params) tuples

    Returns:
        True if all queries succeeded, False if any failed
    """
    connection = None
    cursor = None

    try:
        connection = self._get_connection()
        cursor = connection.cursor()

        # Execute all queries
        for query, params in queries:
            cursor.execute(query, params)

        # Commit if all succeeded
        connection.commit()
        return True

    except Exception as e:
        # Rollback on any error
        if connection:
            connection.rollback()
        logger.error(f"Transaction failed: {e}")
        return False

    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
```

### 8.2 Critical Transactions

**File Processing (Phase 4):**
- MERGE members
- MERGE member_devices
- INSERT enrollments
- All 3 operations in single transaction

**Batch Creation (3-Phase):**
- INSERT batch
- INSERT attempts (1-100)
- All in single transaction (Phase 1 + Phase 2)
- Phase 3 is separate transaction after Bland AI success

**Webhook Processing:**
- UPDATE attempt
- UPDATE enrollment (if needed)
- INSERT callback (if needed)
- INSERT call log
- INSERT status history (if needed)
- All 4-5 operations in single transaction

### 8.3 Rollback Scenarios

| Scenario | Rollback Scope | Recovery |
|----------|----------------|----------|
| Staging error >10% | Entire file (all rows) | File moved to error/ folder |
| Validation error >50% | Entire file (all rows) | File moved to error/ folder |
| MERGE members fails | Phase 4 transaction | File remains in landing/, retry next run |
| Bland AI submission fails | Phase 1+2 transaction | Batch/attempts deleted, members remain eligible |
| Webhook processing fails | Webhook transaction | Bland AI retries webhook, duplicate detection prevents reprocessing |

---

## 9. Index Requirements & Performance

### 9.1 Required Indexes

**members table:**
```sql
CREATE NONCLUSTERED INDEX IX_members_member_id ON engage360.members(member_id);
CREATE NONCLUSTERED INDEX IX_members_primary_phone ON engage360.members(primary_phone);
```

**member_campaign_enrollments_enhanced table:**
```sql
CREATE NONCLUSTERED INDEX IX_enrollments_status_activation
ON engage360.member_campaign_enrollments_enhanced(current_status, activation_start_date)
INCLUDE (member_id, campaign_id, call_5_timestamp, campaign_end_date);

CREATE NONCLUSTERED INDEX IX_enrollments_member_campaign
ON engage360.member_campaign_enrollments_enhanced(member_id, campaign_id);
```

**outreach_attempts table:**
```sql
CREATE NONCLUSTERED INDEX IX_attempts_enrollment_ts
ON engage360.outreach_attempts(enrollment_id, attempt_ts DESC)
INCLUDE (disposition);

CREATE NONCLUSTERED INDEX IX_attempts_batch_disposition
ON engage360.outreach_attempts(batch_id, disposition);
```

**outreach_batches table:**
```sql
CREATE NONCLUSTERED INDEX IX_batches_status
ON engage360.outreach_batches(batch_status)
INCLUDE (batch_id, vendor_batch_id, created_at);
```

**outreach_callback_queue table:**
```sql
CREATE NONCLUSTERED INDEX IX_callbacks_status_time
ON engage360.outreach_callback_queue(status, scheduled_callback_time)
INCLUDE (enrollment_id, attempt_count, created_at);
```

**bland_call_logs table:**
```sql
CREATE UNIQUE NONCLUSTERED INDEX IX_call_logs_call_id
ON engage360.bland_call_logs(call_id);
```

### 9.2 Query Performance Metrics

| Query | Avg Duration | Rows Scanned | Rows Returned | Index Used |
|-------|--------------|--------------|---------------|------------|
| Eligibility query | 2-5 sec | 50K enrollments | 0-1000 | IX_enrollments_status_activation |
| Get pending callbacks | <1 sec | 1K callbacks | 0-100 | IX_callbacks_status_time |
| Duplicate detection | <100 ms | 500K logs | 0-1 | IX_call_logs_call_id (unique) |
| Batch reconciliation | <1 sec | 5K batches | 0-100 | IX_batches_status, IX_attempts_batch_disposition |

### 9.3 Performance Optimization Tips

**1. Use NOLOCK for Read-Only Queries:**
```sql
-- Eligibility query (read-only, no locks needed)
SELECT * FROM engage360.member_campaign_enrollments_enhanced WITH (NOLOCK)
WHERE ...
```

**2. Batch INSERT Operations:**
```python
# Instead of 100 separate INSERTs
for member in members:
    execute_query("INSERT ...", (member_id,))

# Use single transaction with 100 INSERTs
queries = [(insert_query, (member_id,)) for member in members]
execute_transaction(queries)
```

**3. Use DISTINCT Carefully:**
```sql
-- Avoid DISTINCT with ORDER BY (SQL Server limitation)
-- Use ROW_NUMBER() instead
WITH RankedMembers AS (
    SELECT
        member_id,
        ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY created_at DESC) AS rn
    FROM table
)
SELECT member_id FROM RankedMembers WHERE rn = 1;
```

**4. Limit Result Sets:**
```sql
-- Add TOP for large queries
SELECT TOP 1000 * FROM ...
```

---

## 10. Data Retention & Cleanup

### 10.1 Retention Policies

| Table | Retention Period | Cleanup Method |
|-------|------------------|----------------|
| members | Permanent | Manual deletion only |
| member_devices | Permanent | Manual deletion only |
| campaigns_enhanced | Permanent | Manual archival |
| member_campaign_enrollments_enhanced | Permanent | Status transitions only |
| outreach_batches | 90 days | Automated cleanup job |
| outreach_attempts | 90 days | Automated cleanup job |
| outreach_callback_queue | 7 days | Automated cleanup job |
| bland_call_logs | 1 year | Automated cleanup job |
| stg_device_activation_delta | 1 day | Automated cleanup job |

### 10.2 Cleanup Queries

**Staging Table Cleanup (Daily):**

```sql
-- Delete staging rows older than 1 day
DELETE FROM engage360_stg.stg_device_activation_delta
WHERE created_at < DATEADD(DAY, -1, SYSDATETIMEOFFSET());
```

**Callback Queue Cleanup (Weekly):**

```sql
-- Delete completed/timeout callbacks older than 7 days
DELETE FROM engage360.outreach_callback_queue
WHERE status IN ('Completed', 'Timeout')
  AND (completed_at < DATEADD(DAY, -7, SYSDATETIMEOFFSET())
       OR updated_at < DATEADD(DAY, -7, SYSDATETIMEOFFSET()));
```

**Batch/Attempt Cleanup (Monthly):**

```sql
-- Delete batches older than 90 days
DELETE FROM engage360.outreach_batches
WHERE created_at < DATEADD(DAY, -90, SYSDATETIMEOFFSET());

-- Orphaned attempts cleaned up via CASCADE DELETE foreign key
```

**Call Logs Cleanup (Annually):**

```sql
-- Delete call logs older than 1 year
DELETE FROM engage360.bland_call_logs
WHERE created_at < DATEADD(YEAR, -1, SYSDATETIMEOFFSET());
```

---

## Summary

This document provides comprehensive SQL reference for all Device Activation database operations:

1. **File Processing:** 5-phase ETL with staging, validation, and core table MERGE/INSERT
2. **Scheduler Operations:** Eligibility query (200+ lines) for Call 1-4 and Call 5+ logic
3. **Batch Tracking:** 3-phase pattern (Pending → Submitted → Completed)
4. **Webhook Processing:** Atomic updates across 4-5 tables
5. **Callback Management:** Queue operations with business hours validation and timeout logic
6. **Status Transitions:** Audit trail for enrollment, batch, attempt, and callback states
7. **Transaction Management:** Rollback capabilities for data consistency
8. **Performance:** Index requirements and optimization strategies
9. **Data Retention:** Cleanup policies and automated maintenance

**Related Documentation:**
- [Complete Architecture](DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md) - Master reference
- [System Architecture](../FLOWS/DEVICE_ACTIVATION_SYSTEM_ARCHITECTURE.md#diagram-2-database-schema-erd) - ERD diagrams
- [State Machines](../FLOWS/DEVICE_ACTIVATION_STATE_MACHINES.md) - Status transition diagrams

---

**End of Document**
