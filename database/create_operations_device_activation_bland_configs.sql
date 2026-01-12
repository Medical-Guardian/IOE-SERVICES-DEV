-- =====================================================================================
-- Script: Create Bland AI Configuration for Operations Device Activation Campaigns
-- Purpose: Configure Bland AI parameters for Medicaid and DTC/MA campaigns
-- Date: 2025-12-18
-- Campaign Type: Operations
-- =====================================================================================

-- =====================================================================================
-- ✅ ACTUAL VALUES PROVIDED - Ready to run!
-- =====================================================================================
-- pathway_id: 323f8d52-6e30-459c-9f71-e395b3c3ba69 (Device Activation pathway)
-- voice: bc97a31e-b0b8-49e5-bcb8-393fcc6a86ea (Grace voice)
-- webhook: https://ioe-function-e2g7e6d4e6hme4ge.eastus2-01.azurewebsites.net/api/bland-ai-webhook
-- =====================================================================================

-- =====================================================================================
-- STEP 1: Verify campaigns exist
-- =====================================================================================
SELECT campaign_id, name, campaign_type, operating_start_time, operating_end_time, timezone_flag, status
FROM engage360.campaigns_enhanced
WHERE campaign_id IN (
    '0F69659B-491B-40E2-88C3-ABC7D87385B2',  -- Device Activation - Medicaid
    'BA865458-60F9-4EBB-9FB5-D195B532CF5A'   -- Device Activation - DTC/MA
);

-- Expected output: 2 rows
-- Verify:
-- - Both campaigns have campaign_type = 'Operations'
-- - operating_start_time = '09:00:00'
-- - operating_end_time = '17:00:00' (5 PM)
-- - timezone_flag = 'member_tz'
-- - status = 'Active'

GO

-- =====================================================================================
-- STEP 2: Check if Bland AI configs already exist
-- =====================================================================================
SELECT
    cc.config_id,
    cc.campaign_id,
    c.name AS campaign_name,
    cc.config_status,
    cc.created_ts,
    cc.bland_parameters_global
FROM engage360.campaign_call_configs_enhanced cc
JOIN engage360.campaigns_enhanced c ON cc.campaign_id = c.campaign_id
WHERE cc.campaign_id IN (
    '0F69659B-491B-40E2-88C3-ABC7D87385B2',
    'BA865458-60F9-4EBB-9FB5-D195B532CF5A'
);

-- If this returns any rows, configs already exist
-- You may want to UPDATE instead of INSERT

GO

-- =====================================================================================
-- STEP 3: Insert Bland AI Config for Device Activation - Medicaid
-- =====================================================================================

INSERT INTO engage360.campaign_call_configs_enhanced (
    config_id,
    campaign_id,
    bland_parameters_global,
    config_status,
    created_ts
) VALUES (
    NEWID(),
    '0F69659B-491B-40E2-88C3-ABC7D87385B2',  -- Device Activation - Medicaid
    '{
        "from": "+18336000078",
        "model": "base",
        "voice": "bc97a31e-b0b8-49e5-bcb8-393fcc6a86ea",
        "record": true,
        "endpoint": "https://api.bland.ai",
        "language": "auto",
        "pathway_id": "323f8d52-6e30-459c-9f71-e395b3c3ba69",
        "pathway_version": 0,
        "max_duration": 12,
        "background_track": "office",
        "voicemail_action": "leave_message",
        "voicemail_message": "Hi there, this is Grace calling from Medical Guardian. I''m trying to reach {{first_name}} {{last_name}} to assist with device activation. I''ll try calling back later, goodbye!",
        "wait_for_greeting": false,
        "noise_cancellation": true,
        "answered_by_enabled": true,
        "block_interruptions": false,
        "interruption_threshold": 400,
        "sensitive_voicemail_detection": true,
        "use_batch": true,
        "timezone": "America/New_York",
        "webhook": "https://ioe-function-e2g7e6d4e6hme4ge.eastus2-01.azurewebsites.net/api/bland-ai-webhook?code=3IlwYsB3O4Ie8jcZegOouI_Fj1nf4N-5K_cGMJpmQBy8AzFuR9syPQ%3D%3D",
        "request_data": {},
        "metadata": {}
    }',
    'active',
    SYSDATETIMEOFFSET()
);

GO

-- =====================================================================================
-- STEP 4: Insert Bland AI Config for Device Activation - DTC/MA
-- =====================================================================================

INSERT INTO engage360.campaign_call_configs_enhanced (
    config_id,
    campaign_id,
    bland_parameters_global,
    config_status,
    created_ts
) VALUES (
    NEWID(),
    'BA865458-60F9-4EBB-9FB5-D195B532CF5A',  -- Device Activation - DTC/MA
    '{
        "from": "+18336000078",
        "model": "base",
        "voice": "bc97a31e-b0b8-49e5-bcb8-393fcc6a86ea",
        "record": true,
        "endpoint": "https://api.bland.ai",
        "language": "auto",
        "pathway_id": "323f8d52-6e30-459c-9f71-e395b3c3ba69",
        "pathway_version": 0,
        "max_duration": 12,
        "background_track": "office",
        "voicemail_action": "leave_message",
        "voicemail_message": "Hi there, this is Grace calling from Medical Guardian. I''m trying to reach {{first_name}} {{last_name}} to assist with device activation. I''ll try calling back later, goodbye!",
        "wait_for_greeting": false,
        "noise_cancellation": true,
        "answered_by_enabled": true,
        "block_interruptions": false,
        "interruption_threshold": 400,
        "sensitive_voicemail_detection": true,
        "use_batch": true,
        "timezone": "America/New_York",
        "webhook": "https://ioe-function-e2g7e6d4e6hme4ge.eastus2-01.azurewebsites.net/api/bland-ai-webhook?code=3IlwYsB3O4Ie8jcZegOouI_Fj1nf4N-5K_cGMJpmQBy8AzFuR9syPQ%3D%3D",
        "request_data": {},
        "metadata": {}
    }',
    'active',
    SYSDATETIMEOFFSET()
);

GO

-- =====================================================================================
-- STEP 5: Verify configs were created successfully
-- =====================================================================================

SELECT
    cc.config_id,
    c.name AS campaign_name,
    cc.config_status,
    JSON_VALUE(cc.bland_parameters_global, '$.pathway_id') AS pathway_id,
    JSON_VALUE(cc.bland_parameters_global, '$.voice_id') AS voice_id,
    JSON_VALUE(cc.bland_parameters_global, '$.webhook_url') AS webhook_url,
    JSON_VALUE(cc.bland_parameters_global, '$.max_duration') AS max_duration,
    cc.created_ts
FROM engage360.campaign_call_configs_enhanced cc
JOIN engage360.campaigns_enhanced c ON cc.campaign_id = c.campaign_id
WHERE cc.campaign_id IN (
    '0F69659B-491B-40E2-88C3-ABC7D87385B2',
    'BA865458-60F9-4EBB-9FB5-D195B532CF5A'
)
ORDER BY c.name;

-- Expected output: 2 rows
-- Verify:
-- - pathway_id is NOT 'TODO_DEVICE_ACTIVATION_MEDICAID_PATHWAY' (should be actual value)
-- - voice_id is NOT 'TODO_GRACE_VOICE_ID' (should be actual value)
-- - webhook_url = 'https://ioe-function.azurewebsites.net/api/bland_ai_webhook'
-- - config_status = 'active'

GO

-- =====================================================================================
-- ALTERNATIVE: If you need to UPDATE existing configs instead of INSERT
-- =====================================================================================

/*
-- =====================================================================================
-- NOTE: User has already manually added these configurations to the database!
-- =====================================================================================
-- The configs below were manually inserted with these actual values:
-- - pathway_id: 323f8d52-6e30-459c-9f71-e395b3c3ba69
-- - voice: bc97a31e-b0b8-49e5-bcb8-393fcc6a86ea
-- - webhook: https://ioe-function-e2g7e6d4e6hme4ge.eastus2-01.azurewebsites.net/api/bland-ai-webhook
--
-- Use UPDATE queries below only if you need to modify existing configs
-- =====================================================================================

UPDATE engage360.campaign_call_configs_enhanced
SET
    bland_parameters_global = '{
        "from": "+18336000078",
        "model": "base",
        "voice": "bc97a31e-b0b8-49e5-bcb8-393fcc6a86ea",
        "record": true,
        "endpoint": "https://api.bland.ai",
        "language": "auto",
        "pathway_id": "323f8d52-6e30-459c-9f71-e395b3c3ba69",
        "pathway_version": 0,
        "max_duration": 12,
        "background_track": "office",
        "voicemail_action": "leave_message",
        "voicemail_message": "Hi there, this is Grace calling from Medical Guardian. I''m trying to reach {{first_name}} {{last_name}} to assist with device activation. I''ll try calling back later, goodbye!",
        "wait_for_greeting": false,
        "noise_cancellation": true,
        "answered_by_enabled": true,
        "block_interruptions": false,
        "interruption_threshold": 400,
        "sensitive_voicemail_detection": true,
        "use_batch": true,
        "timezone": "America/New_York",
        "webhook": "https://ioe-function-e2g7e6d4e6hme4ge.eastus2-01.azurewebsites.net/api/bland-ai-webhook?code=3IlwYsB3O4Ie8jcZegOouI_Fj1nf4N-5K_cGMJpmQBy8AzFuR9syPQ%3D%3D",
        "request_data": {},
        "metadata": {}
    }',
    config_status = 'active',
    updated_ts = SYSDATETIMEOFFSET()
WHERE campaign_id = '0F69659B-491B-40E2-88C3-ABC7D87385B2';

UPDATE engage360.campaign_call_configs_enhanced
SET
    bland_parameters_global = '{
        "from": "+18336000078",
        "model": "base",
        "voice": "bc97a31e-b0b8-49e5-bcb8-393fcc6a86ea",
        "record": true,
        "endpoint": "https://api.bland.ai",
        "language": "auto",
        "pathway_id": "323f8d52-6e30-459c-9f71-e395b3c3ba69",
        "pathway_version": 0,
        "max_duration": 12,
        "background_track": "office",
        "voicemail_action": "leave_message",
        "voicemail_message": "Hi there, this is Grace calling from Medical Guardian. I''m trying to reach {{first_name}} {{last_name}} to assist with device activation. I''ll try calling back later, goodbye!",
        "wait_for_greeting": false,
        "noise_cancellation": true,
        "answered_by_enabled": true,
        "block_interruptions": false,
        "interruption_threshold": 400,
        "sensitive_voicemail_detection": true,
        "use_batch": true,
        "timezone": "America/New_York",
        "webhook": "https://ioe-function-e2g7e6d4e6hme4ge.eastus2-01.azurewebsites.net/api/bland-ai-webhook?code=3IlwYsB3O4Ie8jcZegOouI_Fj1nf4N-5K_cGMJpmQBy8AzFuR9syPQ%3D%3D",
        "request_data": {},
        "metadata": {}
    }',
    config_status = 'active',
    updated_ts = SYSDATETIMEOFFSET()
WHERE campaign_id = 'BA865458-60F9-4EBB-9FB5-D195B532CF5A';
*/

GO

-- =====================================================================================
-- NOTES:
-- =====================================================================================
-- 1. pathway_id: Bland AI pathway that defines the conversation flow for device activation
-- 2. voice_id: The AI voice to use (e.g., "maya", "grace", "ryan", etc.)
-- 3. webhook_url: Where Bland AI will send call results
-- 4. max_duration: Maximum call length in seconds (600 = 10 minutes)
-- 5. wait_for_greeting: AI waits for person to speak first before starting
-- 6. record: Record all calls for quality assurance
-- 7. voicemail_action: What to do if voicemail detected ("hangup" = don't leave message)
-- 8. interruption_threshold: How sensitive AI is to interruptions (100 = normal)
-- 9. temperature: AI creativity level (0.7 = balanced)
-- 10. language: Primary language for the call ("en" = English)
-- =====================================================================================

-- =====================================================================================
-- BEFORE RUNNING THIS SCRIPT:
-- =====================================================================================
-- 1. Get actual pathway_id values from Bland AI dashboard
-- 2. Get actual voice_id from Bland AI dashboard
-- 3. Replace all TODO placeholders in the JSON above
-- 4. Verify the webhook URL is correct for your environment
-- 5. Run STEP 1 and STEP 2 first to understand current state
-- =====================================================================================
