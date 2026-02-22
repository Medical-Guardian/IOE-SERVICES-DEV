/*
Database Migration: Add Channel Column to ioe.members Table
Purpose: Enable device vs phone routing for DTC campaigns
Date: 2025-01-17
Related Feature: Device/Phone Call Routing (channel_type in CSV → Channel in database)

This migration adds the Channel column to the members table if it doesn't already exist,
and sets a default value of 'phone' for backward compatibility.
*/

-- Check if Channel column exists, add if missing
IF NOT EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID('ioe.members')
    AND name = 'Channel'
)
BEGIN
    PRINT '📋 Adding Channel column to ioe.members table...';

    ALTER TABLE ioe.members
    ADD Channel VARCHAR(20) NULL;

    PRINT '✅ Channel column added successfully';
END
ELSE
BEGIN
    PRINT 'ℹ️ Channel column already exists in ioe.members';
END
GO

-- Set default to 'phone' for existing members with NULL Channel
PRINT '📋 Updating NULL Channel values to default "phone"...';

UPDATE ioe.members
SET Channel = 'phone'
WHERE Channel IS NULL;

DECLARE @updated_count INT = @@ROWCOUNT;
PRINT '✅ Updated ' + CAST(@updated_count AS VARCHAR) + ' members to default Channel = "phone"';
GO

-- Verify the migration
PRINT '📋 Verifying migration...';

SELECT
    COUNT(*) as total_members,
    SUM(CASE WHEN Channel IS NULL THEN 1 ELSE 0 END) as null_channel_count,
    SUM(CASE WHEN Channel = 'phone' THEN 1 ELSE 0 END) as phone_channel_count,
    SUM(CASE WHEN Channel = 'device' THEN 1 ELSE 0 END) as device_channel_count
FROM ioe.members;

PRINT '✅ Migration complete!';
GO
