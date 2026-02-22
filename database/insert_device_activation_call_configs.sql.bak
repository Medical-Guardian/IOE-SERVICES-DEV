-- =====================================================================================
-- Device Activation Campaign Configuration - Bland AI Settings
-- =====================================================================================
-- Purpose: Insert campaign call configuration records for Device Activation campaigns
-- Created: 2025-12-22
-- BusinessCaseID: BC-TBD (Device Activation System)
--
-- This script creates configuration records in campaign_call_configs_enhanced table
-- to store Bland AI parameters (pathway_id, voice_id, etc.) for Device Activation campaigns.
--
-- INSTRUCTIONS:
-- 1. Replace 'YOUR_PATHWAY_ID_HERE' with the actual Bland AI pathway ID
-- 2. Replace 'YOUR_VOICE_ID_HERE' with the actual Bland AI voice ID (optional)
-- 3. Adjust other parameters as needed (webhook_url, max_duration, etc.)
-- 4. Run this script in Azure SQL Database
-- 5. Verify inserts using the verification query at the end
-- =====================================================================================

-- =====================================================================================
-- INSERT CONFIGURATION FOR DEVICE ACTIVATION - DTC/MA CAMPAIGN
-- =====================================================================================
-- This configuration will be used for all Device Activation - DTC/MA calls

PRINT '📋 Inserting configuration for Device Activation - DTC/MA campaign...';

INSERT INTO engage360.campaign_call_configs_enhanced (
    campaign_id,
    call_type,
    config_name,
    bland_parameters_global,
    config_status
)
SELECT
    campaign_id,
    'DeviceActivation' AS call_type,
    'Device Activation DTC/MA - Bland AI Config' AS config_name,
    N'{
        "pathway_id": "YOUR_PATHWAY_ID_HERE",
        "voice_id": "YOUR_VOICE_ID_HERE",
        "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
        "max_duration": 300,
        "wait_for_greeting": true,
        "record": true,
        "temperature": 0.7,
        "interruption_threshold": 100
    }' AS bland_parameters_global,
    'active' AS config_status
FROM engage360.campaigns_enhanced
WHERE name = 'Device Activation - DTC/MA'
  AND NOT EXISTS (
      SELECT 1
      FROM engage360.campaign_call_configs_enhanced cc
      WHERE cc.campaign_id = campaigns_enhanced.campaign_id
        AND cc.call_type = 'DeviceActivation'
        AND cc.config_status = 'active'
  );

IF @@ROWCOUNT > 0
    PRINT '✅ Configuration inserted for Device Activation - DTC/MA';
ELSE
    PRINT '⚠️ Configuration already exists or campaign not found';

PRINT '';
GO

-- =====================================================================================
-- INSERT CONFIGURATION FOR DEVICE ACTIVATION - MEDICAID CAMPAIGN
-- =====================================================================================
-- This configuration will be used for all Device Activation - Medicaid calls
-- NOTE: Per user requirements, using same pathway_id as DTC/MA

PRINT '📋 Inserting configuration for Device Activation - Medicaid campaign...';

INSERT INTO engage360.campaign_call_configs_enhanced (
    campaign_id,
    call_type,
    config_name,
    bland_parameters_global,
    config_status
)
SELECT
    campaign_id,
    'DeviceActivation' AS call_type,
    'Device Activation Medicaid - Bland AI Config' AS config_name,
    N'{
        "pathway_id": "YOUR_PATHWAY_ID_HERE",
        "voice_id": "YOUR_VOICE_ID_HERE",
        "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
        "max_duration": 300,
        "wait_for_greeting": true,
        "record": true,
        "temperature": 0.7,
        "interruption_threshold": 100
    }' AS bland_parameters_global,
    'active' AS config_status
FROM engage360.campaigns_enhanced
WHERE name = 'Device Activation - Medicaid'
  AND NOT EXISTS (
      SELECT 1
      FROM engage360.campaign_call_configs_enhanced cc
      WHERE cc.campaign_id = campaigns_enhanced.campaign_id
        AND cc.call_type = 'DeviceActivation'
        AND cc.config_status = 'active'
  );

IF @@ROWCOUNT > 0
    PRINT '✅ Configuration inserted for Device Activation - Medicaid';
ELSE
    PRINT '⚠️ Configuration already exists or campaign not found';

PRINT '';
GO

-- =====================================================================================
-- VERIFICATION QUERY
-- =====================================================================================
-- Run this to verify the configuration records were inserted correctly

PRINT '🔍 Verifying Device Activation campaign configurations...';
PRINT '';

SELECT
    c.name AS campaign_name,
    c.campaign_type,
    c.status AS campaign_status,
    cc.config_name,
    cc.call_type,
    cc.bland_parameters_global,
    cc.config_status,
    cc.created_ts,
    cc.updated_ts
FROM engage360.campaign_call_configs_enhanced cc
JOIN engage360.campaigns_enhanced c ON cc.campaign_id = c.campaign_id
WHERE cc.call_type = 'DeviceActivation'
  AND cc.config_status = 'active'
ORDER BY c.name;

PRINT '';
PRINT '✅ Verification complete';
PRINT '';
PRINT '⚠️  IMPORTANT: Before running the scheduler, make sure to:';
PRINT '   1. Replace YOUR_PATHWAY_ID_HERE with actual Bland AI pathway ID';
PRINT '   2. Replace YOUR_VOICE_ID_HERE with actual Bland AI voice ID';
PRINT '   3. Update webhook_url if using different Azure Function App URL';
PRINT '   4. Verify all campaigns are Active (campaign_status = ''Active'')';
PRINT '';
GO

-- =====================================================================================
-- UPDATE EXISTING CONFIGURATION (OPTIONAL)
-- =====================================================================================
-- Use this section if you need to update an existing configuration

-- Example: Update pathway_id for Device Activation - DTC/MA
/*
UPDATE cc
SET cc.bland_parameters_global = JSON_MODIFY(
    cc.bland_parameters_global,
    '$.pathway_id',
    'NEW_PATHWAY_ID_HERE'
)
FROM engage360.campaign_call_configs_enhanced cc
JOIN engage360.campaigns_enhanced c ON cc.campaign_id = c.campaign_id
WHERE c.name = 'Device Activation - DTC/MA'
  AND cc.call_type = 'DeviceActivation'
  AND cc.config_status = 'active';

PRINT '✅ pathway_id updated for Device Activation - DTC/MA';
*/

-- Example: Update voice_id for all Device Activation campaigns
/*
UPDATE cc
SET cc.bland_parameters_global = JSON_MODIFY(
    cc.bland_parameters_global,
    '$.voice_id',
    'NEW_VOICE_ID_HERE'
)
FROM engage360.campaign_call_configs_enhanced cc
WHERE cc.call_type = 'DeviceActivation'
  AND cc.config_status = 'active';

PRINT '✅ voice_id updated for all Device Activation campaigns';
*/

-- =====================================================================================
-- END OF SCRIPT
-- =====================================================================================
--
-- Summary:
-- - Created configuration records for Device Activation campaigns
-- - Stored Bland AI parameters in campaign_call_configs_enhanced table
-- - Enabled database-only configuration management (no environment variables needed)
-- - Campaign-specific: Can use different pathways per campaign if needed
-- - Flexible: Update via SQL without code deployment
--
-- Next Steps:
-- 1. Update pathway_id and voice_id placeholders with actual values
-- 2. Deploy updated code to Azure Function App
-- 3. Test scheduler by triggering manually: POST to /api/create_device_activation_batch
-- 4. Verify logs show database configuration being used
-- 5. Monitor for successful batch submission to Bland AI
--
-- =====================================================================================
