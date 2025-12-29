# Device Activation CSV - Required Fields Update

**Date:** 2025-12-29
**Change Type:** Validation Enhancement
**Impact:** CSV files must now include 26 required fields (up from 9)

---

## Summary of Changes

### New Required Fields Added
- **campaign_name_source** - Campaign name from source system
- **monitoring_system_id** - Monitoring system identifier

### Previously Optional Fields Now REQUIRED
The following 17 fields are now mandatory:

1. **salesforce_account_number** - Primary matching key for member records
2. **member_email** - Member's email address (must be valid format)
3. **member_address_street** - Street address
4. **member_address_city** - City
5. **member_address_state** - State (2-letter code)
6. **member_address_zip** - ZIP code
7. **member_address_country** - Country (defaults to 'US' if not provided)
8. **member_dob** - Date of birth (required for activation tracking)
9. **device_name** - Device model name
10. **member_brand** - Member's brand/affiliation
11. **device_phone_number** - Device phone number (must be valid US phone)
12. **fall_detection** - Fall detection setting (true/false, 1/0, yes/no)
13. **powersaver_mode** - Power saving mode (Default/Standard/Battery Saver)
14. **campaign_parameters** - Campaign configuration parameters

---

## Complete List of 26 Required Fields

### Always Required (24 fields)

| # | Field Name | Type | Format/Valid Values | Default Value |
|---|------------|------|---------------------|---------------|
| 1 | partner_name | String | Must be "Medical Guardian" | - |
| 2 | campaign_name_source | String | Any string | - |
| 3 | salesforce_account_id | String | 18-char Salesforce ID (001...) | - |
| 4 | salesforce_account_number | String | Business identifier | - |
| 5 | member_first_name | String | Letters, spaces, apostrophes | - |
| 6 | member_last_name | String | Letters, spaces, apostrophes | - |
| 7 | member_phone_number | String | 10-digit US phone | - |
| 8 | member_email | String | Valid email format | - |
| 9 | member_address_street | String | Street address | - |
| 10 | member_address_city | String | City name | - |
| 11 | member_address_state | String | 2-letter state code (NY, CA, etc.) | - |
| 12 | member_address_zip | String | 5-digit ZIP code | - |
| 13 | member_address_country | String | Country code | 'US' (if empty) |
| 14 | member_dob | Date | YYYY-MM-DD or MM/DD/YYYY | - |
| 15 | member_timezone | String | IANA timezone (America/New_York) | - |
| 16 | language_pref | String | EN, ES, Other | 'EN' (if empty) |
| 17 | device_udi | String | 5-50 characters | - |
| 18 | device_name | String | Device model name | - |
| 19 | member_brand | String | Brand name | - |
| 20 | device_phone_number | String | 10-digit US phone | - |
| 21 | fall_detection | String | true/false, yes/no, 1/0 | - |
| 22 | powersaver_mode | String | Default/Standard/Battery Saver | - |
| 23 | campaign_parameters | String | Any string (config params) | - |
| 24 | monitoring_system_id | String | Monitoring system ID | - |
| 25 | enrollment_status | String | ENROLL/UPDATE/UNENROLL | 'ENROLL' (if empty) |

### Conditionally Required (1 field)

| # | Field Name | Type | Condition | Format |
|---|------------|------|-----------|--------|
| 26 | unenrollment_reason | String | REQUIRED when enrollment_status = 'UNENROLL' | Any string |

---

## Updated CSV Header (27 columns)

```csv
partner_name,campaign_name_source,salesforce_account_id,salesforce_account_number,member_first_name,member_last_name,member_phone_number,member_email,member_address_street,member_address_city,member_address_state,member_address_zip,member_address_country,member_dob,member_timezone,language_pref,device_udi,device_name,member_brand,device_phone_number,fall_detection,powersaver_mode,campaign_parameters,monitoring_system_id,enrollment_status,unenrollment_reason,is_device_callable
```

---

## Validation Error Messages

If any required field is missing, you'll receive specific error messages:

### New Error Messages
- ❌ `salesforce_account_number is required`
- ❌ `campaign_name_source is required`
- ❌ `member_email is required`
- ❌ `member_address_street is required`
- ❌ `member_address_city is required`
- ❌ `member_address_state is required`
- ❌ `member_address_zip is required`
- ❌ `member_dob is required`
- ❌ `device_name is required`
- ❌ `member_brand is required`
- ❌ `device_phone_number is required`
- ❌ `fall_detection is required`
- ❌ `powersaver_mode is required`
- ❌ `campaign_parameters is required`
- ❌ `monitoring_system_id is required`

### Format Validation Errors
- ❌ `Invalid fall_detection value: 'XYZ' (must be true/false, 1/0, yes/no)`
- ❌ `Invalid powersaver_mode: 'XYZ' (must be: Default, Standard, or Battery Saver)`
- ❌ `Invalid email format: 'not-an-email'`
- ❌ `Invalid member_phone_number: '123'`
- ❌ `Invalid device_phone_number: '999'`
- ❌ `Invalid member_dob format: 'ABC' (supported: MM/DD/YYYY, YYYY-MM-DD, DD/MM/YYYY, etc.)`

---

## Migration Guide for Existing CSVs

### Step 1: Add New Required Columns
Add these 2 new columns to your CSV template:
- `campaign_name_source` - Add after `partner_name`
- `monitoring_system_id` - Add after `campaign_parameters`

### Step 2: Populate Previously Optional Fields
Ensure all rows have values for:
- `salesforce_account_number`
- `member_email`
- `member_address_street`, `member_address_city`, `member_address_state`, `member_address_zip`
- `member_dob`
- `device_name`
- `member_brand`
- `device_phone_number`
- `fall_detection`
- `powersaver_mode`
- `campaign_parameters`

### Step 3: Use Correct Formats
- **fall_detection**: Use `1`/`0`, `true`/`false`, or `yes`/`no` (case-insensitive)
- **powersaver_mode**: Use `Default`, `Standard`, or `Battery Saver` (case-insensitive)
- **member_email**: Must be valid email format (user@domain.com)
- **member_dob**: Use `YYYY-MM-DD` or `MM/DD/YYYY`
- **member_phone_number**, **device_phone_number**: 10-digit US phone numbers

### Step 4: Optional Fields with Defaults
These fields can be left empty and will use defaults:
- `member_address_country` → defaults to `'US'`
- `language_pref` → defaults to `'EN'`
- `enrollment_status` → defaults to `'ENROLL'`

---

## Example Valid Row

```csv
Medical Guardian,Device Activation - Medicaid,001ABC123,ACC-123456,John,Doe,5551234567,john.doe@email.com,123 Main St,New York,NY,10001,US,1980-01-15,America/New_York,EN,UDI-123456,MGMini,MedScope,5559876543,1,Standard,test_params,a3lR30000012HU1IAM,ENROLL,,Y
```

**Field-by-field breakdown:**
- partner_name: `Medical Guardian`
- campaign_name_source: `Device Activation - Medicaid`
- salesforce_account_id: `001ABC123`
- salesforce_account_number: `ACC-123456`
- member_first_name: `John`
- member_last_name: `Doe`
- member_phone_number: `5551234567`
- member_email: `john.doe@email.com`
- member_address_street: `123 Main St`
- member_address_city: `New York`
- member_address_state: `NY`
- member_address_zip: `10001`
- member_address_country: `US`
- member_dob: `1980-01-15`
- member_timezone: `America/New_York`
- language_pref: `EN`
- device_udi: `UDI-123456`
- device_name: `MGMini`
- member_brand: `MedScope`
- device_phone_number: `5559876543`
- fall_detection: `1` (true)
- powersaver_mode: `Standard`
- campaign_parameters: `test_params`
- monitoring_system_id: `a3lR30000012HU1IAM`
- enrollment_status: `ENROLL`
- unenrollment_reason: (empty - not unenrolling)
- is_device_callable: `Y`

---

## Impact on File Processing

### ✅ Files with All Required Fields
- Will process successfully
- Will be moved to `fs-device-activation/processed/`

### ❌ Files Missing Required Fields
- Will fail validation
- Will be moved to `fs-device-activation/error/`
- Error details logged in `engage360_stg.stg_device_activation_delta` table
- Specific error messages identify which fields are missing

### Error Threshold
- Default: 10% of rows can fail validation
- If >10% of rows have errors, entire file is rejected
- Example: File with 100 rows must have at least 91 valid rows

---

## Testing Checklist

Before uploading CSV to production:

- [ ] Added `campaign_name_source` column
- [ ] Added `monitoring_system_id` column
- [ ] All 26 required fields populated for every row
- [ ] `salesforce_account_number` not empty
- [ ] `member_email` is valid email format
- [ ] All 5 address fields populated (street, city, state, zip, country)
- [ ] `member_dob` in valid date format
- [ ] `device_name` not empty
- [ ] `member_brand` not empty
- [ ] `device_phone_number` is valid 10-digit phone
- [ ] `fall_detection` uses true/false, yes/no, or 1/0
- [ ] `powersaver_mode` uses Default/Standard/Battery Saver
- [ ] `campaign_parameters` not empty
- [ ] `monitoring_system_id` not empty
- [ ] Test file uploaded to `fs-device-activation/landing/`
- [ ] Verify file moves to `processed/` (not `error/`)

---

## Support

**For Questions or Issues:**
- Review error messages in `engage360_stg.stg_device_activation_delta`
- Check Azure Function logs in Application Insights
- Contact: AI-POD Team - Data Science at Medical Guardian

---

## Code Changes

**Files Modified:**
- `af_code/af_device_activation_logic.py`
  - Updated CSV schema (lines 930-969)
  - Added validation logic (lines 1060-1393)

**Test Files Updated:**
- `tests/test_device_activation_logic.py`
  - Updated fixtures with all required fields

**Git Commit:** Device Activation: Add 26 required field validation

---

**Last Updated:** 2025-12-29
**BusinessCaseID:** BC-TBD (Device Activation System)
