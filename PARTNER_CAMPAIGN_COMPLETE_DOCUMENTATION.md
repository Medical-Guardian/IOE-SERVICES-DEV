# Partner Campaign Scheduler - Complete Documentation

**Complete Technical Reference for IOE Partner Campaign Scheduler with Bland AI Integration**

---

## Table of Contents

1. [Overview](#overview)
2. [File Hierarchy](#file-hierarchy)
3. [Database Schema](#database-schema)
4. [Complete SQL Queries](#complete-sql-queries)
5. [Care Gap Details](#care-gap-details)
6. [Bland AI Integration](#bland-ai-integration)
7. [Code Examples by Component](#code-examples-by-component)
8. [Step-by-Step Guides](#step-by-step-guides)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Configuration Reference](#configuration-reference)

---

## Overview

The Partner Campaign Scheduler is an Azure Function that orchestrates automated voice campaigns for healthcare partners using Bland AI's batch calling API. It runs on a timer trigger (every 30 minutes) and can also be triggered manually via HTTP endpoint.

### Key Features
- **Timer-based execution**: Runs every 30 minutes at 5 minutes past the half-hour
- **Timezone-aware scheduling**: Supports both operating_tz (campaign timezone) and member_tz (individual member timezones)
- **Member-wise frequency protection**: Tracks attempts per member, not per batch
- **Disposition-based retry logic**: Handles Completed, Failed, NoAnswer, and Pending dispositions
- **Flexible care gap selection**: Prioritizes care gaps per campaign configuration
- **3-phase database tracking**: Create batch → Create attempts → Update with vendor_batch_id
- **DTC-compatible payload**: 18+ global parameters matching existing DTC implementation

### Architecture Pattern
```
Timer/HTTP Trigger → Campaign Qualification → Member Eligibility → Batch Build → Bland AI Submission → Database Tracking
```

---

## File Hierarchy

```
IOE-functions/
│
├── functions/
│   └── partner_campaign_scheduler.py          # Azure Function entry point (Timer + HTTP)
│
├── af_code/
│   ├── shared/
│   │   ├── bland_ai_client.py                 # Bland AI API client (shared)
│   │   └── timezone_utils.py                  # TimezoneConverter utility
│   │
│   ├── bland_ai_webhook/
│   │   └── services/
│   │       ├── config_manager.py              # Key Vault configuration manager
│   │       └── database_service.py            # Database connection service
│   │
│   └── partner_campaign_scheduler/
│       ├── models/
│       │   ├── batch_request.py               # BatchRequest, BatchResult models
│       │   ├── eligible_member.py             # EligibleMember model
│       │   └── qualified_campaign.py          # QualifiedCampaign model
│       │
│       ├── services/
│       │   ├── campaign_qualifier.py          # Identifies campaigns ready to run
│       │   ├── member_eligibility.py          # Finds eligible members per campaign
│       │   ├── batch_orchestrator.py          # Builds batch payloads
│       │   ├── database_tracker.py            # Tracks batches and attempts in DB
│       │   └── care_gap_mapper.py             # Maps care gap flags to completion flags
│       │
│       ├── CAMPAIGN_QUALIFICATION_LOGIC.md    # 1300+ line detailed qualification docs
│       └── README.md                          # High-level overview
│
├── requirements.txt                            # Python dependencies
└── host.json                                   # Azure Functions configuration
```

---

## Database Schema

### Core Tables Used

#### 1. `engage360.campaigns_enhanced`
**Purpose**: Campaign configuration and scheduling settings

| Column | Type | Description |
|--------|------|-------------|
| `campaign_id` | uniqueidentifier | Primary key |
| `org_id` | uniqueidentifier | Organization FK |
| `name` | nvarchar | Campaign display name |
| `campaign_description` | nvarchar | Description |
| `campaign_type` | nvarchar | Must be 'Partner' for this scheduler |
| `status` | nvarchar | Must be 'Active' or 'Testing' (case-insensitive) |
| `primary_channel` | nvarchar | Must be 'voice' for calls |
| `contact_pref` | nvarchar | 'member_preference', 'auto', 'phone' |
| `call_days_of_week` | nvarchar | Comma-separated: 'Monday,Tuesday,...' |
| `operating_start_time` | time | Daily window start (HH:MM:SS) |
| `operating_end_time` | time | Daily window end (HH:MM:SS) |
| `operating_tz` | nvarchar | Timezone: 'EST', 'CST', 'America/New_York' |
| `scheduling_mode` | nvarchar | 'Now', 'Flexible', 'Scheduled' |
| `frequency_value` | int | Number for frequency (e.g., 1) |
| `frequency_unit` | nvarchar | 'day', 'week', 'month' |
| `timezone_flag` | nvarchar | 'operating_tz' or 'member_tz' |
| `max_care_gaps_per_member` | int | Max care gaps to include per call |
| `audience_file_batch` | nvarchar | File batch identifier |
| `start_ts` | datetimeoffset | Campaign start date (time ignored, date-only comparison in operating_tz) |
| `end_ts` | datetimeoffset | Campaign end date (time ignored, date-only comparison in operating_tz) |

#### 2. `engage360.campaign_call_configs_enhanced`
**Purpose**: Bland AI configuration per campaign

| Column | Type | Description |
|--------|------|-------------|
| `config_id` | uniqueidentifier | Primary key |
| `campaign_id` | uniqueidentifier | Campaign FK |
| `call_type_id` | uniqueidentifier | Call type FK |
| `config_status` | nvarchar | Must be 'active' |
| `bland_parameters_global` | nvarchar(MAX) | JSON with ALL Bland AI parameters |

**Example `bland_parameters_global` JSON**:
```json
{
  "pathway_id": "partner-wellness-pathway-123",
  "pathway_version": "2024-01-15",
  "voice_id": "partner-voice-456",
  "webhook_url": "https://ioe-functions.azurewebsites.net/api/bland_ai_webhook",
  "wait_for_greeting": true,
  "record": true,
  "answered_by_enabled": true,
  "noise_cancellation": true,
  "interruption_threshold": 100,
  "block_interruptions": false,
  "max_duration": 300,
  "model": "enhanced",
  "temperature": 0.7,
  "language": "en",
  "background_track": "default",
  "endpoint": null,
  "from": "+15551234567",
  "timezone": "America/New_York"
}
```

#### 3. `engage360.member_campaign_enrollments_enhanced`
**Purpose**: Tracks member enrollment in campaigns

| Column | Type | Description |
|--------|------|-------------|
| `enrollment_id` | uniqueidentifier | Primary key |
| `member_id` | uniqueidentifier | Member FK |
| `campaign_id` | uniqueidentifier | Campaign FK |
| `current_status` | nvarchar | Must be 'Active' to be eligible |
| `enrollment_ts` | datetimeoffset | When member joined campaign |

#### 4. `engage360.outreach_batches`
**Purpose**: Tracks batch submissions to Bland AI

| Column | Type | Description |
|--------|------|-------------|
| `batch_id` | uniqueidentifier | Primary key |
| `campaign_id` | uniqueidentifier | Campaign FK |
| `vendor_batch_id` | nvarchar | Bland AI batch_id from response |
| `batch_status` | nvarchar | 'Pending' → 'Submitted' |
| `submitted_ts` | datetimeoffset | When batch was submitted |
| `created_ts` | datetimeoffset | When batch was created |

#### 5. `engage360.outreach_attempts`
**Purpose**: Tracks individual call attempts per member

| Column | Type | Description |
|--------|------|-------------|
| `attempt_id` | uniqueidentifier | Primary key |
| `batch_id` | uniqueidentifier | Batch FK |
| `enrollment_id` | uniqueidentifier | Enrollment FK |
| `member_id` | uniqueidentifier | Member FK |
| `disposition` | nvarchar | 'Pending', 'Completed', 'Failed', 'NoAnswer' |
| `attempt_ts` | datetimeoffset | When attempt was made |
| `call_details` | nvarchar(MAX) | JSON with phone, care gaps, metadata |

**Disposition Logic**:
- **Pending**: Call in progress, wait for completion (exclude from eligibility)
- **Completed**: Successful call (exclude from eligibility, counts toward frequency)
- **Failed**: Failed call (allow retry per policy)
- **NoAnswer**: No answer (allow retry per policy)

#### 6. `engage360.members`
**Purpose**: Member demographic and contact information

| Column | Type | Description |
|--------|------|-------------|
| `member_id` | uniqueidentifier | Primary key |
| `first_name` | nvarchar | Member first name |
| `last_name` | nvarchar | Member last name |
| `phone` | nvarchar | Primary phone number |
| `phone2` | nvarchar | Alternate phone |
| `member_tz` | nvarchar | Member's timezone preference |
| `file_batch` | nvarchar | Import batch identifier |
| `[care_gap_columns]` | bit | 30+ care gap flag columns |

**Care Gap Flag Columns** (examples):
- `awv_import_flag`, `ckd_import_flag`, `crc_import_flag`, `bcs_import_flag`
- `ccs_import_flag`, `col_import_flag`, `oud_import_flag`, `ssd_import_flag`
- `cbp_import_flag`, `cdc_hba1c_import_flag`, `cdc_eye_import_flag`
- `omw_import_flag`, `bcs_import_flag`, `fall_risk_import_flag`
- And 15+ more...

#### 7. `engage360.care_gaps`
**Purpose**: Maps care gap import flags to completion flags

| Column | Type | Description |
|--------|------|-------------|
| `care_gap_id` | uniqueidentifier | Primary key |
| `csv_import_flag_name` | nvarchar | Column name in members table (e.g., 'awv_import_flag') |
| `completion_flag_name` | nvarchar | Completion flag name (e.g., 'awv_completed') |
| `care_gap_name` | nvarchar | Display name (e.g., 'Annual Wellness Visit') |
| `priority` | int | Priority for selection |

#### 8. `engage360.orgs`
**Purpose**: Organization details for campaigns

| Column | Type | Description |
|--------|------|-------------|
| `org_id` | uniqueidentifier | Primary key |
| `org_name` | nvarchar | Organization name |
| `org_type` | nvarchar | Organization type |
| `partner_contact_name` | nvarchar | Partner contact person |

---

## Complete SQL Queries

### Query 1: Campaign Qualification Query

**File**: `af_code/partner_campaign_scheduler/services/campaign_qualifier.py:35-69`

**Purpose**: Find all Partner campaigns that are qualified to run right now based on schedule and configuration.

```sql
SELECT
    c.campaign_id,
    c.org_id,
    c.name,
    c.campaign_description,
    c.contact_pref,
    c.call_days_of_week,
    c.operating_start_time,
    c.operating_end_time,
    c.operating_tz,
    c.scheduling_mode,
    c.frequency_value,
    c.frequency_unit,
    c.timezone_flag,
    c.max_care_gaps_per_member,
    c.audience_file_batch,
    cc.config_id,
    cc.call_type_id,
    cc.bland_parameters_global,
    o.org_type,
    o.partner_contact_name,
    o.org_name
FROM engage360.campaigns_enhanced c
LEFT JOIN engage360.campaign_call_configs_enhanced cc
    ON c.campaign_id = cc.campaign_id
    AND cc.config_status = 'active'
LEFT JOIN engage360.orgs o ON c.org_id = o.org_id
WHERE c.campaign_type = 'Partner'
  AND LOWER(c.status) IN ('active', 'testing')
  AND c.primary_channel = 'voice'
  AND c.audience_file_batch IS NOT NULL
```

**Filters Explained**:
- `campaign_type = 'Partner'`: Only Partner campaigns (not DTC)
- `LOWER(c.status) IN ('active', 'testing')`: Campaign must be Active or Testing (case-insensitive)
- `primary_channel = 'voice'`: Voice calls only (not SMS/email)
- `audience_file_batch IS NOT NULL`: Campaign has an audience file assigned
- `config_status = 'active'`: Call configuration must be active

**Note on start_ts/end_ts**: These fields are retrieved from the database (added to SELECT clause) but validated in Python using timezone-aware **date-only** comparison via the `_is_campaign_time_valid()` method. This ensures campaigns start/end on the correct DATE in their configured `operating_tz`, regardless of the time component stored in the database.

**Post-Query Python Checks**:
After retrieving campaigns, Python code checks:
1. **Campaign date window** (`_is_campaign_time_valid()`): Current date (in `operating_tz`) falls between `start_ts` and `end_ts` dates (date-only comparison, time component ignored)
2. **Day of week**: Current day matches `call_days_of_week`
3. **Time window**: Current time is between `operating_start_time` and `operating_end_time`
4. **Timezone mode**: Uses `timezone_flag` to determine if checking operating_tz or member_tz
5. **Flexible scheduling**: If `scheduling_mode = 'Flexible'`, validates `frequency_value` and `frequency_unit`

---

### Query 2: Member Eligibility Query (COMPLETE WITH ALL CTEs)

**File**: `af_code/partner_campaign_scheduler/services/member_eligibility.py:40-244`

**Purpose**: Find up to 1000 eligible members for a campaign, prioritizing members who have never been attempted and applying frequency protection.

```sql
-- CTE 1: Get frequency from campaign configuration
WITH FrequencyConfig AS (
    SELECT
        frequency_value,
        frequency_unit
    FROM engage360.campaigns_enhanced
    WHERE campaign_id = @campaign_id
),

-- CTE 2: Calculate member-wise frequency count (how many COMPLETED attempts in the frequency window)
FrequencyCheck AS (
    SELECT
        mce.member_id,
        COUNT(DISTINCT oa.attempt_id) as completed_attempts_in_window
    FROM engage360.member_campaign_enrollments_enhanced mce
    INNER JOIN engage360.outreach_attempts oa ON mce.enrollment_id = oa.enrollment_id
    INNER JOIN engage360.outreach_batches ob ON oa.batch_id = ob.batch_id
    CROSS JOIN FrequencyConfig fc
    WHERE ob.campaign_id = @campaign_id
      AND oa.disposition = 'Completed'  -- Only count successful calls
      AND (
          -- If frequency_unit is 'day': check within last N days
          (fc.frequency_unit = 'day' AND oa.attempt_ts >= DATEADD(day, -fc.frequency_value, SYSDATETIMEOFFSET()))
          OR
          -- If frequency_unit is 'week': check within last N weeks
          (fc.frequency_unit = 'week' AND oa.attempt_ts >= DATEADD(week, -fc.frequency_value, SYSDATETIMEOFFSET()))
          OR
          -- If frequency_unit is 'month': check within last N months
          (fc.frequency_unit = 'month' AND oa.attempt_ts >= DATEADD(month, -fc.frequency_value, SYSDATETIMEOFFSET()))
      )
    GROUP BY mce.member_id
),

-- CTE 3: Check if member has an ACTIVE attempt today (Completed or Pending)
TodayActiveAttempts AS (
    -- Check if THIS MEMBER has an active attempt today (member-wise, not batch-wise)
    -- Exclude: 'Completed' (successful) and 'Pending' (in progress)
    -- Allow retry: 'Failed' and 'NoAnswer' per policy
    SELECT DISTINCT mce.member_id
    FROM engage360.member_campaign_enrollments_enhanced mce
    INNER JOIN engage360.outreach_attempts oa ON mce.enrollment_id = oa.enrollment_id
    INNER JOIN engage360.outreach_batches ob ON oa.batch_id = ob.batch_id
    WHERE ob.campaign_id = @campaign_id
      AND CAST(oa.attempt_ts AS DATE) = CAST(SYSDATETIMEOFFSET() AS DATE)
      AND oa.disposition IN ('Completed', 'Pending')  -- Exclude successful OR in-progress calls
),

-- CTE 4: Use ROW_NUMBER to deduplicate members (instead of SELECT DISTINCT)
RankedMembers AS (
    SELECT
        mce.member_id,
        mce.campaign_id,
        mce.enrollment_id,
        m.first_name,
        m.last_name,
        m.phone,
        m.phone2,
        m.member_tz,
        m.file_batch,
        -- Dynamically include all 30+ care gap flag columns
        m.awv_import_flag,
        m.ckd_import_flag,
        m.crc_import_flag,
        m.bcs_import_flag,
        m.ccs_import_flag,
        m.col_import_flag,
        m.oud_import_flag,
        m.ssd_import_flag,
        m.cbp_import_flag,
        m.cdc_hba1c_import_flag,
        m.cdc_eye_import_flag,
        m.omw_import_flag,
        m.fall_risk_import_flag,
        -- ... (15+ more care gap flags) ...
        fc.last_attempt_ts,
        ROW_NUMBER() OVER (
            PARTITION BY mce.member_id
            ORDER BY
                -- Prioritize members who have never been attempted (NULL last_attempt_ts)
                CASE WHEN fc.last_attempt_ts IS NULL THEN 0 ELSE 1 END,
                fc.last_attempt_ts ASC  -- Then oldest attempt first
        ) as rn
    FROM engage360.member_campaign_enrollments_enhanced mce
    INNER JOIN engage360.members m ON mce.member_id = m.member_id
    LEFT JOIN (
        -- Subquery to get last attempt timestamp per member
        SELECT
            mce2.member_id,
            MAX(oa.attempt_ts) as last_attempt_ts
        FROM engage360.member_campaign_enrollments_enhanced mce2
        INNER JOIN engage360.outreach_attempts oa ON mce2.enrollment_id = oa.enrollment_id
        INNER JOIN engage360.outreach_batches ob ON oa.batch_id = ob.batch_id
        WHERE ob.campaign_id = @campaign_id
        GROUP BY mce2.member_id
    ) fc ON mce.member_id = fc.member_id
    LEFT JOIN FrequencyCheck fchk ON mce.member_id = fchk.member_id
    WHERE mce.campaign_id = @campaign_id
      AND mce.current_status = 'Active'  -- Member enrollment must be Active
      AND m.file_batch = @audience_file_batch  -- Member must be in campaign's audience batch
      -- Frequency protection: Allow if no completed attempts in window
      AND (fchk.completed_attempts_in_window IS NULL OR fchk.completed_attempts_in_window = 0)
      -- Today protection: No active attempt today (Completed or Pending)
      AND mce.member_id NOT IN (SELECT member_id FROM TodayActiveAttempts)
)

-- Final SELECT: Get top 1000 deduplicated members
SELECT TOP 1000
    member_id,
    campaign_id,
    enrollment_id,
    first_name,
    last_name,
    phone,
    phone2,
    member_tz,
    file_batch,
    awv_import_flag,
    ckd_import_flag,
    crc_import_flag,
    bcs_import_flag,
    ccs_import_flag,
    col_import_flag,
    oud_import_flag,
    ssd_import_flag,
    cbp_import_flag,
    cdc_hba1c_import_flag,
    cdc_eye_import_flag,
    omw_import_flag,
    fall_risk_import_flag,
    -- ... (15+ more care gap flags) ...
    last_attempt_ts
FROM RankedMembers
WHERE rn = 1  -- Only first row per member (deduplication)
ORDER BY
    -- Prioritize members who have never been attempted
    CASE WHEN last_attempt_ts IS NULL THEN 0 ELSE 1 END,
    last_attempt_ts ASC
```

**Parameters**:
- `@campaign_id`: Campaign UUID
- `@audience_file_batch`: Audience file batch identifier from campaign

**Eligibility Criteria**:
1. ✅ **Active enrollment**: `mce.current_status = 'Active'`
2. ✅ **Correct audience**: `m.file_batch = @audience_file_batch`
3. ✅ **Frequency protection**: No completed attempts in last N days/weeks/months
4. ✅ **No active attempt today**: No 'Completed' or 'Pending' attempts today
5. ✅ **Failed/NoAnswer can retry**: These dispositions don't block eligibility

**Deduplication Strategy**:
- Uses `ROW_NUMBER() OVER (PARTITION BY mce.member_id)` instead of `SELECT DISTINCT`
- Avoids SQL Server error: "ORDER BY items must appear in the select list if SELECT DISTINCT is specified"
- Final WHERE filters `rn = 1` to get only first row per member

---

### Query 3: Care Gap Mapping Query

**File**: `af_code/partner_campaign_scheduler/services/care_gap_mapper.py:21-27`

**Purpose**: Load care gap import flag to completion flag mappings from database.

```sql
SELECT
    csv_import_flag_name,
    completion_flag_name
FROM engage360.care_gaps
```

**Example Results**:
| csv_import_flag_name | completion_flag_name |
|---------------------|---------------------|
| awv_import_flag | awv_completed |
| ckd_import_flag | ckd_completed |
| crc_import_flag | crc_completed |
| bcs_import_flag | bcs_completed |
| cdc_hba1c_import_flag | cdc_hba1c_completed |

**Usage**: When building call metadata, converts member care gap flags to completion flag names expected by Bland AI pathway.

---

### Query 4: Batch Creation Query

**File**: `af_code/partner_campaign_scheduler/services/database_tracker.py:29-60`

**Purpose**: Create a new outreach batch record with 'Pending' status.

```sql
INSERT INTO engage360.outreach_batches (
    batch_id,
    campaign_id,
    batch_status,
    created_ts,
    submitted_ts
)
VALUES (
    @batch_id,           -- UUID generated in Python
    @campaign_id,        -- Campaign UUID
    'Pending',           -- Initial status
    SYSDATETIMEOFFSET(), -- Created timestamp
    NULL                 -- Not yet submitted
)
```

**Parameters**:
- `@batch_id`: New UUID for this batch
- `@campaign_id`: Campaign UUID

---

### Query 5: Attempt Creation Query

**File**: `af_code/partner_campaign_scheduler/services/database_tracker.py:77-108`

**Purpose**: Create individual attempt records for each member in the batch.

```sql
INSERT INTO engage360.outreach_attempts (
    attempt_id,
    batch_id,
    enrollment_id,
    member_id,
    disposition,
    attempt_ts,
    call_details
)
VALUES (
    @attempt_id,         -- UUID generated in Python
    @batch_id,           -- Batch UUID
    @enrollment_id,      -- Member's enrollment UUID
    @member_id,          -- Member UUID
    'Pending',           -- Initial status
    SYSDATETIMEOFFSET(), -- Attempt timestamp
    @call_details        -- JSON with phone, care gaps, metadata
)
```

**call_details JSON Example**:
```json
{
  "phone_number": "+15551234567",
  "care_gaps": [
    {
      "name": "awv_import_flag",
      "completion_flag": "awv_completed"
    },
    {
      "name": "ckd_import_flag",
      "completion_flag": "ckd_completed"
    }
  ],
  "metadata": {
    "campaign_id": "abc-123",
    "first_name": "John",
    "last_name": "Doe"
  }
}
```

---

### Query 6: Batch Status Update Query

**File**: `af_code/partner_campaign_scheduler/services/database_tracker.py:127-140`

**Purpose**: Update batch with vendor_batch_id after successful Bland AI submission.

```sql
UPDATE engage360.outreach_batches
SET
    batch_status = 'Submitted',
    vendor_batch_id = @vendor_batch_id,
    submitted_ts = SYSDATETIMEOFFSET()
WHERE batch_id = @batch_id
```

**Parameters**:
- `@batch_id`: Batch UUID
- `@vendor_batch_id`: Bland AI's returned batch_id

---

## Care Gap Details

### Care Gap Mapping Service

**File**: `af_code/partner_campaign_scheduler/services/care_gap_mapper.py`

The CareGapMapper service loads mappings from `engage360.care_gaps` table on initialization and provides lookup functionality.

**Class Definition**:
```python
class CareGapMapper:
    """
    Service to map care gap import flags to completion flag names
    Loads mappings from [engage360].[care_gaps] table on initialization.
    """

    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        self.care_gap_mapping = {}  # {csv_import_flag_name: completion_flag_name}
        self._load_care_gap_mapping()
```

**Loading Mapping**:
```python
def _load_care_gap_mapping(self):
    """Load care gap mappings from database into memory"""
    query = """
        SELECT
            csv_import_flag_name,
            completion_flag_name
        FROM engage360.care_gaps
    """

    results = self.db_service.execute_query(query, fetch_results=True)

    for row in results:
        csv_flag = row['csv_import_flag_name']
        completion_flag = row['completion_flag_name']
        self.care_gap_mapping[csv_flag] = completion_flag

    logger.info(f"📋 [CARE-GAP] Loaded {len(self.care_gap_mapping)} care gap mappings")
```

**Lookup Function**:
```python
def get_completion_flag_name(self, csv_import_flag_name: str) -> Optional[str]:
    """
    Get completion flag name for a given import flag

    Args:
        csv_import_flag_name: e.g., "awv_import_flag"

    Returns:
        completion_flag_name: e.g., "awv_completed"
        None if mapping not found
    """
    return self.care_gap_mapping.get(csv_import_flag_name)
```

### Care Gap Selection Logic

**File**: `af_code/partner_campaign_scheduler/services/batch_orchestrator.py:208-241`

**Purpose**: Select up to `max_care_gaps` care gaps for each member call.

```python
def _select_care_gaps(self, member: EligibleMember, campaign: QualifiedCampaign) -> List[Dict[str, str]]:
    """
    Select care gaps for a member based on campaign configuration

    Args:
        member: EligibleMember with all care gap flags
        campaign: QualifiedCampaign with max_care_gaps configuration

    Returns:
        List of care gap dicts with 'name' and 'completion_flag'
    """
    max_gaps = campaign.max_care_gaps or 3  # Default to 3 if not set

    # All 30+ possible care gap flag columns
    care_gap_flags = [
        'awv_import_flag', 'ckd_import_flag', 'crc_import_flag',
        'bcs_import_flag', 'ccs_import_flag', 'col_import_flag',
        'oud_import_flag', 'ssd_import_flag', 'cbp_import_flag',
        'cdc_hba1c_import_flag', 'cdc_eye_import_flag',
        'omw_import_flag', 'fall_risk_import_flag',
        # ... 15+ more flags ...
    ]

    selected_gaps = []

    for flag_name in care_gap_flags:
        if len(selected_gaps) >= max_gaps:
            break  # Reached max limit

        # Check if member has this care gap (flag value = 1 or True)
        flag_value = getattr(member, flag_name, None)

        if flag_value:  # Care gap exists
            # Get completion flag name from mapper
            completion_flag = self.care_gap_mapper.get_completion_flag_name(flag_name)

            if completion_flag:
                selected_gaps.append({
                    'name': flag_name,
                    'completion_flag': completion_flag
                })

    logger.info(f"🎯 [BATCH-ORCHESTRATOR] Selected {len(selected_gaps)} care gaps for member (max={max_gaps})")
    return selected_gaps
```

**Selection Rules**:
1. Iterate through all care gap flag columns in order
2. Include care gap if member's flag value is `1` or `True`
3. Stop when `max_care_gaps_per_member` limit is reached
4. Map each import flag to its completion flag name using CareGapMapper

### Complete Care Gap List

**All 30+ Care Gap Flags** (from `engage360.members` table):

| Import Flag | Completion Flag | Full Name |
|------------|----------------|-----------|
| awv_import_flag | awv_completed | Annual Wellness Visit |
| ckd_import_flag | ckd_completed | Chronic Kidney Disease Monitoring |
| crc_import_flag | crc_completed | Colorectal Cancer Screening |
| bcs_import_flag | bcs_completed | Breast Cancer Screening |
| ccs_import_flag | ccs_completed | Cervical Cancer Screening |
| col_import_flag | col_completed | Colonoscopy |
| oud_import_flag | oud_completed | Opioid Use Disorder |
| ssd_import_flag | ssd_completed | Social Services Determination |
| cbp_import_flag | cbp_completed | Controlling Blood Pressure |
| cdc_hba1c_import_flag | cdc_hba1c_completed | Diabetes HbA1c Control |
| cdc_eye_import_flag | cdc_eye_completed | Diabetes Eye Exam |
| omw_import_flag | omw_completed | Osteoporosis Management Women |
| fall_risk_import_flag | fall_risk_completed | Falls Risk Assessment |
| bcs_fu_import_flag | bcs_fu_completed | Breast Cancer Screening Follow-up |
| ccs_fu_import_flag | ccs_fu_completed | Cervical Cancer Screening Follow-up |
| art_import_flag | art_completed | Adherence to Refill of Diabetes Medications |
| mrp_import_flag | mrp_completed | Medication Reconciliation Post-Discharge |
| trc_import_flag | trc_completed | Transitions of Care |
| spr_import_flag | spr_completed | Statin Preventive Therapy |
| dms_import_flag | dms_completed | Disease Modifying Anti-Rheumatic Drug |
| ra_import_flag | ra_completed | Rheumatoid Arthritis Management |
| ibd_import_flag | ibd_completed | Inflammatory Bowel Disease |
| ... | ... | ... |

*(15+ additional care gaps depending on organization configuration)*

---

## Bland AI Integration

### Bland AI Client Architecture

**File**: `af_code/shared/bland_ai_client.py`

The BlandAIClient is a shared service following the DTC Intro Call pattern for batch submission.

### Initialization

```python
class BlandAIClient:
    """
    Shared Bland AI API client following IOE patterns

    Uses synchronous HTTP requests (requests library) for batch submission.
    This follows the architecture pattern used by DTC Intro Call function.
    """

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager

        # Fetch secrets from Azure Key Vault
        self.api_key = config_manager.get_config("BlandAIkey")
        self.encrypted_key = config_manager.get_config("Blandaitwilio")  # Twilio encryption key
        self.batch_url = config_manager.get_config(
            "BLAND_AI_BATCH_URL",
            "https://api.bland.ai/v2/batches/create"  # Default endpoint
        )

        # Validation
        if not self.api_key:
            logger.error("🚨 [BLAND-CLIENT] BlandAIkey not configured in Key Vault")
            raise ValueError("Bland AI API key is required")

        if not self.encrypted_key:
            logger.warning("⚠️ [BLAND-CLIENT] Blandaitwilio (encrypted_key) not configured")
```

### Three-Header Pattern (DTC Compatible)

```python
def submit_batch_calls(self, batch_request) -> Dict[str, Any]:
    """Submit batch call request to Bland AI (SYNCHRONOUS)"""

    # Build headers following DTC pattern (3 headers total)
    headers = {
        "Authorization": f"Bearer {self.api_key}",  # 1. Bland AI API authentication
        "Content-Type": "application/json",          # 2. JSON payload format
    }

    # 3. Add encrypted_key header if available (DTC pattern - Twilio encryption key)
    if self.encrypted_key:
        headers["encrypted_key"] = self.encrypted_key
        logger.info("🔐 [BLAND-CLIENT] Added encrypted_key header (Blandaitwilio)")
    else:
        logger.warning("⚠️ [BLAND-CLIENT] encrypted_key header NOT added")
```

### All 18 Bland AI Global Parameters

**File**: `af_code/shared/bland_ai_client.py:74-100`

The client extracts ALL parameters from `bland_parameters_global` JSON field:

```python
# Extract all 18+ parameters from bland_parameters_global JSON
bland_params = batch_request.bland_parameters_global or {}

# Build global_config with ALL parameters (filter None values like DTC)
global_config = {
    k: v
    for k, v in {
        # 1. Pathway Configuration
        "pathway_id": batch_request.pathway_id,              # Required: Bland AI pathway UUID
        "pathway_version": bland_params.get("pathway_version"),  # Optional: Pathway version

        # 2. Voice Configuration
        "voice": batch_request.voice_id,                     # Required: Voice UUID

        # 3. Call Behavior
        "wait_for_greeting": bland_params.get("wait_for_greeting"),  # Wait for answerer to speak first
        "record": bland_params.get("record"),                # Record the call
        "answered_by_enabled": bland_params.get("answered_by_enabled"),  # AMD detection

        # 4. Audio Processing
        "noise_cancellation": bland_params.get("noise_cancellation"),  # Enable noise cancellation
        "interruption_threshold": bland_params.get("interruption_threshold"),  # Interruption sensitivity (0-200)
        "block_interruptions": bland_params.get("block_interruptions"),  # Block user interruptions

        # 5. Call Duration
        "max_duration": bland_params.get("max_duration"),    # Max call duration in seconds

        # 6. AI Model Configuration
        "model": bland_params.get("model"),                  # AI model: "base", "turbo", "enhanced"
        "temperature": bland_params.get("temperature"),      # Response randomness (0.0-1.0)
        "language": bland_params.get("language"),            # Language code: "en", "es", etc.

        # 7. Audio Customization
        "background_track": bland_params.get("background_track"),  # Background audio URL

        # 8. Integration
        "endpoint": bland_params.get("endpoint"),            # Custom endpoint for transfers
        "from": bland_params.get("from"),                    # Caller ID phone number
        "timezone": bland_params.get("timezone"),            # Timezone for scheduling
        "webhook": bland_params.get("webhook") or bland_params.get("webhook_url"),  # Webhook URL
    }.items()
    if v is not None  # Only include non-None values (DTC pattern)
}
```

**Parameter Details**:

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `pathway_id` | string | Bland AI conversational pathway UUID | "partner-wellness-pathway-123" |
| `pathway_version` | string | Specific pathway version | "2024-01-15" |
| `voice` | string | Voice UUID for TTS | "partner-voice-456" |
| `wait_for_greeting` | boolean | Wait for answerer to speak first | `true` |
| `record` | boolean | Record the call | `true` |
| `answered_by_enabled` | boolean | Answering Machine Detection | `true` |
| `noise_cancellation` | boolean | Enable noise cancellation | `true` |
| `interruption_threshold` | integer | Sensitivity 0-200 (higher = less sensitive) | `100` |
| `block_interruptions` | boolean | Block user interruptions during speech | `false` |
| `max_duration` | integer | Max call duration in seconds | `300` (5 minutes) |
| `model` | string | AI model: "base", "turbo", "enhanced" | "enhanced" |
| `temperature` | float | Response randomness 0.0-1.0 | `0.7` |
| `language` | string | Language code | "en" |
| `background_track` | string | Background audio URL | "https://..." |
| `endpoint` | string | Custom endpoint for transfers | null |
| `from` | string | Caller ID phone number | "+15551234567" |
| `timezone` | string | Timezone for scheduling | "America/New_York" |
| `webhook` | string | Webhook URL for call events | "https://ioe-functions..." |

### Complete Bland AI Payload Structure

**Payload Format** (following DTC pattern):

```json
{
  "global": {
    "pathway_id": "partner-wellness-pathway-123",
    "pathway_version": "2024-01-15",
    "voice": "partner-voice-456",
    "wait_for_greeting": true,
    "record": true,
    "answered_by_enabled": true,
    "noise_cancellation": true,
    "interruption_threshold": 100,
    "block_interruptions": false,
    "max_duration": 300,
    "model": "enhanced",
    "temperature": 0.7,
    "language": "en",
    "background_track": "default",
    "from": "+15551234567",
    "timezone": "America/New_York",
    "webhook": "https://ioe-functions.azurewebsites.net/api/bland_ai_webhook"
  },
  "call_objects": [
    {
      "phone_number": "+15559876543",
      "request_data": {
        "first_name": "John",
        "last_name": "Doe",
        "care_gaps": [
          {
            "name": "awv_import_flag",
            "completion_flag": "awv_completed"
          },
          {
            "name": "ckd_import_flag",
            "completion_flag": "ckd_completed"
          }
        ]
      },
      "metadata": {
        "campaign_id": "abc-123-def-456",
        "enrollment_id": "xyz-789-uvw-012",
        "member_id": "member-345-678"
      }
    }
  ]
}
```

**Payload Building Code** (`bland_ai_client.py:115-128`):

```python
# Convert "calls" to "call_objects" with "phone_number" field (DTC format)
call_objects = []
for call in batch_request.calls:
    call_obj = {
        "phone_number": call["to"],  # Rename "to" to "phone_number"
        "request_data": call["request_data"],
        "metadata": call["metadata"]
    }
    call_objects.append(call_obj)

payload = {
    "global": global_config,
    "call_objects": call_objects
}
```

### HTTP Request (Synchronous)

```python
# SYNCHRONOUS HTTP POST - blocks until response or timeout
response = requests.post(
    self.batch_url,  # https://api.bland.ai/v2/batches/create
    headers=headers,
    json=payload,
    timeout=60  # Wait max 60 seconds
)

logger.info(f"📡 [BLAND-CLIENT] Response status: {response.status_code}")

if response.status_code == 200:
    response_data = response.json()
    returned_batch_id = response_data.get("batch_id")

    logger.info(f"✅ [BLAND-CLIENT] Batch submitted successfully")
    logger.info(f"📦 [BLAND-CLIENT] Returned Batch ID: {returned_batch_id}")

    return {
        "success": True,
        "batch_id": returned_batch_id,
        "calls_submitted": len(call_objects),
        "response": response_data
    }
```

### Success Response Example

```json
{
  "batch_id": "bland-batch-abc123",
  "status": "queued",
  "calls_count": 150
}
```

---

## Webhook Processing for Partner Campaigns

### Overview

Partner campaign call results are processed through the Bland AI webhook endpoint at `/api/bland_ai_webhook`. The webhook updates call attempt records and member enrollment status based on call outcomes.

**File**: `af_code/bland_ai_webhook/services/database_orchestrator.py` (Method: `_build_update_enrollment`)

### Partner Campaign-Specific Behavior

Partner campaigns have **special handling** to prevent incorrect status updates:

**✅ Allowed Status Update**:
- **OPTED_OUT**: When member requests do-not-contact (disposition: DO_NOT_CONTACT, OPT_OUT)
  - Updates `member_campaign_enrollments_enhanced.current_status` from 'Active' → 'OPTED_OUT'

**🚫 Prevented Status Updates**:
- **ENROLLED**: Partner campaigns do NOT use 'ENROLLED' status (they use 'Active')
- **All other statuses**: Member remains 'Active' for future attempts

### Database Updates on Webhook Receipt

#### Tables Updated (4 Total)

1. **`bland_call_logs`** - Complete webhook audit trail (always updated)
2. **`bland_raw_response`** - Raw JSON payload (always updated)
3. **`outreach_attempts`** - Call attempt details (always updated)
4. **`member_campaign_enrollments_enhanced`** - Enrollment status (**only for OPTED_OUT**)

### Webhook Processing Flow for Partner Campaigns

```python
# Step 1: Identify campaign type
campaign_type = metadata.get("campaign_type")  # "Partner"
is_partner_campaign = campaign_type == "Partner"

# Step 2: Map disposition to enrollment status
# Examples:
# - INTERESTED → new_status = "ENROLLED" (default fallback)
# - DO_NOT_CONTACT → new_status = "OPTED_OUT"
# - NO_ANSWER → new_status = "Retry"

# Step 3: Apply Partner campaign filtering
if is_partner_campaign:
    if new_status.upper() == "OPTED_OUT":
        # ✅ Update status: 'Active' → 'OPTED_OUT'
        UPDATE member_campaign_enrollments_enhanced
           SET current_status = 'OPTED_OUT',
               last_attempt_ts = SYSDATETIMEOFFSET()
         WHERE member_id = @member_id
           AND campaign_id = @campaign_id
    else:
        # 🚫 Skip enrollment update - member remains 'Active'
        # Call still logged in outreach_attempts table
        return None  # No enrollment status update
```

### Example Dispositions and Resulting Actions

| Bland AI Disposition | Mapped Status | Partner Campaign Action |
|---------------------|---------------|------------------------|
| `INTERESTED` | ENROLLED | **No status update** (remains 'Active') |
| `NOT_INTERESTED` | Completed | **No status update** (remains 'Active') |
| `CALL_BACK_SCHEDULED` | Completed | **No status update** (remains 'Active') |
| `DO_NOT_CONTACT` | OPTED_OUT | **Update to OPTED_OUT** ✅ |
| `NO_ANSWER` | Retry | **No status update** (remains 'Active') |
| `FAILED` | Failed | **No status update** (remains 'Active') |

### Key Differences from DTC Campaigns

| Aspect | Partner Campaigns | DTC Campaigns |
|--------|------------------|---------------|
| **Initial Status** | 'Active' | 'ENROLLED' or 'PENDING' |
| **Successful Call** | No status update (stays 'Active') | Updates to 'ENROLLED' or other statuses |
| **Opt-Out** | Updates to 'OPTED_OUT' | Updates to 'OPTED_OUT' |
| **Auto-Transition** | Not applicable | Intro → Wellness auto-transition |
| **Status Tracking** | Binary: Active or OPTED_OUT | Multiple states: ENROLLED, PENDING, UNENROLLED, OPTED_OUT |

### Logging Output Example

```
🎯 [DB-ORCH] Campaign identification:
🎯 [DB-ORCH]   - Is Intro Campaign: ❌
🎯 [DB-ORCH]   - Is Wellness Campaign: ❌
🎯 [DB-ORCH]   - Campaign Type from metadata: Partner
🎯 [DB-ORCH]   - Is Partner Campaign: ✅
🤝 [DB-ORCH] ℹ️ Partner campaign call completed successfully
🤝 [DB-ORCH] ℹ️ No enrollment status change needed - member remains 'Active'
🤝 [DB-ORCH] ℹ️ Received status 'ENROLLED' will be logged in outreach_attempts only
🤝 [DB-ORCH] ℹ️ Partner campaigns maintain 'Active' status for all non-opt-out calls
```

### Why This Design?

**Rationale**: Partner campaigns use a simpler status model:
- **'Active'**: Member is eligible for outreach attempts
- **'OPTED_OUT'**: Member has requested no contact

Unlike DTC campaigns which track enrollment progression (PENDING → ENROLLED → UNENROLLED), Partner campaigns only need to track:
1. Is the member contactable? (Active = Yes, OPTED_OUT = No)
2. Frequency protection via `outreach_attempts` table (not enrollment status)

This design:
- ✅ Prevents incorrect status values in database
- ✅ Simplifies Partner campaign logic (binary Active/OptedOut)
- ✅ Maintains call history in `outreach_attempts` for frequency protection
- ✅ Respects opt-out requests immediately

### SQL Query Executed for Opt-Out

```sql
UPDATE engage360.member_campaign_enrollments_enhanced
   SET current_status = 'OPTED_OUT',
       last_attempt_ts = SYSDATETIMEOFFSET()
 WHERE member_id = @member_id
   AND campaign_id = @campaign_id
   AND (current_status IS NULL OR current_status <> 'OPTED_OUT')  -- Idempotent
```

**Idempotent Protection**: The `AND (current_status <> 'OPTED_OUT')` clause prevents duplicate updates if webhook is called multiple times.

---

## Code Examples by Component

### Component 1: Campaign Qualification

**File**: `af_code/partner_campaign_scheduler/services/campaign_qualifier.py`

**What It Does**: Identifies campaigns that are qualified to run right now based on schedule and timezone.

**Key Methods**:

```python
class CampaignQualifier:
    def get_qualified_campaigns(self) -> List[QualifiedCampaign]:
        """Find all Partner campaigns qualified to run right now"""
        # 1. Execute campaign query (shown in SQL Queries section)
        # 2. For each campaign, check timezone and schedule
        # 3. Return list of QualifiedCampaign objects

    def _is_campaign_qualified_now(self, campaign_data: dict, now_utc: datetime) -> bool:
        """Check if campaign qualifies at current time"""
        # Implements timezone-aware day/time checking

    def _parse_bland_parameters(self, bland_parameters_json: str, campaign_name: str) -> dict:
        """Parse bland_parameters_global JSON field"""
        # Extracts pathway_id, voice_id, webhook_url, etc.
```

**Example Usage**:
```python
# In partner_campaign_scheduler.py
qualifier = CampaignQualifier(db_service)
qualified_campaigns = qualifier.get_qualified_campaigns()

for campaign in qualified_campaigns:
    logger.info(f"✅ Campaign qualified: {campaign.name}")
    logger.info(f"   Pathway ID: {campaign.pathway_id}")
    logger.info(f"   Voice ID: {campaign.voice_id}")
```

**Timezone Logic** (`campaign_qualifier.py:141-237`):

```python
def _is_campaign_qualified_now(self, campaign_data: dict, now_utc: datetime) -> bool:
    """Check if campaign is qualified to run at current time"""

    timezone_flag = campaign_data.get('timezone_flag', 'operating_tz')

    if timezone_flag == 'member_tz':
        # Member timezone mode: Check if ANY US timezone qualifies
        us_timezones = TimezoneConverter.get_us_timezones_pytz()

        for tz_name, tz in us_timezones.items():
            now_in_tz = now_utc.astimezone(tz)
            current_day = now_in_tz.strftime('%A')
            current_time = now_in_tz.time()

            # Check both day AND time for this timezone
            if current_day in call_days and start_time <= current_time <= end_time:
                return True  # At least one timezone qualifies

        return False  # No timezone qualifies

    else:
        # Operating timezone mode: Check campaign's specific timezone
        campaign_tz = TimezoneConverter.to_pytz(campaign_data.get('operating_tz', 'EST'))
        now_in_campaign_tz = now_utc.astimezone(campaign_tz)

        current_day = now_in_campaign_tz.strftime('%A')
        current_time = now_in_campaign_tz.time()

        # Check day and time in campaign's timezone
        if current_day not in call_days:
            return False
        if not (start_time <= current_time <= end_time):
            return False

        return True
```

---

### Component 2: Member Eligibility

**File**: `af_code/partner_campaign_scheduler/services/member_eligibility.py`

**What It Does**: Finds up to 1000 eligible members for a campaign with frequency protection.

**Key Method**:

```python
class MemberEligibility:
    def get_eligible_members(
        self,
        campaign: QualifiedCampaign,
        timezone_filter: str = None
    ) -> List[EligibleMember]:
        """
        Get eligible members for a campaign

        Args:
            campaign: QualifiedCampaign object
            timezone_filter: Optional timezone to filter members (for member_tz mode)

        Returns:
            List of EligibleMember objects (max 1000)
        """
        # 1. Build parameters for SQL query
        # 2. Execute member eligibility query (shown in SQL Queries section)
        # 3. Convert results to EligibleMember objects
        # 4. Return list
```

**Example Usage**:
```python
# In partner_campaign_scheduler.py
member_eligibility = MemberEligibility(db_service)

if campaign.timezone_flag == 'member_tz':
    # Member timezone mode: Process each timezone separately
    us_timezones = TimezoneConverter.get_us_timezones()

    for tz_name in us_timezones:
        eligible_members = member_eligibility.get_eligible_members(
            campaign,
            timezone_filter=tz_name
        )
        # Process batch for this timezone...
else:
    # Operating timezone mode: Process all members together
    eligible_members = member_eligibility.get_eligible_members(campaign)
    # Process batch...
```

**Frequency Protection Logic** (in SQL CTE):

```sql
-- Calculate how many COMPLETED attempts in frequency window
FrequencyCheck AS (
    SELECT
        mce.member_id,
        COUNT(DISTINCT oa.attempt_id) as completed_attempts_in_window
    FROM engage360.member_campaign_enrollments_enhanced mce
    INNER JOIN engage360.outreach_attempts oa ON mce.enrollment_id = oa.enrollment_id
    CROSS JOIN FrequencyConfig fc  -- Get frequency_value and frequency_unit
    WHERE oa.disposition = 'Completed'  -- Only successful calls
      AND (
          -- Check within frequency window based on unit
          (fc.frequency_unit = 'day' AND oa.attempt_ts >= DATEADD(day, -fc.frequency_value, SYSDATETIMEOFFSET()))
          OR
          (fc.frequency_unit = 'week' AND oa.attempt_ts >= DATEADD(week, -fc.frequency_value, SYSDATETIMEOFFSET()))
          OR
          (fc.frequency_unit = 'month' AND oa.attempt_ts >= DATEADD(month, -fc.frequency_value, SYSDATETIMEOFFSET()))
      )
    GROUP BY mce.member_id
)

-- Later in WHERE clause:
AND (fchk.completed_attempts_in_window IS NULL OR fchk.completed_attempts_in_window = 0)
```

---

### Component 3: Batch Orchestration

**File**: `af_code/partner_campaign_scheduler/services/batch_orchestrator.py`

**What It Does**: Builds batch payloads with call objects, care gaps, and metadata.

**Key Methods**:

```python
class BatchOrchestrator:
    def build_batch_request(
        self,
        campaign: QualifiedCampaign,
        eligible_members: List[EligibleMember]
    ) -> BatchRequest:
        """
        Build batch request for Bland AI submission

        Args:
            campaign: QualifiedCampaign with Bland AI configuration
            eligible_members: List of EligibleMember objects

        Returns:
            BatchRequest object ready for submission
        """
        # 1. Build call objects for each member
        # 2. Select care gaps per member
        # 3. Add metadata
        # 4. Return BatchRequest
```

**Building Call Objects** (`batch_orchestrator.py:125-189`):

```python
def _build_call_objects(
    self,
    campaign: QualifiedCampaign,
    eligible_members: List[EligibleMember]
) -> List[Dict[str, Any]]:
    """Build call objects for batch submission"""

    calls = []

    for member in eligible_members:
        # 1. Determine phone number based on contact preference
        phone = self._get_member_phone(member, campaign.contact_pref)

        if not phone:
            logger.warning(f"⚠️ Skipping member {member.member_id}: No valid phone")
            continue

        # 2. Select care gaps for this member
        care_gaps = self._select_care_gaps(member, campaign)

        # 3. Build request_data for Bland AI pathway
        request_data = {
            "first_name": member.first_name,
            "last_name": member.last_name,
            "care_gaps": care_gaps  # List of {name, completion_flag} dicts
        }

        # 4. Build metadata for tracking
        metadata = {
            "campaign_id": str(campaign.campaign_id),
            "enrollment_id": str(member.enrollment_id),
            "member_id": str(member.member_id),
            "org_id": str(campaign.org_id),
            "config_id": str(campaign.config_id) if campaign.config_id else None
        }

        # 5. Add call object
        call_obj = {
            "to": phone,
            "request_data": request_data,
            "metadata": metadata
        }
        calls.append(call_obj)

    logger.info(f"📞 [BATCH-ORCHESTRATOR] Built {len(calls)} call objects")
    return calls
```

**Care Gap Selection** (`batch_orchestrator.py:208-241`):

```python
def _select_care_gaps(self, member: EligibleMember, campaign: QualifiedCampaign) -> List[Dict[str, str]]:
    """Select care gaps for a member"""

    max_gaps = campaign.max_care_gaps or 3
    care_gap_flags = [
        'awv_import_flag', 'ckd_import_flag', 'crc_import_flag',
        # ... (30+ flags)
    ]

    selected_gaps = []

    for flag_name in care_gap_flags:
        if len(selected_gaps) >= max_gaps:
            break

        flag_value = getattr(member, flag_name, None)

        if flag_value:  # Member has this care gap
            completion_flag = self.care_gap_mapper.get_completion_flag_name(flag_name)

            if completion_flag:
                selected_gaps.append({
                    'name': flag_name,
                    'completion_flag': completion_flag
                })

    return selected_gaps
```

---

### Component 4: Database Tracking

**File**: `af_code/partner_campaign_scheduler/services/database_tracker.py`

**What It Does**: Tracks batches and attempts in database using 3-phase pattern.

**3-Phase Tracking**:

```python
class DatabaseTracker:
    def track_batch_submission(
        self,
        campaign: QualifiedCampaign,
        calls: List[Dict[str, Any]],
        vendor_batch_id: str
    ) -> uuid.UUID:
        """
        Track batch submission in database (3-phase pattern)

        Phase 1: Create batch record with 'Pending' status
        Phase 2: Create attempt records with 'Pending' disposition
        Phase 3: Update batch with vendor_batch_id and 'Submitted' status

        Returns:
            batch_id (UUID)
        """
```

**Phase 1 - Create Batch**:

```python
def _create_batch_record(self, campaign_id: uuid.UUID) -> uuid.UUID:
    """Phase 1: Create batch record with Pending status"""

    batch_id = uuid.uuid4()

    query = """
        INSERT INTO engage360.outreach_batches (
            batch_id,
            campaign_id,
            batch_status,
            created_ts,
            submitted_ts
        )
        VALUES (?, ?, 'Pending', SYSDATETIMEOFFSET(), NULL)
    """

    params = [str(batch_id), str(campaign_id)]
    self.db_service.execute_query(query, params=params, fetch_results=False)

    logger.info(f"📦 [DB-TRACKER] Created batch: {batch_id}")
    return batch_id
```

**Phase 2 - Create Attempts**:

```python
def _create_attempt_records(self, batch_id: uuid.UUID, calls: List[Dict]) -> None:
    """Phase 2: Create attempt records with Pending disposition"""

    for call in calls:
        attempt_id = uuid.uuid4()

        # Build call_details JSON
        call_details = {
            "phone_number": call["to"],
            "care_gaps": call["request_data"].get("care_gaps", []),
            "metadata": call["metadata"]
        }

        query = """
            INSERT INTO engage360.outreach_attempts (
                attempt_id,
                batch_id,
                enrollment_id,
                member_id,
                disposition,
                attempt_ts,
                call_details
            )
            VALUES (?, ?, ?, ?, 'Pending', SYSDATETIMEOFFSET(), ?)
        """

        params = [
            str(attempt_id),
            str(batch_id),
            str(call["metadata"]["enrollment_id"]),
            str(call["metadata"]["member_id"]),
            json.dumps(call_details)
        ]

        self.db_service.execute_query(query, params=params, fetch_results=False)

    logger.info(f"📝 [DB-TRACKER] Created {len(calls)} attempt records")
```

**Phase 3 - Update Batch**:

```python
def _update_batch_with_vendor_id(self, batch_id: uuid.UUID, vendor_batch_id: str) -> None:
    """Phase 3: Update batch with vendor_batch_id and Submitted status"""

    query = """
        UPDATE engage360.outreach_batches
        SET
            batch_status = 'Submitted',
            vendor_batch_id = ?,
            submitted_ts = SYSDATETIMEOFFSET()
        WHERE batch_id = ?
    """

    params = [vendor_batch_id, str(batch_id)]
    self.db_service.execute_query(query, params=params, fetch_results=False)

    logger.info(f"✅ [DB-TRACKER] Updated batch {batch_id} with vendor ID: {vendor_batch_id}")
```

---

### Component 5: Timezone Utilities

**File**: `af_code/shared/timezone_utils.py`

**What It Does**: Converts between timezone formats (IANA ↔ Windows ↔ Abbreviations).

**Key Methods**:

```python
class TimezoneConverter:
    @staticmethod
    def to_pytz(timezone_input: str):
        """Convert any timezone format to pytz timezone object"""
        # Handles: "EST", "America/New_York", "Eastern Standard Time"

    @staticmethod
    def get_us_timezones_pytz() -> Dict[str, tzinfo]:
        """Get dictionary of US timezones as pytz objects"""
        return {
            'Eastern': pytz.timezone('America/New_York'),
            'Central': pytz.timezone('America/Chicago'),
            'Mountain': pytz.timezone('America/Denver'),
            'Pacific': pytz.timezone('America/Los_Angeles')
        }

    @staticmethod
    def get_us_timezones() -> List[str]:
        """Get list of US timezone IANA names"""
        return [
            'America/New_York',
            'America/Chicago',
            'America/Denver',
            'America/Los_Angeles'
        ]
```

**Example Usage**:

```python
# Convert abbreviation to pytz
campaign_tz = TimezoneConverter.to_pytz('EST')  # Returns pytz.timezone('America/New_York')

# Get all US timezones for member_tz mode
us_timezones = TimezoneConverter.get_us_timezones_pytz()
for tz_name, tz in us_timezones.items():
    now_in_tz = now_utc.astimezone(tz)
    print(f"{tz_name}: {now_in_tz.strftime('%A %H:%M')}")
```

---

## Step-by-Step Guides

### Guide 1: Adding a New Partner Campaign

**Prerequisites**:
- Active organization in `engage360.orgs`
- Bland AI pathway created and pathway_id obtained
- Bland AI voice configured and voice_id obtained
- Member data imported with care gap flags

**Steps**:

#### Step 1: Create Campaign Record

```sql
INSERT INTO engage360.campaigns_enhanced (
    campaign_id,
    org_id,
    name,
    campaign_description,
    campaign_type,
    status,
    primary_channel,
    contact_pref,
    call_days_of_week,
    operating_start_time,
    operating_end_time,
    operating_tz,
    scheduling_mode,
    frequency_value,
    frequency_unit,
    timezone_flag,
    max_care_gaps_per_member,
    audience_file_batch,
    start_ts,
    end_ts
)
VALUES (
    NEWID(),                                    -- campaign_id
    '<org_id>',                                 -- org_id (UUID)
    'Partner Wellness Outreach 2024',           -- name
    'Annual wellness visit reminder calls',     -- campaign_description
    'Partner',                                  -- campaign_type
    'Active',                                   -- status
    'voice',                                    -- primary_channel
    'member_preference',                        -- contact_pref
    'Monday,Tuesday,Wednesday,Thursday,Friday', -- call_days_of_week
    '09:00:00',                                 -- operating_start_time
    '17:00:00',                                 -- operating_end_time
    'EST',                                      -- operating_tz
    'Flexible',                                 -- scheduling_mode
    1,                                          -- frequency_value
    'week',                                     -- frequency_unit
    'member_tz',                                -- timezone_flag
    3,                                          -- max_care_gaps_per_member
    'partner_2024_q1',                          -- audience_file_batch
    SYSDATETIMEOFFSET(),                        -- start_ts
    NULL                                        -- end_ts (ongoing)
)
```

#### Step 2: Create Call Configuration

```sql
INSERT INTO engage360.campaign_call_configs_enhanced (
    config_id,
    campaign_id,
    call_type_id,
    config_status,
    bland_parameters_global
)
VALUES (
    NEWID(),                                    -- config_id
    '<campaign_id>',                            -- campaign_id (from Step 1)
    '<call_type_id>',                           -- call_type_id
    'active',                                   -- config_status
    '{
        "pathway_id": "partner-wellness-pathway-123",
        "pathway_version": "2024-01-15",
        "voice_id": "partner-voice-456",
        "webhook_url": "https://ioe-functions.azurewebsites.net/api/bland_ai_webhook",
        "wait_for_greeting": true,
        "record": true,
        "answered_by_enabled": true,
        "noise_cancellation": true,
        "interruption_threshold": 100,
        "block_interruptions": false,
        "max_duration": 300,
        "model": "enhanced",
        "temperature": 0.7,
        "language": "en",
        "from": "+15551234567",
        "timezone": "America/New_York"
    }'                                          -- bland_parameters_global (JSON)
)
```

#### Step 3: Enroll Members

```sql
-- Enroll all members from audience file batch with at least one care gap
INSERT INTO engage360.member_campaign_enrollments_enhanced (
    enrollment_id,
    member_id,
    campaign_id,
    current_status,
    enrollment_ts
)
SELECT
    NEWID(),                    -- enrollment_id
    m.member_id,
    '<campaign_id>',            -- campaign_id
    'Active',                   -- current_status
    SYSDATETIMEOFFSET()         -- enrollment_ts
FROM engage360.members m
WHERE m.file_batch = 'partner_2024_q1'  -- Match audience_file_batch
  AND (
      -- Has at least one care gap
      m.awv_import_flag = 1 OR
      m.ckd_import_flag = 1 OR
      m.crc_import_flag = 1 OR
      m.bcs_import_flag = 1
      -- ... (check other care gaps)
  )
```

#### Step 4: Verify Configuration

```sql
-- Check campaign is configured correctly
SELECT
    c.campaign_id,
    c.name,
    c.status,
    c.operating_start_time,
    c.operating_end_time,
    c.timezone_flag,
    cc.config_id,
    cc.bland_parameters_global,
    COUNT(DISTINCT mce.member_id) as enrolled_members
FROM engage360.campaigns_enhanced c
LEFT JOIN engage360.campaign_call_configs_enhanced cc
    ON c.campaign_id = cc.campaign_id
LEFT JOIN engage360.member_campaign_enrollments_enhanced mce
    ON c.campaign_id = mce.campaign_id
WHERE c.campaign_id = '<campaign_id>'
GROUP BY
    c.campaign_id,
    c.name,
    c.status,
    c.operating_start_time,
    c.operating_end_time,
    c.timezone_flag,
    cc.config_id,
    cc.bland_parameters_global
```

#### Step 5: Test Execution

Trigger the function manually via HTTP endpoint:

```bash
curl -X POST "https://ioe-functions.azurewebsites.net/api/partner_campaign_scheduler" \
  -H "Content-Type: application/json"
```

Check Azure Function logs for:
- ✅ Campaign qualified
- ✅ Members found eligible
- ✅ Batch submitted to Bland AI
- ✅ Database tracking completed

---

### Guide 2: Troubleshooting Failed Batch Submission

**Symptom**: Batch submission to Bland AI fails with error.

**Troubleshooting Steps**:

#### Step 1: Check Azure Function Logs

Look for error messages with `[BLAND-CLIENT]` prefix:

```
❌ [BLAND-CLIENT] Batch submission failed: Invalid JSON response (HTTP 400)
```

#### Step 2: Verify Bland AI Configuration

Check that all required parameters are configured:

```sql
SELECT
    c.name,
    cc.bland_parameters_global
FROM engage360.campaigns_enhanced c
INNER JOIN engage360.campaign_call_configs_enhanced cc
    ON c.campaign_id = cc.campaign_id
WHERE c.campaign_id = '<campaign_id>'
```

Verify JSON contains:
- ✅ `pathway_id`
- ✅ `voice_id`
- ✅ `webhook_url`

#### Step 3: Check Azure Key Vault Secrets

Verify secrets are configured in Azure Key Vault:
- ✅ `BlandAIkey`: Bland AI API key
- ✅ `Blandaitwilio`: Encrypted key for Twilio

#### Step 4: Inspect Complete Payload in Logs

Search logs for `COMPLETE JSON PAYLOAD` to see exact payload sent to Bland AI:

```
📄 [BLAND-CLIENT] COMPLETE JSON PAYLOAD:
{
  "global": {
    "pathway_id": "...",
    "voice": "...",
    ...
  },
  "call_objects": [...]
}
```

#### Step 5: Verify Bland AI API Endpoint

Check that endpoint is correct:

```python
# Should be:
https://api.bland.ai/v2/batches/create

# NOT:
https://api.bland.ai/v1/calls  # Old endpoint
```

#### Step 6: Test Payload Manually

Use curl to test Bland AI API directly:

```bash
curl -X POST "https://api.bland.ai/v2/batches/create" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -H "encrypted_key: YOUR_ENCRYPTED_KEY" \
  -d '{
    "global": {
      "pathway_id": "test-pathway",
      "voice": "test-voice",
      "webhook": "https://test-webhook.com"
    },
    "call_objects": [
      {
        "phone_number": "+15551234567",
        "request_data": {},
        "metadata": {}
      }
    ]
  }'
```

---

### Guide 3: Monitoring Campaign Performance

**Query 1: Campaign Execution History**

```sql
-- Get batch submission history for a campaign
SELECT
    ob.batch_id,
    ob.vendor_batch_id,
    ob.batch_status,
    ob.submitted_ts,
    COUNT(DISTINCT oa.attempt_id) as total_attempts,
    SUM(CASE WHEN oa.disposition = 'Completed' THEN 1 ELSE 0 END) as completed_calls,
    SUM(CASE WHEN oa.disposition = 'Pending' THEN 1 ELSE 0 END) as pending_calls,
    SUM(CASE WHEN oa.disposition = 'Failed' THEN 1 ELSE 0 END) as failed_calls,
    SUM(CASE WHEN oa.disposition = 'NoAnswer' THEN 1 ELSE 0 END) as no_answer_calls
FROM engage360.outreach_batches ob
LEFT JOIN engage360.outreach_attempts oa ON ob.batch_id = oa.batch_id
WHERE ob.campaign_id = '<campaign_id>'
  AND ob.submitted_ts >= DATEADD(day, -7, SYSDATETIMEOFFSET())  -- Last 7 days
GROUP BY
    ob.batch_id,
    ob.vendor_batch_id,
    ob.batch_status,
    ob.submitted_ts
ORDER BY ob.submitted_ts DESC
```

**Query 2: Member Call History**

```sql
-- Get call history for a specific member
SELECT
    m.first_name,
    m.last_name,
    m.phone,
    oa.attempt_ts,
    oa.disposition,
    ob.vendor_batch_id,
    oa.call_details
FROM engage360.members m
INNER JOIN engage360.outreach_attempts oa ON m.member_id = oa.member_id
INNER JOIN engage360.outreach_batches ob ON oa.batch_id = ob.batch_id
WHERE m.member_id = '<member_id>'
  AND ob.campaign_id = '<campaign_id>'
ORDER BY oa.attempt_ts DESC
```

**Query 3: Care Gap Completion Rates**

```sql
-- Analyze care gap completion rates
SELECT
    JSON_VALUE(oa.call_details, '$.care_gaps[0].name') as care_gap,
    COUNT(DISTINCT oa.attempt_id) as total_attempts,
    SUM(CASE WHEN oa.disposition = 'Completed' THEN 1 ELSE 0 END) as completed_calls,
    CAST(SUM(CASE WHEN oa.disposition = 'Completed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS DECIMAL(5,2)) as completion_rate
FROM engage360.outreach_attempts oa
INNER JOIN engage360.outreach_batches ob ON oa.batch_id = ob.batch_id
WHERE ob.campaign_id = '<campaign_id>'
  AND ob.submitted_ts >= DATEADD(day, -30, SYSDATETIMEOFFSET())
GROUP BY JSON_VALUE(oa.call_details, '$.care_gaps[0].name')
ORDER BY total_attempts DESC
```

---

## Troubleshooting Guide

### Issue 1: "No campaigns qualified"

**Symptoms**:
```
📊 [CAMPAIGN-QUALIFIER] QUALIFICATION COMPLETE: 0 campaigns qualified out of 5 total
```

**Possible Causes**:

1. **Campaign outside operating hours**
   - Check: `operating_start_time` and `operating_end_time`
   - Fix: Adjust times or wait for operating window

2. **Wrong day of week**
   - Check: `call_days_of_week` doesn't include current day
   - Fix: Add current day to allowed days

3. **Timezone misconfiguration**
   - Check: `timezone_flag` and `operating_tz` settings
   - Fix: Verify timezone matches intended schedule

4. **Missing Bland AI configuration**
   - Check: `bland_parameters_global` is NULL or invalid
   - Fix: Add call configuration record

**Debug Query**:
```sql
SELECT
    c.name,
    c.status,
    c.call_days_of_week,
    c.operating_start_time,
    c.operating_end_time,
    c.operating_tz,
    c.timezone_flag,
    cc.bland_parameters_global
FROM engage360.campaigns_enhanced c
LEFT JOIN engage360.campaign_call_configs_enhanced cc
    ON c.campaign_id = cc.campaign_id
WHERE c.campaign_type = 'Partner'
  AND LOWER(c.status) IN ('active', 'testing')
```

---

### Issue 2: "No eligible members found"

**Symptoms**:
```
📊 [MEMBER-ELIGIBILITY] Found 0 eligible members for campaign
```

**Possible Causes**:

1. **All members already contacted today**
   - Check: Members have 'Completed' or 'Pending' attempts today
   - Fix: Wait until tomorrow or adjust frequency settings

2. **Frequency protection blocking all members**
   - Check: All members have completed call within frequency window
   - Fix: Adjust `frequency_value` or `frequency_unit`

3. **No active enrollments**
   - Check: No members with `current_status = 'Active'`
   - Fix: Enroll members in campaign

4. **Audience file batch mismatch**
   - Check: Members' `file_batch` doesn't match campaign's `audience_file_batch`
   - Fix: Update campaign or import members with correct batch

**Debug Query**:
```sql
-- Check member enrollment status
SELECT
    COUNT(*) as total_enrolled,
    SUM(CASE WHEN mce.current_status = 'Active' THEN 1 ELSE 0 END) as active_enrolled,
    SUM(CASE WHEN m.file_batch = c.audience_file_batch THEN 1 ELSE 0 END) as matching_batch
FROM engage360.campaigns_enhanced c
LEFT JOIN engage360.member_campaign_enrollments_enhanced mce
    ON c.campaign_id = mce.campaign_id
LEFT JOIN engage360.members m
    ON mce.member_id = m.member_id
WHERE c.campaign_id = '<campaign_id>'
```

---

### Issue 3: "Batch submission failed - HTTP 400"

**Symptoms**:
```
❌ [BLAND-CLIENT] Batch submission failed: Invalid request (HTTP 400)
```

**Possible Causes**:

1. **Missing required parameter**
   - Check: `pathway_id`, `voice_id`, or `webhook` missing from payload
   - Fix: Add missing parameter to `bland_parameters_global` JSON

2. **Invalid phone number format**
   - Check: Phone not in E.164 format (+15551234567)
   - Fix: Verify member phone numbers

3. **Invalid pathway_id or voice_id**
   - Check: IDs don't exist in Bland AI
   - Fix: Verify IDs are correct and active

**Debug Steps**:
1. Check complete payload in logs (search for "COMPLETE JSON PAYLOAD")
2. Verify all required global parameters are present
3. Test with minimal payload (1 call) to isolate issue

---

### Issue 4: "Batch submission failed - HTTP 401"

**Symptoms**:
```
❌ [BLAND-CLIENT] Batch submission failed: Unauthorized (HTTP 401)
```

**Possible Causes**:

1. **Invalid API key**
   - Check: `BlandAIkey` in Azure Key Vault
   - Fix: Update with valid API key from Bland AI

2. **Expired API key**
   - Check: API key may have been rotated
   - Fix: Request new API key from Bland AI

**Debug Steps**:
```python
# Verify API key is loaded
logger.info(f"API Key (last 8 chars): {self.api_key[-8:]}")
```

---

### Issue 5: "SQL ORDER BY error"

**Symptoms**:
```
pymssql.exceptions.OperationalError: (145, b'ORDER BY items must appear in the select list if SELECT DISTINCT is specified')
```

**Root Cause**: Using `SELECT DISTINCT` with `ORDER BY` on columns not in SELECT list.

**Fix**: Already implemented using `ROW_NUMBER()` window function instead of `SELECT DISTINCT`.

**If Still Occurring**: Check that latest code is deployed to Azure Function.

---

### Issue 6: "Pending calls never complete"

**Symptoms**: Attempts stuck in 'Pending' disposition indefinitely.

**Possible Causes**:

1. **Webhook not receiving callbacks**
   - Check: Bland AI webhook endpoint is accessible
   - Fix: Verify webhook URL in `bland_parameters_global`

2. **Webhook errors preventing updates**
   - Check: Azure Function logs for webhook errors
   - Fix: Debug webhook function (`bland_ai_webhook`)

**Debug Query**:
```sql
-- Find old pending attempts (>24 hours)
SELECT
    oa.attempt_id,
    oa.attempt_ts,
    ob.vendor_batch_id,
    DATEDIFF(hour, oa.attempt_ts, SYSDATETIMEOFFSET()) as hours_pending
FROM engage360.outreach_attempts oa
INNER JOIN engage360.outreach_batches ob ON oa.batch_id = ob.batch_id
WHERE oa.disposition = 'Pending'
  AND oa.attempt_ts < DATEADD(hour, -24, SYSDATETIMEOFFSET())
ORDER BY oa.attempt_ts ASC
```

---

## Configuration Reference

### Azure Key Vault Secrets

| Secret Name | Purpose | Example Value |
|-------------|---------|---------------|
| `BlandAIkey` | Bland AI API authentication | `sk_abc123...` |
| `Blandaitwilio` | Twilio encryption key (DTC pattern) | `enc_xyz789...` |
| `BLAND_AI_BATCH_URL` | Batch API endpoint (optional) | `https://api.bland.ai/v2/batches/create` |

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | Max output token limit | `32000` |
| `DB_CONNECTION_STRING` | SQL Server connection | From Key Vault |

### Azure Function Configuration

**File**: `host.json`

```json
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true,
        "maxTelemetryItemsPerSecond": 20
      }
    }
  },
  "functionTimeout": "00:10:00"
}
```

**Timer Trigger Schedule**:
```python
schedule="5 */30 * * * *"  # Every 30 minutes at 5 minutes past (e.g., 9:05, 9:35, 10:05)
```

**Cron Format**:
```
{second} {minute} {hour} {day} {month} {day_of_week}
5        */30     *      *     *       *
```

---

## Related Documentation

### Existing Documentation Files

1. **CAMPAIGN_QUALIFICATION_LOGIC.md** (1300+ lines)
   - Detailed timezone logic
   - 40+ test cases
   - Database table schemas
   - TimezoneConverter API
   - Edge case handling

2. **README.md**
   - High-level overview
   - Quick start guide
   - Architecture diagram

### External References

- **Bland AI API Docs**: https://docs.bland.ai/api-reference/batches/create
- **Azure Functions Python**: https://docs.microsoft.com/azure/azure-functions/functions-reference-python
- **PyMSSQL Documentation**: https://pymssql.readthedocs.io/
- **pytz Timezone Database**: https://pytz.sourceforge.net/

---

## Appendix: Common SQL Patterns

### Pattern 1: UUID Serialization

**Problem**: UUIDs must be converted to strings for SQL parameters.

```python
# Correct
params = [str(uuid_value)]

# Incorrect
params = [uuid_value]  # Will cause pymssql error
```

### Pattern 2: Timezone-Aware Timestamps

**Always use** `SYSDATETIMEOFFSET()` for timezone-aware timestamps:

```sql
-- Correct
SELECT SYSDATETIMEOFFSET()  -- Returns: 2024-01-15 14:30:00.0000000 +00:00

-- Incorrect
SELECT GETDATE()  -- Returns: 2024-01-15 14:30:00.000 (no timezone)
```

### Pattern 3: JSON Extraction in SQL

```sql
-- Extract value from JSON column
JSON_VALUE(bland_parameters_global, '$.pathway_id')

-- Extract object from JSON
JSON_QUERY(bland_parameters_global, '$.analysis_schema')
```

### Pattern 4: Window Functions for Deduplication

```sql
-- Use ROW_NUMBER instead of SELECT DISTINCT when ordering
WITH RankedMembers AS (
    SELECT
        member_id,
        ROW_NUMBER() OVER (PARTITION BY member_id ORDER BY last_attempt_ts ASC) as rn
    FROM ...
)
SELECT * FROM RankedMembers WHERE rn = 1
```

---

**End of Documentation**

*Last Updated: 2024-01-15*
*Version: 1.0*
