/*
Database Migration: Add contact_pref Column to engage360.campaigns_enhanced Table
Purpose: Enable campaign-level device vs phone routing configuration for DTC campaigns
Date: 2025-01-17
Related Feature: Device/Phone Call Routing (contact_pref campaign setting)

This migration adds the contact_pref column to the campaigns_enhanced table if it doesn't already exist,
and sets a default value of 'phone' for backward compatibility.

Valid Values:
- 'phone': Always call primary_phone (default, backward compatible)
- 'device': Always call device_phone_number (if callable)
- 'member_preference': Use member's Channel field preference with fallback
- 'auto': Alias for 'member_preference'
*/

-- Check if contact_pref column exists, add if missing
IF NOT EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID('engage360.campaigns_enhanced')
    AND name = 'contact_pref'
)
BEGIN
    PRINT '📋 Adding contact_pref column to engage360.campaigns_enhanced table...';

    ALTER TABLE engage360.campaigns_enhanced
    ADD contact_pref VARCHAR(50) DEFAULT 'phone' NULL;

    PRINT '✅ contact_pref column added successfully';
END
ELSE
BEGIN
    PRINT 'ℹ️ contact_pref column already exists in engage360.campaigns_enhanced';
END
GO

-- Set default to 'phone' for existing campaigns with NULL contact_pref
PRINT '📋 Updating NULL contact_pref values to default "phone"...';

UPDATE engage360.campaigns_enhanced
SET contact_pref = 'phone'
WHERE contact_pref IS NULL;

DECLARE @updated_count INT = @@ROWCOUNT;
PRINT '✅ Updated ' + CAST(@updated_count AS VARCHAR) + ' campaigns to default contact_pref = "phone"';
GO

-- Verify the migration
PRINT '📋 Verifying migration...';

SELECT
    COUNT(*) as total_campaigns,
    SUM(CASE WHEN contact_pref IS NULL THEN 1 ELSE 0 END) as null_pref_count,
    SUM(CASE WHEN contact_pref = 'phone' THEN 1 ELSE 0 END) as phone_pref_count,
    SUM(CASE WHEN contact_pref = 'device' THEN 1 ELSE 0 END) as device_pref_count,
    SUM(CASE WHEN contact_pref = 'member_preference' THEN 1 ELSE 0 END) as member_pref_count
FROM engage360.campaigns_enhanced;

PRINT '✅ Migration complete!';
GO

/*
OPTIONAL: Update specific DTC campaigns to use device routing

-- Example: Enable device routing for a specific campaign
UPDATE engage360.campaigns_enhanced
SET contact_pref = 'member_preference'  -- Respect individual member preferences
WHERE campaign_id = '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC';  -- DTC Intro Campaign

-- Example: Force all members in a campaign to use devices
UPDATE engage360.campaigns_enhanced
SET contact_pref = 'device'
WHERE campaign_id = 'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B';  -- DTC Wellness Campaign
*/
