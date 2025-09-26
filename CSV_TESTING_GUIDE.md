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
org_id,salesforce_account_number,enrollment_status,language_preference,channel_type,member_first_name,member_last_name,device_udi,device_name,device_phone_clean,is_device_callable_clean,member_address,member_city,member_state,member_zip,member_country,timezone,preferred_contact_method,call_days_of_week,preferred_window
ORG001,123456789,enroll,English,Phone,John,Doe,UDI123456789,Emergency Device,+15551234567,Y,123 Main St,Anytown,CA,90210,USA,America/Los_Angeles,Phone,Monday Tuesday Wednesday,EV1-2
ORG001,987654321,update,Spanish,Email,Maria,Garcia,UDI987654321,Home Device,+15559876543,N,456 Oak Ave,Springfield,IL,62701,USA,America/Chicago,Email,Thursday Friday,EV4-6
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
org_id,salesforce_account_number,enrollment_status,language_preference,channel_type,member_first_name,member_last_name,device_udi,device_name,device_phone_clean,is_device_callable_clean,member_address,member_city,member_state,member_zip,member_country,timezone,preferred_contact_method,call_days_of_week,preferred_window
,123456789,enroll,English,Phone,John,Doe,UDI123456789,Emergency Device,+15551234567,Y,123 Main St,Anytown,CA,90210,USA,America/Los_Angeles,Phone,Monday Tuesday Wednesday,EV1-2
ORG001,,update,Spanish,Email,Maria,Garcia,UDI987654321,Home Device,+15559876543,N,456 Oak Ave,Springfield,IL,62701,USA,America/Chicago,Email,Thursday Friday,EV4-6
ORG001,111111111,invalid_status,InvalidLang,InvalidChannel,,,,,,,,,,,InvalidTZ,InvalidMethod,InvalidDays,InvalidWindow
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
org_id,salesforce_account_number,enrollment_status,language_preference,channel_type,member_first_name,member_last_name,device_udi,device_name,device_phone_clean,is_device_callable_clean,member_address,member_city,member_state,member_zip,member_country,timezone,preferred_contact_method,call_days_of_week,preferred_window
ORG001,123456789,enroll,English,Phone,John,Doe,UDI123456789,Emergency Device,+15551234567,Y,123 Main St,Anytown,CA,90210,USA,America/Los_Angeles,Phone,Monday Tuesday Wednesday Thursday Friday,EV1-2
ORG001,987654321,update,Spanish,Email,Maria,Garcia,UDI987654321,Home Device,+15559876543,N,456 Oak Ave,Springfield,IL,62701,USA,America/Chicago,Email,Monday Wednesday Friday,EV4-6
ORG002,111222333,enroll,English,Phone,Robert,Johnson,UDI111222333,Mobile Device,+15551112222,Y,789 Pine St,Riverside,TX,75001,USA,America/Central,Phone,Tuesday Thursday Saturday,EV2-3
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