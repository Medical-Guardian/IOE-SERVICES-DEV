# This file contains static configuration values and SQL queries for the application.
# Secrets and environment-specific settings are managed by the ConfigManager.

ERROR_LOG_TABLE = "engage360.error_log"
# API Endpoints
BLAND_AI_BATCH_URL = "https://api.bland.ai/v2/batches/create"

# SQL Queries (using %s for pymssql parameter binding)
GET_CAMPAIGN_CONFIG_QUERY = """
    SELECT bland_parameters_global, call_type
    FROM engage360.campaign_call_configs_enhanced 
    WHERE campaign_id = %s AND config_status = 'active'
"""

CREATE_BATCH_QUERY = """
    INSERT INTO engage360.outreach_batches 
    (batch_id, campaign_id, batch_status, total_calls_intended, created_ts)
    VALUES (%s, %s, 'Pending', %s, SYSDATETIMEOFFSET())
"""

# Add other queries here...
