# Device Activation CSV File Reference

## Overview

This document describes the CSV file format for Device Activation campaign member enrollments. The CSV file contains member information, device details, and enrollment data for Medical Guardian's Device Activation campaign.

---

## File Naming Convention

**Pattern:** `MedicalGuardian_DeviceActivation_YYYYMMDD_Delta.csv`

**Examples:**
- `MedicalGuardian_DeviceActivation_20251207_Delta.csv`
- `MedicalGuardian_DeviceActivation_20251215_Delta.csv`

**Notes:**
- Files must start with `MedicalGuardian_DeviceActivation_`
- Files must end with `_Delta.csv`
- Date format: YYYYMMDD (4-digit year, 2-digit month, 2-digit day)
- Files not matching this pattern will be skipped by the Azure Function

---

## Blob Storage Location

**Container:** `fs-device-activation`

**Folder Structure:**
- `landing/` - Incoming files (trigger location)
- `staging/` - Files being processed
- `processed/` - Successfully processed files
- `error/` - Failed files

**Upload Location:** `fs-device-activation/landing/`

---

## CSV File Structure

### Total Fields: 27

**✅ UPDATED 2025-12-29:** Added 2 new required fields (campaign_name_source, monitoring_system_id) and made 17 previously optional fields REQUIRED.

The CSV file must include a header row with the following column names (case-sensitive):

```csv
partner_name,campaign_name_source,salesforce_account_id,salesforce_account_number,member_first_name,member_last_name,member_phone_number,member_email,member_address_street,member_address_city,member_address_state,member_address_zip,member_address_country,member_dob,member_timezone,language_pref,device_udi,device_name,member_brand,device_phone_number,fall_detection,powersaver_mode,campaign_parameters,monitoring_system_id,enrollment_status,unenrollment_reason
```

---

## Field Definitions

### Member Information (11 fields)

#### 1. **salesforce_account_id** (REQUIRED)
- **Type:** String
- **Description:** Salesforce Account ID (18-character ID)
- **Format:** `001XXXXXXXXXXXXXX`
- **Example:** `001SF5000012ABC`
- **Validation:** Required, non-empty
- **New Field:** ✅ This is a NEW field not used in DTC/Partner campaigns

#### 2. **campaign_name_source** (REQUIRED) ✅ NEW
- **Type:** String
- **Description:** Campaign name from source system
- **Format:** Any string
- **Example:** `Device Activation - Medicaid`, `Device Activation - Medicare`
- **Validation:** Required, non-empty
- **Notes:** Identifies the campaign in the source system

#### 3. **salesforce_account_number** (REQUIRED)
- **Type:** String
- **Description:** Salesforce Account Number (business identifier)
- **Format:** `ACC-XXXXXX`
- **Example:** `ACC-100001`
- **Validation:** Required, non-empty
- **Notes:** Used as PRIMARY matching key with org_id for MERGE into members table

#### 3. **member_first_name** (REQUIRED)
- **Type:** String
- **Description:** Member's first name
- **Format:** Any string (letters, spaces, apostrophes only)
- **Example:** `John`, `Maria`, `O'Connor`
- **Validation:** Required, non-empty, max 50 characters after cleaning
- **Processing:**
  - Special characters removed (keeps only letters, spaces, apostrophes)
  - Leading/trailing apostrophes removed (e.g., `'John'` → `John`, `neil'` → `neil`)
  - Middle apostrophes preserved (e.g., `O'Connor` → `O'Connor`)
  - Example: `Huz@098` → `Huz`, `'John` → `John`, `neil'` → `neil`
  - Converted to Proper Case (John, Maria, O'Connor, McDonald)

#### 4. **member_last_name** (REQUIRED)
- **Type:** String
- **Description:** Member's last name
- **Format:** Any string (letters, spaces, apostrophes only)
- **Example:** `Smith`, `Garcia`, `O'Brien`
- **Validation:** Required, non-empty, max 50 characters after cleaning
- **Processing:**
  - Special characters removed (keeps only letters, spaces, apostrophes)
  - Leading/trailing apostrophes removed (e.g., `'Smith'` → `Smith`, `O'Neil'` → `O'Neil`)
  - Middle apostrophes preserved (e.g., `O'Brien` → `O'Brien`)
  - Example: `Syed'...` → `Syed`, `'O'Connor` → `O'Connor`, `neil'` → `neil`
  - Converted to Proper Case (Smith, Garcia, O'Brien, McDonald)

#### 5. **primary_phone** (REQUIRED)
- **Type:** String
- **Description:** Member's primary phone number
- **Format:** 10-digit US phone number (can include dashes, spaces, parentheses)
- **Example:** `5551234567`, `555-123-4567`, `(555) 123-4567`
- **Validation:** Must be valid US phone number (10-11 digits)
- **Processing:** Standardized to E.164 format (+15551234567)

#### 6. **email** (OPTIONAL)
- **Type:** String
- **Description:** Member's email address
- **Format:** Valid email format
- **Example:** `john.smith@email.com`
- **Validation:** If provided, must be valid email format (contains @, domain)
- **Processing:** Converted to lowercase for consistency (emails are case-insensitive)
  - Example: `John.Doe@EXAMPLE.COM` → `john.doe@example.com`
- **Notes:** Can be empty/null

#### 7. **service_address** (REQUIRED)
- **Type:** String
- **Description:** Member's service address (street address)
- **Format:** Any string
- **Example:** `123 Main Street`
- **Validation:** Required, non-empty

#### 8. **city** (REQUIRED)
- **Type:** String
- **Description:** City
- **Format:** Any string
- **Example:** `New York`
- **Validation:** Required, non-empty

#### 9. **state** (REQUIRED)
- **Type:** String
- **Description:** US State (2-letter abbreviation)
- **Format:** 2-letter state code
- **Example:** `NY`, `CA`, `TX`
- **Validation:** Required, 2 characters

#### 10. **zip** (REQUIRED)
- **Type:** String
- **Description:** ZIP code
- **Format:** 5-digit ZIP code (can be 5+4 format)
- **Example:** `10001`, `90001-1234`
- **Validation:** Required, 5+ characters

#### 11. **dob** (REQUIRED)
- **Type:** Date
- **Description:** Member's date of birth
- **Format:** `YYYY-MM-DD`
- **Example:** `1950-05-15`
- **Validation:** Required, valid date format

---

### Communication Preferences (2 fields)

#### 12. **timezone** (REQUIRED)
- **Type:** String
- **Description:** Member's timezone (IANA format)
- **Format:** IANA timezone identifier
- **Valid Values:**
  - `America/New_York` (Eastern)
  - `America/Chicago` (Central)
  - `America/Denver` (Mountain)
  - `America/Los_Angeles` (Pacific)
  - `America/Phoenix` (Arizona - no DST)
- **Example:** `America/New_York`
- **Validation:** Must be valid IANA timezone
- **Notes:** ❌ Do NOT use abbreviations (EST, CST, PST)

#### 13. **language_pref** (REQUIRED)
- **Type:** String
- **Description:** Member's preferred language
- **Valid Values:**
  - `EN` (English)
  - `ES` (Spanish)
  - `Other` (All other languages)
- **Example:** `EN`, `ES`
- **Validation:** Must be EN, ES, or Other
- **Notes:** ISO 639-3 codes (eng, spa) are also accepted and mapped to EN/ES

---

### Device Information (8 fields)

#### 14. **device_udi** (REQUIRED)
- **Type:** String
- **Description:** Unique Device Identifier (UDI)
- **Format:** 5-50 characters
- **Example:** `UDI-MG-2025-001234`
- **Validation:**
  - Required, non-empty, 5-50 characters
  - **File-level check:** Each device_udi must be associated with only ONE salesforce_account_id per file
  - If the same device_udi appears with multiple different salesforce_account_id values, ALL affected rows will be rejected
- **Processing:**
  - Scientific notation converted to full number (e.g., `9.17E+11` → `917000000000`)
  - Used as device_id (primary key) in member_devices table
- **Notes:**
  - A single device can only belong to one Salesforce account
  - If multiple rows have the same device_udi, they must ALL have the same salesforce_account_id
  - Duplicate device_udi with SAME account is allowed (e.g., updating device data)
  - Duplicate device_udi with DIFFERENT accounts will cause file rejection

#### 15. **device_name** (REQUIRED)
- **Type:** String
- **Description:** Device model name
- **Format:** Any string
- **Example:** `MG Classic`, `MG Premier`, `MG Mobile`
- **Validation:** Required, non-empty

#### 16. **brand** (REQUIRED)
- **Type:** String
- **Description:** Device brand/manufacturer
- **Format:** Any string
- **Example:** `Medical Guardian`
- **Validation:** Required, non-empty
- **New Field:** ✅ This is a NEW field for Device Activation

#### 17. **device_phone_number** (OPTIONAL)
- **Type:** String
- **Description:** Phone number assigned to the device
- **Format:** 10-digit US phone number
- **Example:** `5559871234`
- **Validation:** If provided, must be valid US phone number
- **Processing:** Standardized to E.164 format (+15559871234)

#### 18. **is_device_callable** (REQUIRED)
- **Type:** String (Boolean)
- **Description:** Whether the device can receive phone calls
- **Valid Values:** `Y` (Yes), `N` (No)
- **Example:** `Y`, `N`
- **Validation:** Must be Y or N
- **Processing:** Converted to boolean (Y=1, N=0)

#### 19. **delivery_date** (REQUIRED)
- **Type:** Date
- **Description:** Date the device was delivered to the member
- **Format:** `YYYY-MM-DD`
- **Example:** `2025-12-01`
- **Validation:**
  - Required, valid date format
  - Cannot be in the future
  - Cannot be older than 180 days
- **Notes:** Used to calculate activation_start_date (delivery_date + 2 business days)
- **New Field:** ✅ This is a NEW field for Device Activation

#### 20. **fall_detection** (OPTIONAL)
- **Type:** String (Boolean)
- **Description:** Whether fall detection feature is enabled on the device
- **Valid Values (case-insensitive, boolean-like):**
  - **TRUE values:** `true`, `TRUE`, `True`, `1`, `1.0`, `yes`, `YES`, `y`, `Y`
  - **FALSE values:** `false`, `FALSE`, `False`, `0`, `0.0`, `no`, `NO`, `n`, `N`, `f`, `F`
- **Example:** `true`, `false`, `yes`, `no`, `1`, `0`
- **Validation:** Must be boolean-like value (see above)
- **Processing:** All TRUE values normalized to `"true"`, all FALSE values to `"false"`
- **Storage:** Stored as BIT in database (1 = true, 0 = false)
- **Notes:**
  - Can be empty/null (stored as NULL in database)
  - ⚠️ **IMPORTANT**: Do NOT use status strings like "Active" or "Inactive"
  - Use simple boolean values: `true`/`false`, `yes`/`no`, or `1`/`0`
- **New Field:** ✅ This is a NEW field for Device Activation

#### 21. **powersaver_mode** (OPTIONAL)
- **Type:** String
- **Description:** Device power-saving mode setting
- **Valid Values (case-insensitive):**
  - `default` - Default power mode (any case: default, Default, DEFAULT)
  - `standard` - Standard power mode (any case: standard, Standard, STANDARD)
  - `battery saver` - Battery saving mode (any case: battery saver, Battery Saver, BATTERY SAVER)
- **Example:** `default`, `Standard`, `BATTERY SAVER`
- **Validation:** Case-insensitive matching - normalized to Title Case on storage
- **Stored As:** `Default`, `Standard`, `Battery Saver` (Title Case)
- **Notes:**
  - Can be empty/null (stored as NULL in database)
  - For backwards compatibility, CSV column name can be `battery_status` or `powersaver_mode`
  - Values are normalized to Title Case for consistency
- **New Field:** ✅ This is a NEW field for Device Activation

---

### Campaign Information (3 fields)

#### 22. **partner_name** (REQUIRED)
- **Type:** String
- **Description:** Partner organization name
- **Valid Values:** `Medical Guardian` (ONLY)
- **Example:** `Medical Guardian`
- **Validation:** Must be exactly "Medical Guardian" (case-insensitive)
- **Notes:** Used to lookup org_id from engage360.orgs table

#### 23. **customer_type** (REQUIRED)
- **Type:** String
- **Description:** Customer type classification
- **Valid Values:**
  - `DTC` - Direct to Consumer
  - `MS` - Managed Service
- **Example:** `DTC`, `MS`
- **Validation:** Must be DTC or MS (case-insensitive)
- **Notes:** Affects workflow and business logic
- **New Field:** ✅ This is a NEW field for Device Activation

#### 24. **enrollment_status** (REQUIRED)
- **Type:** String
- **Description:** Enrollment action to perform
- **Valid Values (case-insensitive, accepts present and past tense):**
  - **Present Tense:**
    - `ENROLL` / `enroll` / `Enroll` → Creates new enrollment
    - `UPDATE` / `update` / `Update` → Updates existing enrollment
    - `UNENROLL` / `unenroll` / `Unenroll` → Removes member from campaign
  - **Past Tense (also accepted):**
    - `ENROLLED` / `enrolled` / `Enrolled` → Mapped to `ENROLL`
    - `UPDATED` / `updated` / `Updated` → Mapped to `UPDATE`
    - `UNENROLLED` / `unenrolled` / `Unenrolled` → Mapped to `UNENROLL`
- **Example:** `ENROLL`, `update`, `Unenrolled`
- **Validation:** Case-insensitive - all forms normalized to uppercase
- **Processing:** All forms normalized to `ENROLL`, `UPDATE`, or `UNENROLL`
- **Default:** Empty/blank values default to `ENROLL`
- **Notes:**
  - Most files will use `ENROLL` (for new device activations)
  - Use `UPDATE` to refresh member/device data for existing enrollments
  - If `enrollment_status = UNENROLL`, must provide `unenrollment_reason`

#### 25. **unenrollment_reason** (CONDITIONAL)
- **Type:** String
- **Description:** Reason for removing member from campaign
- **Format:** Any string
- **Example:** `Device returned`, `Member deceased`, `Member declined service`, `Duplicate enrollment`
- **Validation:** REQUIRED when `enrollment_status = UNENROLL`, optional otherwise
- **Processing:** Stored as-is for audit trail
- **Notes:**
  - This field is ONLY required when unenrolling a member
  - Can be blank/null for `ENROLL` and `UPDATE` actions
  - Used for reporting and audit purposes
  - No maximum length enforced

---

## Sample CSV File

**Location:** `documentation/SAMPLE_DEVICE_ACTIVATION.csv`

The sample file contains 10 test records demonstrating:
- ✅ Valid data across all fields
- ✅ Multiple timezones (EST, CST, PST, MST)
- ✅ Both customer types (DTC and MS)
- ✅ Different device models (MG Classic, MG Premier, MG Mobile)
- ✅ Fall detection values (true/false, yes/no, 1/0)
- ✅ Various battery statuses (Default, Standard, Battery Saver)
- ✅ Language preferences (EN, ES)
- ✅ Different delivery dates (recent dates within 180-day window)
- ✅ Enrollment statuses (ENROLL, UPDATE, UNENROLL)

---

## Processing Flow

### 1. **File Upload**
- Upload CSV to `fs-device-activation/landing/`
- Azure Function blob trigger activates

### 2. **Validation**
- Filename pattern validation
- Pandera schema validation (25 fields)
- Row-by-row validation (19 validation rules)
- Error threshold check (10% default)

### 3. **Data Cleansing**
- Phone numbers → E.164 format
- Names → Proper Case
- Timezone → IANA format
- Language → EN/ES/Other

### 4. **Database Operations**
- **MERGE INTO members** (match on org_id + salesforce_account_number)
- **MERGE INTO member_devices** (match on device_udi)
- **INSERT INTO member_campaign_enrollments_enhanced**
  - `activation_start_date = delivery_date + 2 business days` (skips weekends + federal holidays)
  - `campaign_end_date = activation_start_date + 90 days`
  - `customer_type = DTC or MS`
  - `device_activated = 0` (not yet activated)

### 5. **File Movement**
- **Success:** Move to `processed/`
- **Failure:** Move to `error/`

### 6. **Audit Trail**
- Record in `engage360_stg.file_processing_log`
- Record in `engage360_stg.stg_device_activation_delta`

---

## Business Day Calculation Example

**Scenario:** Device delivered on Friday, December 1, 2025

**Calculation:**
1. `delivery_date = 2025-12-01` (Friday)
2. `activation_start_date = delivery_date + 2 business days`
   - Saturday 12/2 → SKIP (weekend)
   - Sunday 12/3 → SKIP (weekend)
   - Monday 12/4 → Business Day 1
   - Tuesday 12/5 → Business Day 2 ✅ **activation_start_date**
3. `campaign_end_date = activation_start_date + 90 days`
   - Tuesday 12/5 + 90 days = **Thursday, March 5, 2026**

**Result:**
- `activation_start_date = 2025-12-05`
- `campaign_end_date = 2026-03-05`

---

## Validation Rules Summary

| Rule # | Field | Validation |
|--------|-------|-----------|
| 1 | partner_name | Must be "Medical Guardian" |
| 2 | salesforce_account_id | Required, non-empty |
| 3 | salesforce_account_number | Required, non-empty |
| 4 | primary_phone | Valid US phone, E.164 format |
| 5 | member_first_name | Required, special chars removed, max 50 chars, Proper Case |
| 6 | member_last_name | Required, special chars removed, max 50 chars, Proper Case |
| 7 | timezone | Valid IANA timezone |
| 8 | language_pref | EN, ES, or Other |
| 9 | dob | Valid date format |
| 10 | email | Valid email format, converted to lowercase (if provided) |
| 11 | device_udi | Required, 5-50 characters |
| 12 | delivery_date | Not future, not >180 days old |
| 13 | customer_type | DTC or MS |
| 14 | fall_detection | Boolean: true/false, yes/no, 1/0 (case-insensitive, if provided) |
| 15 | powersaver_mode | Default/Standard/Battery Saver (case-insensitive, if provided) |
| 16 | is_device_callable | Y or N |
| 17 | **Contact Method** | At least one of: primary_phone, email, or device_phone required |
| 18 | enrollment_status | ENROLL/UPDATE/UNENROLL (+ past tense, case-insensitive) |
| 19 | unenrollment_reason | Required if enrollment_status = UNENROLL |
| 20 | device_udi | No duplicate across different salesforce_account_id (file-level check) |

---

## Error Threshold

**Default:** 10%

**Behavior:**
- If >10% of rows fail validation, the entire file is rejected
- File is moved to `error/` folder
- No data is loaded to production tables
- Error details are stored in staging table

**Example:**
- File with 100 rows, 11 failures → **REJECTED** (11% > 10%)
- File with 100 rows, 9 failures → **ACCEPTED** (9% < 10%, 91 valid rows loaded)

---

## Common Errors and Fixes

### ❌ Error: "Invalid partner_name"
**Fix:** Ensure partner_name = "Medical Guardian" (case-insensitive)

### ❌ Error: "Invalid phone number format"
**Fix:** Use 10-digit US phone number: `5551234567` or `555-123-4567`

### ❌ Error: "Invalid timezone"
**Fix:** Use IANA format: `America/New_York` (NOT `EST`)

### ❌ Error: "Delivery date in future"
**Fix:** Ensure delivery_date is today or earlier

### ❌ Error: "Delivery date too old"
**Fix:** Ensure delivery_date is within last 180 days

### ❌ Error: "Invalid customer_type"
**Fix:** Use `DTC` or `MS` only

### ❌ Error: "Invalid fall_detection format"
**Fix:** Use boolean-like values: true/false, yes/no, 1/0 (case-insensitive)
**Examples:**
- Valid: `true`, `TRUE`, `yes`, `YES`, `1`, `y`, `Y`
- Valid: `false`, `FALSE`, `no`, `NO`, `0`, `n`, `N`, `f`
- Invalid: `Active`, `Inactive`, `enabled`, `disabled`

### ❌ Error: "Invalid powersaver_mode"
**Fix:** Use `default`, `standard`, or `battery saver` (case-insensitive, or leave empty)

### ❌ Error: "member_first_name contains only invalid characters"
**Fix:** Ensure first name contains at least some letters (special characters like @, #, numbers will be automatically removed)
**Example:** `@@@###` is invalid, but `John123` becomes `John`

### ❌ Error: "member_last_name contains only invalid characters"
**Fix:** Ensure last name contains at least some letters (special characters like @, #, numbers will be automatically removed)
**Example:** `12345` is invalid, but `Smith123` becomes `Smith`

### ❌ Error: "member_first_name exceeds maximum length of 50 characters"
**Fix:** Shorten first name to 50 characters or less (measured after special character removal)

### ❌ Error: "member_last_name exceeds maximum length of 50 characters"
**Fix:** Shorten last name to 50 characters or less (measured after special character removal)

### ❌ Error: "At least one contact method required (primary_phone, email, or device_phone)"
**Fix:** Provide at least one valid contact method - either primary_phone, email, or device_phone (cannot have all three empty)

### ❌ Error: "Name contains leading/trailing apostrophes"
**Fix:** Remove apostrophes at the start or end of names (they will be automatically removed during processing)
**Examples:**
- Input: `'John` → Processed as: `John`
- Input: `neil'` → Processed as: `neil`
- Input: `'O'Connor'` → Processed as: `O'Connor`
- Valid: `O'Neil` → Stays as: `O'Neil` (middle apostrophe is correct)
**Note:** This is informational - the system automatically fixes this, no action needed from file creator

### ❌ Error: "Invalid enrollment_status"
**Fix:** Use one of: ENROLL, UPDATE, UNENROLL (or past tense: enrolled, updated, unenrolled) - case-insensitive
**Examples:**
- Valid: `ENROLL`, `enroll`, `Enroll`, `EnRoLL`
- Valid: `UPDATE`, `update`, `Updated`
- Valid: `UNENROLL`, `unenrolled`, `Unenrolled`
- Invalid: `enrol`, `add`, `remove`

### ❌ Error: "unenrollment_reason is required when enrollment_status is 'UNENROLL'"
**Fix:** Provide a reason when unenrolling a member
**Examples:**
- Valid: `Device returned`
- Valid: `Member deceased`
- Valid: `Duplicate enrollment`
- Valid: `Member relocated - out of coverage area`

### ❌ Error: "Duplicate device_udi 'UDI-123' used by multiple accounts: [ACC-001, ACC-002]"
**Fix:** Each device can only belong to one Salesforce account. If you need to transfer a device from one account to another:
1. First unenroll the device from the old account (use enrollment_status = UNENROLL)
2. Then enroll the device to the new account in a separate file upload

**Example of Invalid File:**
```csv
salesforce_account_id,device_udi,...
ACC-001,UDI-123,...  ← First account using device UDI-123
ACC-002,UDI-123,...  ← ERROR: Different account trying to use same device
```

**Example of Valid File (Same Account):**
```csv
salesforce_account_id,device_udi,...
ACC-001,UDI-123,...  ← First row
ACC-001,UDI-123,...  ← OK: Same account can appear multiple times (e.g., updating data)
```

**Notes:**
- All rows with the duplicate device_udi will be rejected (not just the duplicates)
- To fix: Remove or correct the rows so each device_udi belongs to only one account

---

## Testing Checklist

Before uploading a CSV file to production:

- [ ] File name matches pattern: `MedicalGuardian_DeviceActivation_YYYYMMDD_Delta.csv`
- [ ] CSV has header row with all 25 field names
- [ ] All required fields are populated (no empty values)
- [ ] Phone numbers are valid 10-digit US numbers
- [ ] Timezones use IANA format (America/New_York, etc.)
- [ ] Delivery dates are within 180-day window
- [ ] Customer types are DTC or MS
- [ ] Partner name is "Medical Guardian"
- [ ] Device UDI is 5-50 characters
- [ ] is_device_callable is Y or N
- [ ] fall_detection uses boolean values: true/false, yes/no, 1/0 (if provided)
- [ ] powersaver_mode uses valid values: default/standard/battery saver (if provided)
- [ ] enrollment_status uses ENROLL/UPDATE/UNENROLL (any case, present/past tense)
- [ ] unenrollment_reason provided if enrollment_status is UNENROLL
- [ ] Test upload to `fs-device-activation/landing/`
- [ ] Verify successful processing (file moves to `processed/`)
- [ ] Check database for new records in members, member_devices, member_campaign_enrollments_enhanced

---

## Support

**For Issues:**
- Check `engage360_stg.file_processing_log` for error details
- Check `engage360_stg.stg_device_activation_delta` for row-level errors
- Review Azure Function logs in Application Insights

**Contact:**
- AI-POD Team - Data Science at Medical Guardian

---

**Last Updated:** 2025-12-07
**BusinessCaseID:** BC-TBD (Device Activation System)
