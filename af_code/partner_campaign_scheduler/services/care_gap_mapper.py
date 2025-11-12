import logging
from typing import Dict, Optional
from ...bland_ai_webhook.services.database_service import DatabaseService

logger = logging.getLogger(__name__)


class CareGapMapper:
    """
    Service to map care gap import flags to completion flag names

    Loads mappings from [engage360].[care_gaps] table on initialization.
    Used to add completion flag fields to Bland AI request_data.
    """

    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        self.care_gap_mapping = {}
        self._load_care_gap_mapping()

    def _load_care_gap_mapping(self):
        """
        Load care gap to completion flag mapping from database

        Query: SELECT csv_import_flag_name, completion_flag_name
               FROM [engage360].[care_gaps]
        """
        logger.info("🔧 [CARE-GAP-MAPPER] Loading care gap mappings from database...")

        query = """
            SELECT
                csv_import_flag_name,
                completion_flag_name
            FROM engage360.care_gaps
        """

        try:
            results = self.db_service.execute_query(query, fetch_results=True)

            # Build mapping dictionary
            for row in results:
                csv_flag = row["csv_import_flag_name"]
                completion_flag = row["completion_flag_name"]
                self.care_gap_mapping[csv_flag] = completion_flag

            logger.info(
                f"✅ [CARE-GAP-MAPPER] Loaded {len(self.care_gap_mapping)} care gap mappings"
            )
            logger.info(
                f"📊 [CARE-GAP-MAPPER] Available mappings: {list(self.care_gap_mapping.keys())}"
            )

            # Log first few mappings as examples
            if self.care_gap_mapping:
                sample_mappings = list(self.care_gap_mapping.items())[:3]
                for csv_flag, completion_flag in sample_mappings:
                    logger.info(f"   📌 {csv_flag} → {completion_flag}")

        except Exception as e:
            logger.error(f"🚨 [CARE-GAP-MAPPER] Failed to load care gap mappings: {str(e)}")
            import traceback

            logger.error(f"🚨 [CARE-GAP-MAPPER] Traceback: {traceback.format_exc()}")
            # Initialize empty mapping to prevent crashes
            self.care_gap_mapping = {}

    def get_completion_flag_name(self, csv_import_flag_name: str) -> Optional[str]:
        """
        Get completion flag name for a given import flag

        Args:
            csv_import_flag_name: e.g., "awv_import_flag"

        Returns:
            completion_flag_name: e.g., "awv_completed"
        """
        return self.care_gap_mapping.get(csv_import_flag_name)

    def get_all_mappings(self) -> Dict[str, str]:
        """Get all care gap mappings"""
        return self.care_gap_mapping.copy()
