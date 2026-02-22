-- =====================================================================================
-- Diagnostic Query: Check Device Activation Campaign Configuration
-- =====================================================================================
-- Purpose: Verify if configuration exists and check for placeholder values
-- Run this FIRST to understand current state
-- =====================================================================================

PRINT '🔍 Checking Device Activation campaign configurations...';
PRINT '';

-- Check if campaigns exist
PRINT '📋 Step 1: Verify campaigns exist in campaigns_enhanced';
SELECT
    campaign_id,
    name,
    campaign_type,
    status,
    created_ts
FROM engage360.campaigns_enhanced
WHERE name IN ('Device Activation - DTC/MA', 'Device Activation - Medicaid')
ORDER BY name;

PRINT '';
PRINT '📋 Step 2: Check existing call configurations';

-- Check existing configurations
SELECT
    c.name AS campaign_name,
    c.campaign_id,
    cc.config_id,
    cc.call_type,
    cc.config_name,
    cc.bland_parameters_global,
    cc.config_status,
    cc.created_ts
FROM engage360.campaign_call_configs_enhanced cc
JOIN engage360.campaigns_enhanced c ON cc.campaign_id = c.campaign_id
WHERE c.name IN ('Device Activation - DTC/MA', 'Device Activation - Medicaid')
ORDER BY c.name, cc.config_status DESC;

PRINT '';
PRINT '⚠️  If no rows returned in Step 2, configuration needs to be created';
PRINT '⚠️  If pathway_id shows YOUR_PATHWAY_ID_HERE, placeholders need replacing';
PRINT '';

-- Check for placeholder values
PRINT '📋 Step 3: Check for placeholder values that need replacing';
SELECT
    c.name AS campaign_name,
    CASE
        WHEN cc.bland_parameters_global LIKE '%YOUR_PATHWAY_ID_HERE%' THEN '❌ NEEDS PATHWAY_ID'
        ELSE '✅ Pathway ID configured'
    END AS pathway_status,
    CASE
        WHEN cc.bland_parameters_global LIKE '%YOUR_VOICE_ID_HERE%' THEN '❌ NEEDS VOICE_ID'
        ELSE '✅ Voice ID configured'
    END AS voice_status,
    cc.config_status
FROM engage360.campaign_call_configs_enhanced cc
JOIN engage360.campaigns_enhanced c ON cc.campaign_id = c.campaign_id
WHERE c.name IN ('Device Activation - DTC/MA', 'Device Activation - Medicaid')
ORDER BY c.name;

PRINT '';
PRINT '✅ Diagnostic complete';
