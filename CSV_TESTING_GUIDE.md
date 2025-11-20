# CSV File Processing Testing Guide

## Overview
This guide provides comprehensive testing scenarios for both **Partner Campaign** and **DTC (Direct-to-Consumer)** CSV file processing in the IOE Azure Functions platform.

## Table of Contents
1. [Partner Campaign File Testing](#partner-campaign-file-testing)
2. [DTC File Testing](#dtc-file-testing)
3. [Test Data Preparation](#test-data-preparation)
4. [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)

---

## Partner Campaign File Testing

### File Naming Convention
Partner Campaign files must follow this pattern:
```
PartnerName_CampaignName_YYYYMMDD[_Suffix].csv
```

### Test Scenarios

#### Scenario 1: Valid Partner Campaign File
**File Name**: `MedicalGuardian_WellnessCheck_20241226.csv`

**Test CSV Content**:
```csv
partner_name,campaign_name,salesforce_account_number,enrollment_status,member_email,caregiver_email,healthcare_email,language_preference,channel_type,member_first_name,member_last_name,device_udi,device_name,device_phone_number,is_device_callable,member_address,member_city,member_state,member_zip,member_country
Medical Guardian,Wellness Check Campaign,123456789,enroll,john.doe@email.com,jane.doe@email.com,doctor@clinic.com,English,Email,John,Doe,UDI123456789,Emergency Device,+15551234567,Y,123 Main St,Anytown,CA,90210,USA
Medical Guardian,Wellness Check Campaign,987654321,update,mary.smith@email.com,,,Spanish,Phone,Mary,Smith,UDI987654321,Home Device,+15559876543,N,456 Oak Ave,Springfield,IL,62701,USA
```

**Upload Steps**:
1. Navigate to Azure Storage Account → `fs-partner` container
2. Upload file to `landing/` folder
3. Monitor Azure Function logs

**Expected Logs - Success Path**:
```
[2024-12-26 10:00:01] 🟡 New Partner Campaign file detected: MedicalGuardian_WellnessCheck_20241226.csv
[2024-12-26 10:00:01] 📁 Full blob path: fs-partner/landing/MedicalGuardian_WellnessCheck_20241226.csv
[2024-12-26 10:00:02] 🔐 [PARTNER-LOGIC] Attempting to get Azure Storage connection string from Key Vault...
[2024-12-26 10:00:03] ✅ [PARTNER-LOGIC] Successfully retrieved Azure Storage connection string
[2024-12-26 10:00:04] 📊 [PARTNER-LOGIC] Processing Partner Campaign file: MedicalGuardian_WellnessCheck_20241226.csv
[2024-12-26 10:00:05] 📋 [PARTNER-LOGIC] File validation successful - 2 rows detected
[2024-12-26 10:00:06] 🔍 [PARTNER-LOGIC] Starting comprehensive data validation...
[2024-12-26 10:00:07] ✅ [PARTNER-LOGIC] Data validation passed - 0 errors, 0 warnings
[2024-12-26 10:00:08] 💾 [PARTNER-LOGIC] Starting database operations...
[2024-12-26 10:00:09] ✅ [PARTNER-LOGIC] Database operations completed successfully
[2024-12-26 10:00:10] 📁 [PARTNER-LOGIC] Moving file from landing to processed folder
[2024-12-26 10:00:11] ✅ Partner Campaign file processing completed successfully
[2024-12-26 10:00:11] 📊 Summary: Successfully processed 2 records with 0 errors
[2024-12-26 10:00:11] 📈 Records processed: 2
[2024-12-26 10:00:11] ✅ Records succeeded: 2
[2024-12-26 10:00:11] ❌ Records failed: 0
[2024-12-26 10:00:11] ⏱️ Processing time: 10.45s
```

**Expected File Movement**:
- File moves from `fs-partner/landing/` to `fs-partner/processed/`
- Timestamp suffix added: `MedicalGuardian_WellnessCheck_20241226_processed_20241226100011.csv`

---

#### Scenario 2: Invalid File Name
**File Name**: `InvalidFileName.csv`

**Expected Logs - Validation Failure**:
```
[2024-12-26 10:05:01] 🟡 New Partner Campaign file detected: InvalidFileName.csv
[2024-12-26 10:05:01] 📁 Full blob path: fs-partner/landing/InvalidFileName.csv
[2024-12-26 10:05:01] ⚠️ File skipped due to invalid naming pattern: InvalidFileName.csv
[2024-12-26 10:05:01] Expected pattern: PartnerName_CampaignName_YYYYMMDD[_Suffix].csv
```

**Expected Result**: File remains in landing folder, no processing occurs

---

#### Scenario 3: Data Validation Errors
**File Name**: `MedicalGuardian_TestCampaign_20241226.csv`

**Test CSV Content** (with errors):
```csv
partner_name,campaign_name,salesforce_account_number,enrollment_status,member_email,caregiver_email,healthcare_email,language_preference,channel_type,member_first_name,member_last_name,device_udi,device_name,device_phone_number,is_device_callable,member_address,member_city,member_state,member_zip,member_country
Wrong Partner,Test Campaign,abc123,invalid_status,invalid-email,,,InvalidLang,InvalidChannel,,,,,,,,,,,
Medical Guardian,Test Campaign,,enroll,valid@email.com,,,English,Email,John,Doe,,,,,,,,,
```

**Expected Logs - Validation Errors**:
```
[2024-12-26 10:10:01] 🟡 New Partner Campaign file detected: MedicalGuardian_TestCampaign_20241226.csv
[2024-12-26 10:10:05] 🔍 [PARTNER-LOGIC] Starting comprehensive data validation...
[2024-12-26 10:10:06] ❌ [PARTNER-LOGIC] Validation errors found:
[2024-12-26 10:10:06] Row 1: Invalid partner_name: 'Wrong Partner' (expected 'Medical Guardian')
[2024-12-26 10:10:06] Row 1: salesforce_account_number must be numeric: 'abc123'
[2024-12-26 10:10:06] Row 1: Invalid enrollment_status: 'invalid_status' (must be: ['enroll', 'update', 'unenroll'])
[2024-12-26 10:10:06] Row 1: member_email is not a valid email address
[2024-12-26 10:10:06] Row 2: Missing required salesforce_account_number
[2024-12-26 10:10:07] 💥 [PARTNER-LOGIC] Validation failed - Error threshold exceeded: 25.0% > 15.0%
[2024-12-26 10:10:07] 📁 [PARTNER-LOGIC] Moving file to error folder due to validation failures
[2024-12-26 10:10:08] ❌ Partner Campaign file processing failed
[2024-12-26 10:10:08] 💥 Error: Validation failed with 5 errors (25.0% error rate exceeds 15.0% threshold)
[2024-12-26 10:10:08] 🚫 Validation errors: 5
```

**Expected File Movement**: File moves to `fs-partner/error/` folder

---

## DTC File Testing

### File Naming Convention
DTC files must follow this pattern:
```
DTC_YYYYMMDD[_Suffix].csv
```

### Test Scenarios

#### Scenario 4: Valid DTC File
**File Name**: `DTC_20241226.csv`

**Test CSV Content**:
```csv
org_id,salesforce_account_number,enrollment_status,language_preference,channel_type,member_first_name,member_last_name,member_dob,member_gender,device_udi,device_name,device_phone_clean,is_device_callable_clean,member_address,member_city,member_state,member_zip,member_country,timezone,preferred_contact_method,call_days_of_week,preferred_window
ORG001,123456789,enroll,English,Phone,John,Doe,1965-03-15,M,UDI123456789,Emergency Device,+15551234567,Y,123 Main St,Anytown,CA,90210,USA,America/Los_Angeles,Phone,Monday Tuesday Wednesday,EV1-2
ORG001,987654321,update,Spanish,Email,Maria,Garcia,1970-08-22,F,UDI987654321,Home Device,+15559876543,N,456 Oak Ave,Springfield,IL,62701,USA,America/Chicago,Email,Thursday Friday,EV4-6
```

**Upload Steps**:
1. Navigate to Azure Storage Account → `fs-dtc` container  
2. Upload file to `landing/` folder
3. Monitor Azure Function logs

**Expected Logs - Success Path**:
```
[2024-12-26 11:00:01] 🟡 New DTC file detected: DTC_20241226.csv
[2024-12-26 11:00:01] 📁 Full blob path: fs-dtc/landing/DTC_20241226.csv
[2024-12-26 11:00:02] 🔐 [DTC-LOGIC] Attempting to get Azure Storage connection string from Key Vault...
[2024-12-26 11:00:03] ✅ [DTC-LOGIC] Successfully retrieved Azure Storage connection string
[2024-12-26 11:00:04] 🔍 [DTC-LOGIC] Starting file batch processing with ID: BATCH_20241226110004
[2024-12-26 11:00:05] 📊 [DTC-LOGIC] File validation successful - 2 rows detected
[2024-12-26 11:00:06] 🧹 [DTC-LOGIC] Data cleansing completed - 0 rows removed, 2 rows remain
[2024-12-26 11:00:07] ✅ [DTC-LOGIC] Business validation passed - 0 critical errors
[2024-12-26 11:00:08] 📥 [DTC-LOGIC] Extract phase: Loading 2 records to staging table
[2024-12-26 11:00:09] ✅ [DTC-LOGIC] Extract completed - 2 records staged
[2024-12-26 11:00:10] 🔄 [DTC-LOGIC] Transform phase: Processing member enrollments
[2024-12-26 11:00:11] ✅ [DTC-LOGIC] Transform completed - 2 members processed, 2 devices updated
[2024-12-26 11:00:12] 💾 [DTC-LOGIC] Load phase: Finalizing database operations
[2024-12-26 11:00:13] ✅ [DTC-LOGIC] Load completed successfully
[2024-12-26 11:00:14] 📁 [DTC-LOGIC] Moving file from landing to processed folder
[2024-12-26 11:00:15] ✅ DTC workflow completed successfully. Duration: 14.32s
[2024-12-26 11:00:15] 📊 Summary: Successfully processed 2 records with 0 errors
[2024-12-26 11:00:15] 📈 Records processed: 2
[2024-12-26 11:00:15] ✅ Records succeeded: 2
[2024-12-26 11:00:15] ❌ Records failed: 0
```

**Expected Database Changes**:
- New records in `engage360.dtc_staging_[env]` table
- Updated `engage360.members` table
- Updated `engage360.member_devices` table
- Updated `engage360.member_campaign_enrollments_enhanced` table

---

#### Scenario 5: DTC File with Business Logic Errors
**File Name**: `DTC_20241226_errors.csv`

**Test CSV Content** (with errors):
```csv
org_id,salesforce_account_number,enrollment_status,language_preference,channel_type,member_first_name,member_last_name,member_dob,member_gender,device_udi,device_name,device_phone_clean,is_device_callable_clean,member_address,member_city,member_state,member_zip,member_country,timezone,preferred_contact_method,call_days_of_week,preferred_window
,123456789,enroll,English,Phone,John,Doe,1965-03-15,M,UDI123456789,Emergency Device,+15551234567,Y,123 Main St,Anytown,CA,90210,USA,America/Los_Angeles,Phone,Monday Tuesday Wednesday,EV1-2
ORG001,,update,Spanish,Email,Maria,Garcia,1970-08-22,F,UDI987654321,Home Device,+15559876543,N,456 Oak Ave,Springfield,IL,62701,USA,America/Chicago,Email,Thursday Friday,EV4-6
ORG001,111111111,invalid_status,InvalidLang,InvalidChannel,,,,,,,,,,,,,InvalidTZ,InvalidMethod,InvalidDays,InvalidWindow
```

**Expected Logs - Business Logic Errors**:
```
[2024-12-26 11:05:01] 🟡 New DTC file detected: DTC_20241226_errors.csv
[2024-12-26 11:05:06] 🧹 [DTC-LOGIC] Data cleansing and validation starting...
[2024-12-26 11:05:07] ❌ [DTC-LOGIC] Critical validation errors found:
[2024-12-26 11:05:07] Row 1: Missing required org_id
[2024-12-26 11:05:07] Row 2: Missing required salesforce_account_number
[2024-12-26 11:05:07] Row 3: Invalid enrollment_status: 'invalid_status' (must be: enroll, update, unenroll)
[2024-12-26 11:05:07] Row 3: Invalid language_preference: 'InvalidLang' (must be: English, Spanish)
[2024-12-26 11:05:07] Row 3: Invalid timezone: 'InvalidTZ'
[2024-12-26 11:05:08] 💥 [DTC-LOGIC] Business validation failed - Error threshold exceeded: 33.3% > 15.0%
[2024-12-26 11:05:08] 📁 [DTC-LOGIC] Moving file to error folder due to validation failures
[2024-12-26 11:05:09] ❌ DTC file processing failed
[2024-12-26 11:05:09] 💥 Error: Business validation failed with 5 critical errors (33.3% error rate exceeds 15.0% threshold)
[2024-12-26 11:05:09] 🔍 Error details: Multiple validation failures detected
[2024-12-26 11:05:09] 🚫 Validation errors: 5
```

**Expected File Movement**: File moves to `fs-dtc/error/` folder

---

#### Scenario 6: DTC File with Duplicate Members

**File Name**: `DTC_20241226_duplicate_members.csv`

**Test CSV Content** (with duplicate members):
```csv
org_id,salesforce_account_number,enrollment_status,language_preference,channel_type,member_first_name,member_last_name,member_dob,member_gender,device_udi,device_name,device_phone_clean,is_device_callable_clean,member_address,member_city,member_state,member_zip,member_country,timezone,preferred_contact_method,call_days_of_week,preferred_window
ORG001,123456789,enroll,English,Phone,John,Doe,1965-03-15,M,UDI123456789,Emergency Device,+15551234567,Y,123 Main St,Anytown,CA,90210,USA,America/Los_Angeles,Phone,Monday Tuesday Wednesday,EV1-2
ORG001,123456789,update,English,Phone,John,Doe,1965-03-15,M,UDI999999999,Different Device,+15551234568,Y,123 Main St,Anytown,CA,90210,USA,America/Los_Angeles,Phone,Monday Tuesday Wednesday,EV1-2
ORG001,987654321,enroll,Spanish,Email,Maria,Garcia,1970-08-22,F,UDI987654321,Home Device,+15559876543,N,456 Oak Ave,Springfield,IL,62701,USA,America/Chicago,Email,Thursday Friday,EV4-6
```

**Issue**: Rows 1 and 2 have identical `org_id` + `salesforce_account_number` (ORG001 + 123456789)

**Expected Logs - Duplicate Detection**:
```
[2024-12-26 11:10:01] 🟡 New DTC file detected: DTC_20241226_duplicate_members.csv
[2024-12-26 11:10:04] 📊 [DTC-LOGIC] File validation successful - 3 rows detected
[2024-12-26 11:10:05] 🧹 [DTC-LOGIC] Data cleansing completed - 0 rows removed, 3 rows remain
[2024-12-26 11:10:06] ✅ [DTC-LOGIC] Business validation passed - 0 critical errors
[2024-12-26 11:10:07] 📥 [DTC-LOGIC] Extract phase: Loading 3 records to staging table
[2024-12-26 11:10:08] ✅ [DTC-LOGIC] Extract completed - 3 records staged
[2024-12-26 11:10:09] 🔄 [DTC-LOGIC] Transform phase: Checking for duplicate members...
[2024-12-26 11:10:10] ❌ [DTC-LOGIC] Duplicate members found in staging data:
[2024-12-26 11:10:10] org_id: ORG001, salesforce_account_number: 123456789, count: 2
[2024-12-26 11:10:10] 💥 [DTC-LOGIC] Transform phase failed - Duplicate detection error
[2024-12-26 11:10:11] 📁 [DTC-LOGIC] Moving file to error folder due to duplicate members
[2024-12-26 11:10:12] ❌ DTC file processing failed
[2024-12-26 11:10:12] 💥 Error: Duplicate members found in staging data
[2024-12-26 11:10:12] 🚫 File moved to error folder
```

**Expected Behavior**:
- **NO records loaded** to production tables (fail-fast)
- File moved to `fs-dtc/error/` folder
- All 3 records remain in staging table for investigation
- Transaction rolled back - zero database updates

**Database Verification** (staging records preserved):
```sql
SELECT
    org_id,
    salesforce_account_number,
    processing_status,
    COUNT(*) as count
FROM engage360_stg.stg_dtc_wellness_delta
WHERE file_batch_id = 'BATCH_20241226111007'
GROUP BY org_id, salesforce_account_number, processing_status
ORDER BY count DESC;

-- Expected Result:
-- org_id    | salesforce_account_number | processing_status | count
-- ORG001    | 123456789                 | TRANSFORMING      | 2     ← Duplicate
-- ORG001    | 987654321                 | TRANSFORMING      | 1     ← Valid
```

---

#### Scenario 7: DTC File with Duplicate Update Enrollments

**File Name**: `DTC_20241226_duplicate_updates.csv`

**Test CSV Content** (with duplicate UPDATE records):
```csv
org_id,salesforce_account_number,enrollment_status,preferred_window
ORG001,123456789,UPDATE,EV1-2
ORG001,123456789,UPDATE,EV4-6
```

**Issue**: Same member (ORG001 + 123456789) has two UPDATE records with conflicting preferred_window

**Expected Logs - Duplicate Update Detection**:
```
[2024-12-26 11:15:01] 🟡 New DTC file detected: DTC_20241226_duplicate_updates.csv
[2024-12-26 11:15:07] 📥 [DTC-LOGIC] Extract phase: Loading 2 records to staging table
[2024-12-26 11:15:08] ✅ [DTC-LOGIC] Extract completed - 2 records staged
[2024-12-26 11:15:09] 🔄 [DTC-LOGIC] Transform phase: Processing member enrollments
[2024-12-26 11:15:10] 🔍 [DTC-LOGIC] Checking for duplicate update enrollments first
[2024-12-26 11:15:11] ❌ [DTC-LOGIC] Duplicate update enrollments found in staging data:
[2024-12-26 11:15:11] member_id: m12345, count: 2
[2024-12-26 11:15:11] 💥 [DTC-LOGIC] Transform phase failed - Duplicate update enrollment error
[2024-12-26 11:15:12] 📁 [DTC-LOGIC] Moving file to error folder
[2024-12-26 11:15:13] ❌ DTC file processing failed
[2024-12-26 11:15:13] 💥 Error: Duplicate update enrollments found in staging data
```

**Expected Behavior**:
- NO enrollment updates applied
- File moved to `fs-dtc/error/` folder
- Prevents conflicting updates to same member

---

#### Scenario 8: DTC File with Duplicate Devices

**File Name**: `DTC_20241226_duplicate_devices.csv`

**Test CSV Content** (with duplicate device_udi):
```csv
org_id,salesforce_account_number,enrollment_status,device_udi,device_phone_clean,is_device_callable_clean
ORG001,123456789,enroll,DEVICE-12345,+15551234567,Y
ORG002,987654321,enroll,DEVICE-12345,+15559876543,Y
```

**Issue**: Same device_udi (DEVICE-12345) assigned to two different members

**Expected Logs - Duplicate Device Detection**:
```
[2024-12-26 11:20:01] 🟡 New DTC file detected: DTC_20241226_duplicate_devices.csv
[2024-12-26 11:20:07] 📥 [DTC-LOGIC] Extract phase: Loading 2 records to staging table
[2024-12-26 11:20:08] ✅ [DTC-LOGIC] Extract completed - 2 records staged
[2024-12-26 11:20:09] 🔄 [DTC-LOGIC] Transform phase: Processing devices
[2024-12-26 11:20:10] 🔍 [DTC-LOGIC] Checking for duplicate devices...
[2024-12-26 11:20:11] ❌ [DTC-LOGIC] Duplicate devices found in staging data:
[2024-12-26 11:20:11] device_udi: DEVICE-12345, count: 2
[2024-12-26 11:20:11] 💥 [DTC-LOGIC] Transform phase failed - Duplicate device error
[2024-12-26 11:20:12] 📁 [DTC-LOGIC] Moving file to error folder
[2024-12-26 11:20:13] ❌ DTC file processing failed
[2024-12-26 11:20:13] 💥 Error: Duplicate devices found in staging data
```

**Expected Behavior**:
- NO device records created
- File moved to `fs-dtc/error/` folder
- Prevents device from being assigned to multiple members

---

### Duplicate Testing Summary

| Duplicate Type | Detection Key | Test Scenario | Expected Outcome |
|---------------|---------------|---------------|------------------|
| **Member Duplicates** | `(org_id, salesforce_account_number)` | Scenario 6 | Entire file fails, moves to error/ |
| **Update Enrollment Duplicates** | `member_id` (for UPDATE status) | Scenario 7 | Entire file fails, moves to error/ |
| **Device Duplicates** | `device_udi` | Scenario 8 | Entire file fails, moves to error/ |

**Critical Behavior for All Duplicate Types**:
- ✅ Duplicates detected in Step 4 (TRANSFORM_AND_LOAD_CORE)
- ❌ **NO partial loading** - All-or-nothing processing
- ❌ **NO records written** to production tables
- ✅ Records remain in staging table for investigation
- ✅ File moved to `error/` folder
- ✅ Detailed error logged to `file_processing_log`

---

## Test Data Preparation

### Required Test Files

#### 1. Valid Partner Campaign Test File
```bash
# Create valid test file
cat > MedicalGuardian_TestCampaign_20241226.csv << 'EOF'
partner_name,campaign_name,salesforce_account_number,enrollment_status,member_email,caregiver_email,healthcare_email,language_preference,channel_type,member_first_name,member_last_name,device_udi,device_name,device_phone_number,is_device_callable,member_address,member_city,member_state,member_zip,member_country
Medical Guardian,Test Campaign,123456789,enroll,john.doe@email.com,jane.doe@email.com,doctor@clinic.com,English,Email,John,Doe,UDI123456789,Emergency Device,+15551234567,Y,123 Main St,Anytown,CA,90210,USA
Medical Guardian,Test Campaign,987654321,update,mary.smith@email.com,bob.smith@email.com,,Spanish,Phone,Mary,Smith,UDI987654321,Home Device,+15559876543,N,456 Oak Ave,Springfield,IL,62701,USA
Medical Guardian,Test Campaign,555666777,unenroll,inactive@email.com,,,English,Email,Jane,Inactive,,,,,,,,,
EOF
```

#### 2. Valid DTC Test File
```bash
# Create valid DTC test file
cat > DTC_20241226.csv << 'EOF'
org_id,salesforce_account_number,enrollment_status,language_preference,channel_type,member_first_name,member_last_name,member_dob,member_gender,device_udi,device_name,device_phone_clean,is_device_callable_clean,member_address,member_city,member_state,member_zip,member_country,timezone,preferred_contact_method,call_days_of_week,preferred_window
ORG001,123456789,enroll,English,Phone,John,Doe,1965-03-15,M,UDI123456789,Emergency Device,+15551234567,Y,123 Main St,Anytown,CA,90210,USA,America/Los_Angeles,Phone,Monday Tuesday Wednesday Thursday Friday,EV1-2
ORG001,987654321,update,Spanish,Email,Maria,Garcia,1970-08-22,F,UDI987654321,Home Device,+15559876543,N,456 Oak Ave,Springfield,IL,62701,USA,America/Chicago,Email,Monday Wednesday Friday,EV4-6
ORG002,111222333,enroll,English,Phone,Robert,Johnson,1980-11-05,,UDI111222333,Mobile Device,+15551112222,Y,789 Pine St,Riverside,TX,75001,USA,America/Central,Phone,Tuesday Thursday Saturday,EV2-3
EOF
```

#### 3. Error Test Files
```bash
# Create invalid partner file (wrong naming)
cat > InvalidPartnerFile.csv << 'EOF'
partner_name,campaign_name
Medical Guardian,Test
EOF

# Create partner file with validation errors
cat > MedicalGuardian_ErrorTest_20241226.csv << 'EOF'
partner_name,campaign_name,salesforce_account_number,enrollment_status,member_email
Wrong Partner,Test Campaign,abc123,invalid_status,invalid-email
Medical Guardian,Test Campaign,,enroll,
EOF

# Create DTC file with validation errors
cat > DTC_20241226_errors.csv << 'EOF'
org_id,salesforce_account_number,enrollment_status,language_preference,timezone
,123456789,enroll,English,America/Los_Angeles
ORG001,,invalid_status,InvalidLang,InvalidTZ
EOF
```

#### 4. Duplicate Detection Test Files

```bash
# Test File 1: Duplicate Members
cat > DTC_20241226_duplicate_members.csv << 'EOF'
org_id,salesforce_account_number,enrollment_status,language_preference,channel_type,member_first_name,member_last_name,member_dob,member_gender,device_udi,device_name,device_phone_clean,is_device_callable_clean,member_address,member_city,member_state,member_zip,member_country,timezone,preferred_contact_method,call_days_of_week,preferred_window
ORG001,123456789,enroll,English,Phone,John,Doe,1965-03-15,M,UDI123456789,Emergency Device,+15551234567,Y,123 Main St,Anytown,CA,90210,USA,America/Los_Angeles,Phone,Monday Tuesday Wednesday,EV1-2
ORG001,123456789,update,English,Phone,John,Doe,1965-03-15,M,UDI999999999,Different Device,+15551234568,Y,123 Main St,Anytown,CA,90210,USA,America/Los_Angeles,Phone,Monday Tuesday Wednesday,EV1-2
ORG001,987654321,enroll,Spanish,Email,Maria,Garcia,1970-08-22,F,UDI987654321,Home Device,+15559876543,N,456 Oak Ave,Springfield,IL,62701,USA,America/Chicago,Email,Thursday Friday,EV4-6
EOF

# Test File 2: Duplicate Update Enrollments
cat > DTC_20241226_duplicate_updates.csv << 'EOF'
org_id,salesforce_account_number,enrollment_status,language_preference,channel_type,member_first_name,member_last_name,member_dob,member_gender,device_udi,device_name,device_phone_clean,is_device_callable_clean,member_address,member_city,member_state,member_zip,member_country,timezone,preferred_contact_method,call_days_of_week,preferred_window
ORG001,123456789,UPDATE,English,Phone,John,Doe,1965-03-15,M,UDI123456789,Emergency Device,+15551234567,Y,123 Main St,Anytown,CA,90210,USA,America/Los_Angeles,Phone,Monday Tuesday Wednesday,EV1-2
ORG001,123456789,UPDATE,English,Phone,John,Doe,1965-03-15,M,UDI999999999,Different Device,+15551234568,Y,123 Main St,Anytown,CA,90210,USA,America/Los_Angeles,Phone,Thursday Friday,EV4-6
EOF

# Test File 3: Duplicate Devices
cat > DTC_20241226_duplicate_devices.csv << 'EOF'
org_id,salesforce_account_number,enrollment_status,language_preference,channel_type,member_first_name,member_last_name,member_dob,member_gender,device_udi,device_name,device_phone_clean,is_device_callable_clean,member_address,member_city,member_state,member_zip,member_country,timezone,preferred_contact_method,call_days_of_week,preferred_window
ORG001,123456789,enroll,English,Phone,John,Doe,1965-03-15,M,DEVICE-12345,Emergency Device,+15551234567,Y,123 Main St,Anytown,CA,90210,USA,America/Los_Angeles,Phone,Monday Tuesday Wednesday,EV1-2
ORG002,987654321,enroll,Spanish,Email,Maria,Garcia,1970-08-22,F,DEVICE-12345,Home Device,+15559876543,Y,456 Oak Ave,Springfield,IL,62701,USA,America/Chicago,Email,Thursday Friday,EV4-6
EOF
```

---

### DTC CSV Field Reference

#### New Optional Fields

**member_gender** (Added: 2025-11-07, Updated: 2025-11-10)
- **Type**: String (optional)
- **Accepted Values**:
  - `M` or `Male` → Stored as "M" (CHAR 1)
  - `F` or `Female` → Stored as "F" (CHAR 1)
  - Any other value → Stored as NULL (production constraint: only M, F, NULL allowed)
  - Empty/blank → Stored as NULL (no error)
- **Validation**: No validation errors if missing or empty
- **Location in CSV**: After `member_dob`, before `member_email`
- **Database**: Stored in `engage360.members.gender` (CHAR 1 with CHECK constraint)
- **Constraint**: Production table allows only 'M', 'F', or NULL
- **Behavior**:
  - If provided in CSV, value is standardized (M/F) or mapped to NULL
  - If not provided, field remains NULL (no error thrown)
  - On updates, uses `ISNULL()` to preserve existing value if new CSV doesn't provide it
  - Values like "Other", "Non-binary" are stored as NULL for database compatibility

**Example with gender**:
```csv
member_first_name,member_last_name,member_dob,member_gender
John,Doe,1965-03-15,M
Jane,Smith,1970-08-22,Female
```

**Example without gender (valid)**:
```csv
member_first_name,member_last_name,member_dob
John,Doe,1965-03-15
Jane,Smith,1970-08-22
```

Both examples above are valid. The gender field is completely optional.

---

## Monitoring and Troubleshooting

### Azure Function Logs Access

#### Method 1: Azure Portal
1. Navigate to Azure Portal → Function App → Your Function
2. Go to **Functions** → Select function (e.g., `ProcessPartnerCampaignBlobValidationUI`)
3. Click **Monitor** → **Logs**
4. View real-time logs during file upload

#### Method 2: Log Stream
1. In Function App → **Log stream**
2. Real-time monitoring of all function executions

#### Method 3: Application Insights
1. Navigate to **Application Insights** linked to your Function App
2. Go to **Logs** → Run KQL queries:

```kql
// View all Partner Campaign processing logs
traces
| where message contains "Partner Campaign"
| order by timestamp desc
| take 50

// View DTC processing logs
traces  
| where message contains "DTC"
| order by timestamp desc
| take 50

// View error logs only
traces
| where severityLevel >= 3
| order by timestamp desc
| take 20
```

### Database Verification Queries

#### Check Staging Data
```sql
-- Check DTC staging data
SELECT TOP 10 *
FROM engage360.dtc_staging_dev
ORDER BY created_ts DESC;

-- Check processing status
SELECT processing_status, COUNT(*) as count
FROM engage360.dtc_staging_dev
WHERE file_batch_id = 'BATCH_20241226110004'
GROUP BY processing_status;
```

#### Investigate Duplicate Errors

When a file fails due to duplicates, use these queries to investigate:

**1. Find Member Duplicates in Staging**:
```sql
SELECT
    org_id,
    LTRIM(RTRIM(salesforce_account_number)) AS salesforce_account_number,
    COUNT(*) as duplicate_count,
    STRING_AGG(CAST(row_number AS VARCHAR), ', ') as row_numbers
FROM engage360_stg.stg_dtc_wellness_delta
WHERE file_batch_id = 'YOUR-FILE-BATCH-ID'
  AND processing_status = 'TRANSFORMING'
  AND org_id IS NOT NULL
  AND salesforce_account_number IS NOT NULL
GROUP BY org_id, LTRIM(RTRIM(salesforce_account_number))
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;
```

**2. Find Update Enrollment Duplicates**:
```sql
SELECT
    m.member_id,
    stg.org_id,
    stg.salesforce_account_number,
    COUNT(*) as duplicate_count,
    STRING_AGG(stg.preferred_window, ', ') as conflicting_windows
FROM engage360_stg.stg_dtc_wellness_delta stg
JOIN engage360.members m
    ON m.org_id = stg.org_id
    AND m.salesforce_account_number = stg.salesforce_account_number
WHERE stg.file_batch_id = 'YOUR-FILE-BATCH-ID'
  AND stg.processing_status = 'TRANSFORMING'
  AND UPPER(LTRIM(RTRIM(stg.enrollment_status))) = 'UPDATE'
GROUP BY m.member_id, stg.org_id, stg.salesforce_account_number
HAVING COUNT(*) > 1;
```

**3. Find Device Duplicates**:
```sql
SELECT
    stg.device_udi,
    COUNT(*) as duplicate_count,
    STRING_AGG(stg.salesforce_account_number, ', ') as assigned_to_members,
    STRING_AGG(stg.device_phone_clean, ', ') as phone_numbers
FROM engage360_stg.stg_dtc_wellness_delta stg
WHERE stg.file_batch_id = 'YOUR-FILE-BATCH-ID'
  AND stg.processing_status = 'TRANSFORMING'
  AND stg.device_udi IS NOT NULL
  AND LTRIM(RTRIM(stg.device_udi)) != ''
GROUP BY stg.device_udi
HAVING COUNT(*) > 1;
```

**4. Check File Processing Log for Duplicate Errors**:
```sql
SELECT
    file_batch_id,
    file_name,
    processing_status,
    final_error_message,
    processing_start_ts,
    processing_end_ts,
    DATEDIFF(SECOND, processing_start_ts, processing_end_ts) as duration_seconds
FROM engage360_stg.file_processing_log
WHERE final_error_message LIKE '%Duplicate%'
  OR file_name LIKE '%YOUR-FILE-NAME%'
ORDER BY processing_start_ts DESC;
```

**5. View All Records from Failed Batch**:
```sql
SELECT
    row_number,
    org_id,
    salesforce_account_number,
    enrollment_status,
    device_udi,
    processing_status,
    error_message
FROM engage360_stg.stg_dtc_wellness_delta
WHERE file_batch_id = 'YOUR-FILE-BATCH-ID'
ORDER BY row_number;
```

#### Check Member Updates
```sql
-- Verify member enrollments
SELECT TOP 10 
    m.salesforce_account_number,
    mce.current_status,
    mce.preferred_window,
    mce.updated_ts
FROM engage360.members m
JOIN engage360.member_campaign_enrollments_enhanced mce ON m.member_id = mce.member_id
ORDER BY mce.updated_ts DESC;

-- Check device updates
SELECT TOP 10
    md.device_id,
    md.member_id, 
    md.device_phone_number,
    md.is_device_callable,
    md.updated_ts
FROM engage360.member_devices md
ORDER BY md.updated_ts DESC;
```

### Common Error Scenarios and Solutions

#### Error 1: File Not Processing
**Symptoms**: File uploaded but no logs appear

**Possible Causes**:
- Incorrect file naming pattern
- File not uploaded to correct container/folder
- Azure Function not running

**Debugging Steps**:
```bash
# Check file location
az storage blob list --container-name fs-partner --prefix landing/ --account-name [storage-account]

# Check function status
az functionapp show --name [function-app] --resource-group [rg] --query state
```

#### Error 2: Database Connection Issues
**Symptoms**: Logs show "Database error" or "Connection failed"

**Expected Log Pattern**:
```
💥 [DatabaseService] Database error: Login failed for user 'xyz'
💥 [DatabaseService] Failed to fetch/parse connection string: Secret 'DatabaseConnectionString' is empty
```

**Debugging Steps**:
1. Verify Key Vault secrets exist and are accessible
2. Check Function App identity permissions
3. Validate connection string format

#### Error 3: Validation Threshold Exceeded
**Symptoms**: File moves to error folder with validation messages

**Expected Log Pattern**:
```
💥 [PARTNER-LOGIC] Validation failed - Error threshold exceeded: 25.0% > 15.0%
🚫 Validation errors: 5
```

**Solution**: Review data quality or adjust error threshold in code

### Performance Benchmarks

#### Expected Processing Times
- **Small files** (1-100 records): 5-15 seconds
- **Medium files** (101-1000 records): 15-60 seconds  
- **Large files** (1001-5000 records): 1-5 minutes

#### Memory and Resource Usage
- **Memory**: 512MB-1GB depending on file size
- **CPU**: Scales automatically with Azure Functions consumption plan
- **Database connections**: Pool managed automatically

### Test Automation Script

```bash
#!/bin/bash
# CSV Testing Automation Script

echo "🚀 Starting CSV Processing Tests..."

# Set variables
STORAGE_ACCOUNT="your-storage-account"
PARTNER_CONTAINER="fs-partner"
DTC_CONTAINER="fs-dtc"

# Test 1: Valid Partner File
echo "Test 1: Uploading valid partner file..."
az storage blob upload \
    --file MedicalGuardian_TestCampaign_20241226.csv \
    --container-name $PARTNER_CONTAINER \
    --name landing/MedicalGuardian_TestCampaign_20241226.csv \
    --account-name $STORAGE_ACCOUNT

sleep 30  # Wait for processing

# Test 2: Valid DTC File  
echo "Test 2: Uploading valid DTC file..."
az storage blob upload \
    --file DTC_20241226.csv \
    --container-name $DTC_CONTAINER \
    --name landing/DTC_20241226.csv \
    --account-name $STORAGE_ACCOUNT

sleep 30  # Wait for processing

# Test 3: Error Files
echo "Test 3: Uploading error test files..."
az storage blob upload \
    --file MedicalGuardian_ErrorTest_20241226.csv \
    --container-name $PARTNER_CONTAINER \
    --name landing/MedicalGuardian_ErrorTest_20241226.csv \
    --account-name $STORAGE_ACCOUNT

echo "✅ All test files uploaded. Monitor Azure Function logs for results."
```

---

## Summary

This testing guide provides:
- **8 comprehensive test scenarios** covering success and error cases
- **Detailed expected logs** for each scenario 
- **Step-by-step testing procedures**
- **Database verification queries**
- **Troubleshooting guidance**
- **Performance benchmarks**
- **Automation scripts**

Use this guide to systematically test CSV file processing and verify that all business logic, error handling, and data validation is working correctly in your IOE Azure Functions platform.