-- =====================================================================================
-- Device Activation Staging Table Creation
-- =====================================================================================
-- Purpose: Create staging table for Device Activation CSV file processing
-- BusinessCaseID: BC-TBD (Device Activation System)
-- Created: 2025-12-12
-- Updated: 2025-12-16 - Updated Day 0 logic (first business day on or after enrollment)
-- Updated: 2025-12-23 - Added address_country, member_brand; removed obsolete cleaned columns
--
-- This table stores raw CSV data from Device Activation file uploads and tracks
-- the 5-phase ETL processing workflow:
-- Phase 1: Extract (CSV → DataFrame)
-- Phase 2: Load to Staging (INSERT with PENDING status)
-- Phase 3: Validate (UPDATE to VALIDATED status after cleansing)
-- Phase 4: Transform & Load Core (MERGE into members/devices/enrollments, UPDATE to PROCESSED)
-- Phase 5: Audit & Log (File processing log)
--
-- Pattern: Follows ioe_stg.stg_dtc_wellness_delta structure
-- =====================================================================================

-- Step 1: Check if table already exists
IF EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'ioe_stg'
    AND TABLE_NAME = 'stg_device_activation_delta'
)
BEGIN
    PRINT '⚠️  Table ioe_stg.stg_device_activation_delta already exists.'
    PRINT 'ℹ️  Skipping table creation.'
    PRINT 'ℹ️  To modify the table, use ALTER TABLE statements or DROP and recreate.'

    -- Display existing table structure
    SELECT
        COLUMN_NAME,
        DATA_TYPE,
        CHARACTER_MAXIMUM_LENGTH,
        IS_NULLABLE,
        COLUMN_DEFAULT
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'ioe_stg'
    AND TABLE_NAME = 'stg_device_activation_delta'
    ORDER BY ORDINAL_POSITION;
END
ELSE
BEGIN
    PRINT '✅ Creating stg_device_activation_delta table...'

    -- Step 2: Create staging table
    CREATE TABLE ioe_stg.stg_device_activation_delta (
        -- =================================================================
        -- File Metadata Columns
        -- =================================================================
        file_batch_id UNIQUEIDENTIFIER NOT NULL,
        row_number_in_file INT,
        uploaded_by_user NVARCHAR(100),
        uploaded_ts DATETIMEOFFSET DEFAULT SYSDATETIMEOFFSET(),
        processing_status NVARCHAR(50) DEFAULT 'PENDING',      -- PENDING → VALIDATING → VALIDATED → TRANSFORMING → PROCESSED
        validation_status NVARCHAR(50) DEFAULT 'PENDING',      -- PENDING → VALIDATED → VALIDATION_ERROR
        error_message NVARCHAR(MAX),

        -- =================================================================
        -- CSV Fields (28 columns from actual source file)
        -- =================================================================

        -- Campaign Metadata (NEW - first columns in actual CSV)
        partner_name NVARCHAR(100),                            -- Always "Medical Guardian"
        campaign_name_source NVARCHAR(255),                    -- NEW: "Device Activation - Medicaid"

        -- Core Member Identity
        salesforce_account_id NVARCHAR(50),                    -- Primary Salesforce identifier (REQUIRED)
        salesforce_account_number NVARCHAR(50),                -- Secondary Salesforce identifier
        first_name NVARCHAR(100),
        last_name NVARCHAR(100),

        -- Contact Information
        primary_phone NVARCHAR(20),                            -- Will be auto-formatted to E.164 (+1 prefix)
        email NVARCHAR(255),

        -- Member Address (combined from 5 CSV fields during validation)
        service_address NVARCHAR(500),                         -- Combined: street, city, state zip
        city NVARCHAR(100),                                    -- From member_address_city
        state NVARCHAR(2),                                     -- From member_address_state
        zip NVARCHAR(10),                                      -- From member_address_zip
        address_country NVARCHAR(50),                          -- Country code (US, CA, etc.)

        -- Member Demographics
        dob DATE,                                              -- Date of birth
        timezone NVARCHAR(50),                                 -- Mapped to IANA format (America/New_York)
        language_pref NVARCHAR(10),                            -- Mapped to EN/ES/Other
        member_brand NVARCHAR(100),                            -- Member brand/plan (MedScope, MG State Pay, etc.)

        -- Device Information
        device_udi NVARCHAR(100),                              -- Device UDI/Serial Number (REQUIRED)
        device_name NVARCHAR(100),                             -- Device model name (MGMini, Mini Lite, etc.)
        brand NVARCHAR(100),                                   -- Device brand (MedScope, MG State Pay, etc.)
        device_phone_number NVARCHAR(20),                      -- Device's phone number (E.164)
        is_device_callable BIT,                                -- Can device be called? (1/0)

        -- Device Status (normalized to Title Case)
        fall_detection NVARCHAR(10),                           -- 'true'/'false' from CSV (lowercase)
        powersaver_mode NVARCHAR(50),                          -- 'Default'/'Standard'/'Battery Saver' (Title Case)

        -- Campaign Tracking (NEW columns from actual CSV)
        campaign_parameters NVARCHAR(MAX),                     -- NEW: JSON or text parameters
        monitoring_system_id NVARCHAR(100),                    -- NEW: Salesforce monitoring system ID
        enrollment_status NVARCHAR(20),                        -- ENROLL, UPDATE, UNENROLL
        unenrollment_reason NVARCHAR(255),                     -- NEW: Reason if unenrolled

        -- =================================================================
        -- Cleaned/Transformed Columns (populated during Phase 3: Validate)
        -- =================================================================
        first_name_clean NVARCHAR(100),                        -- Proper case
        last_name_clean NVARCHAR(100),                         -- Proper case
        primary_phone_clean NVARCHAR(20),                      -- Standardized E.164
        device_phone_clean NVARCHAR(20),                       -- Standardized E.164
        is_device_callable_clean BIT,                          -- Converted boolean
        timezone_clean NVARCHAR(50),                           -- Validated IANA timezone
        language_pref_clean NVARCHAR(10),                      -- Mapped to EN/ES/Other
        service_address_clean NVARCHAR(500),                   -- Combined from 5 address fields
        brand_clean NVARCHAR(100),                             -- Cleaned brand value
        org_id UNIQUEIDENTIFIER,                               -- Looked up from partner_name

        -- =================================================================
        -- Processing Timestamps
        -- =================================================================
        cleansing_started_ts DATETIMEOFFSET,                   -- Phase 3 start
        cleansing_completed_ts DATETIMEOFFSET,                 -- Phase 3 end
        enrollment_started_ts DATETIMEOFFSET,                  -- Phase 4 start
        enrollment_completed_ts DATETIMEOFFSET,                -- Phase 4 end

        -- =================================================================
        -- Tracking Columns (populated during Phase 4: Transform & Load)
        -- =================================================================
        member_id_processed UNIQUEIDENTIFIER,                  -- Member UUID from members table
        enrollment_id_processed UNIQUEIDENTIFIER,              -- Enrollment UUID from member_campaign_enrollments_enhanced

        -- =================================================================
        -- Constraints
        -- =================================================================
        PRIMARY KEY (file_batch_id, row_number_in_file),

        CONSTRAINT CHK_processing_status CHECK (
            processing_status IN ('PENDING', 'VALIDATING', 'VALIDATED', 'TRANSFORMING', 'PROCESSED', 'ERROR')
        ),

        CONSTRAINT CHK_validation_status CHECK (
            validation_status IN ('PENDING', 'VALIDATED', 'VALIDATION_ERROR')
        ),

        CONSTRAINT CHK_enrollment_status CHECK (
            enrollment_status IN ('ENROLL', 'UPDATE', 'UNENROLL', NULL)
        ),

        CONSTRAINT CHK_language_pref_clean CHECK (
            language_pref_clean IN ('EN', 'ES', 'Other', NULL)
        )
    );

    PRINT '✅ Table created successfully!'

    -- Step 3: Create indexes for efficient queries
    PRINT '📊 Creating indexes...'

    -- Index for file batch queries
    CREATE INDEX idx_stg_device_activation_file_batch
    ON ioe_stg.stg_device_activation_delta(file_batch_id, processing_status);

    PRINT '✅ Index created: idx_stg_device_activation_file_batch'

    -- Index for error tracking
    CREATE INDEX idx_stg_device_activation_error
    ON ioe_stg.stg_device_activation_delta(processing_status, uploaded_ts DESC)
    WHERE processing_status = 'ERROR';

    PRINT '✅ Index created: idx_stg_device_activation_error'

    -- Index for member lookup during transformation
    CREATE INDEX idx_stg_device_activation_member
    ON ioe_stg.stg_device_activation_delta(salesforce_account_number, org_id, processing_status);

    PRINT '✅ Index created: idx_stg_device_activation_member'

    PRINT ''
    PRINT '✅ STAGING TABLE CREATION COMPLETE'
    PRINT ''
    PRINT '📋 Table Details:'
    PRINT '   Schema: ioe_stg'
    PRINT '   Table: stg_device_activation_delta'
    PRINT '   Columns: 51 total (7 metadata + 28 CSV + 10 cleaned + 4 timestamps + 2 tracking)'
    PRINT '   Indexes: 3 created'
    PRINT '   Constraints: 4 CHECK constraints'
    PRINT ''
    PRINT '📝 Next Steps:'
    PRINT '   1. Verify table structure (query INFORMATION_SCHEMA.COLUMNS)'
    PRINT '   2. Test INSERT operation with sample data'
    PRINT '   3. Proceed to CSV file upload testing'
END

-- =====================================================================================
-- Usage Examples (Optional - Run Separately)
-- =====================================================================================

-- Example 1: Insert sample row
/*
DECLARE @file_batch_id UNIQUEIDENTIFIER = NEWID()

INSERT INTO ioe_stg.stg_device_activation_delta (
    file_batch_id,
    row_number_in_file,
    uploaded_by_user,
    processing_status,
    validation_status,
    partner_name,
    campaign_name_source,
    salesforce_account_id,
    salesforce_account_number,
    first_name,
    last_name,
    primary_phone,
    device_udi,
    enrollment_status
) VALUES (
    @file_batch_id,
    1,
    'AzureFunction',
    'PENDING',
    'PENDING',
    'Medical Guardian',
    'Device Activation - Medicaid',
    '001Uv00000I0JrdIAF',
    '7438599',
    'Alisha',
    'Stanford',
    '+16076440277',
    '530618496',
    'ENROLL'
);

SELECT * FROM ioe_stg.stg_device_activation_delta WHERE file_batch_id = @file_batch_id;
*/

-- Example 2: Query pending rows for processing
/*
SELECT
    file_batch_id,
    row_number_in_file,
    salesforce_account_id,
    first_name,
    last_name,
    device_udi,
    processing_status,
    validation_status,
    uploaded_ts
FROM ioe_stg.stg_device_activation_delta
WHERE validation_status = 'PENDING'
ORDER BY uploaded_ts DESC;
*/

-- Example 3: Update row to VALIDATED after cleansing
/*
UPDATE ioe_stg.stg_device_activation_delta
SET
    processing_status = 'VALIDATED',
    validation_status = 'VALIDATED',
    first_name_clean = 'Alisha',
    last_name_clean = 'Stanford',
    primary_phone_clean = '+16076440277',
    timezone_clean = 'America/New_York',
    language_pref_clean = 'EN',
    org_id = (SELECT org_id FROM ioe.orgs WHERE org_name = 'Medical Guardian'),
    cleansing_completed_ts = SYSDATETIMEOFFSET()
WHERE file_batch_id = '<file-batch-id>' AND validation_status = 'PENDING';
*/

-- Example 4: Query rows with errors
/*
SELECT
    file_batch_id,
    row_number_in_file,
    salesforce_account_id,
    first_name,
    error_message,
    uploaded_ts
FROM ioe_stg.stg_device_activation_delta
WHERE validation_status = 'VALIDATION_ERROR'
ORDER BY uploaded_ts DESC;
*/

-- Example 5: File batch statistics
/*
SELECT
    file_batch_id,
    COUNT(*) as total_rows,
    SUM(CASE WHEN processing_status = 'PROCESSED' THEN 1 ELSE 0 END) as processed,
    SUM(CASE WHEN validation_status = 'VALIDATION_ERROR' THEN 1 ELSE 0 END) as errors,
    MIN(uploaded_ts) as file_loaded_at,
    MAX(enrollment_completed_ts) as processing_completed_at
FROM ioe_stg.stg_device_activation_delta
GROUP BY file_batch_id
ORDER BY MIN(uploaded_ts) DESC;
*/

-- =====================================================================================
-- Processing Status Lifecycle
-- =====================================================================================
--
-- Status Flow:
-- 1. PENDING → Row inserted from CSV, waiting for validation
-- 2. VALIDATING → Python validation logic running
-- 3. VALIDATED → Row passed all validation checks, ready for transformation
-- 4. TRANSFORMING → MERGE/INSERT operations in progress
-- 5. PROCESSED → Successfully loaded into core tables (members, devices, enrollments)
-- 6. ERROR → Validation or transformation failed (see error_message column)
--
-- Validation Status Flow:
-- 1. PENDING → Row waiting for validation
-- 2. VALIDATED → All field validations passed
-- 3. VALIDATION_ERROR → One or more field validations failed (see error_message)
--
-- Processing Phases:
-- Phase 1: Extract (CSV → DataFrame) - Not tracked in this table
-- Phase 2: Load to Staging (INSERT with PENDING status)
-- Phase 3: Validate (UPDATE to VALIDATED, populate *_clean columns)
-- Phase 4: Transform & Load (UPDATE to PROCESSED, populate *_processed columns)
-- Phase 5: Audit & Log (File processing log, move file to processed folder)
--
-- =====================================================================================

-- =====================================================================================
-- Table Schema Notes
-- =====================================================================================
--
-- UPDATED: 2025-12-16 - Changed to match actual 27-column CSV format and Day 0 logic
--
-- Key Changes from Original Specification:
-- 1. REMOVED FIELDS:
--    - delivery_date (no longer needed - using first business day on or after enrollment_ts as Day 0)
--    - customer_type (not in actual CSV)
--
-- 2. NEW FIELDS (from actual CSV):
--    - campaign_name_source (source campaign name)
--    - campaign_parameters (JSON/text campaign config)
--    - monitoring_system_id (Salesforce monitoring system reference)
--    - unenrollment_reason (reason for unenrollment if applicable)
--
-- 3. RENAMED FIELDS (to match Python INSERT):
--    - member_first_name → first_name
--    - member_last_name → last_name
--    - member_phone_number → primary_phone
--    - member_email → email
--    - customer_timezone → timezone
--
-- 4. DATA TRANSFORMATION (during validation):
--    - Phone numbers: Auto-add +1 prefix if 10 digits
--    - Timezones: Map EST/CST/MST/PST → America/New_York, America/Chicago, etc.
--    - Language: Map English/Spanish/Korean → EN/ES/Other
--    - Address: Combine 5 fields (street, city, state, zip, country) → service_address
--    - Fall detection: Convert 1/0 → Active/Inactive
--    - Battery mode: Map "Standard" → "Good"
--
-- 5. ENROLLMENT DATE CALCULATION (FINAL - 2025-12-16):
--    - enrollment_ts = File upload timestamp (files accepted ANY day, including weekends/holidays)
--    - activation_start_date = First business day on or after enrollment_ts (Day 0)
--      * If Mon-Fri (business day) → activation_start_date = enrollment_ts date (same day)
--      * If Sat/Sun/Holiday → activation_start_date = next business day
--    - First call happens on Day 0 (activation_start_date)
--    - campaign_end_date = activation_start_date + 90 calendar days
--    - Call Schedule:
--      * Call 1: Day 0 (activation_start_date)
--      * Call 2: Day 2 (+2 business days from Call 1)
--      * Call 3: Day 4 (+2 business days from Call 2)
--      * Call 4: Day 9 (+5 business days from Call 3)
--      * Call 5+: Every 7 calendar days (weekly) until 90-day limit
--
-- 6. FIELD USAGE:
--    - partner_name: Always "Medical Guardian" for device activation
--    - campaign_name_source: "Device Activation - Medicaid" (from actual CSV)
--    - enrollment_status: ENROLL (new), UPDATE (existing), UNENROLL (remove)
--    - brand: From member_brand field (MedScope, MG State Pay, etc.)
--
-- =====================================================================================
