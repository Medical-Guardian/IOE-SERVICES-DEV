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

### Total Fields: 24

The CSV file must include a header row with the following column names (case-sensitive):

```csv
salesforce_account_id,salesforce_account_number,member_first_name,member_last_name,primary_phone,email,service_address,city,state,zip,dob,timezone,language_pref,device_udi,device_name,brand,device_phone_number,is_device_callable,delivery_date,fall_detection_status,powersaver_mode,partner_name,customer_type,enrollment_status
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

#### 2. **salesforce_account_number** (REQUIRED)
- **Type:** String
- **Description:** Salesforce Account Number (business identifier)
- **Format:** `ACC-XXXXXX`
- **Example:** `ACC-100001`
- **Validation:** Required, non-empty
- **Notes:** Used as match key with org_id for MERGE into members table

#### 3. **member_first_name** (REQUIRED)
- **Type:** String
- **Description:** Member's first name
- **Format:** Any string
- **Example:** `John`, `Maria`
- **Validation:** Required, non-empty
- **Processing:** Converted to Proper Case (John, Maria)

#### 4. **member_last_name** (REQUIRED)
- **Type:** String
- **Description:** Member's last name
- **Format:** Any string
- **Example:** `Smith`, `Garcia`
- **Validation:** Required, non-empty
- **Processing:** Converted to Proper Case (Smith, Garcia)

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
- **Validation:** Required, non-empty, 5-50 characters
- **Notes:** Used as device_id (primary key) in member_devices table

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

#### 20. **fall_detection_status** (OPTIONAL)
- **Type:** String
- **Description:** Status of fall detection feature on the device
- **Valid Values:**
  - `Active` - Fall detection is enabled and active
  - `Inactive` - Fall detection is disabled
  - `Not Applicable` - Device does not have fall detection
  - `Unknown` - Status unknown
- **Example:** `Active`, `Inactive`
- **Validation:** If provided, must be one of the valid values
- **Notes:** Can be empty/null
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
- **Valid Values:**
  - `ENROLL` - Enroll member in campaign
  - `UNENROLL` - Remove member from campaign
- **Example:** `ENROLL`
- **Validation:** Must be ENROLL or UNENROLL
- **Notes:** Most files will use ENROLL

---

## Sample CSV File

**Location:** `documentation/SAMPLE_DEVICE_ACTIVATION.csv`

The sample file contains 10 test records demonstrating:
- ✅ Valid data across all fields
- ✅ Multiple timezones (EST, CST, PST, MST)
- ✅ Both customer types (DTC and MS)
- ✅ Different device models (MG Classic, MG Premier, MG Mobile)
- ✅ Various device statuses (Active, Inactive, Not Applicable, Unknown)
- ✅ Various battery statuses (Good, Low, Critical, Charging, Unknown)
- ✅ Language preferences (EN, ES)
- ✅ Different delivery dates (recent dates within 180-day window)

---

## Processing Flow

### 1. **File Upload**
- Upload CSV to `fs-device-activation/landing/`
- Azure Function blob trigger activates

### 2. **Validation**
- Filename pattern validation
- Pandera schema validation (24 fields)
- Row-by-row validation (13 validation rules)
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
| 5 | member_first_name | Required, Proper Case |
| 6 | member_last_name | Required, Proper Case |
| 7 | timezone | Valid IANA timezone |
| 8 | language_pref | EN, ES, or Other |
| 9 | dob | Valid date format |
| 10 | email | Valid email format (if provided) |
| 11 | device_udi | Required, 5-50 characters |
| 12 | delivery_date | Not future, not >180 days old |
| 13 | customer_type | DTC or MS |
| 14 | fall_detection_status | Active/Inactive/Not Applicable/Unknown (if provided) |
| 15 | powersaver_mode | Default/Standard/Battery Saver (case-insensitive, if provided) |
| 16 | is_device_callable | Y or N |

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

### ❌ Error: "Invalid fall_detection_status"
**Fix:** Use `Active`, `Inactive`, `Not Applicable`, or `Unknown` (or leave empty)

### ❌ Error: "Invalid powersaver_mode"
**Fix:** Use `default`, `standard`, or `battery saver` (case-insensitive, or leave empty)

---

## Testing Checklist

Before uploading a CSV file to production:

- [ ] File name matches pattern: `MedicalGuardian_DeviceActivation_YYYYMMDD_Delta.csv`
- [ ] CSV has header row with all 24 field names
- [ ] All required fields are populated (no empty values)
- [ ] Phone numbers are valid 10-digit US numbers
- [ ] Timezones use IANA format (America/New_York, etc.)
- [ ] Delivery dates are within 180-day window
- [ ] Customer types are DTC or MS
- [ ] Partner name is "Medical Guardian"
- [ ] Device UDI is 5-50 characters
- [ ] is_device_callable is Y or N
- [ ] fall_detection_status uses valid values (if provided)
- [ ] powersaver_mode uses valid values: default/standard/battery saver (if provided)
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
