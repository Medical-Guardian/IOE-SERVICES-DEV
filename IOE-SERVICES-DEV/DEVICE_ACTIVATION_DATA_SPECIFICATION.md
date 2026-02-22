# Device Activation Campaign - Data Specification

**Purpose:** Define the data fields and CSV format for ingesting members into the Device Activation campaign
**Date:** December 2024
**Campaign:** Device Activation (Grace AI Agent)

---

## Table of Contents

1. [Overview](#overview)
2. [Required CSV Fields](#required-csv-fields)
3. [Data Validation Rules](#data-validation-rules)
4. [CSV File Format](#csv-file-format)
5. [Database Storage](#database-storage)
6. [Processing Workflow](#processing-workflow)

---

## Overview

**Campaign Purpose:**
Automated outreach to help customers activate their Medical Guardian devices (MGMini) when no signal is detected within a certain timeframe after delivery.

**Trigger:**
- Device delivered to customer
- No device signal detected after 5 days (configurable)
- Customer needs assistance activating device

**Data Source:**
- SFTP file location: `/device-activation/landing/`
- File format: CSV
- Naming convention: `MedicalGuardian_DeviceActivation_YYYYMMDD_Delta.csv`

---

## Required CSV Fields

### **Core Member Identity** (REQUIRED)

| Field Name | Type | Required | Description | Example |
|------------|------|----------|-------------|---------|
| `salesforce_account_id` | String(50) | YES | Unique Salesforce account identifier | `SF-2025-001234` |
| `salesforce_account_number` | String(50) | YES | Secondary Salesforce identifier (legacy) | `ACC-789456` |
| `member_first_name` | String(100) | YES | Member's first name | `Sarah` |
| `member_last_name` | String(100) | YES | Member's last name | `Johnson` |

**Note:** Both `salesforce_account_id` and `salesforce_account_number` are required for data integrity.

---

### **Contact Information** (REQUIRED)

| Field Name | Type | Required | Description | Example |
|------------|------|----------|-------------|---------|
| `member_phone_number` | String(20) | YES | Member's primary phone number (E.164 format) | `+15551234567` |
| `member_email` | String(255) | NO | Member's email address | `sarah.johnson@example.com` |

---

### **Member Address** (REQUIRED)

| Field Name | Type | Required | Description | Example |
|------------|------|----------|-------------|---------|
| `service_address` | String(255) | YES | Street address where device was delivered | `123 Main Street` |
| `city` | String(100) | YES | City | `Boston` |
| `state` | String(2) | YES | State abbreviation (2-letter) | `MA` |
| `zip` | String(10) | YES | ZIP code | `02101` |

---

### **Member Demographics** (REQUIRED)

| Field Name | Type | Required | Description | Example |
|------------|------|----------|-------------|---------|
| `dob` | Date | YES | Date of birth (YYYY-MM-DD format) | `1950-06-15` |
| `customer_timezone` | String(50) | YES | IANA timezone format | `America/New_York` |
| `language_pref` | String(10) | NO | Language preference (EN, ES, Other) | `EN` |

---

### **Device Information** (REQUIRED)

| Field Name | Type | Required | Description | Example |
|------------|------|----------|-------------|---------|
| `device_udi` | String(100) | YES | Device UDI (Unique Device Identifier) / Serial Number | `MGM-12345-2025` |
| `device_name` | String(100) | YES | Device model name | `MGMini` |
| `brand` | String(100) | YES | Device brand | `Medical Guardian` |
| `device_phone_number` | String(20) | NO | Device's phone number (if callable) | `+15551234568` |
| `is_device_callable` | Boolean | NO | Can the device be called directly? (Y/N, TRUE/FALSE, 1/0) | `Y` |
| `delivery_date` | Date | YES | Date device was delivered (YYYY-MM-DD) | `2025-01-06` |

---

### **Device Status** (REQUIRED)

| Field Name | Type | Required | Description | Example |
|------------|------|----------|-------------|---------|
| `fall_detection_status` | String(50) | YES | Fall detection feature status | `Active`, `Inactive`, `Not Applicable` |
| `powersaver_mode` | String(50) | YES | Device power management mode | `Default`, `Standard`, `Battery Saver` |

**Valid Values:**
- **fall_detection_status**: `Active`, `Inactive`, `Not Applicable`, `Unknown`
- **powersaver_mode**: `Default`, `Standard`, `Battery Saver`

**Note:** The field `battery_status` was renamed to `powersaver_mode` as of 2025-12-22. CSV files may use either column name for backward compatibility.

---

### **Campaign Metadata** (REQUIRED)

| Field Name | Type | Required | Description | Example |
|------------|------|----------|-------------|---------|
| `partner_name` | String(100) | YES | Organization/Partner name | `Medical Guardian` |
| `customer_type` | String(10) | YES | Customer type: DTC or MS | `DTC` |
| `enrollment_status` | String(20) | YES | ENROLL (new) or UPDATE (existing) | `ENROLL` |

**Valid Values:**
- **customer_type**: `DTC` (Direct-to-Consumer), `MS` (Managed Services)
- **enrollment_status**: `ENROLL` (new enrollment), `UPDATE` (update existing), `UNENROLL` (remove from campaign)

---

## Data Validation Rules

### **Field Validation**

#### **Phone Numbers**
- **Format:** E.164 international format
- **Pattern:** `+1XXXXXXXXXX` (US numbers)
- **Length:** 11-15 digits including country code
- **Example:** `+15551234567`
- **Validation:** Must start with `+` and contain only digits after

#### **Timezone**
- **Format:** IANA timezone identifier
- **Valid US timezones:**
  - `America/New_York` (EST/EDT)
  - `America/Chicago` (CST/CDT)
  - `America/Denver` (MST/MDT)
  - `America/Los_Angeles` (PST/PDT)
  - `America/Phoenix` (MST - no DST)
- **Default:** If invalid, defaults to `America/New_York`

#### **Dates**
- **Format:** `YYYY-MM-DD` (ISO 8601)
- **delivery_date:** Cannot be in the future
- **dob:** Must be a valid date, typically >= 18 years ago

#### **State**
- **Format:** 2-letter state abbreviation
- **Examples:** `MA`, `NY`, `CA`, `TX`, `FL`
- **Validation:** Must be valid US state code

#### **Email**
- **Format:** Standard email format
- **Pattern:** `name@domain.com`
- **Validation:** Optional but must be valid if provided

#### **Boolean Fields** (is_device_callable)
- **Valid values:**
  - `Y`, `YES`, `TRUE`, `1` → stored as `1` (TRUE)
  - `N`, `NO`, `FALSE`, `0` → stored as `0` (FALSE)
  - Case-insensitive

#### **Language Preference**
- **Valid values:** `EN` (English), `ES` (Spanish), `Other`
- **ISO 639 codes supported:** Will be mapped to platform format
  - `eng`, `en` → `EN`
  - `spa`, `es` → `ES`
  - All other codes → `Other`
- **Default:** `EN` if not provided

---

### **Business Rules**

1. **Unique Member Identification:**
   - Combination of `salesforce_account_id` + `partner_name` must be unique
   - System uses `salesforce_account_id` as primary business key

2. **Device Tracking:**
   - `device_udi` must be unique across all devices
   - One device can be associated with one member at a time

3. **Enrollment Logic:**
   - `ENROLL`: Creates new member record and enrolls in device_activation campaign
   - `UPDATE`: Updates existing member information, keeps enrollment active
   - `UNENROLL`: Removes member from campaign

4. **Customer Type Impact:**
   - `DTC`: Campaign ends at 90 days with no further action
   - `MS`: At 90 days, flags for human sales/support follow-up

5. **Call Scheduling:**
   - **Call 1 (Day 2):** delivery_date + 2 business days (excluding weekends and federal holidays)
   - **Call 2 (Day 4):** Call 1 + 2 business days
   - **Call 3 (Day 6):** Call 2 + 2 business days
   - **Call 4+ (Weekly):** Every 7 calendar days until Day 90

6. **Business Hours Validation:**
   - Calls only during: Monday-Friday, 9 AM - 5 PM (dual-timezone validation)
   - Medical Guardian hours: 9 AM - 5 PM EST
   - Member hours: 9 AM - 5 PM (member's local timezone)
   - Federal holidays excluded

---

## CSV File Format

### **File Naming Convention**
```
MedicalGuardian_DeviceActivation_YYYYMMDD_Delta.csv
```

**Examples:**
- `MedicalGuardian_DeviceActivation_20250106_Delta.csv`
- `MedicalGuardian_DeviceActivation_20250113_Delta.csv`

---

### **CSV Header Row (Column Order)**

```csv
salesforce_account_id,salesforce_account_number,member_first_name,member_last_name,member_phone_number,member_email,service_address,city,state,zip,dob,customer_timezone,language_pref,device_udi,device_name,brand,device_phone_number,is_device_callable,delivery_date,fall_detection_status,powersaver_mode,partner_name,customer_type,enrollment_status
```

**Note:** For backward compatibility, CSV files may still use `battery_status` as the column name - it will be automatically mapped to `powersaver_mode` during processing.

---

### **Sample CSV Data**

```csv
salesforce_account_id,salesforce_account_number,member_first_name,member_last_name,member_phone_number,member_email,service_address,city,state,zip,dob,customer_timezone,language_pref,device_udi,device_name,brand,device_phone_number,is_device_callable,delivery_date,fall_detection_status,powersaver_mode,partner_name,customer_type,enrollment_status
SF-2025-001234,ACC-789456,Sarah,Johnson,+15551234567,sarah.j@example.com,123 Main Street,Boston,MA,02101,1950-06-15,America/New_York,EN,MGM-12345-2025,MGMini,Medical Guardian,+15551234568,Y,2025-01-06,Active,Standard,Medical Guardian,DTC,ENROLL
SF-2025-001235,ACC-789457,John,Martinez,+15559876543,john.m@example.com,456 Oak Avenue,Los Angeles,CA,90001,1948-03-22,America/Los_Angeles,ES,MGM-12346-2025,MGMini,Medical Guardian,,N,2025-01-05,Active,Default,Medical Guardian,DTC,ENROLL
SF-2025-001236,ACC-789458,Mary,Chen,+15556543210,mary.chen@example.com,789 Elm Street,Chicago,IL,60601,1955-11-08,America/Chicago,EN,MGM-12347-2025,MGMini,Medical Guardian,+15556543211,Y,2025-01-04,Inactive,Battery Saver,Medical Guardian,MS,ENROLL
SF-2025-001237,ACC-789459,Robert,Williams,+15554321098,,321 Pine Road,Phoenix,AZ,85001,1952-07-19,America/Phoenix,EN,MGM-12348-2025,MGMini,Medical Guardian,,N,2025-01-03,Not Applicable,Standard,Medical Guardian,DTC,ENROLL
```

---

### **CSV Requirements**

1. **Encoding:** UTF-8
2. **Line Endings:** CRLF or LF
3. **Delimiter:** Comma (`,`)
4. **Text Qualifier:** Double quotes (`"`) for fields containing commas or special characters
5. **Header Row:** Required (first row must be column names)
6. **Empty Values:** Use empty string `""` or leave blank for optional fields
7. **Date Format:** ISO 8601 (`YYYY-MM-DD`)
8. **Phone Format:** E.164 (`+1XXXXXXXXXX`)

---

## Database Storage

### **Staging Table: `engage360_stg.stg_device_activation_delta`**

```sql
CREATE TABLE engage360_stg.stg_device_activation_delta (
    -- File metadata
    file_batch_id UNIQUEIDENTIFIER NOT NULL,
    source_filename NVARCHAR(255),
    row_number_in_file INT,
    load_timestamp DATETIMEOFFSET,
    processing_status NVARCHAR(50),  -- PENDING, VALIDATING, VALIDATED, PROCESSED, ERROR
    error_message NVARCHAR(MAX),

    -- Member identity
    salesforce_account_id NVARCHAR(50) NOT NULL,
    salesforce_account_number NVARCHAR(50) NOT NULL,
    member_first_name NVARCHAR(100),
    member_last_name NVARCHAR(100),

    -- Contact info
    member_phone_number NVARCHAR(20),
    member_email NVARCHAR(255),

    -- Address
    service_address NVARCHAR(255),
    city NVARCHAR(100),
    state NVARCHAR(2),
    zip NVARCHAR(10),

    -- Demographics
    dob DATE,
    customer_timezone NVARCHAR(50),
    language_pref NVARCHAR(10),

    -- Device info
    device_udi NVARCHAR(100) NOT NULL,
    device_name NVARCHAR(100),
    brand NVARCHAR(100),
    device_phone_number NVARCHAR(20),
    is_device_callable BIT,
    delivery_date DATE NOT NULL,

    -- Device status
    fall_detection_status NVARCHAR(50),
    powersaver_mode NVARCHAR(50),

    -- Campaign metadata
    partner_name NVARCHAR(100),
    customer_type NVARCHAR(10),
    enrollment_status NVARCHAR(20),

    -- Cleaned columns
    first_name_clean NVARCHAR(100),
    last_name_clean NVARCHAR(100),
    primary_phone_clean NVARCHAR(20),
    timezone_clean NVARCHAR(50),
    org_id UNIQUEIDENTIFIER,

    -- Processing timestamps
    cleansing_started_ts DATETIMEOFFSET,
    cleansing_completed_ts DATETIMEOFFSET,
    enrollment_started_ts DATETIMEOFFSET,
    enrollment_completed_ts DATETIMEOFFSET,

    -- Tracking
    member_id_processed UNIQUEIDENTIFIER,
    enrollment_id_processed UNIQUEIDENTIFIER,

    PRIMARY KEY (file_batch_id, row_number_in_file)
);
```

---

### **Core Tables**

#### **engage360.members**
```sql
-- Stores member demographics and contact information
member_id UNIQUEIDENTIFIER PRIMARY KEY,
org_id UNIQUEIDENTIFIER NOT NULL,
salesforce_account_id NVARCHAR(50) NOT NULL,    -- NEW: Primary Salesforce ID
salesforce_account_number NVARCHAR(50) NOT NULL,
first_name NVARCHAR(100),
last_name NVARCHAR(100),
primary_phone NVARCHAR(20),
email NVARCHAR(255),
dob DATE,
timezone NVARCHAR(50),
language_pref NVARCHAR(10),
address_street NVARCHAR(255),
address_city NVARCHAR(100),
address_state NVARCHAR(2),
address_zip NVARCHAR(10),
address_country NVARCHAR(10) DEFAULT 'US',
created_ts DATETIMEOFFSET,
updated_ts DATETIMEOFFSET
```

#### **engage360.member_devices** (Enhanced for Device Activation)
```sql
device_id NVARCHAR(100) PRIMARY KEY,          -- Device UDI
member_id UNIQUEIDENTIFIER NOT NULL,
device_phone_number NVARCHAR(20),
is_device_callable BIT,
device_name NVARCHAR(100),
brand NVARCHAR(100),                           -- NEW
delivery_date DATE,                            -- NEW
activation_date DATE,                          -- NEW: Set when device activates
fall_detection_status NVARCHAR(50),           -- NEW
powersaver_mode NVARCHAR(50),                 -- NEW (renamed from battery_status 2025-12-22)
last_signal_received_ts DATETIMEOFFSET,       -- NEW: Last time device sent signal
created_ts DATETIMEOFFSET,
updated_ts DATETIMEOFFSET
```

#### **engage360.member_campaign_enrollments_enhanced**
```sql
enrollment_id UNIQUEIDENTIFIER PRIMARY KEY,
member_id UNIQUEIDENTIFIER NOT NULL,
campaign_id UNIQUEIDENTIFIER NOT NULL,
enrollment_ts DATETIMEOFFSET,
current_status NVARCHAR(50),  -- ENROLLED, PENDING, COMPLETED, OPTED_OUT
activation_start_date DATE,   -- NEW: delivery_date + 2 business days
campaign_end_date DATE,       -- NEW: activation_start_date + 90 days
customer_type NVARCHAR(10),   -- NEW: DTC or MS
device_activated BIT,         -- NEW: TRUE when device sends signal
activation_confirmed_ts DATETIMEOFFSET  -- NEW: When activation confirmed
```

#### **engage360.outreach_attempts** (Enhanced)
```sql
attempt_id UNIQUEIDENTIFIER PRIMARY KEY,
enrollment_id UNIQUEIDENTIFIER NOT NULL,
batch_id UNIQUEIDENTIFIER,
vendor_session_id NVARCHAR(100),
disposition NVARCHAR(50),
call_sequence_number INT,     -- NEW: 1, 2, 3, 4, 5... (Call 1, Call 2, etc.)
callback_type NVARCHAR(50),   -- NEW: 'scheduled', 'unboxing', 'charging', NULL
device_status_at_call NVARCHAR(50),  -- NEW: 'unboxed', 'charged', 'testing', NULL
attempt_ts DATETIMEOFFSET,
duration_sec INT,
response_summary NVARCHAR(MAX),
next_action NVARCHAR(255)
```

---

## Processing Workflow

### **Phase 1: File Ingestion (SFTP → Blob Storage)**

1. CSV file uploaded to SFTP location: `/device-activation/landing/`
2. Azure Function blob trigger detects new file
3. File downloaded and validated for structure

---

### **Phase 2: Extraction & Validation**

```python
# Extract function
- Parse CSV file
- Validate header columns
- Count total rows
- Generate file_batch_id (UUID)

# Validation checks
- Required fields present
- Phone number E.164 format
- Timezone valid IANA format
- Dates in YYYY-MM-DD format
- State is valid 2-letter code
- Email format valid (if provided)
- Boolean values valid (Y/N/TRUE/FALSE/1/0)
```

---

### **Phase 3: Data Cleansing**

```python
# Cleansing operations
- Standardize phone numbers to E.164
- Convert timezone to IANA format
- Proper case names (First Name → First name)
- Parse dates to DATE type
- Convert boolean strings to BIT (Y → 1, N → 0)
- Trim whitespace from all text fields
- Validate state codes against US state list
```

---

### **Phase 4: Database Load**

```sql
-- Step 1: Load to staging table
INSERT INTO engage360_stg.stg_device_activation_delta
VALUES (...);

-- Step 2: Validate against business rules
UPDATE staging
SET org_id = (SELECT org_id FROM engage360.orgs WHERE org_name = partner_name);

-- Step 3: MERGE into core tables
MERGE engage360.members ...
MERGE engage360.member_devices ...
MERGE engage360.member_campaign_enrollments_enhanced ...

-- Step 4: Calculate call schedule
UPDATE enrollments
SET activation_start_date = add_business_days(delivery_date, 2),
    campaign_end_date = DATEADD(DAY, 90, activation_start_date);
```

---

### **Phase 5: Call Scheduling**

```python
# For each enrolled member:
call_1_date = add_business_days(delivery_date, 2)  # Day 2
call_2_date = add_business_days(call_1_date, 2)    # Day 4
call_3_date = add_business_days(call_2_date, 2)    # Day 6
call_4_date = add_business_days(call_3_date, 5)    # Day 11
# Weekly thereafter until Day 90

# Business day calculation excludes:
- Weekends (Saturday, Sunday)
- US Federal holidays (Christmas, Thanksgiving, etc.)

# Business hours validation (dual-timezone):
- Medical Guardian: 9 AM - 5 PM EST
- Member: 9 AM - 5 PM (member's local timezone)
```

---

## Field Mapping Summary

### **Fields Removed (Not Needed):**
- ❌ `checkin_time` - Not needed for device activation
- ❌ `caregiver_first_name` - Not needed
- ❌ `caregiver_last_name` - Not needed
- ❌ `caregiver_phone_number` - Not needed
- ❌ `caregiver_email` - Not needed

### **Fields Added (Device Activation Specific):**
- ✅ `salesforce_account_id` - Primary Salesforce identifier
- ✅ `service_address` - Delivery address
- ✅ `dob` - Date of birth
- ✅ `city` - City
- ✅ `state` - State
- ✅ `zip` - ZIP code
- ✅ `brand` - Device brand
- ✅ `fall_detection_status` - Fall detection feature status
- ✅ `powersaver_mode` - Power management mode (Default/Standard/Battery Saver)

---

## Error Handling

### **File-Level Errors**
- Invalid CSV format → Reject entire file
- Missing required columns → Reject entire file
- File size > 50 MB → Reject entire file

### **Row-Level Errors**
- Missing required field → Mark row as ERROR, log to error table
- Invalid phone format → Mark row as ERROR
- Invalid timezone → Default to America/New_York, log warning
- Invalid date → Mark row as ERROR
- Duplicate salesforce_account_id → Update existing member

### **Error Logging**
```sql
-- Error details stored in staging table
processing_status = 'ERROR'
error_message = 'Invalid phone format: missing country code'
```

---

**Last Updated:** December 2024
**Version:** 1.0
**Campaign:** Device Activation (Grace AI Agent)
