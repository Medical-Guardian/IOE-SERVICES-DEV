# Operations Device Activation Campaigns - Deployment Checklist

**Date:** 2025-12-18
**Campaigns:** Device Activation - Medicaid & Device Activation - DTC/MA
**Status:** 🟢 READY FOR DEPLOYMENT

---

## ✅ Completed Items

### 1. Code Implementation
- ✅ **Column Mapping Logic** - `af_code/af_device_activation_logic.py` (lines 776-827)
  - Maps CSV columns with `member_` prefix to staging table columns
  - Handles `powersaver_mode` → `battery_status`
  - Handles `fall_detection` → `fall_detection_status`
  - Adds default `address_country = 'US'`

- ✅ **Blob Trigger Function** - `functions/operations_device_activation_file_processor.py`
  - Monitors `fs-ops/landing` container
  - Validates filename patterns (Medicaid, DTCMA)
  - Extracts campaign ID from filename
  - Delegates to existing device activation logic

- ✅ **Function Registration** - `function_app.py` (lines 96-102)
  - Registered `operations_device_activation_bp`
  - Includes error handling and logging

- ✅ **Scheduler Updates** - `functions/device_activation_scheduler.py`
  - Changed from 30 to 15 minute intervals (line 43)
  - Updated documentation for Operations support

- ✅ **Campaign Closure Scheduler** - `functions/device_activation_campaign_closure.py`
  - Timer trigger: Every hour at :00 minutes (`0 0 * * * *`)
  - HTTP endpoint: `/api/device_activation_campaign_closure`
  - Auto-unenrolls members when 90-day campaign window expires
  - Distributed locking prevents concurrent executions
  - BusinessCaseID: BC-DA-007

- ✅ **Eligibility Service** - `af_code/device_activation_scheduler/services/eligibility_service.py` (lines 93-95)
  - Added `campaign_type = 'Operations'` to SQL WHERE clause
  - Supports both Device Activation and Operations campaigns

---

### 2. Database Configuration

- ✅ **Campaigns Created**
  - Device Activation - Medicaid: `0F69659B-491B-40E2-88C3-ABC7D87385B2`
  - Device Activation - DTC/MA: `BA865458-60F9-4EBB-9FB5-D195B532CF5A`
  - Both have `campaign_type = 'Operations'`
  - Both have `operating_end_time = '17:00:00'` (5 PM)

- ✅ **Bland AI Configurations Added** (manually by user)
  - Both campaigns have configs in `campaign_call_configs_enhanced` table
  - `pathway_id`: `323f8d52-6e30-459c-9f71-e395b3c3ba69`
  - `voice`: `bc97a31e-b0b8-49e5-bcb8-393fcc6a86ea`
  - `webhook`: `https://ioe-function-e2g7e6d4e6hme4ge.eastus2-01.azurewebsites.net/api/bland-ai-webhook`
  - `voicemail_message`: Custom device activation message
  - `config_status`: `active`

- ✅ **member_identifiers Table** - Already exists (no changes needed)

- ✅ **Staging Table** - `ioe_stg.stg_device_activation_delta` (already exists)
  - Includes `monitoring_system_id` column
  - Includes `campaign_parameters` column
  - Ready for Operations campaigns

---

### 3. Azure Infrastructure

- ✅ **Blob Storage Container** - `fs-ops` (already exists)
  - Folders: `landing/`, `processed/`, `error/`
  - Connection: `AzureWebJobsStorage`

---

### 4. Documentation

- ✅ **SQL Scripts**
  - `database/add_salesforce_account_id_to_members.sql`
  - `database/create_operations_device_activation_bland_configs.sql` (updated with actual values)
  - `database/DATABASE_SETUP_INSTRUCTIONS.md`

- ✅ **Reference Documents**
  - `BLAND_AI_CONFIG_STORAGE_REFERENCE.md` (how pathway_id/voice_id are stored)
  - `OPERATIONS_DEVICE_ACTIVATION_DEPLOYMENT_CHECKLIST.md` (this file)

---

## ⏳ Pending Items

### 1. Optional Database Schema Update

**Check if salesforce_account_id column exists:**
```sql
SELECT COLUMN_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe'
  AND TABLE_NAME = 'members'
  AND COLUMN_NAME = 'salesforce_account_id';
```

**If NOT EXISTS, run:**
```bash
# Use Azure Data Studio or SQL Server Management Studio
# File: database/add_salesforce_account_id_to_members.sql
```

**Expected Result:** Column added with index

**If EXISTS:** Skip this step

---

### 2. Deployment to Azure

**Deploy function app:**
```bash
# Login to Azure
az login

# Deploy function
func azure functionapp publish IOE-function --python

# Expected output:
# ✅ Successfully registered Operations Device Activation file processor (Medicaid, DTC/MA)
```

**Verify deployment in Azure Portal:**
1. Navigate to Function App: `IOE-function`
2. Go to Functions → Check for:
   - `operations_device_activation_file_processor` (Blob trigger)
   - `device_activation_scheduler` (Timer trigger: 15 min)
   - `device_activation_campaign_closure` (Timer trigger: hourly)
3. Go to Monitor → Check for successful startup logs

---

### 3. Verify Scheduler is Running

**Check scheduler logs in Application Insights:**
```kusto
traces
| where message contains "DEVICE-ACTIVATION-SCHEDULER"
| where timestamp > ago(30m)
| project timestamp, message, severityLevel
| order by timestamp desc
```

**Expected logs (every 15 minutes):**
- `⏰ [TIMER] Device Activation Scheduler TRIGGERED`
- `🔍 [ELIGIBILITY-SERVICE] Starting member eligibility query...`
- `✅ [TIMER] Device Activation Scheduler COMPLETED`

**Verify campaign closure scheduler:**
```kusto
traces
| where message contains "DA-CLOSURE"
| where timestamp > ago(3h)
| project timestamp, message, severityLevel
| order by timestamp desc
```

**Expected logs (every hour at :00 minutes):**
- `⏰ [DA-CLOSURE] Device Activation Campaign Closure Scheduler TRIGGERED`
- `✅ [DA-CLOSURE] Distributed lock acquired successfully`
- `✅ [DA-CLOSURE] Found X enrollments to close`
- `✅ [DA-CLOSURE] Successfully unenrolled X members`

**Test HTTP endpoint:**
```bash
curl -X GET "https://ioe-function.azurewebsites.net/api/device_activation_campaign_closure?code=<function-key>"

# Expected response:
# {
#   "success": true,
#   "request_id": "da-closure-http-...",
#   "result": {
#     "enrollments_closed": X,
#     "campaigns_affected": ["Device Activation - Medicaid", "Device Activation - DTC/MA"],
#     "members_unenrolled": X
#   }
# }
```

---

### 4. Test with Sample CSV Files

**Create test CSV for Medicaid:**
```csv
partner_name,campaign_name_source,language_pref,salesforce_account_number,salesforce_account_id,member_first_name,member_last_name,member_phone_number,member_timezone,member_dob,member_email,member_address_street,member_address_city,member_address_state,member_address_zip,member_address_country,device_udi,device_name,member_brand,device_phone_number,campaign_parameters,monitoring_system_id,fall_detection,powersaver_mode,enrollment_status,unenrollment_reason
Medical Guardian,Device Activation - Medicaid,English,5743441,0016R00003PVck4QAD,Barbara,McDaniel,+18173137409,CST,1935-12-16,mcdanielbf@gmail.com,4424 Overton Crest St,Fort Worth,TX,76109,USA,457128490,MGMini,Medical Guardian,+17182887685,,a3lR3000000a9XpIAI,False,Standard,enrolled,
```

**Upload to Azure Blob Storage:**
```bash
# Method 1: Azure Portal
# Navigate to Storage Account → fs-ops container → landing folder → Upload

# Method 2: Azure CLI
az storage blob upload \
  --account-name <storage-account> \
  --container-name fs-ops \
  --name "landing/MedicalGuardian_DeviceActivationMedicaid_20251218_DELTA.csv" \
  --file test_medicaid.csv
```

**Expected Result:**
- Blob trigger fires
- File processed successfully
- File moved to `fs-ops/processed/`
- Data in `ioe_stg.stg_device_activation_delta`
- Members upserted in `ioe.members`
- Devices upserted in `ioe.member_devices`
- Enrollments created in `ioe.member_campaign_enrollments_enhanced`

---

### 5. Verify File Processing

**Check Application Insights for processing logs:**
```kusto
traces
| where message contains "OPS-DEVICE-ACTIVATION"
| where timestamp > ago(1h)
| project timestamp, message, severityLevel
| order by timestamp desc
```

**Expected log sequence:**
1. `🔔 [OPS-DEVICE-ACTIVATION] Blob trigger fired for file: ...`
2. `✅ [OPS-DEVICE-ACTIVATION] Filename pattern validated successfully`
3. `📋 [OPS-DEVICE-ACTIVATION] Campaign: Device Activation - Medicaid`
4. `🚀 [OPS-DEVICE-ACTIVATION] Starting file processing...`
5. `✅ [OPS-DEVICE-ACTIVATION] File processing completed successfully`

**Verify staging table:**
```sql
SELECT TOP 10 *
FROM ioe_stg.stg_device_activation_delta
WHERE file_batch_id IN (
    SELECT TOP 1 file_batch_id
    FROM ioe_stg.stg_device_activation_delta
    ORDER BY created_ts DESC
)
ORDER BY created_ts DESC;
```

---

### 6. Verify Scheduler Picks Up Eligible Members

**Check eligibility query results:**
```sql
-- This is the same query the scheduler runs
DECLARE @CurrentUtcTimestamp DATETIMEOFFSET = SYSDATETIMEOFFSET();

SELECT
    e.enrollment_id,
    e.member_id,
    e.campaign_id,
    c.campaign_name,
    m.first_name,
    m.last_name,
    m.primary_phone,
    e.activation_start_date,
    e.campaign_end_date
FROM ioe.member_campaign_enrollments_enhanced e
JOIN ioe.members m ON e.member_id = m.member_id
JOIN ioe.campaigns_enhanced c ON e.campaign_id = c.campaign_id
WHERE
    (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
    AND c.status = 'Active'
    AND e.current_status = 'ENROLLED'
    AND e.device_activated = 0
    AND @CurrentUtcTimestamp >= e.activation_start_date
    AND @CurrentUtcTimestamp <= e.campaign_end_date
    AND c.campaign_id IN (
        '0F69659B-491B-40E2-88C3-ABC7D87385B2',  -- Medicaid
        'BA865458-60F9-4EBB-9FB5-D195B532CF5A'   -- DTC/MA
    );
```

**Expected Result:**
- Returns members enrolled in Operations campaigns
- Members past Day 2 (activation_start_date)
- Members within 90-day window
- No recent attempts in callback queue

---

### 7. Verify Bland AI Batch Submission

**Check batch creation logs:**
```kusto
traces
| where message contains "BATCH-ORCH" or message contains "Bland AI"
| where timestamp > ago(1h)
| project timestamp, message, severityLevel
| order by timestamp desc
```

**Expected log sequence:**
1. `🎯 [BATCH-ORCH] Using Bland AI config: pathway_id=323f8d52-..., voice=bc97a31e-...`
2. `📋 [BATCH-ORCH] Creating batch for X eligible members`
3. `✅ [BATCH-ORCH] Batch submitted successfully: batch_id=...`

**Verify batch in database:**
```sql
SELECT TOP 5
    b.batch_id,
    b.campaign_id,
    c.name AS campaign_name,
    b.batch_status,
    b.total_calls_intended,
    b.vendor_batch_id,
    b.created_ts
FROM ioe.outreach_batches b
JOIN ioe.campaigns_enhanced c ON b.campaign_id = c.campaign_id
WHERE b.campaign_id IN (
    '0F69659B-491B-40E2-88C3-ABC7D87385B2',
    'BA865458-60F9-4EBB-9FB5-D195B532CF5A'
)
ORDER BY b.created_ts DESC;
```

---

### 8. Monitor Webhook Processing

**Check webhook logs:**
```kusto
traces
| where message contains "BLAND-AI-WEBHOOK"
| where timestamp > ago(1h)
| project timestamp, message, severityLevel
| order by timestamp desc
```

**Verify call logs:**
```sql
SELECT TOP 5
    bcl.call_id,
    bcl.batch_id,
    bcl.call_status,
    bcl.from_number,
    bcl.to_number,
    bcl.call_length,
    bcl.price,
    bcl.created_ts
FROM ioe.bland_call_logs bcl
WHERE bcl.batch_id IN (
    SELECT batch_id
    FROM ioe.outreach_batches
    WHERE campaign_id IN (
        '0F69659B-491B-40E2-88C3-ABC7D87385B2',
        'BA865458-60F9-4EBB-9FB5-D195B532CF5A'
    )
)
ORDER BY bcl.created_ts DESC;
```

---

## 🎯 Success Criteria

### File Processing Success
- ✅ CSV uploaded to `fs-ops/landing`
- ✅ Blob trigger fires within 10 seconds
- ✅ File validates successfully (filename pattern, columns)
- ✅ Data inserted into staging table
- ✅ Members and devices upserted
- ✅ Enrollments created with correct campaign_id
- ✅ monitoring_system_id stored in member_identifiers
- ✅ File moved to `fs-ops/processed/`
- ✅ No errors in Application Insights

### Scheduler Success
- ✅ Timer trigger fires every 15 minutes
- ✅ Eligibility query returns Operations campaign members
- ✅ Business hours validation works (9 AM - 5 PM EST)
- ✅ Batch created in `outreach_batches` table
- ✅ Attempts created in `outreach_attempts` table
- ✅ Bland AI batch submitted successfully
- ✅ vendor_batch_id stored in database

### Bland AI Integration Success
- ✅ Batch payload contains correct pathway_id: `323f8d52-6e30-459c-9f71-e395b3c3ba69`
- ✅ Batch payload contains correct voice: `bc97a31e-b0b8-49e5-bcb8-393fcc6a86ea`
- ✅ Webhook URL correct: `https://ioe-function-e2g7e6d4e6hme4ge.eastus2-01.azurewebsites.net/api/bland-ai-webhook`
- ✅ Calls initiated by Bland AI
- ✅ Webhook receives call results
- ✅ Call logs inserted into bland_call_logs
- ✅ Disposition mapped correctly
- ✅ Enrollment status updated based on disposition

---

## 🚀 Deployment Commands

```bash
# 1. Login to Azure
az login

# 2. Navigate to project directory
cd /home/zubair-ashfaque/MG-IOE/Azure\ Function/Azure_function_Deployment/IOE-functions

# 3. Install dependencies (if needed)
pip install -r requirements.txt

# 4. Run quality checks (optional but recommended)
black --line-length 100 af_code/
ruff check af_code/
mypy af_code/

# 5. Deploy to Azure
func azure functionapp publish IOE-function --python

# 6. Verify deployment
az functionapp logs tail --name IOE-function --resource-group <resource-group>
```

---

## 📊 Monitoring Queries

### Check Recent File Processing
```kusto
traces
| where message contains "OPS-DEVICE-ACTIVATION"
| where timestamp > ago(24h)
| summarize count() by tostring(parse_json(message).campaign_name), bin(timestamp, 1h)
| render timechart
```

### Check Scheduler Runs
```kusto
traces
| where message contains "DEVICE-ACTIVATION-SCHEDULER"
| where message contains "TRIGGERED"
| where timestamp > ago(24h)
| summarize count() by bin(timestamp, 15m)
| render timechart
```

### Check Bland AI Batch Submissions
```sql
SELECT
    c.name AS campaign_name,
    COUNT(*) AS batch_count,
    SUM(b.total_calls_intended) AS total_calls,
    AVG(b.total_calls_intended) AS avg_calls_per_batch
FROM ioe.outreach_batches b
JOIN ioe.campaigns_enhanced c ON b.campaign_id = c.campaign_id
WHERE b.campaign_id IN (
    '0F69659B-491B-40E2-88C3-ABC7D87385B2',
    'BA865458-60F9-4EBB-9FB5-D195B532CF5A'
)
AND b.created_ts >= DATEADD(day, -7, SYSDATETIMEOFFSET())
GROUP BY c.name;
```

---

## 🔧 Troubleshooting

### Issue: Blob trigger not firing
**Solution:** Check blob trigger connection string and container permissions

### Issue: File processing fails
**Solution:** Check Application Insights for error logs, verify CSV format matches expected columns

### Issue: Scheduler not creating batches
**Solution:** Verify campaigns are Active, check eligibility query returns members, verify business hours

### Issue: Bland AI submission fails
**Solution:** Verify pathway_id and voice are correct in database, check API key in Key Vault

### Issue: Webhook not receiving calls
**Solution:** Verify webhook URL is accessible from Bland AI, check Azure Function URL includes auth code

---

## 📝 Post-Deployment Checklist

- [ ] Deploy function app to Azure
- [ ] Verify function registered successfully
- [ ] Upload test CSV file for Medicaid
- [ ] Upload test CSV file for DTC/MA
- [ ] Verify files processed successfully
- [ ] Check scheduler runs every 15 minutes
- [ ] Verify Bland AI batches submitted
- [ ] Monitor webhook processing
- [ ] Review Application Insights for errors
- [ ] Verify call logs in database

---

**Ready for Production!** 🎉

All code and database configurations are complete. Follow the deployment steps above to go live.
