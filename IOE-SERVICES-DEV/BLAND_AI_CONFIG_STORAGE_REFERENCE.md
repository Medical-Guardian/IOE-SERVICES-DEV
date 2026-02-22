# Bland AI Configuration Storage - pathway_id and voice_id Reference

**Date:** 2025-12-18
**Purpose:** Document where and how pathway_id and voice_id are stored for all campaign types

---

## Storage Location

**Table:** `engage360.campaign_call_configs_enhanced`
**Column:** `bland_parameters_global` (NVARCHAR(MAX) - stores JSON)

All campaigns (DTC, Partner, Device Activation, Operations) store their Bland AI configuration in this table.

---

## How It Works

### 1. Database Storage

Each campaign has a configuration record in `campaign_call_configs_enhanced`:

```sql
-- Example query to see current configs
SELECT
    c.name AS campaign_name,
    cc.config_id,
    cc.campaign_id,
    cc.config_status,
    JSON_VALUE(cc.bland_parameters_global, '$.pathway_id') AS pathway_id,
    JSON_VALUE(cc.bland_parameters_global, '$.voice_id') AS voice_id,
    cc.bland_parameters_global
FROM engage360.campaign_call_configs_enhanced cc
JOIN engage360.campaigns_enhanced c ON cc.campaign_id = c.campaign_id
WHERE cc.config_status = 'active'
ORDER BY c.name;
```

### 2. Application Retrieval

**Pattern used by all schedulers:**

```python
# Step 1: Query database for bland_parameters_global
GET_CAMPAIGN_CONFIG_QUERY = """
SELECT
    ccc.bland_parameters_global,
    ccc.call_type
FROM engage360.campaign_call_configs_enhanced ccc
JOIN engage360.campaigns_enhanced c ON ccc.campaign_id = c.campaign_id
WHERE ccc.campaign_id = %s AND ccc.config_status = 'active'
"""

# Step 2: Parse JSON and extract values
results = db_service.execute_query(GET_CAMPAIGN_CONFIG_QUERY, (campaign_id,))
bland_parameters = results[0]["bland_parameters_global"]
config = json.loads(bland_parameters) if isinstance(bland_parameters, str) else bland_parameters

# Step 3: Get pathway_id and voice_id
pathway_id = config.get("pathway_id")
voice_id = config.get("voice_id") or config.get("voice")  # Support both field names
```

---

## Existing Campaign Configurations

### DTC Intro Call Campaign

**Campaign ID:** `34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC`
**Campaign Name:** DTC Intro Call

**Example Configuration (from documentation):**
```json
{
    "pathway_id": "pathway-dtc-intro-v1",
    "voice_id": "maya",
    "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
    "wait_for_greeting": true,
    "record": true,
    "answered_by_enabled": true,
    "noise_cancellation": true,
    "interruption_threshold": 100,
    "max_duration": 600,
    "model": "enhanced",
    "temperature": 0.7,
    "language": "en"
}
```

**Code References:**
- **Config Query:** `af_code/af_dtc_intro_call/utils/config.py` (lines 24-32)
- **Batch Building:** `af_code/af_dtc_intro_call/services/blandai_service.py` (lines 129-152)

---

### DTC Wellness Check Campaign

**Campaign ID:** `E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B`
**Campaign Name:** DTC Wellness Check

**Example Configuration (from documentation):**
```json
{
    "pathway_id": "pathway-dtc-wellness-v2",
    "voice_id": "grace",
    "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
    "wait_for_greeting": true,
    "record": true,
    "answered_by_enabled": true,
    "noise_cancellation": true,
    "interruption_threshold": 100,
    "max_duration": 600,
    "model": "enhanced",
    "temperature": 0.7,
    "language": "en"
}
```

**Pattern:** Same as DTC Intro Call (shared codebase in `af_code/af_dtc_intro_call/`)

---

### Partner Campaigns

**Example:** Health Check Partner Campaign

**Configuration Structure:**
```json
{
    "pathway_id": "partner-wellness-pathway-123",
    "pathway_version": "2024-01-15",
    "voice_id": "partner-voice-456",
    "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
    "wait_for_greeting": true,
    "record": true,
    "answered_by_enabled": true,
    "noise_cancellation": true,
    "interruption_threshold": 100,
    "block_interruptions": false,
    "max_duration": 300,
    "model": "enhanced",
    "temperature": 0.7,
    "language": "en",
    "from": "+15551234567",
    "timezone": "America/New_York"
}
```

**Code References:**
- **Config Query:** `af_code/partner_campaign_scheduler/services/campaign_qualifier.py` (line 64)
- **Parsing:** `campaign_qualifier.py` `_parse_bland_parameters()` method (line 506)

---

## Operations Device Activation Campaigns (NEW)

### Device Activation - Medicaid

**Campaign ID:** `0F69659B-491B-40E2-88C3-ABC7D87385B2`
**Campaign Name:** Device Activation - Medicaid
**Campaign Type:** Operations

**Configuration (TO BE CREATED):**
```json
{
    "pathway_id": "TODO_DEVICE_ACTIVATION_MEDICAID_PATHWAY",
    "voice_id": "TODO_GRACE_VOICE_ID",
    "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
    "max_duration": "600",
    "wait_for_greeting": true,
    "record": true,
    "voicemail_action": "hangup",
    "interruption_threshold": 100,
    "temperature": 0.7,
    "language": "en"
}
```

---

### Device Activation - DTC/MA

**Campaign ID:** `BA865458-60F9-4EBB-9FB5-D195B532CF5A`
**Campaign Name:** Device Activation - DTC/MA
**Campaign Type:** Operations

**Configuration (TO BE CREATED):**
```json
{
    "pathway_id": "TODO_DEVICE_ACTIVATION_DTCMA_PATHWAY",
    "voice_id": "TODO_GRACE_VOICE_ID",
    "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
    "max_duration": "600",
    "wait_for_greeting": true,
    "record": true,
    "voicemail_action": "hangup",
    "interruption_threshold": 100,
    "temperature": 0.7,
    "language": "en"
}
```

---

## How to Create Bland AI Configs for Operations Campaigns

### Step 1: Get pathway_id and voice_id from Bland AI

You need to obtain these values from your Bland AI dashboard:

1. **pathway_id** - Go to Bland AI dashboard → Pathways section
   - For Medicaid campaign: Create or use existing pathway for device activation (Medicaid)
   - For DTC/MA campaign: Create or use existing pathway for device activation (DTC/MA)

2. **voice_id** - Common values: `"maya"`, `"grace"`, `"alex"`, etc.
   - Check with your Bland AI configuration team
   - Or use same voice as DTC campaigns

### Step 2: Update SQL Script

Edit `database/create_operations_device_activation_bland_configs.sql`:

**Replace:**
```json
"pathway_id": "TODO_DEVICE_ACTIVATION_MEDICAID_PATHWAY"
```

**With your actual value:**
```json
"pathway_id": "pathway-device-activation-medicaid-v1"
```

**Replace:**
```json
"voice_id": "TODO_GRACE_VOICE_ID"
```

**With your actual value:**
```json
"voice_id": "grace"
```

### Step 3: Run INSERT Statements

```sql
-- Insert config for Device Activation - Medicaid
INSERT INTO engage360.campaign_call_configs_enhanced (
    config_id,
    campaign_id,
    bland_parameters_global,
    config_status,
    created_ts
) VALUES (
    NEWID(),
    '0F69659B-491B-40E2-88C3-ABC7D87385B2',  -- Medicaid campaign
    '{
        "pathway_id": "pathway-device-activation-medicaid-v1",  -- ← YOUR ACTUAL VALUE
        "voice_id": "grace",                                     -- ← YOUR ACTUAL VALUE
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
INSERT INTO engage360.campaign_call_configs_enhanced (
    config_id,
    campaign_id,
    bland_parameters_global,
    config_status,
    created_ts
) VALUES (
    NEWID(),
    'BA865458-60F9-4EBB-9FB5-D195B532CF5A',  -- DTC/MA campaign
    '{
        "pathway_id": "pathway-device-activation-dtcma-v1",     -- ← YOUR ACTUAL VALUE
        "voice_id": "grace",                                     -- ← YOUR ACTUAL VALUE
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

### Step 4: Verify Configuration

```sql
-- Verify both configs were created
SELECT
    c.name AS campaign_name,
    cc.config_status,
    JSON_VALUE(cc.bland_parameters_global, '$.pathway_id') AS pathway_id,
    JSON_VALUE(cc.bland_parameters_global, '$.voice_id') AS voice_id,
    cc.created_ts
FROM engage360.campaign_call_configs_enhanced cc
JOIN engage360.campaigns_enhanced c ON cc.campaign_id = c.campaign_id
WHERE cc.campaign_id IN (
    '0F69659B-491B-40E2-88C3-ABC7D87385B2',  -- Medicaid
    'BA865458-60F9-4EBB-9FB5-D195B532CF5A'   -- DTC/MA
);
```

**Expected Result:**
```
campaign_name                      config_status  pathway_id                              voice_id
Device Activation - Medicaid       active         pathway-device-activation-medicaid-v1   grace
Device Activation - DTC/MA         active         pathway-device-activation-dtcma-v1      grace
```

---

## Code Implementation Status

### ✅ Operations Device Activation Code (Already Implemented)

The batch orchestrator for Device Activation campaigns retrieves Bland AI config from database:

**File:** `af_code/device_activation_scheduler/services/batch_orchestrator.py`

**Code Pattern:**
```python
# Query bland_parameters_global from database
bland_config_query = """
    SELECT bland_parameters_global
    FROM engage360.campaign_call_configs_enhanced
    WHERE campaign_id = %s
      AND config_status = 'active'
"""

config_results = self.db_service.execute_query(
    bland_config_query,
    (str(campaign_id),),
    fetch_results=True
)

# Parse JSON
bland_parameters = config_results[0]['bland_parameters_global']
bland_params = json.loads(bland_parameters) if isinstance(bland_parameters, str) else bland_parameters

# Extract pathway_id and voice_id
pathway_id = bland_params.get('pathway_id') or bland_params.get('task')
voice_id = bland_params.get('voice_id') or bland_params.get('voice')
```

**Status:** ✅ Code complete - just needs database records created

---

## Environment Variables (NOT USED for Operations Campaigns)

**Note:** The user mentioned wanting to use environment variables, but the existing code pattern for Device Activation uses **database storage** like DTC and Partner campaigns.

If you want to use environment variables instead, you would need to modify `batch_orchestrator.py` to:

```python
import os

# Option 1: Single shared pathway for all Device Activation campaigns
pathway_id = os.environ.get("DEVICE_ACTIVATION_PATHWAY_ID")
voice_id = os.environ.get("DEVICE_ACTIVATION_VOICE_ID")

# Option 2: Separate pathways per campaign
if campaign_id == "0F69659B-491B-40E2-88C3-ABC7D87385B2":  # Medicaid
    pathway_id = os.environ.get("DEVICE_ACTIVATION_MEDICAID_PATHWAY_ID")
    voice_id = os.environ.get("DEVICE_ACTIVATION_VOICE_ID")
elif campaign_id == "BA865458-60F9-4EBB-9FB5-D195B532CF5A":  # DTC/MA
    pathway_id = os.environ.get("DEVICE_ACTIVATION_DTCMA_PATHWAY_ID")
    voice_id = os.environ.get("DEVICE_ACTIVATION_VOICE_ID")
```

**Recommendation:** Use database storage (like DTC/Partner) for consistency and easier management per campaign.

---

## Summary

### Current Status

| Campaign Type | pathway_id Storage | voice_id Storage | Implementation Status |
|---------------|-------------------|------------------|----------------------|
| **DTC Intro** | Database (campaign_call_configs_enhanced) | Database | ✅ Active in production |
| **DTC Wellness** | Database (campaign_call_configs_enhanced) | Database | ✅ Active in production |
| **Partner Campaigns** | Database (campaign_call_configs_enhanced) | Database | ✅ Active in production |
| **Device Activation (Original)** | Database (campaign_call_configs_enhanced) | Database | ✅ Active in production |
| **Operations - Medicaid** | Database (campaign_call_configs_enhanced) | Database | ⏳ Code complete, needs DB setup |
| **Operations - DTC/MA** | Database (campaign_call_configs_enhanced) | Database | ⏳ Code complete, needs DB setup |

### What You Need to Provide

1. **pathway_id for Device Activation - Medicaid campaign**
   - Example format: `"pathway-device-activation-medicaid-v1"`

2. **pathway_id for Device Activation - DTC/MA campaign**
   - Example format: `"pathway-device-activation-dtcma-v1"`

3. **voice_id (shared by both campaigns)**
   - Example: `"grace"` or `"maya"`
   - Same voice can be used for both campaigns

### Next Steps

1. ✅ Code implementation: Complete
2. ⏳ Get pathway_id values from Bland AI team
3. ⏳ Update SQL script with actual values
4. ⏳ Run database scripts
5. ⏳ Deploy to Azure
6. ⏳ Test with sample CSV files

---

**Questions?**
- Need help getting pathway_id from Bland AI? Contact your Bland AI account manager
- Want to use different voices? Check Bland AI voice library
- Need to modify other Bland AI parameters? Update the JSON in bland_parameters_global
