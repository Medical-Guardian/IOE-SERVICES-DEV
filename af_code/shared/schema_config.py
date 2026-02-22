"""
Schema configuration for IOE Azure Functions.
Reads DB_SCHEMA and DB_SCHEMA_STG from environment variables at module import time.
Defaults maintain backward compatibility with existing deployments.

Usage:
    from af_code.shared.schema_config import IOE_SCHEMA, IOE_SCHEMA_STG
    query = f"SELECT * FROM {IOE_SCHEMA}.members WHERE member_id = %s"
"""

import logging
import os

logger = logging.getLogger(__name__)

IOE_SCHEMA: str = os.environ.get("DB_SCHEMA", "ioe")
IOE_SCHEMA_STG: str = os.environ.get("DB_SCHEMA_STG", "ioe_stg")

logger.info(f"[SCHEMA-CONFIG] Loaded schemas: main='{IOE_SCHEMA}', staging='{IOE_SCHEMA_STG}'")
