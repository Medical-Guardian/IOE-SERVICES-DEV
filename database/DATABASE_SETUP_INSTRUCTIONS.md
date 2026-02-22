# Database Setup Instructions - Operations Device Activation Campaigns

**Date:** 2025-12-18
**Campaigns:** Device Activation - Medicaid, Device Activation - DTC/MA
**Campaign Type:** Operations

---

## Quick Summary

You need to run **2 SQL scripts** to set up the database for Operations Device Activation campaigns:

1. ✅ **Add salesforce_account_id column** to members table (conditional - may already exist)
2. ✅ **Create Bland AI configurations** for both campaigns (requires pathway_id and voice_id from Bland AI)

---

## Pre-Requisites

### Before Running Any Scripts

1. **Get Bland AI Configuration Values**
   - Log into Bland AI dashboard
   - Find the pathway_id for:
     - Device Activation - Medicaid campaign
     - Device Activation - DTC/MA campaign
   - Find the voice_id (e.g., "maya", "grace", "ryan", etc.)

2. **Verify Azure SQL Database Connection**
   - Connect to: Azure SQL Database (ioe schema)
   - Ensure you have ALTER TABLE and INSERT permissions

---

## Script 1: Add salesforce_account_id Column

**File:** `database/add_salesforce_account_id_to_members.sql`

### What This Does
- Adds a new column `salesforce_account_id` to the `ioe.members` table
- Creates an index for efficient lookups
- This column stores the Salesforce Account ID from your CSV files

### Steps to Run

#### Step 1: Check if Column Already Exists

Run this query first:

```sql
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe'
  AND TABLE_NAME = 'members'
  AND COLUMN_NAME = 'salesforce_account_id';
```

**Expected Results:**
- **If 0 rows returned:** Column does NOT exist → Proceed to Step 2
- **If 1 row returned:** Column ALREADY exists → Skip to Script 2

---

#### Step 2: Add the Column (Only if Step 1 returned 0 rows)

Run the full script:

```sql
-- Add salesforce_account_id column
ALTER TABLE ioe.members
ADD salesforce_account_id NVARCHAR(50) NULL;

GO

-- Create index
CREATE NONCLUSTERED INDEX IX_members_salesforce_account_id
ON ioe.members (salesforce_account_id)
WHERE salesforce_account_id IS NOT NULL;

GO
```

---

#### Step 3: Verify Success

Run this verification query:

```sql
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe'
  AND TABLE_NAME = 'members'
  AND COLUMN_NAME = 'salesforce_account_id';
```

**Expected Output:**
```
COLUMN_NAME              DATA_TYPE    CHARACTER_MAXIMUM_LENGTH    IS_NULLABLE
salesforce_account_id    nvarchar     50                          YES
```

✅ **Success!** Column created successfully.

---

## Script 2: Create Bland AI Configurations

**File:** `database/create_operations_device_activation_bland_configs.sql`

### What This Does
- Creates Bland AI configuration records for both Operations campaigns
- Stores pathway_id, voice_id, webhook URL, and other AI parameters

### Steps to Run

#### Step 1: Verify Campaigns Exist

Run this query:

```sql
SELECT campaign_id, name, campaign_type, operating_start_time, operating_end_time, timezone_flag, status
FROM ioe.campaigns_enhanced
WHERE campaign_id IN (
    '0F69659B-491B-40E2-88C3-ABC7D87385B2',  -- Device Activation - Medicaid
    'BA865458-60F9-4EBB-9FB5-D195B532CF5A'   -- Device Activation - DTC/MA
);
```

**Expected Output:** 2 rows

**Verify:**
- ✅ campaign_type = 'Operations'
- ✅ operating_start_time = '09:00:00'
- ✅ operating_end_time = '17:00:00' (5 PM)
- ✅ timezone_flag = 'member_tz'
- ✅ status = 'Active'

---

#### Step 2: Check if Bland AI Configs Already Exist

Run this query:

```sql
SELECT
    cc.config_id,
    cc.campaign_id,
    c.name AS campaign_name,
    cc.config_status,
    cc.created_ts
FROM ioe.campaign_call_configs_enhanced cc
JOIN ioe.campaigns_enhanced c ON cc.campaign_id = c.campaign_id
WHERE cc.campaign_id IN (
    '0F69659B-491B-40E2-88C3-ABC7D87385B2',
    'BA865458-60F9-4EBB-9FB5-D195B532CF5A'
);
```

**Expected Results:**
- **If 0 rows returned:** Configs do NOT exist → Proceed to Step 3 (INSERT)
- **If 2 rows returned:** Configs ALREADY exist → Use Step 4 (UPDATE) instead

---

#### Step 3: Insert Bland AI Configs (Only if Step 2 returned 0 rows)

**IMPORTANT:** Before running, replace these placeholders in the script:
- `TODO_DEVICE_ACTIVATION_MEDICAID_PATHWAY` → Your actual Medicaid pathway_id
- `TODO_DEVICE_ACTIVATION_DTCMA_PATHWAY` → Your actual DTC/MA pathway_id
- `TODO_GRACE_VOICE_ID` → Your actual voice_id (e.g., "maya", "grace")

Then run:

```sql
-- Insert config for Device Activation - Medicaid
INSERT INTO ioe.campaign_call_configs_enhanced (
    config_id,
    campaign_id,
    bland_parameters_global,
    config_status,
    created_ts
) VALUES (
    NEWID(),
    '0F69659B-491B-40E2-88C3-ABC7D87385B2',
    '{
        "pathway_id": "YOUR_ACTUAL_MEDICAID_PATHWAY_ID",
        "voice_id": "YOUR_ACTUAL_VOICE_ID",
        "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
        "max_duration": "600",
        "wait_for_greeting": true,
        "record": true,
        "voicemail_action": "hangup",
        "interruption_threshold": 100,
        "temperature": 0.7,
        "language": "en"
    }',
    'active',
    SYSDATETIMEOFFSET()
);

-- Insert config for Device Activation - DTC/MA
INSERT INTO ioe.campaign_call_configs_enhanced (
    config_id,
    campaign_id,
    bland_parameters_global,
    config_status,
    created_ts
) VALUES (
    NEWID(),
    'BA865458-60F9-4EBB-9FB5-D195B532CF5A',
    '{
        "pathway_id": "YOUR_ACTUAL_DTCMA_PATHWAY_ID",
        "voice_id": "YOUR_ACTUAL_VOICE_ID",
        "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
        "max_duration": "600",
        "wait_for_greeting": true,
        "record": true,
        "voicemail_action": "hangup",
        "interruption_threshold": 100,
        "temperature": 0.7,
        "language": "en"
    }',
    'active',
    SYSDATETIMEOFFSET()
);
```

---

#### Step 4: Alternative - Update Existing Configs (If Step 2 returned 2 rows)

If configs already exist, UPDATE them instead:

```sql
UPDATE ioe.campaign_call_configs_enhanced
SET
    bland_parameters_global = '{
        "pathway_id": "YOUR_ACTUAL_MEDICAID_PATHWAY_ID",
        "voice_id": "YOUR_ACTUAL_VOICE_ID",
        "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
        "max_duration": "600",
        "wait_for_greeting": true,
        "record": true,
        "voicemail_action": "hangup",
        "interruption_threshold": 100,
        "temperature": 0.7,
        "language": "en"
    }',
    config_status = 'active',
    updated_ts = SYSDATETIMEOFFSET()
WHERE campaign_id = '0F69659B-491B-40E2-88C3-ABC7D87385B2';

UPDATE ioe.campaign_call_configs_enhanced
SET
    bland_parameters_global = '{
        "pathway_id": "YOUR_ACTUAL_DTCMA_PATHWAY_ID",
        "voice_id": "YOUR_ACTUAL_VOICE_ID",
        "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
        "max_duration": "600",
        "wait_for_greeting": true,
        "record": true,
        "voicemail_action": "hangup",
        "interruption_threshold": 100,
        "temperature": 0.7,
        "language": "en"
    }',
    config_status = 'active',
    updated_ts = SYSDATETIMEOFFSET()
WHERE campaign_id = 'BA865458-60F9-4EBB-9FB5-D195B532CF5A';
```

---

#### Step 5: Verify Configs Created Successfully

Run this verification query:

```sql
SELECT
    cc.config_id,
    c.name AS campaign_name,
    cc.config_status,
    JSON_VALUE(cc.bland_parameters_global, '$.pathway_id') AS pathway_id,
    JSON_VALUE(cc.bland_parameters_global, '$.voice_id') AS voice_id,
    JSON_VALUE(cc.bland_parameters_global, '$.webhook_url') AS webhook_url,
    JSON_VALUE(cc.bland_parameters_global, '$.max_duration') AS max_duration,
    cc.created_ts
FROM ioe.campaign_call_configs_enhanced cc
JOIN ioe.campaigns_enhanced c ON cc.campaign_id = c.campaign_id
WHERE cc.campaign_id IN (
    '0F69659B-491B-40E2-88C3-ABC7D87385B2',
    'BA865458-60F9-4EBB-9FB5-D195B532CF5A'
)
ORDER BY c.name;
```

**Expected Output:** 2 rows

**Verify:**
- ✅ pathway_id is NOT 'TODO_...' (should be your actual value)
- ✅ voice_id is NOT 'TODO_...' (should be your actual value)
- ✅ webhook_url = 'https://ioe-function.azurewebsites.net/api/bland_ai_webhook'
- ✅ config_status = 'active'

✅ **Success!** Bland AI configurations created successfully.

---

## Verification - Check member_identifiers Table

The `member_identifiers` table should already exist. Verify with:

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'ioe'
  AND TABLE_NAME = 'member_identifiers'
ORDER BY ORDINAL_POSITION;
```

**Expected Output:** 5 columns
- member_identifier_id (uniqueidentifier)
- member_id (uniqueidentifier)
- id_type (nvarchar, 50)
- id_value (nvarchar, 100)
- created_ts (datetimeoffset)

✅ **If you see these columns, the table is ready to use.**

---

## Summary Checklist

After running all scripts, verify:

- [ ] salesforce_account_id column exists in members table
- [ ] Index IX_members_salesforce_account_id created
- [ ] member_identifiers table exists (should already exist)
- [ ] 2 Bland AI configs created in campaign_call_configs_enhanced
- [ ] Bland AI configs have actual pathway_id and voice_id (not TODO placeholders)
- [ ] Both configs have config_status = 'active'
- [ ] Both campaigns have campaign_type = 'Operations'
- [ ] Both campaigns have operating_end_time = '17:00:00' (5 PM)

---

## Next Steps

After database setup is complete:

1. ✅ Database scripts completed
2. ⏭️ Deploy Python code changes (blob trigger, column mapping, enrollment logic)
3. ⏭️ Test with sample CSV files
4. ⏭️ Monitor Application Insights for successful processing

---

## Troubleshooting

### Issue: salesforce_account_id column already exists
**Solution:** Skip Script 1, proceed to Script 2

### Issue: Bland AI configs already exist
**Solution:** Use UPDATE queries instead of INSERT queries (see Step 4)

### Issue: Don't know pathway_id or voice_id
**Solution:** Contact Bland AI support or check your Bland AI dashboard under Pathways section

### Issue: member_identifiers table doesn't exist
**Solution:** This table should already exist. If it doesn't, contact the database admin - it's a core table used by other campaigns

---

## Support

If you encounter any issues:
1. Check the error message from SQL Server
2. Verify you have proper permissions (ALTER TABLE, INSERT, UPDATE)
3. Ensure you replaced all TODO placeholders with actual values
4. Review the verification queries to understand current state

---

**Last Updated:** 2025-12-18
**Author:** Claude Code Implementation Plan
