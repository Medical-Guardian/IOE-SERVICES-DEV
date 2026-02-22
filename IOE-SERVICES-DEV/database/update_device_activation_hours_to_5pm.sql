-- ============================================================
-- Device Activation Business Hours Update: 4 PM → 5 PM EST
-- Date: 2026-01-12
-- Author: AI-POD Team
-- ============================================================

USE engage360;
GO

-- Step 1: Verify current configuration before update
SELECT
    campaign_id,
    campaign_name,
    operating_tz,
    operating_start_time,
    operating_end_time,
    timezone_flag,
    status
FROM engage360.campaigns_enhanced
WHERE campaign_name IN ('Device Activation', 'Operations_Device_Activation')
ORDER BY campaign_name;

-- Expected Results:
-- Device Activation: operating_end_time = '16:00:00' (4 PM)
-- Operations_Device_Activation: operating_end_time = '16:00:00' (4 PM)

GO

-- Step 2: Update Device Activation campaign
UPDATE engage360.campaigns_enhanced
SET
    operating_end_time = '17:00:00',  -- Change from 16:00:00 (4 PM) to 17:00:00 (5 PM)
    modified_dt = SYSDATETIMEOFFSET(),
    modified_by = 'SYSTEM_HOURS_UPDATE_2026_01_12'
WHERE campaign_name = 'Device Activation'
  AND operating_end_time = '16:00:00';  -- Safety check: only update if currently 4 PM

-- Verify update
SELECT @@ROWCOUNT AS 'Device_Activation_Rows_Updated';

GO

-- Step 3: Update Operations Device Activation campaign
UPDATE engage360.campaigns_enhanced
SET
    operating_end_time = '17:00:00',  -- Change from 16:00:00 (4 PM) to 17:00:00 (5 PM)
    modified_dt = SYSDATETIMEOFFSET(),
    modified_by = 'SYSTEM_HOURS_UPDATE_2026_01_12'
WHERE campaign_name = 'Operations_Device_Activation'
  AND operating_end_time = '16:00:00';  -- Safety check: only update if currently 4 PM

-- Verify update
SELECT @@ROWCOUNT AS 'Operations_Device_Activation_Rows_Updated';

GO

-- Step 4: Verify both campaigns now have 5 PM end time
SELECT
    campaign_id,
    campaign_name,
    operating_tz,
    operating_start_time,
    operating_end_time,
    timezone_flag,
    modified_dt,
    modified_by,
    status
FROM engage360.campaigns_enhanced
WHERE campaign_name IN ('Device Activation', 'Operations_Device_Activation')
ORDER BY campaign_name;

-- Expected Results:
-- Both campaigns: operating_end_time = '17:00:00' (5 PM)
-- Both campaigns: modified_by = 'SYSTEM_HOURS_UPDATE_2026_01_12'
-- Both campaigns: modified_dt = current timestamp

GO

PRINT '✅ Device Activation business hours successfully updated: 4 PM → 5 PM EST';
PRINT 'Next Step: Deploy code changes to Azure Functions to update BUSINESS_END_HOUR constant';
