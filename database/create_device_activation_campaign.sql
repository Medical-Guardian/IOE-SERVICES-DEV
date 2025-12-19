-- =====================================================================================
-- Device Activation Campaign Setup
-- =====================================================================================
-- Purpose: Create the Device Activation campaign record in engage360.campaigns_enhanced
-- BusinessCaseID: BC-TBD (Device Activation System)
-- Created: 2025-12-07
--
-- This campaign is used by:
-- - CSV file processor (device_activation_file_processor.py)
-- - Device activation scheduler (device_activation_scheduler.py - to be implemented)
-- - Member campaign enrollments (member_campaign_enrollments_enhanced table)
--
-- Campaign Configuration:
-- - Type: Device Activation
-- - Operating Hours: 9 AM - 4 PM EST (dual-timezone validation with member timezone)
-- - 90-day campaign lifecycle from activation_start_date
-- - Supports both DTC and MS customer types
-- =====================================================================================

-- Step 1: Check if campaign already exists
IF EXISTS (
    SELECT 1
    FROM engage360.campaigns_enhanced
    WHERE campaign_name = 'Device Activation'
)
BEGIN
    PRINT '⚠️  Campaign "Device Activation" already exists. Skipping creation.'
    PRINT 'ℹ️  To update the campaign, run an UPDATE statement instead.'

    -- Display existing campaign details
    SELECT
        campaign_id,
        campaign_name,
        campaign_type,
        status,
        org_id,
        operating_tz,
        timezone_flag,
        operating_start_time,
        operating_end_time,
        start_ts,
        end_ts,
        created_ts,
        updated_ts
    FROM engage360.campaigns_enhanced
    WHERE campaign_name = 'Device Activation';
END
ELSE
BEGIN
    PRINT '✅ Creating new Device Activation campaign...'

    -- Step 2: Get Medical Guardian org_id
    DECLARE @org_id UNIQUEIDENTIFIER;

    SELECT @org_id = org_id
    FROM engage360.orgs
    WHERE org_name = 'Medical Guardian';

    IF @org_id IS NULL
    BEGIN
        PRINT '❌ ERROR: Medical Guardian organization not found in engage360.orgs table!'
        PRINT 'ℹ️  Please ensure Medical Guardian exists in orgs table before creating campaign.'
        RAISERROR('Medical Guardian org_id not found', 16, 1);
        RETURN;
    END

    PRINT '✅ Found Medical Guardian org_id: ' + CAST(@org_id AS VARCHAR(50))

    -- Step 3: Insert Device Activation campaign
    INSERT INTO engage360.campaigns_enhanced (
        campaign_id,
        campaign_name,
        campaign_type,
        status,
        org_id,
        start_ts,
        end_ts,
        operating_tz,
        timezone_flag,
        operating_start_time,
        operating_end_time,
        created_ts,
        updated_ts
    )
    VALUES (
        NEWID(),                                    -- campaign_id (auto-generated UUID)
        'Device Activation',                        -- campaign_name
        'Device Activation',                        -- campaign_type
        'Active',                                   -- status
        @org_id,                                    -- org_id (Medical Guardian)
        '2025-12-01 00:00:00+00:00',               -- start_ts (adjust as needed)
        '2026-12-31 23:59:59+00:00',               -- end_ts (adjust as needed)
        'America/New_York',                         -- operating_tz (EST/EDT)
        'member_tz',                                -- timezone_flag (dual-timezone: MG EST + member timezone)
        '09:00:00',                                 -- operating_start_time (9 AM)
        '16:00:00',                                 -- operating_end_time (4 PM - Medical Guardian hours)
        SYSDATETIMEOFFSET(),                        -- created_ts
        SYSDATETIMEOFFSET()                         -- updated_ts
    );

    PRINT '✅ Device Activation campaign created successfully!'

    -- Step 4: Display created campaign details
    PRINT ''
    PRINT '📋 Campaign Details:'
    PRINT '-------------------'

    SELECT
        campaign_id,
        campaign_name,
        campaign_type,
        status,
        org_id,
        operating_tz,
        timezone_flag,
        operating_start_time,
        operating_end_time,
        start_ts,
        end_ts,
        created_ts,
        updated_ts
    FROM engage360.campaigns_enhanced
    WHERE campaign_name = 'Device Activation';

    PRINT ''
    PRINT '✅ CAMPAIGN SETUP COMPLETE'
    PRINT ''
    PRINT '📝 Next Steps:'
    PRINT '   1. Save the campaign_id from the output above'
    PRINT '   2. Test CSV file ingestion (upload to fs-device-activation/landing/)'
    PRINT '   3. Verify member enrollments in member_campaign_enrollments_enhanced'
    PRINT '   4. Proceed to Phase 5: Call Scheduler Implementation'
END

-- =====================================================================================
-- Verification Queries (Optional - Run Separately)
-- =====================================================================================

-- Query 1: Verify campaign exists
-- SELECT * FROM engage360.campaigns_enhanced WHERE campaign_name = 'Device Activation';

-- Query 2: Check member enrollments for this campaign
-- SELECT e.*, m.first_name, m.last_name, m.primary_phone
-- FROM engage360.member_campaign_enrollments_enhanced e
-- JOIN engage360.members m ON e.member_id = m.member_id
-- WHERE e.campaign_id = (SELECT campaign_id FROM engage360.campaigns_enhanced WHERE campaign_name = 'Device Activation')
-- ORDER BY e.created_ts DESC;

-- Query 3: Check device records linked to enrolled members
-- SELECT md.*, m.first_name, m.last_name
-- FROM engage360.member_devices md
-- JOIN engage360.members m ON md.member_id = m.member_id
-- WHERE m.member_id IN (
--     SELECT member_id
--     FROM engage360.member_campaign_enrollments_enhanced
--     WHERE campaign_id = (SELECT campaign_id FROM engage360.campaigns_enhanced WHERE campaign_name = 'Device Activation')
-- )
-- ORDER BY md.delivery_date DESC;

-- =====================================================================================
-- Campaign Configuration Notes
-- =====================================================================================
--
-- timezone_flag: 'member_tz' (Dual-Timezone Mode)
-- ------------------------------------------------
-- This campaign validates business hours in BOTH:
-- 1. Medical Guardian timezone (operating_tz = America/New_York)
-- 2. Member's individual timezone (members.timezone)
--
-- Call attempts only proceed if BOTH conditions are met:
-- - Current time in MG EST is between 9 AM - 4 PM (Medical Guardian hours)
-- - Current time in member's timezone is between 9 AM - 5 PM
--
-- This respects both MG operating hours AND member local hours.
--
-- Operating Hours: 9 AM - 4 PM for MG (operating_start_time / operating_end_time)
-- ---------------------------------------------------------------------------
-- - Used by scheduler for eligibility filtering
-- - Used by business_hours_utils.can_make_call() for validation
-- - Federal holidays are automatically skipped
-- - Weekends are automatically skipped
--
-- Campaign Lifecycle: start_ts / end_ts
-- --------------------------------------
-- - start_ts: 2025-12-01 (campaign start date)
-- - end_ts: 2026-12-31 (campaign end date)
-- - Individual member 90-day windows: activation_start_date + 90 days
--
-- Campaign Type: 'Device Activation'
-- -----------------------------------
-- - Used in metadata for Bland AI webhook processing
-- - Used for disposition mapping
-- - Used for callback queue filtering
--
-- =====================================================================================
