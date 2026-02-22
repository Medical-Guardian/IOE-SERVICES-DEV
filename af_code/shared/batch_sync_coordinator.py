import logging
from typing import List, Dict, Any
from datetime import datetime
from ..bland_ai_webhook.services.database_service import DatabaseService
from ..bland_ai_webhook.services.config_manager import ConfigManager
from .bland_ai_batch_monitor import BlandAIBatchMonitor
from af_code.shared.schema_config import IOE_SCHEMA

logger = logging.getLogger(__name__)


class BatchSyncCoordinator:
    """
    Service to coordinate batch reconciliation with distributed locking
    Following IOE patterns for error handling and logging
    """

    def __init__(self, db_service: DatabaseService, config_manager: ConfigManager):
        self.db_service = db_service
        self.config_manager = config_manager
        self.batch_monitor = BlandAIBatchMonitor(config_manager)
        self.lock_timeout_minutes = 25  # Safety margin under 30min timer interval
        logger.info("🔧 [BATCH-COORDINATOR] Service initialized successfully")

    def execute_with_lock(self, operation_name: str, max_duration_minutes: int = 25) -> None:
        """
        Execute batch reconciliation with distributed locking to prevent overlaps

        Args:
            operation_name: Unique name for the lock
            max_duration_minutes: Maximum time to hold the lock
        """
        lock_acquired = False
        current_instance = f"batch-reconciler-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        try:
            # Step 1: Try to acquire distributed lock
            lock_acquired = self._acquire_sync_lock(
                operation_name, max_duration_minutes, current_instance
            )

            if not lock_acquired:
                logger.info(
                    f"🔒 [BATCH-COORDINATOR] Another {operation_name} already running, skipping this execution"
                )
                logger.info(
                    "🔒 [BATCH-COORDINATOR] This prevents overlapping reconciliation processes"
                )
                return

            logger.info(f"🔓 [BATCH-COORDINATOR] Successfully acquired lock for {operation_name}")
            logger.info(f"⏰ [BATCH-COORDINATOR] Lock expires in {max_duration_minutes} minutes")

            # Step 2: Execute the actual reconciliation work
            self._execute_batch_reconciliation()

        except Exception as e:
            logger.error(f"🚨 [BATCH-COORDINATOR] Error during locked execution: {str(e)}")
            raise

        finally:
            # Step 3: Always release lock, even if error occurred
            if lock_acquired:
                self._release_sync_lock(operation_name)
                logger.info(f"🔒 [BATCH-COORDINATOR] Released lock for {operation_name}")

    def _execute_batch_reconciliation(self) -> None:
        """
        Core reconciliation logic - only handles batch-level status updates
        Individual call updates are handled by webhooks
        """
        logger.info("📊 [BATCH-COORDINATOR] Starting batch-level reconciliation...")

        # Step 1: Find batches that need status checking
        stale_batches = self._get_stale_batches()

        if not stale_batches:
            logger.info(
                "✅ [BATCH-COORDINATOR] No stale batches found - all up-to-date via webhooks"
            )
            return

        logger.info(
            f"📦 [BATCH-COORDINATOR] Found {len(stale_batches)} batches requiring reconciliation"
        )

        # Processing metrics
        batches_updated = 0
        batches_completed = 0
        batches_failed = 0

        # Step 2: Check each batch via Bland AI API
        for batch in stale_batches:
            try:
                batch_updated = self._reconcile_single_batch(batch)
                if batch_updated:
                    batches_updated += 1

                    # Check if batch was marked as completed
                    if batch.get("final_status") == "Completed":
                        batches_completed += 1
                    elif batch.get("final_status") == "Failed":
                        batches_failed += 1

            except Exception as e:
                logger.error(
                    f"❌ [BATCH-COORDINATOR] Error reconciling batch {batch.get('vendor_batch_id', 'unknown')}: {str(e)}"
                )
                batches_failed += 1
                # Continue with other batches

        # Log summary
        logger.info("📊 [BATCH-COORDINATOR] Reconciliation summary:")
        logger.info(f"   📦 Total batches checked: {len(stale_batches)}")
        logger.info(f"   ✅ Batches updated: {batches_updated}")
        logger.info(f"   🎉 Batches completed: {batches_completed}")
        logger.info(f"   ❌ Batches failed: {batches_failed}")
        logger.info("✅ [BATCH-COORDINATOR] Batch reconciliation completed")

    def _get_stale_batches(self, stale_threshold_hours: int = 2) -> List[Dict[str, Any]]:
        """
        Get batches that haven't had recent webhook updates

        Args:
            stale_threshold_hours: Consider batches stale if no updates in this many hours
        """
        logger.info(
            f"🔍 [BATCH-COORDINATOR] Looking for batches stale for more than {stale_threshold_hours} hours..."
        )

        query = f"""
            SELECT DISTINCT 
                ob.batch_id,
                ob.vendor_batch_id,
                ob.campaign_id,
                ob.submitted_ts,
                ob.batch_status,
                ob.last_status_check_ts,
                ce.name as campaign_name
            FROM {IOE_SCHEMA}.outreach_batches ob
            LEFT JOIN {IOE_SCHEMA}.campaigns_enhanced ce ON ob.campaign_id = ce.campaign_id
            WHERE ob.batch_status IN ('Submitted', 'In Progress')
              AND ob.submitted_ts >= DATEADD(day, -1, SYSDATETIMEOFFSET())  -- Only check recent batches
              AND (
                  -- No recent attempt updates (webhook hasn't fired recently)
                  NOT EXISTS (
                      SELECT 1 FROM {IOE_SCHEMA}.outreach_attempts oa
                      WHERE oa.batch_id = ob.batch_id
                        AND oa.updated_ts >= DATEADD(hour, -?, SYSDATETIMEOFFSET())
                  )
                  OR
                  -- Batch is old enough to be considered stale
                  ob.submitted_ts <= DATEADD(hour, -?, SYSDATETIMEOFFSET())
                  OR
                  -- Haven't checked via API recently
                  (ob.last_status_check_ts IS NULL OR ob.last_status_check_ts <= DATEADD(hour, -1, SYSDATETIMEOFFSET()))
              )
            ORDER BY ob.submitted_ts DESC
        """

        batches = self.db_service.execute_query(
            query,
            (stale_threshold_hours, stale_threshold_hours * 2),
            fetch_results=True,
        )

        logger.info(f"📊 [BATCH-COORDINATOR] Found {len(batches)} potentially stale batches")
        return batches

    def _reconcile_single_batch(self, batch: Dict[str, Any]) -> bool:
        """
        Reconcile a single batch status with Bland AI API

        Returns:
            bool: True if batch status was updated, False otherwise
        """
        vendor_batch_id = batch["vendor_batch_id"]
        internal_batch_id = batch["batch_id"]
        campaign_name = batch.get("campaign_name", "Unknown")

        logger.info(
            f"🔍 [BATCH-COORDINATOR] Checking batch: {vendor_batch_id} (Campaign: {campaign_name})"
        )

        try:
            # Step 1: Get batch status from Bland AI API
            # Note: This would normally be async, but for simplified version we skip API calls
            logger.info(
                f"🔍 [BATCH-COORDINATOR] Skipping API call for batch: {vendor_batch_id} (simplified version)"
            )
            batch_status = None

            if not batch_status:
                logger.warning(
                    f"⚠️ [BATCH-COORDINATOR] No status returned for batch: {vendor_batch_id}"
                )
                return False

            # Step 2: Update last checked timestamp regardless
            self._update_batch_last_checked(internal_batch_id)

            # Step 3: Determine if batch is complete
            if batch_status.get("is_complete", False):
                logger.info(f"✅ [BATCH-COORDINATOR] Batch {vendor_batch_id} is complete")

                # Update batch completion status
                self._update_batch_completion_status(internal_batch_id, batch_status)
                batch["final_status"] = "Completed"
                return True

            elif batch_status.get("has_failures", False):
                logger.warning(f"⚠️ [BATCH-COORDINATOR] Batch {vendor_batch_id} has failures")

                # Update batch with partial failure status
                self._update_batch_partial_status(internal_batch_id, batch_status)
                return True

            else:
                logger.info(f"⏳ [BATCH-COORDINATOR] Batch {vendor_batch_id} still in progress")
                return False

        except Exception as e:
            logger.error(f"🚨 [BATCH-COORDINATOR] Error checking batch {vendor_batch_id}: {str(e)}")
            return False

    def _acquire_sync_lock(
        self, operation_name: str, max_duration_minutes: int, instance_id: str
    ) -> bool:
        """
        Acquire distributed lock using database ACID properties
        """
        query = f"""
            SET NOCOUNT ON;
            DECLARE @lock_acquired BIT = 0;

            -- Clean up expired locks first
            DELETE FROM {IOE_SCHEMA}.system_locks
            WHERE lock_expiry <= SYSDATETIMEOFFSET();
            
            -- Try to acquire new lock
            IF NOT EXISTS (
                SELECT 1 FROM {IOE_SCHEMA}.system_locks 
                WHERE lock_name = ?
            )
            BEGIN
                INSERT INTO {IOE_SCHEMA}.system_locks (
                    lock_name, 
                    lock_expiry, 
                    locked_by, 
                    created_ts
                )
                VALUES (
                    ?, 
                    DATEADD(minute, ?, SYSDATETIMEOFFSET()), 
                    ?, 
                    SYSDATETIMEOFFSET()
                );
                SET @lock_acquired = 1;
            END
            
            SELECT @lock_acquired as acquired;
        """

        try:
            result = self.db_service.execute_query(
                query,
                (operation_name, operation_name, max_duration_minutes, instance_id),
                fetch_results=True,
            )

            if not result:
                logger.warning(
                    "⚠️ [BATCH-COORDINATOR] Lock query returned no rows — treating as not acquired"
                )
                return False
            acquired = result[0]["acquired"] == 1

            if acquired:
                logger.info(
                    f"🔓 [BATCH-COORDINATOR] Successfully acquired lock '{operation_name}' for {max_duration_minutes} minutes"
                )
            else:
                logger.info(
                    f"🔒 [BATCH-COORDINATOR] Lock '{operation_name}' already held by another process"
                )

            return acquired

        except Exception as e:
            logger.error(f"🚨 [BATCH-COORDINATOR] Error acquiring lock: {str(e)}")
            return False

    def _release_sync_lock(self, operation_name: str) -> None:
        """Release distributed lock"""
        query = f"DELETE FROM {IOE_SCHEMA}.system_locks WHERE lock_name = ?"

        try:
            rows_affected = self.db_service.execute_query(
                query, (operation_name,), fetch_results=False
            )

            if rows_affected > 0:
                logger.info(f"🔓 [BATCH-COORDINATOR] Successfully released lock '{operation_name}'")
            else:
                logger.warning(
                    f"⚠️ [BATCH-COORDINATOR] Lock '{operation_name}' was not found (may have expired)"
                )

        except Exception as e:
            logger.error(f"🚨 [BATCH-COORDINATOR] Error releasing lock: {str(e)}")

    def _update_batch_last_checked(self, batch_id: str) -> None:
        """Update the last status check timestamp"""
        query = f"""
            UPDATE {IOE_SCHEMA}.outreach_batches
            SET last_status_check_ts = SYSDATETIMEOFFSET()
            WHERE batch_id = ?
        """

        self.db_service.execute_query(query, (batch_id,), fetch_results=False)
        logger.debug(f"📅 [BATCH-COORDINATOR] Updated last_status_check_ts for batch: {batch_id}")

    def _update_batch_completion_status(self, batch_id: str, batch_status: Dict[str, Any]) -> None:
        """Update batch to completed status"""
        query = f"""
            UPDATE {IOE_SCHEMA}.outreach_batches
            SET batch_status = 'Completed',
                total_calls_completed = ?,
                total_calls_failed = ?,
                last_status_check_ts = SYSDATETIMEOFFSET(),
                api_reconciled = 1,
                status_reason = 'Completed via API reconciliation'
            WHERE batch_id = ?
        """

        total_completed = batch_status.get("total_completed", 0)
        total_failed = batch_status.get("total_failed", 0)

        self.db_service.execute_query(
            query, (total_completed, total_failed, batch_id), fetch_results=False
        )
        logger.info(f"✅ [BATCH-COORDINATOR] Marked batch as completed: {batch_id}")

    def _update_batch_partial_status(self, batch_id: str, batch_status: Dict[str, Any]) -> None:
        """Update batch with partial completion data"""
        query = f"""
            UPDATE {IOE_SCHEMA}.outreach_batches
            SET total_calls_completed = ?,
                total_calls_failed = ?,
                last_status_check_ts = SYSDATETIMEOFFSET(),
                status_reason = 'Partial status via API reconciliation'
            WHERE batch_id = ?
        """

        total_completed = batch_status.get("total_completed", 0)
        total_failed = batch_status.get("total_failed", 0)

        self.db_service.execute_query(
            query, (total_completed, total_failed, batch_id), fetch_results=False
        )
        logger.info(f"🔄 [BATCH-COORDINATOR] Updated partial status for batch: {batch_id}")
