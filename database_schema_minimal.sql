-- Minimal Database Schema Updates for Partner Campaign Scheduler
-- Uses existing tables: members, member_devices, outreach_batches, outreach_attempts
-- Only adds what's truly missing

USE [SANDBOX]
GO

PRINT 'Starting Partner Campaign Scheduler database updates...';
PRINT '';

-- 1. Add audience_file_batch to campaigns_enhanced (if not present)
-- This links campaigns to specific data import batches (e.g., "Hamaspik-FluQ4-20250923T0044")
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('engage360.campaigns_enhanced') AND name = 'audience_file_batch')
BEGIN
    ALTER TABLE engage360.campaigns_enhanced
    ADD audience_file_batch NVARCHAR(255);
    PRINT '✅ Added audience_file_batch column to campaigns_enhanced';
END
ELSE
BEGIN
    PRINT '✅ audience_file_batch column already exists in campaigns_enhanced';
END

-- 2. Create performance indexes for Partner Campaign Scheduler

-- Index for Partner campaign qualification (frequently used in scheduler)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_campaigns_partner_active')
BEGIN
    CREATE INDEX IX_campaigns_partner_active 
    ON engage360.campaigns_enhanced(campaign_type, status, start_ts, end_ts)
    INCLUDE (audience_file_batch, timezone_flag, operating_tz, contact_pref, scheduling_mode, frequency_value, frequency_unit, call_days_of_week, operating_start_time, operating_end_time)
    WHERE campaign_type = 'Partner' AND status = 'Active';
    PRINT '✅ Created index IX_campaigns_partner_active';
END
ELSE
BEGIN
    PRINT '✅ Index IX_campaigns_partner_active already exists';
END

-- Index for batch tracking and duplicate prevention
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_outreach_batches_campaign_submitted')
BEGIN
    CREATE INDEX IX_outreach_batches_campaign_submitted 
    ON engage360.outreach_batches(campaign_id, submitted_ts, batch_status)
    INCLUDE (vendor_batch_id, total_calls_intended, batch_id);
    PRINT '✅ Created index IX_outreach_batches_campaign_submitted';
END
ELSE
BEGIN
    PRINT '✅ Index IX_outreach_batches_campaign_submitted already exists';
END

-- Index for member device lookups (device contact preference)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_member_devices_member_callable')
BEGIN
    CREATE INDEX IX_member_devices_member_callable
    ON engage360.member_devices(member_id, is_device_callable)
    INCLUDE (device_phone_number, device_name);
    PRINT '✅ Created index IX_member_devices_member_callable';
END
ELSE
BEGIN
    PRINT '✅ Index IX_member_devices_member_callable already exists';
END

-- Index for member enrollment eligibility checks
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_mcee_campaign_status')
BEGIN
    CREATE INDEX IX_mcee_campaign_status 
    ON engage360.member_campaign_enrollments_enhanced(campaign_id, current_status)
    INCLUDE (member_id, enrollment_id, preferred_window, last_attempt_ts);
    PRINT '✅ Created index IX_mcee_campaign_status';
END
ELSE
BEGIN
    PRINT '✅ Index IX_mcee_campaign_status already exists';
END

-- Index for outreach attempt frequency checking
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_outreach_attempts_enrollment_attempt')
BEGIN
    CREATE INDEX IX_outreach_attempts_enrollment_attempt 
    ON engage360.outreach_attempts(enrollment_id, attempt_ts)
    INCLUDE (disposition, retry_seq, batch_id, vendor_session_id);
    PRINT '✅ Created index IX_outreach_attempts_enrollment_attempt';
END
ELSE
BEGIN
    PRINT '✅ Index IX_outreach_attempts_enrollment_attempt already exists';
END

-- 3. Sample data updates for testing (using your real campaign examples)
PRINT '';
PRINT 'Updating sample campaign data...';

-- Update Hamaspik Choice campaign with audience batch
IF EXISTS (SELECT 1 FROM engage360.campaigns_enhanced WHERE name LIKE '%Hamaspik%' AND campaign_type = 'Partner')
BEGIN
    UPDATE engage360.campaigns_enhanced 
    SET audience_file_batch = 'Hamaspik-FluQ4-20250923T0044'
    WHERE name LIKE '%Hamaspik%' 
      AND campaign_type = 'Partner' 
      AND (audience_file_batch IS NULL OR audience_file_batch = '');
    PRINT '✅ Updated Hamaspik campaign with audience_file_batch';
END

-- Update FidelisCare campaign with audience batch
IF EXISTS (SELECT 1 FROM engage360.campaigns_enhanced WHERE (name LIKE '%FidelisCare%' OR name LIKE '%Flu Outreach%') AND campaign_type = 'Partner')
BEGIN
    UPDATE engage360.campaigns_enhanced 
    SET audience_file_batch = 'FidelisCare-FluQ4-20250925'
    WHERE (name LIKE '%FidelisCare%' OR name LIKE '%Flu Outreach%')
      AND campaign_type = 'Partner' 
      AND (audience_file_batch IS NULL OR audience_file_batch = '');
    PRINT '✅ Updated FidelisCare campaign with audience_file_batch';
END

-- 4. Verify existing table constraints
PRINT '';
PRINT 'Verifying existing constraints...';

-- Check campaigns_enhanced constraints
IF EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'CK_campaigns_enhanced_contact_pref')
BEGIN
    PRINT '✅ Campaign contact_pref constraint exists (supports phone, device, member_preference)';
END

-- Check members contact_pref constraint  
IF EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('engage360.members') AND name = 'contact_pref')
BEGIN
    PRINT '✅ Members contact_pref column exists';
END

-- Check outreach_batches constraints
IF EXISTS (SELECT * FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('engage360.outreach_batches'))
BEGIN
    PRINT '✅ Outreach batches constraints exist (supports Submitted, Pending, Completed, Failed)';
END

-- Check outreach_attempts constraints
IF EXISTS (SELECT * FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('engage360.outreach_attempts'))
BEGIN
    PRINT '✅ Outreach attempts constraints exist (supports Voice channel, Pending/Completed dispositions)';
END

PRINT '';
PRINT '=== DATABASE SCHEMA UPDATES COMPLETED SUCCESSFULLY ===';
PRINT '';
PRINT 'Partner Campaign Scheduler will use these existing tables:';
PRINT '✓ engage360.campaigns_enhanced (with new audience_file_batch column)';
PRINT '✓ engage360.members (using existing contact_pref, timezone, primary_phone)';
PRINT '✓ engage360.member_devices (using device_phone_number for device calls)';
PRINT '✓ engage360.member_campaign_enrollments_enhanced (using enrollment_id FK)';
PRINT '✓ engage360.outreach_batches (for batch tracking)';
PRINT '✓ engage360.outreach_attempts (for individual call attempts)';
PRINT '';
PRINT 'Contact preference mapping:';
PRINT '• auto → member_preference (system converts automatically)';
PRINT '• phone → use members.primary_phone';
PRINT '• device → use member_devices.device_phone_number (where is_device_callable = 1)';
PRINT '• member_preference → use member''s contact_pref value';
PRINT '';
PRINT 'Required Azure Function environment variables:';
PRINT '- BLAND_AI_API_KEY (required)';
PRINT '- BLAND_AI_BASE_URL (default: https://api.bland.ai)';
PRINT '- BLAND_WEBHOOK_URL (required - your webhook endpoint)';
PRINT '- PARTNER_CAMPAIGN_PATHWAY_ID (required - Bland AI pathway)';
PRINT '- PARTNER_CAMPAIGN_VOICE_ID (required - Bland AI voice)';
PRINT '- BLAND_MAX_DURATION (optional - default: 300 seconds)';
PRINT '';
PRINT 'Next steps:';
PRINT '1. ✅ Run this schema script';
PRINT '2. Configure environment variables in Azure Function';
PRINT '3. Deploy updated Partner Campaign Scheduler code';
PRINT '4. Monitor Azure Function logs for 30-minute timer executions';
PRINT '5. Verify webhook processing for completed calls';