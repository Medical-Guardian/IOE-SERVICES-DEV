-- Add transfer_phone_number to staging table
USE engage360_stg;

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360_stg'
      AND TABLE_NAME = 'stg_device_activation_delta'
      AND COLUMN_NAME = 'transfer_phone_number'
)
BEGIN
    ALTER TABLE engage360_stg.stg_device_activation_delta
    ADD transfer_phone_number VARCHAR(20) NULL;
    PRINT 'Column transfer_phone_number added to stg_device_activation_delta';
END
ELSE
    PRINT 'Column transfer_phone_number already exists in stg_device_activation_delta';

-- Add transfer_phone_number to core table
USE engage360;

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'engage360'
      AND TABLE_NAME = 'member_campaign_enrollments_enhanced'
      AND COLUMN_NAME = 'transfer_phone_number'
)
BEGIN
    ALTER TABLE engage360.member_campaign_enrollments_enhanced
    ADD transfer_phone_number VARCHAR(20) NULL;
    PRINT 'Column transfer_phone_number added to member_campaign_enrollments_enhanced';
END
ELSE
    PRINT 'Column transfer_phone_number already exists in member_campaign_enrollments_enhanced';

-- Verification
SELECT 'Staging table verification:';
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360_stg'
  AND TABLE_NAME = 'stg_device_activation_delta'
  AND COLUMN_NAME = 'transfer_phone_number';

SELECT 'Core table verification:';
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'engage360'
  AND TABLE_NAME = 'member_campaign_enrollments_enhanced'
  AND COLUMN_NAME = 'transfer_phone_number';
