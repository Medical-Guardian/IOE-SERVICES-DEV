# DTC NaN Fix - Deployment Steps

## Quick Start Deployment Guide

**Status**: Ready for deployment
**Estimated Time**: 30 minutes (deployment + initial testing)

---

## Pre-Deployment Checklist

- [x] Code changes implemented in `af_code/af_dtc_logic.py`
- [x] Unit tests created and passing (`test_safe_value_dtc.py`)
- [x] Python syntax validated (no compilation errors)
- [ ] Git commit created with changes
- [ ] Code pushed to main branch
- [ ] Azure CLI authenticated
- [ ] Azure Function App name confirmed: `IOE-function`

---

## Step 1: Commit Changes (5 minutes)

### Check Current Status
```bash
cd /home/zubair-ashfaque/MG-IOE/Azure\ Function/Azure_function_Deployment/IOE-functions
git status
```

**Expected Changes**:
- Modified: `af_code/af_dtc_logic.py`
- Untracked: `test_safe_value_dtc.py`
- Untracked: `DTC_NAN_FIX_IMPLEMENTATION_SUMMARY.md`
- Untracked: `DTC_NAN_FIX_DEPLOYMENT_STEPS.md`

### Stage and Commit Changes
```bash
# Add the main fix
git add af_code/af_dtc_logic.py

# Add test file
git add test_safe_value_dtc.py

# Add documentation
git add DTC_NAN_FIX_IMPLEMENTATION_SUMMARY.md
git add DTC_NAN_FIX_DEPLOYMENT_STEPS.md

# Create commit
git commit -m "Fix DTC staging load NaN-to-SQL error

Add safe_value() utility to convert pandas NaN to None before SQL insertion.
Prevents pymssql serialization error that causes SQL Server error 207
'Invalid column name nan'.

Changes:
- Add safe_value() utility function (lines 663-697)
- Wrap all staging load values with safe_value() (lines 828-870)
- Add NaN conversion monitoring and logging
- Add unit tests (test_safe_value_dtc.py)

Same fix used in Device Activation (commit 0d99f8f).

Fixes: SQL Error 207 during DTC file processing with empty unenrollment_reason"
```

### Push to Repository
```bash
git push origin main
```

**Verification**: Check GitHub/Azure DevOps for commit

---

## Step 2: Run Quality Checks (5 minutes)

### Code Formatting
```bash
black --line-length 100 af_code/af_dtc_logic.py
```

### Linting
```bash
ruff check af_code/af_dtc_logic.py
```

### Type Checking (Optional)
```bash
mypy af_code/af_dtc_logic.py
```

### Security Scan (Optional)
```bash
bandit -r af_code/af_dtc_logic.py
```

**Expected**: All checks should pass (or show existing issues, not new ones)

---

## Step 3: Deploy to Azure (10 minutes)

### Authenticate to Azure
```bash
az login
```

### Deploy Function App
```bash
func azure functionapp publish IOE-function --python
```

**Expected Output**:
```
Getting site publishing info...
Preparing archive...
Uploading content...
Upload completed successfully.
Deployment successful.
Syncing triggers...
Functions in IOE-function:
    ...
```

### Verify Deployment
```bash
az functionapp logs tail --name IOE-function --resource-group <your-resource-group>
```

**Look for**:
```
✅ Successfully registered DTC File Processor blueprint
```

**Deployment Complete**: Azure Function App is now running with the fix

---

## Step 4: Integration Test (10 minutes)

### Option A: Upload Test CSV to Blob Storage

**Create Test File**: `test_dtc_with_nan.csv`
```csv
partner_name,campaign_name_source,language_pref,member_first_name,member_last_name,member_phone_number,enrollment_status,unenrollment_reason
Medical Guardian,MGEngage360_DTC_wellness_check,EN,Maria,Engageuat,+14692783034,enroll,
```

**Upload to Azure**:
```bash
az storage blob upload \
  --account-name <your-storage-account> \
  --container-name fs-dtc/landing \
  --name "TEST_DTC_NaN_$(date +%Y%m%d_%H%M%S).csv" \
  --file test_dtc_with_nan.csv
```

**Monitor Processing**:
```bash
az functionapp logs tail --name IOE-function --resource-group <your-resource-group>
```

**Expected Logs**:
```
[Information] Processing file: TEST_DTC_NaN_20260129_XXXXXX.csv
[Information] Data validation completed: Total rows: 1, Valid rows: 1
[Warning] ⚠️ Converted 1 NaN values to None for SQL compatibility
[Information] Executing bulk insert of 1 records...
[Information] ✅ Staging load successful: 1 records inserted
[Information] Moving file to 'processed' folder
```

**Success Criteria**:
- ✅ No SQL error 207
- ✅ File processed to completion
- ✅ Warning log shows NaN conversion
- ✅ File moved to `processed/` folder

### Option B: Re-process Failed Production File

**Locate Failed File**:
```bash
az storage blob list \
  --account-name <your-storage-account> \
  --container-name fs-dtc/error \
  --query "[?name=='MedicalGuardian_DTCWellness_20260128_Delta.csv']"
```

**Copy to Landing Folder**:
```bash
az storage blob copy start \
  --source-container fs-dtc/error \
  --source-blob MedicalGuardian_DTCWellness_20260128_Delta.csv \
  --account-name <your-storage-account> \
  --destination-container fs-dtc/landing \
  --destination-blob MedicalGuardian_DTCWellness_20260128_Delta_REPROCESS.csv
```

**Monitor Processing** (same as Option A)

**Verify in Database**:
```sql
SELECT TOP 1
    source_filename,
    member_first_name,
    enrollment_status,
    unenrollment_reason,
    processing_status,
    error_message
FROM engage360_stg.stg_dtc_wellness_delta
WHERE source_filename LIKE '%REPROCESS%'
ORDER BY load_timestamp DESC;
```

**Expected Result**:
- `processing_status`: 'PENDING' (not 'ERROR')
- `unenrollment_reason`: NULL (not 'nan')
- `error_message`: NULL (no error)

---

## Step 5: Monitoring (24 hours)

### Application Insights Queries

**Query 1: Check for SQL Error 207**
```kusto
traces
| where timestamp > ago(24h)
| where message contains "Invalid column name 'nan'"
| project timestamp, message, severityLevel
| order by timestamp desc
```

**Expected**: Zero results

**Query 2: Monitor NaN Conversions**
```kusto
traces
| where timestamp > ago(24h)
| where message contains "Converted"
| where message contains "NaN values to None"
| project timestamp, message
| order by timestamp desc
```

**Expected**: Some results (indicates NaN values being handled correctly)

**Query 3: Check DTC File Processing Success**
```kusto
traces
| where timestamp > ago(24h)
| where message contains "Staging load successful"
| summarize count() by bin(timestamp, 1h)
| order by timestamp desc
```

**Expected**: Consistent successful processing

### Database Monitoring

**Query: Recent DTC Staging Errors**
```sql
SELECT TOP 20
    source_filename,
    processing_status,
    error_message,
    load_timestamp,
    member_first_name,
    enrollment_status
FROM engage360_stg.stg_dtc_wellness_delta
WHERE load_timestamp >= DATEADD(hour, -24, GETDATE())
  AND processing_status = 'ERROR'
ORDER BY load_timestamp DESC;
```

**Expected**: Zero rows (or no new error 207 messages)

**Query: NaN Field Distribution**
```sql
SELECT
    COUNT(*) as total_records,
    COUNT(unenrollment_reason) as non_null_unenrollment,
    COUNT(*) - COUNT(unenrollment_reason) as null_unenrollment
FROM engage360_stg.stg_dtc_wellness_delta
WHERE load_timestamp >= DATEADD(hour, -24, GETDATE());
```

**Expected**: Some NULL values (converted from NaN), no 'nan' strings

---

## Verification Checklist

### Immediate (Day 1)

- [ ] Deployment completed successfully
- [ ] Function app registered DTC processor blueprint
- [ ] Test CSV processed without error 207
- [ ] Warning log shows NaN conversion count
- [ ] Test file moved to `processed/` folder
- [ ] Database shows NULL (not 'nan') in unenrollment_reason
- [ ] No new error 207 in Application Insights

### Short-term (Week 1)

- [ ] DTC file processing success rate ≥ 95%
- [ ] No recurring error 207 patterns
- [ ] Average processing time unchanged
- [ ] No unexpected NULL values in other fields
- [ ] NaN conversion warnings at reasonable levels (<10 per file)

### Long-term (Month 1)

- [ ] No rollback required
- [ ] Data quality metrics stable
- [ ] No new related issues reported
- [ ] Fix documented in CLAUDE.md (if needed)

---

## Troubleshooting

### Issue: Deployment Fails

**Error**: `Deployment failed with error`

**Fix**:
1. Check Azure CLI authentication: `az account show`
2. Verify function app name: `az functionapp list --query "[?name=='IOE-function']"`
3. Check resource group permissions
4. Try manual deployment via Azure Portal

### Issue: Still Getting Error 207

**Error**: `Invalid column name 'nan'` still appears

**Possible Causes**:
1. Old code cached - restart function app
2. Deployment didn't complete - redeploy
3. Different file processor affected - check Partner/Device Activation

**Fix**:
```bash
# Restart function app
az functionapp restart --name IOE-function --resource-group <rg>

# Redeploy
func azure functionapp publish IOE-function --python
```

### Issue: NaN Conversion Count Too High

**Warning**: `Converted 1000+ NaN values to None`

**Investigation**:
1. Check CSV file quality - many empty cells?
2. Check validation logic - creating NaN during processing?
3. Review DataFrame operations - are they converting None to NaN?

**Fix**: May need to investigate data quality upstream

### Issue: Valid Values Converted to NULL

**Error**: Expected values showing as NULL in database

**Investigation**:
1. Check safe_value() logic - is it working correctly?
2. Run unit tests again: `python test_safe_value_dtc.py`
3. Check if values were already None/NaN in CSV

**Fix**: May need to adjust validation logic if false positives

---

## Rollback Procedure

### If Critical Issue Occurs

**Decision Criteria**:
- Multiple files failing with new error patterns
- Data integrity issues (valid values becoming NULL)
- Performance degradation >20%
- Unrecoverable errors

**Rollback Steps** (15 minutes):

```bash
# 1. Find commit hash before fix
git log --oneline -5

# 2. Revert the commit
git revert <commit-hash-of-fix>

# 3. Push revert
git push origin main

# 4. Redeploy
func azure functionapp publish IOE-function --python

# 5. Verify rollback
az functionapp logs tail --name IOE-function --resource-group <rg>
```

**Temporary Workaround**:
- Email data team: "Ensure no empty cells in unenrollment_reason column"
- Pre-process CSVs to replace empty cells with 'N/A'
- Manual database cleanup for affected records

---

## Success Metrics

### Target Metrics (24 hours post-deployment)

| Metric | Target | How to Check |
|--------|--------|--------------|
| Error 207 count | 0 | Application Insights |
| DTC success rate | ≥95% | Database staging table |
| Processing time | ±5% baseline | Function execution logs |
| New exceptions | 0 | Application Insights exceptions |
| Data integrity | 100% | Database spot checks |

### Baseline Metrics (Pre-Fix)

| Metric | Baseline |
|--------|----------|
| Error 207 count | 1+ per file with empty unenrollment_reason |
| DTC success rate | ~95% (failures from error 207) |
| Processing time | ~2-5 seconds per file |

---

## Post-Deployment Tasks

### Documentation Updates

- [ ] Update CLAUDE.md with fix reference (if needed)
- [ ] Add to README.md release notes
- [ ] Document in team wiki/knowledge base
- [ ] Share fix with team (email/Slack)

### Follow-up Improvements

- [ ] Consider moving safe_value() to shared utilities
- [ ] Apply same fix to Partner campaign processor (if needed)
- [ ] Add CSV validation for data quality
- [ ] Set up alerts for high NaN conversion counts

---

## Contact & Support

**For Deployment Issues**:
- Azure DevOps: IOE Services project
- IT Operations: Medical Guardian IT team

**For Code Issues**:
- AI-POD Team: Data Science at Medical Guardian
- GitHub Issues: IOE-functions repository

**Emergency Contact**:
- Medical Guardian IT Operations
- On-call AI-POD engineer

---

**Deployment Guide Version**: 1.0
**Last Updated**: 2026-01-29
**Next Review**: Post-deployment (24 hours after deployment)
