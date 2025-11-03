# Campaign Qualification Logic Documentation

## Table of Contents
1. [Overview](#overview)
2. [Core Database Tables & Mapping](#core-database-tables--mapping)
3. [Timezone Logic Explained](#timezone-logic-explained)
4. [Qualification Algorithm](#qualification-algorithm)
5. [Test Cases - All Scenarios](#test-cases---all-scenarios)
6. [Edge Cases & Handling](#edge-cases--handling)

---

## Overview

The Partner Campaign Scheduler uses timezone-aware qualification logic to determine which campaigns should run at any given moment. It supports two timezone modes:
- **`operating_tz`**: Campaign uses a single timezone for all members
- **`member_tz`**: Each member is called in their individual timezone

---

## Core Database Tables & Mapping

### 1. `engage360.campaigns_enhanced`

**Purpose**: Stores campaign configuration including scheduling rules

| Column | Type | Purpose | Example Values | Notes |
|--------|------|---------|----------------|-------|
| `campaign_id` | UNIQUEIDENTIFIER | Primary key | `304DFAD6-AFDF-4EFE-89FE-8F929B072395` | Auto-generated |
| `org_id` | UNIQUEIDENTIFIER | Organization FK | `071F957A-B275-4BA2-999C-2A82824165EB` | Links to `engage360.orgs` |
| `name` | NVARCHAR(255) | Campaign display name | `HC_PA_Q4-2025_BCS-GSD v33` | User-defined |
| `campaign_type` | NVARCHAR(50) | Type of campaign | `Partner`, `Internal` | **Must be 'Partner' to qualify** |
| `status` | NVARCHAR(50) | Campaign status | `Active`, `Testing`, `Inactive`, `Draft` | **Must be 'Active' or 'Testing' (case-insensitive)** |
| `primary_channel` | NVARCHAR(50) | Communication channel | `Voice`, `Email`, `SMS` | **Must be 'voice' to qualify** |
| `start_ts` | DATETIMEOFFSET | Campaign start date/time | `2025-10-16 23:06:00.0000000 +00:00` | Campaign won't run before this |
| `end_ts` | DATETIMEOFFSET | Campaign end date/time | `2025-11-16 17:00:00.0000000 +00:00` | Campaign won't run after this |
| `call_days_of_week` | NVARCHAR(255) | Days campaign can run | `Monday,Tuesday,Wednesday,Thursday` | Comma-separated day names |
| `operating_start_time` | TIME | Daily start time | `19:06:00` (7:06 PM) | In campaign's operating_tz |
| `operating_end_time` | TIME | Daily end time | `23:28:00` (11:28 PM) | In campaign's operating_tz |
| `operating_tz` | NVARCHAR(100) | Campaign timezone | `EST`, `Eastern Standard Time`, `CST` | SQL Server timezone name |
| `timezone_flag` | NVARCHAR(50) | Timezone mode | `operating_tz`, `member_tz` | **Controls qualification logic** |
| `scheduling_mode` | NVARCHAR(50) | Scheduling type | `Flexible`, `Fixed` | Determines frequency rules |
| `frequency_value` | INT | How often to call | `2`, `1`, `7` | Used with frequency_unit |
| `frequency_unit` | NVARCHAR(50) | Frequency period | `day`, `week`, `month` | **Required for Flexible mode** |
| `max_care_gaps_per_member` | INT | Max gaps per member | `3`, `5`, `1` | Limits calls per member |
| `contact_pref` | NVARCHAR(50) | Contact preference | `phone`, `auto`, `member_preference` | `auto` → converted to `member_preference` |
| `audience_file_batch` | NVARCHAR(255) | Audience batch ID | `HamaspikChoice_Q125FluFrCallList...` | **Required to qualify** |
| `campaign_description` | NVARCHAR(MAX) | Description | `ad asd asd a` | Optional metadata |

**Qualification Filters in SQL Query:**
```sql
WHERE c.campaign_type = 'Partner'
  AND LOWER(c.status) IN ('active', 'testing')
  AND c.primary_channel = 'voice'
  AND (c.start_ts IS NULL OR c.start_ts <= SYSDATETIMEOFFSET())
  AND (c.end_ts IS NULL OR c.end_ts >= SYSDATETIMEOFFSET())
  AND c.audience_file_batch IS NOT NULL
```

---

### 2. `engage360.campaign_call_configs_enhanced`

**Purpose**: Stores call-specific configuration for campaigns

| Column | Type | Purpose | Example Values | Notes |
|--------|------|---------|----------------|-------|
| `config_id` | UNIQUEIDENTIFIER | Primary key | Auto-generated | Used in QualifiedCampaign model |
| `campaign_id` | UNIQUEIDENTIFIER | FK to campaigns_enhanced | Campaign ID | Links config to campaign |
| `call_type_id` | UNIQUEIDENTIFIER | Call type identifier | Auto-generated | Used in QualifiedCampaign model |
| `config_status` | NVARCHAR(50) | Config status | `active`, `inactive` | **Must be 'active'** |

**Join Condition:**
```sql
LEFT JOIN engage360.campaign_call_configs_enhanced cc
    ON c.campaign_id = cc.campaign_id
    AND cc.config_status = 'active'
```

---

### 3. `engage360.orgs`

**Purpose**: Organization metadata

| Column | Type | Purpose | Example Values | Notes |
|--------|------|---------|----------------|-------|
| `org_id` | UNIQUEIDENTIFIER | Primary key | Organization ID | Links to campaigns |
| `org_type` | NVARCHAR(100) | Organization type | `Health Plan`, `Provider` | Used in QualifiedCampaign model |

**Join Condition:**
```sql
LEFT JOIN engage360.orgs o ON c.org_id = o.org_id
```

---

### 4. `engage360.members`

**Purpose**: Member information for eligibility checks

| Column | Type | Purpose | Example Values | Notes |
|--------|------|---------|----------------|-------|
| `member_id` | UNIQUEIDENTIFIER | Primary key | Auto-generated | Unique member identifier |
| `enrollment_id` | UNIQUEIDENTIFIER | Active enrollment | Auto-generated | FK to enrollments table |
| `first_name` | NVARCHAR(100) | Member first name | `John` | Used in call payload |
| `last_name` | NVARCHAR(100) | Member last name | `Smith` | Used in call payload |
| `primary_phone` | NVARCHAR(20) | Phone number | `+1234567890` | **Required for calls** |
| `timezone` | NVARCHAR(100) | Member timezone | `Eastern Standard Time`, `Pacific Standard Time` | **Used when timezone_flag='member_tz'** |
| `language_pref` | NVARCHAR(50) | Preferred language | `English`, `Spanish` | Used in call routing |
| `dob` | DATE | Date of birth | `1950-01-15` | Used in call payload |
| `address_street` | NVARCHAR(255) | Street address | `123 Main St` | Used in call payload |
| `address_city` | NVARCHAR(100) | City | `New York` | Used in call payload |
| `address_state` | NVARCHAR(50) | State | `NY` | Used in call payload |
| `address_zip` | NVARCHAR(20) | ZIP code | `10001` | Used in call payload |
| `salesforce_account_number` | NVARCHAR(100) | Salesforce ID | `SF-12345` | Used in metadata |

---

### 5. `engage360.outreach_batches`

**Purpose**: Tracks batch submissions to Bland AI

| Column | Type | Purpose | Example Values | Notes |
|--------|------|---------|----------------|-------|
| `batch_id` | UNIQUEIDENTIFIER | Primary key | Auto-generated | Internal batch tracking |
| `campaign_id` | UNIQUEIDENTIFIER | FK to campaigns | Campaign ID | Links batch to campaign |
| `vendor_batch_id` | NVARCHAR(255) | Bland AI batch ID | `batch_abc123` | Returned from Bland AI API |
| `batch_status` | NVARCHAR(50) | Current status | `Submitted`, `Pending`, `Completed`, `Failed` | Updated by reconciler |
| `total_calls_intended` | INT | Members in batch | `1000`, `250` | Set at submission |
| `total_calls_completed` | INT | Completed calls | `950` | Updated by reconciler |
| `total_calls_failed` | INT | Failed calls | `50` | Updated by reconciler |
| `submitted_ts` | DATETIMEOFFSET | Submission time | Current timestamp | When batch was sent |
| `last_status_check_ts` | DATETIMEOFFSET | Last reconciliation | Last check time | Updated by reconciler |
| `status_reason` | NVARCHAR(MAX) | Status details | Error messages | For debugging |

---

### 6. `engage360.outreach_attempts`

**Purpose**: Individual call attempts within batches

| Column | Type | Purpose | Example Values | Notes |
|--------|------|---------|----------------|-------|
| `attempt_id` | UNIQUEIDENTIFIER | Primary key | Auto-generated | Unique attempt identifier |
| `enrollment_id` | UNIQUEIDENTIFIER | FK to member enrollment | Enrollment ID | Links to member |
| `batch_id` | UNIQUEIDENTIFIER | FK to outreach_batches | Batch ID | Links to batch |
| `channel` | NVARCHAR(50) | Communication channel | `Voice`, `Email`, `SMS` | Must match campaign |
| `vendor_session_id` | NVARCHAR(255) | Bland AI call ID | `call_xyz789` | From Bland AI webhook |
| `attempt_ts` | DATETIMEOFFSET | Attempt timestamp | Current timestamp | When created |
| `disposition` | NVARCHAR(100) | Call result | `Pending`, `Completed`, `Failed`, `No Answer` | Updated by webhook |
| `retry_seq` | INT | Retry attempt number | `0`, `1`, `2` | Increments on retries |
| `updated_ts` | DATETIMEOFFSET | Last update time | Update timestamp | When disposition changed |

---

## Timezone Logic Explained

### Timezone Formats Used in IOE System

The IOE system supports **3 different timezone formats** and uses the `TimezoneConverter` utility to convert between them:

#### 1. IANA Format (America/New_York, America/Chicago)
- **Used in**: `members.timezone` database field
- **Used by**: pytz library in Python
- **Example**: `America/New_York`, `America/Chicago`, `America/Denver`, `America/Los_Angeles`
- **Purpose**: Standard timezone names recognized by most modern systems

#### 2. Abbreviation Format (EST, CST, MST, PST)
- **Used in**: `campaigns_enhanced.operating_tz` database field (legacy)
- **Example**: `EST`, `CST`, `MST`, `PST`, `EDT`, `CDT`, `MDT`, `PDT`
- **Purpose**: Short form for user-friendly display
- **Note**: Automatically converted to IANA or Windows format as needed

#### 3. Windows Format (Eastern Standard Time)
- **Used in**: SQL Server `AT TIME ZONE` clause
- **Example**: `Eastern Standard Time`, `Central Standard Time`, `Mountain Standard Time`, `Pacific Standard Time`
- **Purpose**: Required by SQL Server for timezone conversions

### TimezoneConverter Utility

Located at: `af_code/shared/timezone_utils.py`

**Key Methods:**

```python
from af_code.shared.timezone_utils import TimezoneConverter

# Convert any format to IANA (for pytz)
iana_tz = TimezoneConverter.to_iana('EST')  # Returns 'America/New_York'

# Convert any format to Windows (for SQL Server)
windows_tz = TimezoneConverter.to_windows('EST')  # Returns 'Eastern Standard Time'

# Convert any format to pytz object
pytz_tz = TimezoneConverter.to_pytz('EST')  # Returns pytz.timezone('America/New_York')
```

**Conversion Examples:**

| Input | to_iana() | to_windows() | to_pytz() |
|-------|-----------|--------------|-----------|
| `EST` | `America/New_York` | `Eastern Standard Time` | `<America/New_York>` |
| `America/Chicago` | `America/Chicago` | `Central Standard Time` | `<America/Chicago>` |
| `Central Standard Time` | `America/Chicago` | `Central Standard Time` | `<America/Chicago>` |
| `PST` | `America/Los_Angeles` | `Pacific Standard Time` | `<America/Los_Angeles>` |
| `America/Denver` | `America/Denver` | `Mountain Standard Time` | `<America/Denver>` |

### Supported Timezone Mappings

```python
# Abbreviations → IANA
'EST' → 'America/New_York'
'CST' → 'America/Chicago'
'MST' → 'America/Denver'
'PST' → 'America/Los_Angeles'

# IANA → Windows (for SQL Server)
'America/New_York' → 'Eastern Standard Time'
'America/Chicago' → 'Central Standard Time'
'America/Denver' → 'Mountain Standard Time'
'America/Los_Angeles' → 'Pacific Standard Time'
```

### US Timezones Used

```python
us_timezones = {
    'Eastern': pytz.timezone('America/New_York'),      # UTC-5 (EST) / UTC-4 (EDT)
    'Central': pytz.timezone('America/Chicago'),       # UTC-6 (CST) / UTC-5 (CDT)
    'Mountain': pytz.timezone('America/Denver'),       # UTC-7 (MST) / UTC-6 (MDT)
    'Pacific': pytz.timezone('America/Los_Angeles')    # UTC-8 (PST) / UTC-7 (PDT)
}
```

**Note:** pytz automatically handles Daylight Saving Time (DST) transitions.

### Timezone Conversion in Practice

#### Campaign Qualifier (Python - uses IANA):
```python
# Campaign has operating_tz = 'EST'
campaign_tz = TimezoneConverter.to_pytz('EST')  # Returns America/New_York pytz object
now_in_campaign_tz = now_utc.astimezone(campaign_tz)
```

#### Member Eligibility (SQL - uses Windows):
```python
# Campaign has operating_tz = 'EST' or 'America/New_York'
operating_tz_windows = TimezoneConverter.to_windows(campaign.operating_tz)
# Returns 'Eastern Standard Time' for SQL AT TIME ZONE clause
```

#### Member Timezone (SQL - IANA to Windows Conversion):
Since `members.timezone` stores IANA format (e.g., `America/New_York`) but SQL Server's `AT TIME ZONE` requires Windows format, the member eligibility query includes inline CASE statements to convert:

```sql
-- Member has timezone = 'America/New_York' in database
-- SQL query converts to Windows format for AT TIME ZONE clause
SYSDATETIMEOFFSET() AT TIME ZONE
    CASE m.timezone
        WHEN 'America/New_York' THEN 'Eastern Standard Time'
        WHEN 'America/Chicago' THEN 'Central Standard Time'
        WHEN 'America/Denver' THEN 'Mountain Standard Time'
        WHEN 'America/Los_Angeles' THEN 'Pacific Standard Time'
        -- ... additional mappings
        ELSE 'Eastern Standard Time'  -- Fallback default
    END
```

**Location**: `af_code/partner_campaign_scheduler/services/member_eligibility.py` (lines 163-186, 195-218)

---

## Qualification Algorithm

### High-Level Flow

```
1. Get current UTC time
2. Query active Partner campaigns from database
3. For each campaign:
   a. Check timezone_flag mode
   b. If operating_tz: Check campaign's timezone
   c. If member_tz: Check all US timezones
   d. Validate day of week in appropriate timezone(s)
   e. Validate time window in appropriate timezone(s)
   f. Validate flexible scheduling configuration
4. Return list of qualified campaigns
```

### Detailed Logic by Timezone Mode

#### Mode 1: `timezone_flag = 'operating_tz'`

**Use Case**: Campaign runs in a single timezone (e.g., all Pennsylvania members called in EST)

**Logic:**
```python
1. Get campaign's operating_tz (e.g., "EST")
2. Map to pytz timezone (e.g., "US/Eastern")
3. Convert current UTC to campaign timezone
4. Check if current day in campaign timezone matches call_days_of_week
5. Check if current time in campaign timezone is within operating hours
6. Both must be TRUE for campaign to qualify
```

**Example:**
```
Campaign Configuration:
- operating_tz: EST
- call_days_of_week: Monday,Tuesday,Wednesday,Thursday
- operating_start_time: 19:06:00 (7:06 PM)
- operating_end_time: 23:28:00 (11:28 PM)
- timezone_flag: operating_tz

Current UTC: Friday 00:37:00
Convert to EST: Thursday 20:37:00

Checks:
- Day: Thursday ∈ [Monday, Tuesday, Wednesday, Thursday] ✅
- Time: 20:37 ∈ [19:06 - 23:28] ✅
Result: QUALIFIED ✅
```

---

#### Mode 2: `timezone_flag = 'member_tz'`

**Use Case**: Each member is called in their own timezone from `members.timezone`

**Logic:**
```python
1. Check ALL 4 US timezones (Eastern, Central, Mountain, Pacific)
2. For each timezone:
   a. Convert current UTC to that timezone
   b. Check if day matches call_days_of_week
   c. Check if time is within operating hours
3. Campaign qualifies if ANY timezone meets BOTH day AND time criteria
```

**Example:**
```
Campaign Configuration:
- call_days_of_week: Monday,Tuesday,Wednesday,Thursday
- operating_start_time: 20:00:00 (8:00 PM)
- operating_end_time: 22:00:00 (10:00 PM)
- timezone_flag: member_tz

Current UTC: Friday 03:30:00

Check all timezones:
- Eastern: Friday 23:30 → Day=Friday ❌, Time=23:30 (outside 20-22) ❌ → FAIL
- Central: Thursday 22:30 → Day=Thursday ✅, Time=22:30 (outside 20-22) ❌ → FAIL
- Mountain: Thursday 21:30 → Day=Thursday ✅, Time=21:30 (inside 20-22) ✅ → PASS ✅
- Pacific: Thursday 20:30 → Day=Thursday ✅, Time=20:30 (inside 20-22) ✅ → PASS ✅

Result: QUALIFIED ✅ (Mountain and Pacific members eligible)
```

---

### Flexible Scheduling Validation

**Required for `scheduling_mode = 'Flexible'`:**

```python
- frequency_value must be > 0
- frequency_unit must be in ['day', 'week', 'month']
- Both must be present
```

**Example:**
```
Valid: frequency_value=2, frequency_unit='week'
Invalid: frequency_value=0, frequency_unit='week'
Invalid: frequency_value=2, frequency_unit=NULL
Invalid: frequency_value=2, frequency_unit='year'
```

---

## Test Cases - All Scenarios

### Test Suite 1: `operating_tz` Mode

#### Test Case 1.1: Standard Weekday During Hours
```yaml
Campaign:
  operating_tz: EST
  call_days_of_week: Monday,Tuesday,Wednesday,Thursday,Friday
  operating_start_time: 09:00:00
  operating_end_time: 17:00:00
  timezone_flag: operating_tz

UTC Time: Monday 14:00:00
Expected: QUALIFIED ✅

Reason:
  - EST: Monday 09:00 (within Mon-Fri, within 9am-5pm)
```

#### Test Case 1.2: Weekday Outside Hours (Too Early)
```yaml
Campaign:
  operating_tz: EST
  call_days_of_week: Monday,Tuesday,Wednesday,Thursday,Friday
  operating_start_time: 09:00:00
  operating_end_time: 17:00:00
  timezone_flag: operating_tz

UTC Time: Monday 13:00:00
Expected: NOT QUALIFIED ❌

Reason:
  - EST: Monday 08:00 (within Mon-Fri, but before 9am)
```

#### Test Case 1.3: Weekday Outside Hours (Too Late)
```yaml
Campaign:
  operating_tz: EST
  call_days_of_week: Monday,Tuesday,Wednesday,Thursday,Friday
  operating_start_time: 09:00:00
  operating_end_time: 17:00:00
  timezone_flag: operating_tz

UTC Time: Monday 22:30:00
Expected: NOT QUALIFIED ❌

Reason:
  - EST: Monday 17:30 (within Mon-Fri, but after 5pm)
```

#### Test Case 1.4: Wrong Day (Saturday)
```yaml
Campaign:
  operating_tz: EST
  call_days_of_week: Monday,Tuesday,Wednesday,Thursday,Friday
  operating_start_time: 09:00:00
  operating_end_time: 17:00:00
  timezone_flag: operating_tz

UTC Time: Saturday 14:00:00
Expected: NOT QUALIFIED ❌

Reason:
  - EST: Saturday 09:00 (Saturday not in Mon-Fri, even though time is correct)
```

#### Test Case 1.5: Midnight Crossover (Your Actual Bug)
```yaml
Campaign:
  operating_tz: EST
  call_days_of_week: Monday,Tuesday,Wednesday,Thursday
  operating_start_time: 19:06:00
  operating_end_time: 23:28:00
  timezone_flag: operating_tz

UTC Time: Friday 00:37:00
Expected: QUALIFIED ✅

Reason:
  - UTC: Friday 00:37
  - EST: Thursday 20:37 (Thursday is in Mon-Thu, time is in 19:06-23:28)
  - BUG WAS: Checked Friday (UTC day) instead of Thursday (EST day)
```

#### Test Case 1.6: Evening Hours Ending After Midnight
```yaml
Campaign:
  operating_tz: PST
  call_days_of_week: Friday,Saturday,Sunday
  operating_start_time: 18:00:00
  operating_end_time: 23:59:00
  timezone_flag: operating_tz

UTC Time: Saturday 03:00:00
Expected: QUALIFIED ✅

Reason:
  - PST: Friday 19:00 (Friday is in Fri-Sun, time is in 18:00-23:59)
```

#### Test Case 1.7: CST Timezone
```yaml
Campaign:
  operating_tz: Central Standard Time
  call_days_of_week: Tuesday,Wednesday,Thursday
  operating_start_time: 10:00:00
  operating_end_time: 14:00:00
  timezone_flag: operating_tz

UTC Time: Wednesday 16:30:00
Expected: QUALIFIED ✅

Reason:
  - CST: Wednesday 10:30 (Wednesday is in Tue-Thu, time is in 10:00-14:00)
```

---

### Test Suite 2: `member_tz` Mode

#### Test Case 2.1: All Timezones Qualified
```yaml
Campaign:
  call_days_of_week: Monday,Tuesday,Wednesday,Thursday,Friday
  operating_start_time: 14:00:00
  operating_end_time: 18:00:00
  timezone_flag: member_tz

UTC Time: Tuesday 19:00:00
Expected: QUALIFIED ✅

Reason:
  - Eastern: Tuesday 14:00 ✅ (day OK, time OK)
  - Central: Tuesday 13:00 ❌ (day OK, time before 14:00)
  - Mountain: Tuesday 12:00 ❌ (day OK, time before 14:00)
  - Pacific: Tuesday 11:00 ❌ (day OK, time before 14:00)
  - At least one timezone qualifies
```

#### Test Case 2.2: Only Western Timezones Qualified
```yaml
Campaign:
  call_days_of_week: Monday,Tuesday,Wednesday,Thursday,Friday
  operating_start_time: 20:00:00
  operating_end_time: 22:00:00
  timezone_flag: member_tz

UTC Time: Saturday 03:30:00
Expected: QUALIFIED ✅

Reason:
  - Eastern: Saturday 23:30 ❌ (day wrong, time wrong)
  - Central: Friday 22:30 ✅❌ (day OK, time after 22:00)
  - Mountain: Friday 21:30 ✅ (day OK, time OK)
  - Pacific: Friday 20:30 ✅ (day OK, time OK)
  - Mountain and Pacific qualify
```

#### Test Case 2.3: No Timezones Qualified (Day Mismatch)
```yaml
Campaign:
  call_days_of_week: Monday,Tuesday,Wednesday
  operating_start_time: 09:00:00
  operating_end_time: 17:00:00
  timezone_flag: member_tz

UTC Time: Thursday 14:00:00
Expected: NOT QUALIFIED ❌

Reason:
  - Eastern: Thursday 09:00 ❌ (Thursday not in Mon-Wed)
  - Central: Thursday 08:00 ❌ (Thursday not in Mon-Wed)
  - Mountain: Thursday 07:00 ❌ (Thursday not in Mon-Wed)
  - Pacific: Thursday 06:00 ❌ (Thursday not in Mon-Wed)
  - No timezones qualify
```

#### Test Case 2.4: No Timezones Qualified (Time Mismatch)
```yaml
Campaign:
  call_days_of_week: Monday,Tuesday,Wednesday,Thursday,Friday
  operating_start_time: 09:00:00
  operating_end_time: 17:00:00
  timezone_flag: member_tz

UTC Time: Tuesday 02:00:00
Expected: NOT QUALIFIED ❌

Reason:
  - Eastern: Monday 21:00 ✅❌ (day OK, time after 17:00)
  - Central: Monday 20:00 ✅❌ (day OK, time after 17:00)
  - Mountain: Monday 19:00 ✅❌ (day OK, time after 17:00)
  - Pacific: Monday 18:00 ✅❌ (day OK, time after 17:00)
  - No timezones qualify (all outside time window)
```

#### Test Case 2.5: Single Timezone Qualified (Central Only)
```yaml
Campaign:
  call_days_of_week: Wednesday
  operating_start_time: 11:00:00
  operating_end_time: 12:00:00
  timezone_flag: member_tz

UTC Time: Wednesday 17:30:00
Expected: QUALIFIED ✅

Reason:
  - Eastern: Wednesday 12:30 ✅❌ (day OK, time after 12:00)
  - Central: Wednesday 11:30 ✅ (day OK, time OK)
  - Mountain: Wednesday 10:30 ✅❌ (day OK, time before 11:00)
  - Pacific: Wednesday 09:30 ✅❌ (day OK, time before 11:00)
  - Central qualifies
```

#### Test Case 2.6: Evening Hours with Day Transition
```yaml
Campaign:
  call_days_of_week: Thursday
  operating_start_time: 22:00:00
  operating_end_time: 23:59:00
  timezone_flag: member_tz

UTC Time: Friday 04:00:00
Expected: QUALIFIED ✅

Reason:
  - Eastern: Friday 00:00 ❌ (day wrong)
  - Central: Thursday 23:00 ✅ (day OK, time OK)
  - Mountain: Thursday 22:00 ✅ (day OK, time OK)
  - Pacific: Thursday 21:00 ✅❌ (day OK, time before 22:00)
  - Central and Mountain qualify
```

---

### Test Suite 3: Flexible Scheduling Validation

#### Test Case 3.1: Valid Flexible Daily
```yaml
Campaign:
  scheduling_mode: Flexible
  frequency_value: 1
  frequency_unit: day

Expected: PASS ✅
```

#### Test Case 3.2: Valid Flexible Weekly
```yaml
Campaign:
  scheduling_mode: Flexible
  frequency_value: 2
  frequency_unit: week

Expected: PASS ✅
```

#### Test Case 3.3: Valid Flexible Monthly
```yaml
Campaign:
  scheduling_mode: Flexible
  frequency_value: 3
  frequency_unit: month

Expected: PASS ✅
```

#### Test Case 3.4: Invalid - Missing frequency_value
```yaml
Campaign:
  scheduling_mode: Flexible
  frequency_value: NULL
  frequency_unit: week

Expected: FAIL ❌
Reason: frequency_value is required for Flexible mode
```

#### Test Case 3.5: Invalid - Missing frequency_unit
```yaml
Campaign:
  scheduling_mode: Flexible
  frequency_value: 2
  frequency_unit: NULL

Expected: FAIL ❌
Reason: frequency_unit is required for Flexible mode
```

#### Test Case 3.6: Invalid - Zero frequency_value
```yaml
Campaign:
  scheduling_mode: Flexible
  frequency_value: 0
  frequency_unit: day

Expected: FAIL ❌
Reason: frequency_value must be > 0
```

#### Test Case 3.7: Invalid - Negative frequency_value
```yaml
Campaign:
  scheduling_mode: Flexible
  frequency_value: -1
  frequency_unit: week

Expected: FAIL ❌
Reason: frequency_value must be > 0
```

#### Test Case 3.8: Invalid - Wrong frequency_unit
```yaml
Campaign:
  scheduling_mode: Flexible
  frequency_value: 2
  frequency_unit: year

Expected: FAIL ❌
Reason: frequency_unit must be 'day', 'week', or 'month'
```

#### Test Case 3.9: Non-Flexible Mode (No Validation)
```yaml
Campaign:
  scheduling_mode: Fixed
  frequency_value: NULL
  frequency_unit: NULL

Expected: PASS ✅
Reason: Flexible validation only applies to Flexible mode
```

---

### Test Suite 4: Edge Cases

#### Test Case 4.1: Campaign Start Boundary
```yaml
Campaign:
  start_ts: 2025-10-16 19:00:00 +00:00
  operating_tz: EST
  call_days_of_week: Thursday
  operating_start_time: 15:00:00
  operating_end_time: 20:00:00
  timezone_flag: operating_tz

UTC Time: 2025-10-16 19:00:00
Expected: QUALIFIED ✅

Reason:
  - Campaign starts exactly now
  - EST: Thursday 15:00 (day OK, time OK)
```

#### Test Case 4.2: Campaign End Boundary
```yaml
Campaign:
  end_ts: 2025-11-16 17:00:00 +00:00
  operating_tz: EST
  call_days_of_week: Saturday
  operating_start_time: 10:00:00
  operating_end_time: 15:00:00
  timezone_flag: operating_tz

UTC Time: 2025-11-16 17:00:00
Expected: QUALIFIED ✅

Reason:
  - Campaign ends exactly now (inclusive)
  - EST: Saturday 12:00 (day OK, time OK)
```

#### Test Case 4.3: Before Campaign Start
```yaml
Campaign:
  start_ts: 2025-10-20 00:00:00 +00:00

UTC Time: 2025-10-19 23:59:59
Expected: NOT QUALIFIED ❌

Reason: Current time is before campaign start_ts
```

#### Test Case 4.4: After Campaign End
```yaml
Campaign:
  end_ts: 2025-11-16 17:00:00 +00:00

UTC Time: 2025-11-16 17:00:01
Expected: NOT QUALIFIED ❌

Reason: Current time is after campaign end_ts
```

#### Test Case 4.5: Missing audience_file_batch
```yaml
Campaign:
  audience_file_batch: NULL
  (All other criteria met)

Expected: NOT QUALIFIED ❌

Reason: audience_file_batch is required (filtered in SQL query)
```

#### Test Case 4.6: Inactive Campaign
```yaml
Campaign:
  status: Inactive
  (All other criteria met)

Expected: NOT QUALIFIED ❌

Reason: Campaign status must be 'Active' or 'Testing' (filtered in SQL query)
```

#### Test Case 4.7: Wrong Campaign Type
```yaml
Campaign:
  campaign_type: Internal
  (All other criteria met)

Expected: NOT QUALIFIED ❌

Reason: Campaign type must be 'Partner' (filtered in SQL query)
```

#### Test Case 4.8: Wrong Channel
```yaml
Campaign:
  primary_channel: Email
  (All other criteria met)

Expected: NOT QUALIFIED ❌

Reason: Channel must be 'voice' (filtered in SQL query)
```

#### Test Case 4.9: Auto Contact Preference Conversion
```yaml
Campaign:
  contact_pref: auto
  (All other criteria met)

Expected: QUALIFIED ✅ (with contact_pref converted to 'member_preference')

Reason: 'auto' is automatically converted to 'member_preference'
```

#### Test Case 4.10: Exactly at Operating Start Time
```yaml
Campaign:
  operating_tz: EST
  operating_start_time: 09:00:00
  operating_end_time: 17:00:00
  call_days_of_week: Monday
  timezone_flag: operating_tz

UTC Time: Monday 14:00:00
Expected: QUALIFIED ✅

Reason:
  - EST: Monday 09:00:00 (exactly at start time - inclusive)
```

#### Test Case 4.11: Exactly at Operating End Time
```yaml
Campaign:
  operating_tz: EST
  operating_start_time: 09:00:00
  operating_end_time: 17:00:00
  call_days_of_week: Monday
  timezone_flag: operating_tz

UTC Time: Monday 22:00:00
Expected: QUALIFIED ✅

Reason:
  - EST: Monday 17:00:00 (exactly at end time - inclusive)
```

#### Test Case 4.12: One Second After Operating End Time
```yaml
Campaign:
  operating_tz: EST
  operating_start_time: 09:00:00
  operating_end_time: 17:00:00
  call_days_of_week: Monday
  timezone_flag: operating_tz

UTC Time: Monday 22:00:01
Expected: NOT QUALIFIED ❌

Reason:
  - EST: Monday 17:00:01 (one second after end time - exclusive)
```

---

## Edge Cases & Handling

### 1. Daylight Saving Time (DST) Transitions

**Scenario**: DST transition occurs during campaign qualification

**Handling**:
- pytz automatically handles DST transitions
- `US/Eastern` switches between UTC-5 (EST) and UTC-4 (EDT)
- No manual adjustment needed

**Example**:
```python
# Spring Forward (2am → 3am)
UTC: 2025-03-09 07:00:00
EST: 2025-03-09 03:00:00 (EDT - automatically adjusted)

# Fall Back (2am → 1am)
UTC: 2025-11-02 06:00:00
EST: 2025-11-02 01:00:00 (EST - automatically adjusted)
```

---

### 2. Null/Missing Operating Timezone

**Scenario**: `operating_tz` is NULL or empty

**Handling**: Default to `'EST'` / `'US/Eastern'`

```python
operating_tz_name = campaign_data.get('operating_tz', 'EST')
pytz_tz_name = timezone_map.get(operating_tz_name, 'US/Eastern')
```

---

### 3. Unknown Timezone Name

**Scenario**: `operating_tz` contains unrecognized value (e.g., `'XYZ'`)

**Handling**: Default to `'US/Eastern'` via timezone_map fallback

```python
pytz_tz_name = timezone_map.get(operating_tz_name, 'US/Eastern')
# If 'XYZ' not in map, defaults to 'US/Eastern'
```

---

### 4. Empty call_days_of_week

**Scenario**: `call_days_of_week` is NULL or empty string

**Handling**: Campaign does NOT qualify

```python
if not call_days_str:
    logger.warning(f"⚠️ [CAMPAIGN-QUALIFIER] No call days defined for campaign: {campaign_name}")
    return False
```

---

### 5. Invalid call_days_of_week Format

**Scenario**: `call_days_of_week` = `'Mon,Tue,Wed'` (abbreviated instead of full names)

**Handling**: Campaign does NOT qualify (day name mismatch)

**Fix**: Use full day names: `'Monday,Tuesday,Wednesday'`

---

### 6. Timezone Flag Case Sensitivity

**Scenario**: `timezone_flag` = `'Operating_TZ'` or `'MEMBER_TZ'`

**Current Handling**: Case-sensitive comparison (will fail)

**Recommendation**: Add case-insensitive check:
```python
timezone_flag = campaign_data.get('timezone_flag', 'operating_tz').lower()
if timezone_flag == 'member_tz':
    # ...
```

---

### 7. Multiple Campaign Versions

**Scenario**: Same campaign name with different versions (e.g., `v33`, `v34`)

**Handling**: Each version is treated as a separate campaign

**Example from logs**:
```
Campaign: HC_PA_Q4-2025_BCS-GSD v33 (campaign_id: 304DFAD6...)
Campaign: HC_PA_Q4-2025_BCS-GSD v33 (campaign_id: 8A7B5C3D...) - duplicate name
```

**Recommendation**: Use unique campaign_id for tracking, not name

---

### 8. Member Timezone NULL in member_tz Mode

**Scenario**: `timezone_flag='member_tz'` but member has `timezone=NULL`

**Handling**: Member eligibility service should handle this

**Expected Behavior**:
- Campaign qualifies (if any timezone matches)
- Member eligibility filters out members with NULL timezone
- Or defaults member to a timezone (e.g., Eastern)

---

### 9. Operating Hours Crossing Midnight

**Scenario**: `operating_start_time='22:00:00'`, `operating_end_time='02:00:00'`

**Current Handling**: Does NOT support midnight crossover

**Limitation**: Time comparison `start_time <= current_time <= end_time` fails when end < start

**Workaround**: Split into two campaigns:
- Campaign 1: 22:00:00 - 23:59:59
- Campaign 2: 00:00:00 - 02:00:00

**Future Enhancement**: Add midnight crossover logic:
```python
if end_time < start_time:
    # Crosses midnight
    time_check = current_time >= start_time or current_time <= end_time
else:
    time_check = start_time <= current_time <= end_time
```

---

### 10. Unicode in Campaign Names

**Scenario**: Campaign name contains special characters: `'Campaña España v1'`

**Handling**: Fully supported (NVARCHAR columns support Unicode)

---

## Summary Table: Qualification Criteria

| Criterion | Source | Check Type | Failure Result |
|-----------|--------|------------|----------------|
| `campaign_type = 'Partner'` | SQL WHERE | Pre-filter | Not returned from query |
| `LOWER(status) IN ('active', 'testing')` | SQL WHERE | Pre-filter | Not returned from query |
| `primary_channel = 'voice'` | SQL WHERE | Pre-filter | Not returned from query |
| `start_ts` in past | SQL WHERE | Pre-filter | Not returned from query |
| `end_ts` in future | SQL WHERE | Pre-filter | Not returned from query |
| `audience_file_batch` not NULL | SQL WHERE | Pre-filter | Not returned from query |
| Day of week matches | Python | Runtime check | Campaign NOT qualified |
| Time window matches | Python | Runtime check | Campaign NOT qualified |
| Flexible scheduling valid | Python | Runtime check | Campaign NOT qualified |

---

## Logging Output Reference

### Success - operating_tz Mode
```
🕐 [CAMPAIGN-QUALIFIER] Checking in EST timezone: Thursday 20:37:05
📅 [CAMPAIGN-QUALIFIER] Day check PASSED: HC_PA_Q4-2025_BCS-GSD v33 (Thursday)
✅ [CAMPAIGN-QUALIFIER] Operating timezone check PASSED: HC_PA_Q4-2025_BCS-GSD v33
   EST: Thursday 20:37, Window: 19:06:00-23:28:00
✅ [CAMPAIGN-QUALIFIER] Campaign QUALIFIED: HC_PA_Q4-2025_BCS-GSD v33
```

### Success - member_tz Mode
```
✅ [CAMPAIGN-QUALIFIER] Member timezone check PASSED: Campaign XYZ
   Qualified timezones: Central (Thursday 21:30), Mountain (Thursday 20:30), Pacific (Thursday 19:30)
✅ [CAMPAIGN-QUALIFIER] Campaign QUALIFIED: Campaign XYZ
```

### Failure - Day Mismatch
```
🕐 [CAMPAIGN-QUALIFIER] Checking in EST timezone: Friday 08:00:00
📅 [CAMPAIGN-QUALIFIER] Day check FAILED: HC_PA_Q4-2025_BCS-GSD v33
   Current day in EST: Friday, Allowed: ['Monday', 'Tuesday', 'Wednesday', 'Thursday']
❌ [CAMPAIGN-QUALIFIER] Campaign NOT qualified: HC_PA_Q4-2025_BCS-GSD v33
```

### Failure - Time Mismatch
```
🕐 [CAMPAIGN-QUALIFIER] Checking in EST timezone: Thursday 18:00:00
📅 [CAMPAIGN-QUALIFIER] Day check PASSED: HC_PA_Q4-2025_BCS-GSD v33 (Thursday)
⏰ [CAMPAIGN-QUALIFIER] Time check FAILED: HC_PA_Q4-2025_BCS-GSD v33
   Current time in EST: 18:00:00, Window: 19:06:00-23:28:00
❌ [CAMPAIGN-QUALIFIER] Campaign NOT qualified: HC_PA_Q4-2025_BCS-GSD v33
```

### Failure - No Timezones Qualified (member_tz)
```
⏰ [CAMPAIGN-QUALIFIER] Member timezone check FAILED: Campaign XYZ
   No US timezone currently qualifies
   Required: Days=['Monday', 'Tuesday'], Hours=09:00:00-17:00:00
   Current: ET=Wednesday 12:00, CT=Wednesday 11:00, MT=Wednesday 10:00, PT=Wednesday 09:00
❌ [CAMPAIGN-QUALIFIER] Campaign NOT qualified: Campaign XYZ
```

---

## Code Location Reference

| Component | File Path | Lines |
|-----------|-----------|-------|
| **Timezone Utilities** | | |
| Timezone Converter | `af_code/shared/timezone_utils.py` | 1-250+ |
| IANA Conversion | `timezone_utils.py` | `to_iana()` method |
| Windows Conversion | `timezone_utils.py` | `to_windows()` method |
| pytz Conversion | `timezone_utils.py` | `to_pytz()` method |
| **Campaign Qualification** | | |
| Campaign Qualifier | `af_code/partner_campaign_scheduler/services/campaign_qualifier.py` | 1-255 |
| Qualification Logic | `campaign_qualifier.py` | 125-238 |
| operating_tz Check | `campaign_qualifier.py` | 187-216 |
| member_tz Check | `campaign_qualifier.py` | 158-185 |
| Flexible Validation | `campaign_qualifier.py` | 240-255 |
| **Member Eligibility** | | |
| Member Eligibility Service | `af_code/partner_campaign_scheduler/services/member_eligibility.py` | 1-253 |
| SQL Query Builder | `member_eligibility.py` | 96-226 |
| Query Parameters | `member_eligibility.py` | 228-253 |
| **Main Scheduler** | | |
| Partner Campaign Scheduler | `functions/partner_campaign_scheduler.py` | 1-285 |
| Timer Trigger | `partner_campaign_scheduler.py` | 24-54 |
| HTTP Trigger | `partner_campaign_scheduler.py` | 56-123 |
| Shared Execution Logic | `partner_campaign_scheduler.py` | 125-267 |

---

## TimezoneConverter API Reference

### Class: `TimezoneConverter`

Located at: `af_code/shared/timezone_utils.py`

#### Methods

##### `to_iana(tz_input: str) -> str`
Convert any timezone format to IANA format for use with pytz.

**Parameters:**
- `tz_input`: Timezone string (EST, America/New_York, Eastern Standard Time, etc.)

**Returns:**
- IANA timezone name (e.g., `America/New_York`)

**Examples:**
```python
TimezoneConverter.to_iana('EST')                      # → 'America/New_York'
TimezoneConverter.to_iana('America/Chicago')          # → 'America/Chicago'
TimezoneConverter.to_iana('Eastern Standard Time')    # → 'America/New_York'
```

##### `to_windows(tz_input: str) -> str`
Convert any timezone format to Windows timezone name for SQL Server AT TIME ZONE.

**Parameters:**
- `tz_input`: Timezone string (EST, America/New_York, etc.)

**Returns:**
- Windows timezone name (e.g., `Eastern Standard Time`)

**Examples:**
```python
TimezoneConverter.to_windows('EST')                   # → 'Eastern Standard Time'
TimezoneConverter.to_windows('America/Chicago')       # → 'Central Standard Time'
TimezoneConverter.to_windows('PST')                   # → 'Pacific Standard Time'
```

##### `to_pytz(tz_input: str) -> pytz.tzinfo.BaseTzInfo`
Convert any timezone format to pytz timezone object.

**Parameters:**
- `tz_input`: Timezone string

**Returns:**
- pytz timezone object

**Examples:**
```python
TimezoneConverter.to_pytz('EST')                      # → <DstTzInfo 'America/New_York' ...>
TimezoneConverter.to_pytz('America/Chicago')          # → <DstTzInfo 'America/Chicago' ...>
```

##### `get_us_timezones_pytz() -> dict`
Get pytz timezone objects for all US timezones.

**Returns:**
- Dictionary: `{'Eastern': <pytz timezone>, 'Central': <pytz timezone>, ...}`

**Example:**
```python
us_timezones = TimezoneConverter.get_us_timezones_pytz()
# Returns:
# {
#     'Eastern': pytz.timezone('America/New_York'),
#     'Central': pytz.timezone('America/Chicago'),
#     'Mountain': pytz.timezone('America/Denver'),
#     'Pacific': pytz.timezone('America/Los_Angeles')
# }
```

##### `validate_timezone(tz_input: str) -> bool`
Check if timezone string is valid in any format.

**Parameters:**
- `tz_input`: Timezone string

**Returns:**
- `True` if valid, `False` otherwise

**Examples:**
```python
TimezoneConverter.validate_timezone('EST')            # → True
TimezoneConverter.validate_timezone('America/Chicago')# → True
TimezoneConverter.validate_timezone('XYZ')            # → False
```

### Convenience Functions

```python
from af_code.shared.timezone_utils import convert_to_iana, convert_to_windows, convert_to_pytz

# Quick conversions without class name
iana_tz = convert_to_iana('EST')          # → 'America/New_York'
windows_tz = convert_to_windows('EST')    # → 'Eastern Standard Time'
pytz_tz = convert_to_pytz('EST')          # → pytz timezone object
```

### Supported Timezones

#### US Mainland Timezones
- **Eastern**: EST/EDT → America/New_York → Eastern Standard Time
- **Central**: CST/CDT → America/Chicago → Central Standard Time
- **Mountain**: MST/MDT → America/Denver → Mountain Standard Time
- **Pacific**: PST/PDT → America/Los_Angeles → Pacific Standard Time

#### Additional US Timezones
- **Alaska**: AKST/AKDT → America/Anchorage → Alaskan Standard Time
- **Hawaii**: HST → Pacific/Honolulu → Hawaiian Standard Time

#### Major Cities Supported
- America/New_York (New York, Philadelphia, Atlanta, Miami)
- America/Chicago (Chicago, Dallas, Houston, New Orleans)
- America/Denver (Denver, Salt Lake City, Boise)
- America/Los_Angeles (Los Angeles, San Francisco, Seattle)
- America/Phoenix (Phoenix - no DST)
- America/Detroit (Detroit)
- America/Indianapolis (Indianapolis)

### Error Handling

All methods include graceful fallback behavior:

```python
# Unknown timezone → defaults to America/New_York (Eastern)
TimezoneConverter.to_iana('XYZ')          # → 'America/New_York' (with warning)
TimezoneConverter.to_windows('INVALID')   # → 'Eastern Standard Time' (with warning)

# Empty/NULL timezone → defaults to America/New_York
TimezoneConverter.to_iana(None)           # → 'America/New_York' (with warning)
TimezoneConverter.to_iana('')             # → 'America/New_York' (with warning)
```

### Logging

The TimezoneConverter logs all conversions for debugging:

```
🔄 [TIMEZONE] Converted abbreviation 'EST' → 'America/New_York'
🔄 [TIMEZONE] Converted IANA 'America/Chicago' → 'Central Standard Time'
⚠️ [TIMEZONE] Unknown timezone format 'XYZ', defaulting to America/New_York
```

---

## Related Documentation

- [Azure Functions Documentation](../../IOE_AZURE_FUNCTIONS_COMPREHENSIVE_DOCUMENTATION.md)
- [Bland AI API Documentation](https://docs.bland.ai/)
- [pytz Documentation](https://pythonhosted.org/pytz/)
- [IANA Timezone Database](https://www.iana.org/time-zones)
- [SQL Server Timezone Reference](https://docs.microsoft.com/en-us/sql/t-sql/queries/at-time-zone-transact-sql)

---

## Changelog

### Version 1.2 (2025-10-17)
- **BUGFIX**: Added SQL CASE statement to convert member IANA timezones to Windows format
- Fixed error: "The time zone parameter 'America/New_York' provided to AT TIME ZONE clause is invalid"
- Updated member_eligibility.py to handle IANA → Windows conversion inline in SQL query
- Added 26 timezone mappings covering all US timezones and territories

### Version 1.1 (2025-10-17)
- Added TimezoneConverter utility for IANA/Windows/Abbreviation conversions
- Updated timezone logic to support all 3 formats
- Added comprehensive timezone API reference
- Updated examples to use TimezoneConverter

### Version 1.0 (2025-10-17)
- Initial documentation
- Core database table mappings
- Campaign qualification logic
- 40+ test cases
- Edge case handling

---

**Document Version**: 1.2
**Last Updated**: 2025-10-17
**Author**: Claude Code Assistant
**Maintained By**: IOE Development Team
