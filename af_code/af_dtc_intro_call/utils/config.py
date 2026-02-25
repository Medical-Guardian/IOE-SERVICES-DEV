import logging
import os

from af_code.shared.schema_config import IOE_SCHEMA

logger = logging.getLogger(__name__)

# Environment variables
KEY_VAULT_URL = os.environ.get("KEY_VAULT_URL")
DB_SECRET_NAME = os.environ.get("DB_SECRET_NAME", "SqlConnectionString")

# Verify critical environment variables
logger.info("🔍 [DTC-CONFIG] Environment check:")
logger.info(f"   KEY_VAULT_URL: {'✅ Set' if KEY_VAULT_URL else '❌ Missing'}")
logger.info(f"   DB_SECRET_NAME: {'✅ Set' if DB_SECRET_NAME else '❌ Missing'}")

if not KEY_VAULT_URL:
    logger.error("❌ [DTC-CONFIG] CRITICAL: KEY_VAULT_URL environment variable is not set!")
    logger.error("   This will cause all database-dependent functions to fail.")

BLAND_AI_BATCH_URL = "https://api.bland.ai/v2/batches/create"

# SQL Queries
# BUSINESS RULE: One DTC outreach per member per day (intro OR wellness) - other campaigns remain independent
GET_CAMPAIGN_CONFIG_QUERY = f"""
SELECT
    ccc.bland_parameters_global,
    ccc.call_type,
    ISNULL(c.contact_pref, 'phone') as contact_pref  -- Default to 'phone' for backward compatibility
FROM {IOE_SCHEMA}.campaign_call_configs_enhanced ccc
JOIN {IOE_SCHEMA}.campaigns_enhanced c ON ccc.campaign_id = c.campaign_id
WHERE ccc.campaign_id = ? AND ccc.config_status = 'active'
"""

# Using '?' for pyodbc parameter binding
CREATE_BATCH_QUERY = f"""
INSERT INTO {IOE_SCHEMA}.outreach_batches
(batch_id, campaign_id, batch_status, total_calls_intended, created_ts)
VALUES (?, ?, 'Pending', ?, SYSDATETIMEOFFSET())
"""

# Using '?' for pyodbc parameter binding
CREATE_ATTEMPT_QUERY = f"""
INSERT INTO {IOE_SCHEMA}.outreach_attempts
(attempt_id, enrollment_id, channel, attempt_ts, disposition, retry_seq, batch_id)
VALUES (?, ?, 'Voice', SYSUTCDATETIME(), 'Pending', 0, ?)
"""

# --- CHANGE: Added a JOIN to get call_type_code and ensured all member fields are selected ---
GET_MEMBERS_WITH_ATTEMPTS_QUERY = f"""
SELECT
    m.member_id,
    m.salesforce_account_number,
    m.first_name,
    m.last_name,
    m.primary_phone,
    mce.channel,  -- Enrollment-level channel (phone/device)
    m.language_pref,
    m.dob,
    m.address_street,
    m.address_city,
    m.address_state,
    m.address_zip,
    md.device_id as device_udi,
    md.device_phone_number,  -- Device phone number
    md.is_device_callable,
    oa.attempt_id,
    mce.campaign_id,
    mce.enrollment_id,
    cfg.call_type -- Added this field
FROM {IOE_SCHEMA}.outreach_attempts oa
JOIN {IOE_SCHEMA}.member_campaign_enrollments_enhanced mce ON oa.enrollment_id = mce.enrollment_id
JOIN {IOE_SCHEMA}.members m ON mce.member_id = m.member_id
LEFT JOIN {IOE_SCHEMA}.member_devices md
    ON m.member_id = md.member_id
    AND md.service_status = 'In Service'
-- Joined to get the active call configuration for the campaign
LEFT JOIN {IOE_SCHEMA}.campaign_call_configs_enhanced cfg ON mce.campaign_id = cfg.campaign_id AND cfg.config_status = 'active'
WHERE oa.batch_id = ? AND oa.disposition = 'Pending'
"""

# Using '?' for pyodbc parameter binding
UPDATE_BATCH_VENDOR_ID_QUERY = f"""
UPDATE {IOE_SCHEMA}.outreach_batches
SET vendor_batch_id = ?, batch_status = 'Submitted'
WHERE batch_id = ?
"""

# Using '?' for pyodbc parameter binding
UPDATE_BATCH_FAILED_QUERY = f"""
UPDATE {IOE_SCHEMA}.outreach_batches
SET batch_status = 'Failed', error_message = ?
WHERE batch_id = ?
"""

# Using '?' for pyodbc parameter binding
# SEPARATED: Created specific queries for intro calls (PENDING) and wellness calls (ENROLLED)

ELIGIBLE_MEMBERS_QUERY_INTRO = f"""
DECLARE @CurrentUtcTimestamp DATETIMEOFFSET = SYSDATETIMEOFFSET();
DECLARE @TodayStartUtc DATETIMEOFFSET = CAST(CAST(@CurrentUtcTimestamp AS DATE) AS DATETIMEOFFSET);
DECLARE @TodayEndUtc DATETIMEOFFSET = DATEADD(DAY, 1, @TodayStartUtc);

SELECT
    m.member_id,
    m.primary_phone,
    m.timezone,
    mce.enrollment_id,
    mce.preferred_window,
    mce.channel,
    c.name as campaign_name,
    c.campaign_id,
    c.call_days_of_week,
    ISNULL(failed_attempts.failed_count, 0) as todays_failed_attempts,
    md.device_phone_number,
    md.is_device_callable
FROM
    {IOE_SCHEMA}.members AS m
JOIN
    {IOE_SCHEMA}.member_campaign_enrollments_enhanced AS mce ON m.member_id = mce.member_id
JOIN
    {IOE_SCHEMA}.campaigns_enhanced AS c ON mce.campaign_id = c.campaign_id
LEFT JOIN
    {IOE_SCHEMA}.member_devices md ON m.member_id = md.member_id
    AND md.service_status = 'In Service'
LEFT JOIN (
    SELECT
        oa.enrollment_id,
        COUNT(*) as failed_count
    FROM {IOE_SCHEMA}.outreach_attempts oa
    WHERE oa.attempt_ts >= @TodayStartUtc
      AND oa.attempt_ts < @TodayEndUtc
      AND oa.disposition != 'Completed'
    GROUP BY oa.enrollment_id
) failed_attempts ON mce.enrollment_id = failed_attempts.enrollment_id
WHERE
    c.status = 'Active'
    AND mce.current_status = 'ENROLLED'  -- INTRO: Members enrolled and ready for intro calls
    AND m.timezone IS NOT NULL
    AND mce.preferred_window IS NOT NULL
    AND c.campaign_id = ?
    AND (
        -- Channel validation: enforce device status
        mce.channel != 'device'  -- Phone channel: always eligible
        OR (mce.channel = 'device' AND md.device_id IS NOT NULL)  -- Device channel: must have active device
    )
    AND NOT EXISTS (
        -- Check for ANY DTC outreach attempts for this member today (intro OR wellness)
        SELECT 1
        FROM {IOE_SCHEMA}.outreach_attempts oa
        JOIN {IOE_SCHEMA}.member_campaign_enrollments_enhanced other_mce ON oa.enrollment_id = other_mce.enrollment_id
        WHERE other_mce.member_id = m.member_id  -- Same member across all enrollments
          AND other_mce.campaign_id IN (
              '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',  -- DTC Intro Campaign
              'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'   -- DTC Wellness Campaign
          )
          AND oa.attempt_ts >= @TodayStartUtc
          AND oa.attempt_ts < @TodayEndUtc
    );
"""

ELIGIBLE_MEMBERS_QUERY_WELLNESS = f"""
DECLARE @CurrentUtcTimestamp DATETIMEOFFSET = SYSDATETIMEOFFSET();
DECLARE @TodayStartUtc DATETIMEOFFSET = CAST(CAST(@CurrentUtcTimestamp AS DATE) AS DATETIMEOFFSET);
DECLARE @TodayEndUtc DATETIMEOFFSET = DATEADD(DAY, 1, @TodayStartUtc);

SELECT
    m.member_id,
    m.primary_phone,
    m.timezone,
    mce.enrollment_id,
    mce.preferred_window,
    mce.channel,
    c.name as campaign_name,
    c.campaign_id,
    c.call_days_of_week,
    ISNULL(failed_attempts.failed_count, 0) as todays_failed_attempts,
    md.device_phone_number,
    md.is_device_callable
FROM
    {IOE_SCHEMA}.members AS m
JOIN
    {IOE_SCHEMA}.member_campaign_enrollments_enhanced AS mce ON m.member_id = mce.member_id
JOIN
    {IOE_SCHEMA}.campaigns_enhanced AS c ON mce.campaign_id = c.campaign_id
LEFT JOIN
    {IOE_SCHEMA}.member_devices md ON m.member_id = md.member_id
    AND md.service_status = 'In Service'
LEFT JOIN (
    SELECT
        oa.enrollment_id,
        COUNT(*) as failed_count
    FROM {IOE_SCHEMA}.outreach_attempts oa
    WHERE oa.attempt_ts >= @TodayStartUtc
      AND oa.attempt_ts < @TodayEndUtc
      AND oa.disposition != 'Completed'
    GROUP BY oa.enrollment_id
) failed_attempts ON mce.enrollment_id = failed_attempts.enrollment_id
WHERE
    c.status = 'Active'
    AND mce.current_status = 'ENROLLED'  -- WELLNESS: Members enrolled in wellness campaign
    AND m.timezone IS NOT NULL
    AND mce.preferred_window IS NOT NULL
    AND c.campaign_id = ?
    AND (
        -- Channel validation: enforce device status
        mce.channel != 'device'  -- Phone channel: always eligible
        OR (mce.channel = 'device' AND md.device_id IS NOT NULL)  -- Device channel: must have active device
    )
    AND EXISTS (
        -- Ensure intro campaign is UNENROLLED (intro call completed)
        SELECT 1
        FROM {IOE_SCHEMA}.member_campaign_enrollments_enhanced intro_mce
        WHERE intro_mce.member_id = m.member_id
          AND intro_mce.campaign_id = '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC'  -- DTC Intro Campaign
          AND intro_mce.current_status = 'UNENROLLED'
    )
    AND NOT EXISTS (
        -- Check for ANY DTC outreach attempts for this member today (intro OR wellness)
        SELECT 1
        FROM {IOE_SCHEMA}.outreach_attempts oa
        JOIN {IOE_SCHEMA}.member_campaign_enrollments_enhanced other_mce ON oa.enrollment_id = other_mce.enrollment_id
        WHERE other_mce.member_id = m.member_id  -- Same member across all enrollments
          AND other_mce.campaign_id IN (
              '34CC9155-D6DD-42E8-B1EA-DCF73F1E6FAC',  -- DTC Intro Campaign
              'E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B'   -- DTC Wellness Campaign
          )
          AND oa.attempt_ts >= @TodayStartUtc
          AND oa.attempt_ts < @TodayEndUtc
    );
"""

# Backward compatibility: Keep original query name pointing to intro query
ELIGIBLE_MEMBERS_QUERY = ELIGIBLE_MEMBERS_QUERY_INTRO
