# Azure Infrastructure Setup Notes

**Last Updated:** 2025-12-07
**BusinessCaseID:** BC-TBD (Device Activation System)

---

## Overview

This document contains manual setup steps for Azure infrastructure required by the Device Activation system. These steps must be performed by the system administrator before deploying the code.

---

## 1. Azure Blob Storage Container Setup

### Container Name: `fs-device-activation`

### Folder Structure:
```
fs-device-activation/
├── landing/       # CSV files uploaded here (blob trigger location)
├── staging/       # Files being processed
├── processed/     # Successfully processed files
└── error/         # Failed files
```

### Setup Steps:

**Option 1: Azure Portal**
1. Navigate to Azure Storage Account
2. Click "Containers" → "+ Container"
3. Name: `fs-device-activation`
4. Public access level: Private
5. Create the following folders (upload empty placeholder files):
   - `landing/.placeholder`
   - `staging/.placeholder`
   - `processed/.placeholder`
   - `error/.placeholder`

**Option 2: Azure CLI**
```bash
# Set variables
STORAGE_ACCOUNT="<your-storage-account-name>"
CONTAINER_NAME="fs-device-activation"

# Create container
az storage container create \
  --account-name $STORAGE_ACCOUNT \
  --name $CONTAINER_NAME \
  --auth-mode login

# Create folder structure (using zero-byte blob placeholders)
for folder in landing staging processed error; do
  az storage blob upload \
    --account-name $STORAGE_ACCOUNT \
    --container-name $CONTAINER_NAME \
    --name "${folder}/.placeholder" \
    --file /dev/null \
    --auth-mode login
done

# Verify container and folders
az storage blob list \
  --account-name $STORAGE_ACCOUNT \
  --container-name $CONTAINER_NAME \
  --auth-mode login
```

### Verification:
- ✅ Container `fs-device-activation` exists
- ✅ Folders visible: `landing/`, `staging/`, `processed/`, `error/`

---

## 2. Database Campaign Setup

### SQL Script: `database/create_device_activation_campaign.sql`

**Execute this script on Azure SQL Database:**
1. Connect to Azure SQL Database (engage360 database)
2. Run: `database/create_device_activation_campaign.sql`
3. Save the `campaign_id` output for reference

**Expected Output:**
```sql
✅ Device Activation campaign created successfully!

📋 Campaign Details:
-------------------
campaign_id: <UUID>
campaign_name: Device Activation
campaign_type: Device Activation
status: Active
org_id: <Medical Guardian UUID>
operating_tz: America/New_York
timezone_flag: member_tz
operating_start_time: 09:00:00
operating_end_time: 17:00:00
```

**Verification:**
```sql
SELECT campaign_id, campaign_name, campaign_type, status
FROM engage360.campaigns_enhanced
WHERE campaign_name = 'Device Activation';
```

---

## 3. Callback Queue Table Creation

### SQL Script: `database/create_callback_queue_table.sql` (to be created in Phase 6)

**This table will be created later in Phase 6. DO NOT create it yet.**

Schema preview:
```sql
CREATE TABLE engage360.outreach_callback_queue (
    callback_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    enrollment_id UNIQUEIDENTIFIER NOT NULL,
    member_id UNIQUEIDENTIFIER NOT NULL,
    campaign_id UNIQUEIDENTIFIER NOT NULL,
    scheduled_callback_time DATETIMEOFFSET NOT NULL,
    callback_reason VARCHAR(100),
    attempt_count INT DEFAULT 0,
    max_attempts INT DEFAULT 3,
    status VARCHAR(50) DEFAULT 'PENDING',
    ...
);
```

---

## 4. Azure Function App Configuration

### Environment Variables (Required)

Add these to Azure Function App Configuration (or `local.settings.json` for local testing):

```json
{
  "KEY_VAULT_URL": "https://your-keyvault.vault.azure.net/",
  "DB_SECRET_NAME": "SqlConnectionStringIOE",
  "AzureWebJobsStorage": "DefaultEndpointsProtocol=https;...",
  "FUNCTIONS_WORKER_RUNTIME": "python"
}
```

### Azure Key Vault Secrets (Required)

Ensure these secrets exist in Key Vault:
- `SqlConnectionStringIOE` - SQL Server connection string
- `BlandAIkey` - Bland AI API key
- `Blandaitwilio` - Twilio encryption key

---

## 5. Testing Checklist

### After Infrastructure Setup:

- [ ] Blob container `fs-device-activation` created
- [ ] Folder structure created (landing/, staging/, processed/, error/)
- [ ] Database campaign record created (Device Activation)
- [ ] Campaign `campaign_id` saved for reference
- [ ] Environment variables configured in Function App
- [ ] Key Vault secrets verified

### Integration Testing:

- [ ] Upload `SAMPLE_DEVICE_ACTIVATION.csv` to `landing/` folder
- [ ] Verify blob trigger activates
- [ ] Check Application Insights logs for processing
- [ ] Verify file moves to `processed/` folder
- [ ] Check database for member enrollments
- [ ] Verify `activation_start_date` calculation (delivery_date + 2 business days)
- [ ] Verify `campaign_end_date` calculation (activation_start_date + 90 days)

---

## 6. Deployment Verification

### After Code Deployment:

```bash
# Deploy function app
func azure functionapp publish IOE-function --python

# Verify function registration
az functionapp logs tail \
  --name IOE-function \
  --resource-group <resource-group>
```

**Expected Log Output:**
```
✅ Successfully imported device_activation_file_processor
✅ Successfully registered Device Activation file processor
✅ Successfully imported device_activation_scheduler
✅ Successfully registered Device Activation Scheduler
```

---

## 7. Contact & Support

**For Issues:**
- Check Application Insights for error logs
- Review `engage360_stg.file_processing_log` table
- Review `engage360_stg.stg_device_activation_delta` table

**Contact:**
- AI-POD Team - Data Science at Medical Guardian

---

**Notes:**
- All infrastructure setup should be completed BEFORE deploying Phase 5 code
- Save all UUIDs (campaign_id, org_id) for future reference
- Test with sample CSV file before processing production data
- Monitor Application Insights logs during initial testing

---
