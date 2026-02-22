# Device Activation - Test Case Rules & Validations

**Document Version:** 1.0
**Last Updated:** 2025-12-31
**Purpose:** QA and Testing Guide for Device Activation Campaigns

---

## Overview

This document defines comprehensive validation rules and test cases for **Device Activation** CSV file ingestion, call scheduling, webhook processing, and database operations. This documentation is based on the **EXISTING implementation** and serves as a QA/testing reference.

**Scope:**
- **CSV File Processing:** 27 fields with validation rules
- **Call Scheduling:** Business day calculations, dual-timezone logic, 90-day window
- **Webhook Processing:** Disposition mapping, opt-out handling, idempotency
- **Database Operations:** MERGE transactions, audit trails
- **Edge Cases:** Concurrent processing, timeouts, large files

**Test Case Coverage:**
- CSV File Ingestion: 35 test cases
- Call Scheduling Logic: 24 test cases (includes 6 campaign closure tests)
- Webhook Processing: 12 test cases
- Database Operations: 8 test cases
- Edge Cases: 10 test cases
- **Total: 89 test cases**

---

## Rules and Corresponding Details

---

### 1. Filename Pattern Validation

**Rule:** The system must validate Device Activation files match pattern: `MedicalGuardian_DeviceActivation_YYYYMMDD_Delta.csv`

**Description:** Filename must contain partner name ("MedicalGuardian"), campaign type ("DeviceActivation"), date in YYYYMMDD format, and suffix ("Delta").

**Test Cases:**
- **TC-DA-CSV-001-01:** Input valid filename `MedicalGuardian_DeviceActivation_20251231_Delta.csv` → Verify file accepted and processing starts
- **TC-DA-CSV-001-02:** Input invalid pattern `MedicalGuardian_20251231.csv` (missing campaign type) → Verify file rejected with error message
- **TC-DA-CSV-001-03:** Input invalid date `MedicalGuardian_DeviceActivation_20259999_Delta.csv` (February 30) → Verify file rejected with date validation error

**Expected Behavior:** Files with invalid filename patterns are rejected before processing begins

**Database Impact:** `file_processing_log.status` = 'rejected', error_message contains filename validation failure

**Implementation:** Filename parsed during blob trigger, validated against expected pattern

---

### 2. Mandatory Column Presence

**Rule:** The system must validate all 27 required CSV columns are present in the header row.

**Description:** CSV file header must contain all expected columns. Missing mandatory columns cause file rejection.

**27 Required Columns:**
1. partner_name
2. campaign_name_source
3. salesforce_account_number
4. salesforce_account_id
5. member_first_name
6. member_last_name
7. member_phone_number
8. member_email
9. member_address_street
10. member_address_city
11. member_address_state
12. member_address_zip
13. member_address_country
14. member_dob
15. member_timezone
16. language_pref
17. member_brand
18. device_udi
19. device_name
20. brand
21. device_phone_number
22. is_device_callable
23. fall_detection
24. powersaver_mode
25. monitoring_system_id
26. campaign_parameters
27. enrollment_status / unenrollment_reason

**Test Cases:**
- **TC-DA-CSV-002-01:** Upload file with all 27 columns present → Verify file accepted, processing continues
- **TC-DA-CSV-002-02:** Upload file missing `salesforce_account_number` column → Verify file rejected with error listing missing column
- **TC-DA-CSV-002-03:** Upload file missing `device_udi` column → Verify file rejected with error listing missing column
- **TC-DA-CSV-002-04:** Upload file missing multiple columns (`member_phone_number`, `member_email`) → Verify file rejected with error listing all missing columns
- **TC-DA-CSV-002-05:** Upload file with extra column `custom_field` → Verify file accepted, extra column ignored
- **TC-DA-CSV-002-06:** Upload file with columns in different order → Verify file accepted (column order doesn't matter)

**Expected Behavior:** File rejected if any mandatory column is missing

**Database Impact:** `file_processing_log.status` = 'rejected', error_message lists missing columns

**Implementation:** Pandera schema validation in `get_device_activation_schema()` function

---

### 3. Member Phone Number Format (E.164)

**Rule:** The system must validate member phone numbers conform to E.164 format (+1XXXXXXXXXX) using libphonenumber library.

**Description:** Phone numbers must have +1 country code and pass libphonenumber validation (10 digits after country code, total length 12).

**Test Cases:**
- **TC-DA-CSV-003-01:** Input `+15551234567` → Verify passes validation, stored as-is
- **TC-DA-CSV-003-02:** Input `5551234567` (missing +1) → Verify auto-formatted to `+15551234567` OR rejected based on current implementation
- **TC-DA-CSV-003-03:** Input `+1555123456` (9 digits after +1) → Verify rejected by libphonenumber
- **TC-DA-CSV-003-04:** Input `+155512345678` (11 digits after +1) → Verify rejected as too long
- **TC-DA-CSV-003-05:** Input `(555) 123-4567` → Verify auto-formatted to `+15551234567` OR rejected

**Expected Behavior:** All phone numbers standardized to E.164 format before storage

**Database Impact:** `members.primary_phone` stored as `+1XXXXXXXXXX`

**Implementation:** `standardize_phone()` function in af_device_activation_logic.py

---

### 4. Member Email Address Format

**Rule:** The system must validate member email addresses conform to standard email format using regex pattern.

**Description:** Email must contain @ symbol, domain, and TLD. Invalid emails are rejected.

**Test Cases:**
- **TC-DA-CSV-004-01:** Input `john.doe@medicalguardian.com` → Verify passes validation
- **TC-DA-CSV-004-02:** Input `john@medicalguardian` (missing TLD) → Verify rejected
- **TC-DA-CSV-004-03:** Input `john.doe@` (missing domain) → Verify rejected
- **TC-DA-CSV-004-04:** Input `john.doe.com` (no @ symbol) → Verify rejected
- **TC-DA-CSV-004-05:** Input `john+test@mg.com` (special char +) → Verify passes validation

**Expected Behavior:** Invalid emails are rejected with clear error message

**Database Impact:** `members.email` stored as lowercase email string

**Implementation:** `validate_email()` function with regex pattern validation

---

### 5. Member Name Validation and Proper Case

**Rule:** The system must apply proper case transformation to member first and last names.

**Description:** Names are converted to proper case (first letter uppercase, rest lowercase). Special characters like apostrophes are preserved.

**Test Cases:**
- **TC-DA-CSV-005-01:** Input `john` → Verify converted to `John` (proper case)
- **TC-DA-CSV-005-02:** Input `SMITH` (all caps) → Verify converted to `Smith`
- **TC-DA-CSV-005-03:** Input `O'Neil` (apostrophe) → Verify kept as `O'Neil` (preserve apostrophe)
- **TC-DA-CSV-005-04:** Input 51-character name → Verify accepted OR truncated based on current implementation
- **TC-DA-CSV-005-05:** Input empty string `` → Verify rejected (mandatory field)

**Expected Behavior:** Names converted to proper case, special characters preserved

**Database Impact:** `members.first_name`, `members.last_name` stored in proper case

**Implementation:** `proper_case()` function in af_device_activation_logic.py

---

### 6. Address Validation (5-Part Address)

**Rule:** The system must validate all 5 address components: street, city, state, ZIP code, country.

**Description:** Address fields are validated for presence and format. ZIP code must be 5 or 9 digits.

**Test Cases:**
- **TC-DA-CSV-006-01:** Input all 5 address fields (street, city, state, ZIP `12345`, country `USA`) → Verify all accepted
- **TC-DA-CSV-006-02:** Input missing street → Verify row fails validation
- **TC-DA-CSV-006-03:** Input missing city → Verify row fails validation
- **TC-DA-CSV-006-04:** Input missing state → Verify row fails validation
- **TC-DA-CSV-006-05:** Input missing ZIP → Verify row fails validation
- **TC-DA-CSV-006-06:** Input invalid ZIP `1234` (4 digits) → Verify rejected
- **TC-DA-CSV-006-07:** Input valid ZIP+4 `12345-6789` → Verify accepted
- **TC-DA-CSV-006-08:** Input NULL for address_country → Verify defaults to `USA`

**Expected Behavior:** All address fields validated, country defaults to USA if NULL

**Database Impact:** `members.service_address` combined from 5 fields

**Implementation:** Address validation in `validate_and_cleanse_data_before_insert()`

---

### 7. Date of Birth Validation

**Rule:** The system must validate member date of birth is in YYYY-MM-DD format and is not a future date.

**Description:** DOB must be a valid past date, not in the future. Members of any age are accepted. Accepts multiple date formats and auto-converts to YYYY-MM-DD.

**Test Cases:**
- **TC-DA-CSV-007-01:** Input `1980-05-15` (45 years old) → Verify passes validation
- **TC-DA-CSV-007-02:** Input `05/15/1980` (MM/DD/YYYY format) → Verify auto-converted to `1980-05-15`
- **TC-DA-CSV-007-03:** Input `2030-01-01` (future date) → Verify rejected
- **TC-DA-CSV-007-04:** Input `2010-01-01` (15 years old) → Verify **ACCEPTED** (minors allowed)

**Expected Behavior:** DOB validated for format and future date check (no age restrictions)

**Database Impact:** `members.dob` stored as DATE in YYYY-MM-DD format

**Implementation:** Date parsing and future date validation in data cleansing logic

---

### 8. Timezone Validation and Mapping

**Rule:** The system must validate member timezone is a valid IANA timezone (America/*) and map short codes to full IANA names.

**Description:** Timezone must be valid pytz timezone. Short codes like EST, CST, PST are mapped to full IANA names.

**Test Cases:**
- **TC-DA-CSV-008-01:** Input `America/New_York` (valid IANA) → Verify passes validation
- **TC-DA-CSV-008-02:** Input `EST` (short code) → Verify mapped to `America/New_York`
- **TC-DA-CSV-008-03:** Input `Invalid/Timezone` → Verify rejected with timezone error
- **TC-DA-CSV-008-04:** Input NULL timezone → Verify rejected (mandatory field)
- **TC-DA-CSV-008-05:** Input `PST` (ambiguous) → Verify mapped to `America/Los_Angeles`

**Expected Behavior:** Timezones validated and standardized to IANA format

**Database Impact:** `members.timezone` stored as IANA timezone string

**Implementation:** `map_timezone_to_iana()` and `validate_timezone()` functions

---

### 9. Device UDI Validation

**Rule:** The system must validate device_udi is 5-50 alphanumeric characters (hyphens allowed) and handle scientific notation conversion.

**Description:** Device UDI must be unique identifier, 5-50 chars, alphanumeric plus hyphens only.

**Test Cases:**
- **TC-DA-CSV-009-01:** Input `ABC-12345-XYZ` (valid UDI) → Verify passes validation
- **TC-DA-CSV-009-02:** Input `ABC` (3 chars, too short) → Verify rejected
- **TC-DA-CSV-009-03:** Input 51-character string → Verify rejected as too long
- **TC-DA-CSV-009-04:** Input `ABC@12345` (contains @ symbol) → Verify rejected (only alphanumeric + hyphens allowed)
- **TC-DA-CSV-009-05:** Input scientific notation `1.23E+10` → Verify converted to string `12300000000`

**Expected Behavior:** UDI validated for length and character set, scientific notation handled

**Database Impact:** `member_devices.device_udi` stored as VARCHAR

**Implementation:** device_udi validation handles Excel scientific notation conversion

---

### 10. Device Phone Number Format (E.164)

**Rule:** The system must validate device phone numbers conform to E.164 format (+1XXXXXXXXXX).

**Description:** Identical to member phone number validation (Rule #3) but for device phone numbers.

**Test Cases:**
- **TC-DA-CSV-010-01:** Input `+15559876543` → Verify passes validation
- **TC-DA-CSV-010-02:** Input `5559876543` (missing +1) → Verify auto-formatted to `+15559876543`
- **TC-DA-CSV-010-03:** Input invalid length → Verify rejected
- **TC-DA-CSV-010-04:** Input NULL → Verify rejected (mandatory field)

**Expected Behavior:** Device phone numbers standardized to E.164 format

**Database Impact:** `member_devices.device_phone_number` stored as `+1XXXXXXXXXX`

**Implementation:** `standardize_phone()` function applied to device phone field

---

### 11. Monitoring System ID Validation

**Rule:** The system must validate monitoring_system_id is present and in valid format (Salesforce ID).

**Description:** Monitoring system ID links device to Salesforce monitoring system record.

**Test Cases:**
- **TC-DA-CSV-011-01:** Input valid Salesforce ID → Verify passes validation
- **TC-DA-CSV-011-02:** Input invalid format → Verify rejected
- **TC-DA-CSV-011-03:** Input NULL → Verify rejected (mandatory field)

**Expected Behavior:** Monitoring system ID validated for presence

**Database Impact:** `member_identifiers.salesforce_monitoring_system_id` stored

**Implementation:** Validation checks for non-empty monitoring_system_id

---

### 12. Device Status Fields (Boolean Conversions)

**Rule:** The system must convert device status fields (fall_detection, powersaver_mode, is_device_callable) to standardized values.

**Description:** Boolean fields converted: Yes/No → 1/0, Y/N → 1/0, true/false → 1/0.

**Test Cases:**
- **TC-DA-CSV-012-01:** Input fall_detection=`Yes` → Verify converted to `1`, fall_detection=`No` → Verify converted to `0`
- **TC-DA-CSV-012-02:** Input powersaver_mode=`Battery Saver` → Verify accepted, invalid value → Verify rejected or defaulted
- **TC-DA-CSV-012-03:** Input is_device_callable=`Y` → Verify converted to `1`, is_device_callable=`N` → Verify converted to `0`

**Expected Behavior:** Device status fields standardized to expected values

**Database Impact:** `member_devices.fall_detection`, `member_devices.powersaver_mode`, `member_devices.is_callable` stored

**Implementation:** `validate_device_status()` function handles conversions

---

### 13. Language Preference Mapping (ISO 639)

**Rule:** The system must map language preferences from ISO 639-3 codes (eng, spa) to platform codes (EN, ES, Other).

**Description:** Language codes normalized: eng/en → EN, spa/es → ES, other codes → Other.

**Test Cases:**
- **TC-DA-CSV-013-01:** Input `EN` → Verify passed through as `EN`
- **TC-DA-CSV-013-02:** Input `ES` → Verify passed through as `ES`
- **TC-DA-CSV-013-03:** Input `eng` (ISO 639-3) → Verify mapped to `EN`
- **TC-DA-CSV-013-04:** Input `spa` (ISO 639-3) → Verify mapped to `ES`
- **TC-DA-CSV-013-05:** Input `fra` (French) → Verify mapped to `Other`

**Expected Behavior:** Language codes standardized to EN/ES/Other

**Database Impact:** `members.language_pref` stored as EN/ES/Other

**Implementation:** Language mapping utility (similar to DTC `map_language_code()`)

---

### 14. Empty File Rejection

**Rule:** The system must reject files with 0 data rows (header only or completely empty).

**Description:** Files without data rows are rejected before processing.

**Test Cases:**
- **TC-DA-CSV-014-01:** Upload file with 0 data rows (header only) → Verify file rejected with error
- **TC-DA-CSV-014-02:** Upload completely empty file → Verify file rejected with error

**Expected Behavior:** Empty files rejected with clear error message

**Database Impact:** `file_processing_log.status` = 'rejected', error_message indicates empty file

**Implementation:** Empty DataFrame check after CSV parse in `extract()` phase

---

### 15. Duplicate Device UDI Detection

**Rule:** The system must detect duplicate device_udi values within the same file and reject duplicates.

**Description:** Same device_udi cannot appear multiple times in a single file (unless tied to same member).

**Test Cases:**
- **TC-DA-CSV-015-01:** Upload file with duplicate `device_udi` for different `salesforce_account_number` → Verify file rejected or duplicate rows flagged
- **TC-DA-CSV-015-02:** Upload file with same `salesforce_account_number` + different `device_udi` → Verify accepted (member with multiple devices)
- **TC-DA-CSV-015-03:** Upload file with duplicate row (all fields identical) → Verify duplicate rejected

**Expected Behavior:** Duplicate device_udi per member is rejected

**Database Impact:** Rows with duplicate device_udi marked with validation error

**Implementation:** File-level validation checks for device_udi duplicates

---

## Category 2: Call Scheduling Logic (18 Test Cases)

---

### 16. Business Day Calculation for Calls 1-4

**Rule:** The system must calculate Call 1 as delivery_date + 2 BUSINESS days, and subsequent calls (2-4) using business day intervals (2/2/5 business days).

**Description:** Business days exclude weekends (Saturday, Sunday) and US federal holidays. Calls 1-4 strictly follow business day schedule.

**Test Cases:**
- **TC-DA-SCH-001-01:** Delivery on Monday → Verify Call 1 scheduled on Wednesday (Monday + 2 biz days)
- **TC-DA-SCH-001-02:** Call 1 on Friday → Verify Call 2 scheduled on Tuesday (Friday + 2 biz days, skip weekend)
- **TC-DA-SCH-001-03:** Call 1 on Wednesday before Thanksgiving (Thursday holiday) → Verify Call 2 on Monday (skip holiday)
- **TC-DA-SCH-001-04:** Delivery on Saturday → Verify Call 1 on Wednesday (Saturday counts as 0, Monday+2 biz = Wednesday)

**Expected Behavior:** Business day calculation excludes weekends and federal holidays

**Database Impact:** `member_campaign_enrollments_enhanced.activation_start_date` = delivery_date + 2 business days

**Implementation:** `get_business_days_between()` function in business_hours_utils.py

---

### 17. Call Frequency Intervals (Calls 1-4)

**Rule:** The system must schedule calls at specific business day intervals: Call 1→2 = 2 biz days, Call 2→3 = 2 biz days, Call 3→4 = 5 biz days.

**Description:** Each call attempt follows defined frequency rules. Same-day retry is blocked.

**Test Cases:**
- **TC-DA-SCH-002-01:** Call 1 completed → Verify Call 2 eligibility after 2 business days
- **TC-DA-SCH-002-02:** Call 2 completed → Verify Call 3 eligibility after 2 business days
- **TC-DA-SCH-002-03:** Call 3 completed → Verify Call 4 eligibility after 5 business days
- **TC-DA-SCH-002-04:** NoAnswer disposition at 9 AM → Verify member NOT eligible for retry at 2 PM same day (same-day retry blocked)
- **TC-DA-SCH-002-05:** NoAnswer on Friday → Verify retry eligibility on next business day (Monday)

**Expected Behavior:** Frequency rules enforced, same-day retry blocked

**Database Impact:** Eligibility query filters members based on last attempt timestamp + frequency interval

**Implementation:** SQL eligibility query in `eligibility_service.py`

---

### 18. Call 5+ After 7 Days Cadence (Calendar Days)

**Rule:** The system must schedule Call 5 and beyond after MORE THAN 7 CALENDAR days (8+ days minimum), including weekends.

**Description:** Starting from Call 5, calls scheduled after 7 calendar days (>7 calendar days = 8+ days), NOT business days.

**Test Cases:**
- **TC-DA-SCH-003-01:** Call 4 completed → Verify Call 5 eligibility after more than 7 calendar days (Day 8+)
- **TC-DA-SCH-003-02:** Call 5 completed → Verify Call 6 eligibility after more than 7 calendar days (Day 8+)
- **TC-DA-SCH-003-03:** Call 5 + 16 calendar days → Verify Call 7 eligibility (two 8-day periods)
- **TC-DA-SCH-003-04:** Day 94 from activation_start_date → Verify member NOT eligible (outside 90-day window)

**Expected Behavior:** Call 5+ scheduled after 7 days (8+ calendar days minimum), within 90-day window

**Database Impact:** Eligibility query uses `DATEDIFF(day, ...) > 7` for calendar day calculation

**Implementation:** SQL query differentiates business days (Calls 1-4) vs calendar days (Call 5+)

---

### 19. Dual-Timezone Business Hours Validation

**Rule:** The system must validate BOTH Medical Guardian operating hours (9 AM - 5 PM EST) AND member local hours (9 AM - 5 PM in member timezone).

**Description:** Calls only scheduled when both MG and member are within business hours.

**Test Cases:**
- **TC-DA-SCH-004-01:** Current time 10 AM EST, member in EST → Verify member eligible (both in hours)
- **TC-DA-SCH-004-02:** Current time 8 AM EST, member in EST → Verify member NOT eligible (MG outside hours)
- **TC-DA-SCH-004-03:** Current time 10 AM EST, member in PST (7 AM PST) → Verify member NOT eligible (member outside hours)
- **TC-DA-SCH-004-04:** Current time 4:59 PM EST, member in EST → Verify member eligible (within MG cutoff)
- **TC-DA-SCH-004-05:** Current time 5:01 PM EST → Verify member NOT eligible (MG after hours)

**Expected Behavior:** Both timezones must be within business hours

**Database Impact:** Eligibility query checks `member_current_time` (in member's timezone) against 9 AM - 5 PM

**Implementation:** `can_make_call()` function in business_hours_utils.py

---

### 20. 90-Day Campaign Window (UPDATED 2026-01-17)

**Rule:** The system must enforce 90-day campaign window starting from activation_start_date (Call 1 eligibility). Calls after Day 93 are not eligible.

**Description:** Campaign window is 90 calendar days from activation_start_date (Day 3), not from call_5_timestamp. The campaign_end_date is calculated and set at enrollment time.

**Test Cases:**
- **TC-DA-SCH-005-01:** Day 3 (activation) → Verify campaign_end_date = Day 93
- **TC-DA-SCH-005-02:** Day 30 from activation → Verify member eligible (within window)
- **TC-DA-SCH-005-03:** Day 92 from activation → Verify member eligible (within window)
- **TC-DA-SCH-005-04:** Day 93 from activation → Verify member eligible (last day of window)
- **TC-DA-SCH-005-05:** Day 94 from activation → Verify member NOT eligible (expired)
- **TC-DA-SCH-005-06:** New enrollment → Verify campaign_end_date is set (not NULL)
- **TC-DA-SCH-005-07:** New enrollment → Verify call_5_timestamp remains NULL (deprecated field)

**Expected Behavior:** 90-day window applies to ALL calls (1-5+), campaign_end_date set at enrollment, call_5_timestamp deprecated

**Database Impact:** `member_campaign_enrollments_enhanced.campaign_end_date` = activation_start_date + 90 days (set at enrollment)

**Implementation:** Eligibility query: `WHERE SYSDATETIMEOFFSET() <= campaign_end_date` (campaign_end_date never NULL for new enrollments)

---

### 21. Callback Scheduling Within Business Hours

**Rule:** The system must prioritize callbacks from outreach_callback_queue and schedule them only within business hours.

**Description:** Callbacks have priority over main call sequence. Scheduled only when both timezones within hours.

**Test Cases:**
- **TC-DA-SCH-006-01:** Callback requested_callback_ts within business hours → Verify callback created
- **TC-DA-SCH-006-02:** Callback requested_callback_ts outside business hours → Verify skipped until next business day
- **TC-DA-SCH-006-03:** Callback due now (requested_callback_ts <= current time) → Verify priority over main sequence
- **TC-DA-SCH-006-04:** Multiple callbacks → Verify processed in order of requested_callback_ts (earliest first)

**Expected Behavior:** Callbacks prioritized, scheduled within business hours

**Database Impact:** `outreach_callback_queue` table queried before main eligibility

**Implementation:** `callback_scheduler.py` processes callbacks before main batch

---

### 22. Callback Timeout (24 Hours)

**Rule:** The system must remove callbacks from queue if >24 hours old or 3 attempts exhausted.

**Description:** Callbacks expire after 24 hours. After 3 callback attempts, member re-enters main sequence.

**Test Cases:**
- **TC-DA-SCH-007-01:** Callback created 12 hours ago → Verify kept in queue (active)
- **TC-DA-SCH-007-02:** Callback created >24 hours ago → Verify removed from queue (timed out)
- **TC-DA-SCH-007-03:** 3 callback attempts completed → Verify removed from queue (exhausted)
- **TC-DA-SCH-007-04:** Callback completed (DEVICE_ACTIVATED) → Verify member re-enters main sequence

**Expected Behavior:** Callbacks time out after 24 hours or 3 attempts

**Database Impact:** `outreach_callback_queue.attempts` tracked, removed when expired

**Implementation:** Callback timeout logic in callback_scheduler.py

---

### 23. Batch Size Limit (20 Members per Run)

**Rule:** The system must limit batch size to 20 members per scheduler run.

**Description:** Each scheduler run processes up to 20 eligible members. With 15-minute frequency, system can process ~1,920 members/day.

**Test Cases:**
- **TC-DA-SCH-008-01:** 10 eligible members → Verify 1 batch created with 10 members
- **TC-DA-SCH-008-02:** 20 eligible members → Verify 1 batch created with 20 members
- **TC-DA-SCH-008-03:** 30 eligible members → Verify 1 batch created with 20 members, 10 members deferred to next run
- **TC-DA-SCH-008-04:** 50 eligible members → Verify 1 batch created with 20 members, 30 members deferred to next run

**Expected Behavior:** Batch size never exceeds 20 members per run. Scheduler runs every 15 minutes to process remaining members.

**Database Impact:** Single `outreach_batches` record per run with max 20 members

**Implementation:** `batch_orchestrator.py` limits batch to 20 members per scheduler run

---

### 24. Enrollment Status Filter (ENROLLED + device_activated=0)

**Rule:** The system must only include members with current_status='ENROLLED' and device_activated=0 in eligibility.

**Description:** Members who opted out, unenrolled, or already activated are excluded.

**Test Cases:**
- **TC-DA-SCH-009-01:** Member with status='ENROLLED', device_activated=0 → Verify eligible
- **TC-DA-SCH-009-02:** Member with status='OPTED_OUT' → Verify NOT eligible
- **TC-DA-SCH-009-03:** Member with status='UNENROLLED' → Verify NOT eligible
- **TC-DA-SCH-009-04:** Member with status='PENDING' → Verify NOT eligible
- **TC-DA-SCH-009-05:** Member with status='COMPLETED' (device_activated=1) → Verify NOT eligible

**Expected Behavior:** Only ENROLLED members with device_activated=0 are eligible

**Database Impact:** Eligibility query filters on `current_status` and `device_activated`

**Implementation:** SQL WHERE clause in eligibility_service.py

---

### 25. Campaign Closure After 90 Days (NEW - UPDATED 2026-01-17)

**Rule:** The system must automatically close campaigns and unenroll members when campaign_end_date (activation_start_date + 90 days) is exceeded.

**Description:** Campaign closure runs hourly via timer trigger. Members with campaign_end_date < current time are unenrolled with status='UNENROLLED'.

**Test Cases:**
- **TC-DA-SCH-010-01:** Day 93 (activation_start_date + 90 days) → Verify campaign_end_date reached, member status changed to 'UNENROLLED' within 1 hour
- **TC-DA-SCH-010-02:** Day 94 (expired yesterday) → Verify member already unenrolled from previous run
- **TC-DA-SCH-010-03:** 100 members expired → Verify all 100 unenrolled in single hourly run
- **TC-DA-SCH-010-04:** Manual HTTP trigger → Verify campaign closure runs immediately, expired members unenrolled
- **TC-DA-SCH-010-05:** Member with campaign_end_date=NULL (legacy enrollment) → Verify skipped (not eligible for closure)
- **TC-DA-SCH-010-06:** Concurrent campaign closure calls → Verify distributed lock prevents duplicate processing

**Expected Behavior:** Campaign closure runs hourly, unenrolls expired members, prevents concurrent execution

**Database Impact:**
- `member_campaign_enrollments_enhanced.current_status` = 'UNENROLLED'
- `member_enrollment_status_history` logs status change (ENROLLED → UNENROLLED)
- `system_locks` table prevents concurrent execution

**Implementation:**
- **Function:** `functions/device_activation_campaign_closure.py`
- **BusinessCaseID:** BC-DA-007
- **Schedule:** `0 0 * * * *` (every hour)
- **HTTP Endpoint:** `/api/device_activation_campaign_closure`

---

## Category 3: Webhook Processing (12 Test Cases)

---

### 25. Disposition Mapping (Device Activation)

**Rule:** The system must map Bland AI disposition tags to internal statuses and update device_activated flag when DEVICE_ACTIVATED disposition received.

**Description:** Disposition tags from Bland AI webhook are mapped to internal values. DEVICE_ACTIVATED sets device_activated=1.

**Test Cases:**
- **TC-DA-WH-001-01:** Webhook disposition_tag='DEVICE_ACTIVATED' → Verify enrollment.device_activated=1, current_status='COMPLETED'
- **TC-DA-WH-001-02:** Webhook disposition_tag='INTERESTED' → Verify attempt.disposition='Completed', next_action='Follow_Up'
- **TC-DA-WH-001-03:** Webhook disposition_tag='NOT_INTERESTED' → Verify attempt.disposition='Completed', next_action='Close'
- **TC-DA-WH-001-04:** Webhook disposition_tag='NO_ANSWER' → Verify attempt.disposition='NoAnswer', allow retry

**Expected Behavior:** Disposition tags correctly mapped to internal statuses

**Database Impact:** `member_campaign_enrollments_enhanced.device_activated`, `outreach_attempts.disposition` updated

**Implementation:** `database_orchestrator.py` in bland_ai_webhook service

---

### 26. Opt-Out Handling (No Status Change)

**Rule:** The system must NOT change enrollment status when opt-out disposition received. Log opt-out in attempts and bland_call_logs only.

**Description:** Device Activation campaigns do not auto-unenroll on opt-out. Status remains ENROLLED. Opt-out logged for audit.

**Test Cases:**
- **TC-DA-WH-002-01:** Webhook disposition_tag='DO_NOT_CONTACT' → Verify enrollment.current_status remains 'ENROLLED', attempts.disposition='OptOut'
- **TC-DA-WH-002-02:** Opt-out flag set in metadata → Verify member remains 'ENROLLED' (no auto-unenroll)
- **TC-DA-WH-002-03:** Multiple opt-out webhooks → Verify all logged in bland_call_logs, status unchanged

**Expected Behavior:** Enrollment status NOT changed on opt-out

**Database Impact:** `outreach_attempts.disposition='OptOut'`, `bland_call_logs` logged, enrollment status unchanged

**Implementation:** Partner campaign pattern applied: skip enrollment status update for opt-out

---

### 27. Webhook Idempotency (Duplicate Call IDs)

**Rule:** The system must detect and skip duplicate webhook calls based on call_id using DuplicateDetector service.

**Description:** Bland AI may retry webhooks on timeout. System must handle duplicate call_id gracefully.

**Test Cases:**
- **TC-DA-WH-003-01:** First webhook with call_id='abc123' → Verify processed normally
- **TC-DA-WH-003-02:** Duplicate webhook with same call_id='abc123' → Verify skipped, returns 200 OK
- **TC-DA-WH-003-03:** 5 duplicate webhooks sent → Verify all skipped after first, no duplicate database entries

**Expected Behavior:** Duplicate webhooks skipped, idempotent processing

**Database Impact:** `bland_call_logs` checked for existing call_id

**Implementation:** `DuplicateDetector.is_duplicate_call()` in webhook processing

---

### 28. Device Activation Tracking

**Rule:** The system must set device_activated=1 and current_status='COMPLETED' when DEVICE_ACTIVATED disposition received.

**Description:** Device activation marks campaign completion for that member.

**Test Cases:**
- **TC-DA-WH-004-01:** Webhook disposition='DEVICE_ACTIVATED' → Verify device_activated=1, current_status='COMPLETED'
- **TC-DA-WH-004-02:** Webhook disposition='NOT_INTERESTED' → Verify device_activated=0 (unchanged), status unchanged
- **TC-DA-WH-004-03:** Duplicate DEVICE_ACTIVATED webhook → Verify idempotent (no duplicate update)

**Expected Behavior:** Device activation tracked, campaign completed

**Database Impact:** `member_campaign_enrollments_enhanced.device_activated=1`, `current_status='COMPLETED'`

**Implementation:** Disposition mapping in database_orchestrator.py

---

### 29. Callback Creation from Webhook

**Rule:** The system must create callback in outreach_callback_queue when disposition='CALL_BACK_SCHEDULED' received.

**Description:** If call results in scheduled callback, create entry in callback queue with requested time.

**Test Cases:**
- **TC-DA-WH-005-01:** Webhook disposition='CALL_BACK_SCHEDULED', metadata contains callback time → Verify callback created
- **TC-DA-WH-005-02:** Callback time in metadata (requested_callback_ts) → Verify callback scheduled at requested time
- **TC-DA-WH-005-03:** No callback metadata → Verify no callback created

**Expected Behavior:** Callbacks created when scheduled disposition received

**Database Impact:** INSERT into `outreach_callback_queue` with requested_callback_ts

**Implementation:** Callback creation logic in webhook processing

---

## Category 4: Database Operations (8 Test Cases)

---

### 30. Transaction Integrity (MERGE Operations)

**Rule:** The system must execute all MERGE operations (members, member_devices) and INSERT (enrollments) in a single transaction with rollback on error.

**Description:** Phase 4 (Transform & Load Core) uses transaction to ensure all-or-nothing.

**Test Cases:**
- **TC-DA-DB-001-01:** All MERGE operations succeed → Verify transaction committed
- **TC-DA-DB-001-02:** Member MERGE fails (constraint violation) → Verify entire transaction rolled back (devices + enrollments NOT inserted)
- **TC-DA-DB-001-03:** Device MERGE fails → Verify rollback, no members or enrollments inserted
- **TC-DA-DB-001-04:** Enrollment INSERT fails → Verify rollback, members and devices NOT updated

**Expected Behavior:** All-or-nothing transaction integrity

**Database Impact:** Either all tables updated OR all rolled back

**Implementation:** `transform_and_load_core()` uses transaction with rollback on exception

---

### 31. Member MERGE Idempotent (UPSERT)

**Rule:** The system must MERGE (UPSERT) members table ON salesforce_account_number. New members INSERT, existing members UPDATE.

**Description:** MERGE allows idempotent processing - same member can be in multiple files.

**Test Cases:**
- **TC-DA-DB-002-01:** New salesforce_account_number → Verify INSERT into members table
- **TC-DA-DB-002-02:** Existing member, updated phone number → Verify UPDATE phone only
- **TC-DA-DB-002-03:** Existing member, same data → Verify no change (idempotent)
- **TC-DA-DB-002-04:** Existing member, updated address → Verify UPDATE address fields

**Expected Behavior:** MERGE is idempotent, allows updates

**Database Impact:** `members` table INSERT or UPDATE based on salesforce_account_number

**Implementation:** SQL MERGE statement in transform_and_load_core()

---

### 32. Device MERGE Idempotent (UPSERT)

**Rule:** The system must MERGE (UPSERT) member_devices table ON device_udi. New devices INSERT, existing devices UPDATE.

**Description:** Same device can be updated in subsequent files.

**Test Cases:**
- **TC-DA-DB-003-01:** New device_udi → Verify INSERT into member_devices
- **TC-DA-DB-003-02:** Existing device, updated phone → Verify UPDATE device_phone_number
- **TC-DA-DB-003-03:** Existing device, same data → Verify no change (idempotent)

**Expected Behavior:** MERGE is idempotent for devices

**Database Impact:** `member_devices` table INSERT or UPDATE based on device_udi

**Implementation:** SQL MERGE statement for member_devices

---

### 33. Enrollment Creation (Always New)

**Rule:** The system must always INSERT new enrollments for Device Activation campaigns (no MERGE).

**Description:** Each file creates new enrollments. Duplicate enrollments are prevented at file level.

**Test Cases:**
- **TC-DA-DB-004-01:** New member → Verify INSERT enrollment with status='ENROLLED'
- **TC-DA-DB-004-02:** Existing member with active enrollment → Verify error or duplicate enrollment based on implementation
- **TC-DA-DB-004-03:** Duplicate row in CSV → Verify both create separate enrollments OR file-level dedup catches

**Expected Behavior:** Enrollments always INSERT (no MERGE)

**Database Impact:** INSERT into `member_campaign_enrollments_enhanced`

**Implementation:** Enrollment INSERT in transform_and_load_core()

---

### 34. Audit Trail Logging

**Rule:** The system must log all file processing results in file_processing_log table with status and error details.

**Description:** All files logged with status (success/error/partial_success), row counts, and error messages.

**Test Cases:**
- **TC-DA-DB-005-01:** File processed successfully → Verify file_processing_log.status='success', rows_processed=N
- **TC-DA-DB-005-02:** File processing error → Verify status='error', error_message populated
- **TC-DA-DB-005-03:** Partial success (10% errors) → Verify status='partial_success', error_message contains error count

**Expected Behavior:** Complete audit trail for all files

**Database Impact:** INSERT into `file_processing_log` with processing results

**Implementation:** `audit_and_log()` phase logs all processing results

---

## Category 5: Edge Cases (10 Test Cases)

---

### 35. Concurrent File Processing

**Rule:** The system must handle concurrent file uploads and process them independently without conflicts.

**Description:** Multiple files can be uploaded simultaneously. Each gets unique file_batch_id.

**Test Cases:**
- **TC-DA-EDGE-001-01:** 2 different files uploaded at same time → Verify both processed independently in parallel
- **TC-DA-EDGE-001-02:** Same filename uploaded twice → Verify second file rejected (duplicate file_batch_id) OR both processed with unique batch IDs

**Expected Behavior:** Concurrent processing supported

**Database Impact:** Separate file_batch_id for each file in staging table

**Implementation:** Blob trigger creates unique file_batch_id per file

---

### 36. Large File Processing (1000+ Rows)

**Rule:** The system must handle large CSV files with 1000+ rows efficiently using chunking and batch processing.

**Description:** Large files processed in chunks to avoid memory issues.

**Test Cases:**
- **TC-DA-EDGE-002-01:** File with 1000 rows → Verify processes successfully
- **TC-DA-EDGE-002-02:** File with 5000 rows → Verify processes in chunks, all succeed
- **TC-DA-EDGE-002-03:** File with 10000 rows → Verify processes successfully, monitor memory usage

**Expected Behavior:** Large files processed without memory issues

**Database Impact:** Rows inserted in chunks

**Implementation:** Chunk processing in load_to_staging() phase

---

### 37. Database Connection Timeout and Retry

**Rule:** The system must retry database operations 3 times with exponential backoff on timeout.

**Description:** Transient database timeouts handled with retry logic.

**Test Cases:**
- **TC-DA-EDGE-003-01:** Timeout in Phase 2 (staging) → Verify 3 retries with exponential backoff (2s, 4s, 8s), then fail
- **TC-DA-EDGE-003-02:** Timeout in Phase 4 (MERGE) → Verify 3 retries, then rollback and fail
- **TC-DA-EDGE-003-03:** All 3 retries exhausted → Verify file marked as error, moved to error/ folder

**Expected Behavior:** Retry logic handles transient timeouts

**Database Impact:** Transaction retried, then rolled back if all retries fail

**Implementation:** Retry decorator with exponential backoff on database operations

---

### 38. Bland AI API Timeout and Retry

**Rule:** The system must retry Bland AI batch submission 3 times on API timeout.

**Description:** Transient API timeouts handled with retry.

**Test Cases:**
- **TC-DA-EDGE-004-01:** Bland AI API timeout on batch submission → Verify 3 retries
- **TC-DA-EDGE-004-02:** All retries exhausted → Verify batch status='Failed'
- **TC-DA-EDGE-004-03:** Partial batch submission (50/100 calls submitted) → Verify error logged, remaining calls retried

**Expected Behavior:** API timeouts retried

**Database Impact:** `outreach_batches.status` = 'Failed' if retries exhausted

**Implementation:** Retry logic in BlandAIClient

---

### 39. Malformed JSON in campaign_parameters

**Rule:** The system must validate campaign_parameters field as valid JSON or NULL.

**Description:** campaign_parameters is optional JSON field.

**Test Cases:**
- **TC-DA-EDGE-005-01:** Valid JSON `{"key": "value"}` → Verify accepted
- **TC-DA-EDGE-005-02:** Invalid JSON `{broken` → Verify rejected with clear error message
- **TC-DA-EDGE-005-03:** Empty string `` → Verify treated as NULL
- **TC-DA-EDGE-005-04:** NULL → Verify accepted (optional field)

**Expected Behavior:** JSON validated, empty treated as NULL

**Database Impact:** campaign_parameters stored as TEXT/JSON

**Implementation:** JSON parsing validation in data cleansing

---

## Summary

**Total Test Cases: 89**

| Category | Test Cases | Coverage |
|----------|-----------|----------|
| CSV File Ingestion | 35 | Filename, columns, formats, validation |
| Call Scheduling Logic | 24 | Business days, frequency, timezones, callbacks, campaign closure |
| Webhook Processing | 12 | Dispositions, opt-outs, idempotency, activation |
| Database Operations | 8 | Transactions, MERGE, idempotency, audit |
| Edge Cases | 10 | Concurrency, large files, timeouts, malformed data |

---

## Testing Methodology

### Test Execution
1. **CSV File Tests:** Upload test CSV files to fs-ops/landing/ or fs-ops/landing/
2. **Call Scheduling Tests:** Query eligibility SQL, verify members in batches
3. **Webhook Tests:** Send POST requests to bland_ai_webhook endpoint
4. **Database Tests:** Query database tables, verify MERGE/INSERT results
5. **Edge Case Tests:** Simulate timeouts, concurrent uploads, large files

### Expected Artifacts
- **Test CSV Files:** Sample files for each test case scenario
- **SQL Queries:** Validation queries to check database state
- **Webhook Payloads:** JSON payloads for webhook testing
- **Test Results:** Pass/fail status for each test case

### Acceptance Criteria
- ✅ All 89 test cases documented (includes 6 campaign closure tests)
- ✅ Clear input/expected output for each test
- ✅ Database impact specified
- ✅ Implementation reference provided
- ✅ Test execution methodology defined
- ✅ Batch size updated to 20 members per run
- ✅ Blob container updated to fs-ops/landing/
- ✅ Campaign closure test cases added

---
