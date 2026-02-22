# This file contains static configuration values and SQL queries for the application.
# Secrets and environment-specific settings are managed by the ConfigManager.

from af_code.shared.schema_config import IOE_SCHEMA

ERROR_LOG_TABLE = f"{IOE_SCHEMA}.error_log"
# API Endpoints
BLAND_AI_BATCH_URL = "https://api.bland.ai/v2/batches/create"

# SQL Queries (using ? for pyodbc parameter binding)
GET_CAMPAIGN_CONFIG_QUERY = f"""
    SELECT bland_parameters_global, call_type
    FROM {IOE_SCHEMA}.campaign_call_configs_enhanced
    WHERE campaign_id = ? AND config_status = 'active'
"""

CREATE_BATCH_QUERY = f"""
    INSERT INTO {IOE_SCHEMA}.outreach_batches
    (batch_id, campaign_id, batch_status, total_calls_intended, created_ts)
    VALUES (?, ?, 'Pending', ?, SYSDATETIMEOFFSET())
"""

# Add other queries here...
