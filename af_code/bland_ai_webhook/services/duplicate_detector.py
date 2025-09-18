import logging
from .config_manager import ConfigManager
from .database_service import DatabaseService

logger = logging.getLogger(__name__)


class DuplicateDetector:
    """
    Detects and prevents processing of duplicate webhook payloads by checking
    for the existence of a call_id in the database.

    This service relies on the centralized DatabaseService for all database
    interactions, ensuring consistent and reliable data access.
    """

    def __init__(self, config_manager: ConfigManager, db_service: DatabaseService):
        """
        Initializes the DuplicateDetector with required service dependencies.

        Args:
            config_manager: The application's configuration manager.
            db_service: The centralized service for database operations.
        """
        self.config_manager = config_manager
        self.db_service = db_service
        self.call_log_table = self.config_manager.get_config("CALL_LOG_TABLE", "engage360.bland_call_logs")
        logger.info(f"🔍 [DUPLICATE-DETECTOR] Initialized to use DatabaseService for checks.")
        logger.info(f"   - Target Table: {self.call_log_table}")

    def check_duplicate(self, call_id: str) -> bool:
        """
        Checks if a webhook with the given call_id has already been processed.

        This method queries the database via the DatabaseService. It performs a
        simple, efficient existence check, which is the most reliable method for
        preventing duplicate processing, as call_ids should be globally unique.

        Args:
            call_id: The unique call identifier from the webhook payload.

        Returns:
            bool: True if the call_id already exists (is a duplicate), False otherwise.
        """
        if not call_id:
            logger.warning("⚠️ [DUPLICATE-DETECTOR] Received an empty or null call_id to check.")
            return False  # Cannot be a duplicate if the ID is invalid.

        logger.info(f"🔍 [DUPLICATE-DETECTOR] Checking for duplicate call_id: {call_id}")

        try:
            # This query is designed to be fast. We only need to know if at least one
            # record exists, so we select a single, indexed column.
            # NOTE: Using '%s' as the parameter marker, which is correct for pymssql.
            query = f"SELECT call_id FROM {self.call_log_table} WHERE call_id = %s"

            # Use the injected DatabaseService to execute the query.
            # fetch_results=True ensures we get back a list of rows if found.
            result = self.db_service.execute_query(query, (call_id,), fetch_results=True)

            # If the result is not None and not an empty list, a record was found.
            if result:
                logger.warning(
                    f"🚨 [DUPLICATE-DETECTOR] Duplicate detected. Call ID '{call_id}' already exists in the database.")
                return True
            else:
                logger.info(f"✅ [DUPLICATE-DETECTOR] No duplicate found for call_id: {call_id}. Proceeding.")
                return False

        except Exception as e:
            # If any database error occurs, we must log it thoroughly.
            # To ensure system resilience, we "fail open" by assuming it is NOT a
            # duplicate. This prevents a database outage from blocking all incoming webhooks.
            logger.error(
                f"💥 [DUPLICATE-DETECTOR] Database error during duplicate check for call_id '{call_id}': {str(e)}")
            logger.warning("   - Fail-safe engaged: Assuming NOT a duplicate to avoid blocking processing.")
            return False
