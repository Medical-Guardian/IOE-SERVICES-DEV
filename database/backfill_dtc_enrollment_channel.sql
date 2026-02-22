-- ========================================================================
-- DTC Enrollment Channel Backfill Migration
-- ========================================================================
-- Purpose: Migrate DTC campaigns from member-level channel (members.Channel)
--          to enrollment-level channel (member_campaign_enrollments_enhanced.channel)
--
-- Context: Part of enrollment-level channel migration
--          Partner campaigns already use enrollment-level channel
--          DTC campaigns need backfill before code deployment
--
-- Campaigns Affected:
--   - 34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC (DTC Intro)
--   - E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B (DTC Wellness)
--
-- Date: 2026-02-13
-- ========================================================================

USE ioe;
GO

-- Step 1: Preview the backfill (Optional - Comment out for actual run)
-- Shows how many enrollments will be updated
SELECT
    mce.campaign_id,
    COUNT(*) AS enrollments_to_update,
    COUNT(CASE WHEN mce.channel IS NULL THEN 1 END) AS null_channels,
    COUNT(CASE WHEN m.Channel IS NULL THEN 1 END) AS null_member_channel
FROM ioe.member_campaign_enrollments_enhanced mce
JOIN ioe.members m ON mce.member_id = m.member_id
WHERE mce.campaign_id IN (
    '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',  -- DTC Intro
    'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'   -- DTC Wellness
)
GROUP BY mce.campaign_id;
GO

-- Step 2: Backfill enrollment channel from members table
-- Default to 'phone' if member.Channel is NULL
UPDATE mce
SET mce.channel = ISNULL(m.Channel, 'phone')
FROM ioe.member_campaign_enrollments_enhanced mce
JOIN ioe.members m ON mce.member_id = m.member_id
WHERE mce.campaign_id IN (
    '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',  -- DTC Intro
    'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'   -- DTC Wellness
)
AND mce.channel IS NULL;  -- Only update records where channel is currently NULL
GO

-- Step 3: Verification - Should return 0 NULL channels after backfill
SELECT COUNT(*) AS null_channels_remaining
FROM ioe.member_campaign_enrollments_enhanced
WHERE campaign_id IN (
    '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',  -- DTC Intro
    'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'   -- DTC Wellness
)
AND channel IS NULL;
GO

-- Step 4: Verification - Show channel distribution
SELECT
    c.name AS campaign_name,
    mce.channel,
    COUNT(*) AS enrollment_count
FROM ioe.member_campaign_enrollments_enhanced mce
JOIN ioe.campaigns_enhanced c ON mce.campaign_id = c.campaign_id
WHERE mce.campaign_id IN (
    '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',  -- DTC Intro
    'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'   -- DTC Wellness
)
GROUP BY c.name, mce.channel
ORDER BY c.name, mce.channel;
GO

-- Step 5: Verification - Compare with member-level channel (should match)
SELECT
    COUNT(*) AS mismatched_channels
FROM ioe.member_campaign_enrollments_enhanced mce
JOIN ioe.members m ON mce.member_id = m.member_id
WHERE mce.campaign_id IN (
    '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',
    'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'
)
AND mce.channel != ISNULL(m.Channel, 'phone');
-- Expected: 0 (all enrollment channels should match member channels after backfill)
GO

PRINT 'DTC enrollment channel backfill complete!';
PRINT 'Run verification queries to confirm success.';
GO
