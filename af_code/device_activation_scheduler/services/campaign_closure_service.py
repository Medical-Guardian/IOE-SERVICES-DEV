"""
Device Activation Campaign Closure Service

Automatically unenrolls members from Device Activation campaigns when their
90-day campaign window (campaign_end_date) is reached.

BusinessCaseID: BC-DA-007

Author: AI-POD Team - Data Science
Created: 2026-01-20
"""

import logging
from typing import List, Dict, Any
from datetime import datetime
import uuid

from ...bland_ai_webhook.services.database_service import DatabaseService
from ...bland_ai_webhook.services.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class CampaignClosureService:
    """
    Service to automatically close Device Activation campaign enrollments
    when members reach their campaign_end_date (90-day window completion).

    Features:
    - Queries enrollments with expired campaign_end_date
    - Updates enrollment status to UNENROLLED
    - Logs all status changes to audit history
    - Implements distributed locking to prevent concurrent executions
    - Provides comprehensive logging for monitoring and debugging

    BusinessCaseID: BC-DA-007
    """

    def __init__(self, db_service: DatabaseService, config_manager: ConfigManager):
        """
        Initialize Campaign Closure Service

        Args:
            db_service: Database service for SQL operations
            config_manager: Configuration manager for secrets/settings
        """
        self.db_service = db_service
        self.config_manager = config_manager
        self.lock_timeout_minutes = 50  # Safety margin under 60 min timer interval
        logger.info("🔧 [DA-CLOSURE-SVC] Campaign Closure Service initialized successfully")

    def close_expired_campaigns(self) -> Dict[str, Any]:
        """
        Main orchestration method to close expired Device Activation campaigns
        with distributed locking to prevent concurrent executions.

        Returns:
            dict: Summary with keys:
                - enrollments_closed (int): Number of enrollments updated
                - campaigns_affected (List[str]): Campaign names affected
                - members_unenrolled (int): Unique members unenrolled
                - execution_duration_seconds (float): Total execution time
        """
        lock_name = "device_activation_campaign_closure"
        instance_id = f"da-closure-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        lock_acquired = False
        start_time = datetime.utcnow()

        try:
            # Step 1: Acquire distributed lock
            logger.info(f"🔒 [DA-CLOSURE-SVC] Attempting to acquire lock: {lock_name}")
            lock_acquired = self._acquire_lock(lock_name, self.lock_timeout_minutes, instance_id)

            if not lock_acquired:
                logger.info(
                    "🔒 [DA-CLOSURE-SVC] Another instance already running, skipping execution"
                )
                logger.info(
                    "🔒 [DA-CLOSURE-SVC] This prevents overlapping campaign closure processes"
                )
                return {
                    "enrollments_closed": 0,
                    "campaigns_affected": [],
                    "members_unenrolled": 0,
                    "execution_duration_seconds": 0,
                    "skipped_reason": "Lock held by another instance",
                }

            logger.info(f"🔓 [DA-CLOSURE-SVC] Successfully acquired lock for {lock_name}")
            logger.info(f"⏰ [DA-CLOSURE-SVC] Lock expires in {self.lock_timeout_minutes} minutes")

            # Step 2: Execute closure logic
            result = self._process_expired_enrollments()

            # Step 3: Calculate execution duration
            duration = (datetime.utcnow() - start_time).total_seconds()
            result["execution_duration_seconds"] = duration

            return result

        except Exception as e:
            logger.error(f"🚨 [DA-CLOSURE-SVC] Critical error during campaign closure: {str(e)}")
            raise

        finally:
            # Step 4: Always release lock
            if lock_acquired:
                self._release_lock(lock_name)
                logger.info(f"🔓 [DA-CLOSURE-SVC] Released lock for {lock_name}")

    def _process_expired_enrollments(self) -> Dict[str, Any]:
        """
        Core closure logic: query expired enrollments and update status

        Returns:
            dict: Processing summary
        """
        logger.info("📊 [DA-CLOSURE-SVC] Starting expired enrollment processing...")

        # Step 1: Query expired enrollments
        expired_enrollments = self._query_expired_enrollments()

        if not expired_enrollments:
            logger.info("✅ [DA-CLOSURE-SVC] No expired enrollments found")
            return {
                "enrollments_closed": 0,
                "campaigns_affected": [],
                "members_unenrolled": 0,
            }

        logger.info(
            f"📦 [DA-CLOSURE-SVC] Found {len(expired_enrollments)} expired enrollments to process"
        )

        # Step 2: Process each enrollment
        enrollments_closed = 0
        campaigns_affected = set()
        members_unenrolled = set()

        for enrollment in expired_enrollments:
            try:
                enrollment_id = enrollment["enrollment_id"]
                member_id = enrollment["member_id"]
                campaign_id = enrollment["campaign_id"]
                campaign_name = enrollment.get("campaign_name", "Unknown")
                campaign_end_date = enrollment["campaign_end_date"]

                logger.info(
                    f"🔄 [DA-CLOSURE-SVC] Processing enrollment {enrollment_id[:8]}... "
                    f"(Member ID: {str(member_id)[:8]}..., Campaign: {campaign_name})"
                )
                logger.info(f"📅 [DA-CLOSURE-SVC] Campaign end date: {campaign_end_date}")

                # Update enrollment status
                success = self._update_enrollment_status(
                    enrollment_id, member_id, campaign_id, campaign_name, campaign_end_date
                )

                if success:
                    enrollments_closed += 1
                    campaigns_affected.add(campaign_name)
                    members_unenrolled.add(member_id)
                    logger.info(
                        f"✅ [DA-CLOSURE-SVC] Successfully closed enrollment {enrollment_id[:8]}..."
                    )
                else:
                    logger.warning(
                        f"⚠️ [DA-CLOSURE-SVC] Failed to close enrollment {enrollment_id[:8]}..."
                    )

            except Exception as e:
                logger.error(
                    f"❌ [DA-CLOSURE-SVC] Error processing enrollment {enrollment.get('enrollment_id', 'unknown')}: {str(e)}"
                )
                # Continue processing other enrollments

        # Step 3: Return summary
        logger.info("📊 [DA-CLOSURE-SVC] Processing complete:")
        logger.info(f"   ✅ Enrollments closed: {enrollments_closed}")
        logger.info(f"   👥 Unique members unenrolled: {len(members_unenrolled)}")
        logger.info(f"   📋 Campaigns affected: {len(campaigns_affected)}")

        return {
            "enrollments_closed": enrollments_closed,
            "campaigns_affected": sorted(list(campaigns_affected)),
            "members_unenrolled": len(members_unenrolled),
        }

    def _query_expired_enrollments(self) -> List[Dict[str, Any]]:
        """
        Query enrollments where campaign_end_date has been reached

        Returns:
            List of enrollment dictionaries with member and campaign details
        """
        logger.info("🔍 [DA-CLOSURE-SVC] Querying enrollments with expired campaign_end_date...")

        query = """
            SELECT
                e.enrollment_id,
                e.member_id,
                e.campaign_id,
                e.campaign_end_date,
                e.current_status,
                c.name as campaign_name,
                c.campaign_type
            FROM engage360.member_campaign_enrollments_enhanced e
            INNER JOIN engage360.campaigns_enhanced c ON e.campaign_id = c.campaign_id
            INNER JOIN engage360.members m ON e.member_id = m.member_id
            WHERE
                e.current_status = 'ENROLLED'
                AND c.campaign_type = 'Operations'
                AND e.campaign_end_date IS NOT NULL
                AND CAST(SYSDATETIMEOFFSET() AS DATE) >= e.campaign_end_date
            ORDER BY e.campaign_end_date ASC
        """

        try:
            enrollments = self.db_service.execute_query(query, None, fetch_results=True)

            logger.info(
                f"📊 [DA-CLOSURE-SVC] Query returned {len(enrollments)} expired enrollments"
            )

            if enrollments:
                # Log campaign breakdown
                campaigns = {}
                for enrollment in enrollments:
                    campaign_name = enrollment.get("campaign_name", "Unknown")
                    campaigns[campaign_name] = campaigns.get(campaign_name, 0) + 1

                logger.info("📋 [DA-CLOSURE-SVC] Breakdown by campaign:")
                for campaign_name, count in campaigns.items():
                    logger.info(f"   - {campaign_name}: {count} enrollments")

            return enrollments

        except Exception as e:
            logger.error(f"🚨 [DA-CLOSURE-SVC] Error querying expired enrollments: {str(e)}")
            raise

    def _update_enrollment_status(
        self,
        enrollment_id: str,
        member_id: str,
        campaign_id: str,
        campaign_name: str,
        campaign_end_date: Any,
    ) -> bool:
        """
        Update single enrollment to UNENROLLED status and log to audit history

        Args:
            enrollment_id: Enrollment UUID
            member_id: Member UUID
            campaign_id: Campaign UUID
            campaign_name: Campaign name for logging
            campaign_end_date: Campaign end date for details

        Returns:
            bool: True if update successful, False otherwise
        """
        try:
            # Prepare queries for transaction
            update_query = """
                UPDATE engage360.member_campaign_enrollments_enhanced
                SET
                    current_status = 'UNENROLLED',
                    unenrollment_reason = 'Campaign 90-day window completed - reached campaign_end_date',
                    last_attempt_ts = SYSDATETIMEOFFSET()
                WHERE
                    enrollment_id = %s
                    AND current_status = 'ENROLLED'
            """

            audit_query = """
                INSERT INTO engage360.member_enrollment_status_history (
                    history_id,
                    member_id,
                    campaign_id,
                    previous_status,
                    new_status,
                    change_timestamp,
                    change_source,
                    change_details
                )
                VALUES (%s, %s, %s, 'ENROLLED', 'UNENROLLED', SYSDATETIMEOFFSET(), 'AUTOMATED_CLOSURE', %s)
            """

            # Generate history_id
            history_id = str(uuid.uuid4())

            # Change details for audit trail
            change_details = (
                f"Automated closure: campaign_end_date ({campaign_end_date}) reached. "
                f"Campaign: {campaign_name}. "
                f"90-day Device Activation window completed."
            )

            # Execute as transaction (atomic update + audit)
            queries = [
                (update_query, (enrollment_id,)),
                (audit_query, (history_id, member_id, campaign_id, change_details)),
            ]

            self.db_service.execute_transaction(queries)

            logger.debug(
                f"✅ [DA-CLOSURE-SVC] Updated enrollment {enrollment_id[:8]}... to UNENROLLED"
            )
            logger.debug(f"✅ [DA-CLOSURE-SVC] Created audit history record {history_id[:8]}...")

            return True

        except Exception as e:
            logger.error(f"🚨 [DA-CLOSURE-SVC] Error updating enrollment {enrollment_id}: {str(e)}")
            return False

    def _acquire_lock(
        self, operation_name: str, max_duration_minutes: int, instance_id: str
    ) -> bool:
        """
        Acquire distributed lock using database ACID properties

        Args:
            operation_name: Unique lock name
            max_duration_minutes: Lock expiry duration
            instance_id: Instance identifier for debugging

        Returns:
            bool: True if lock acquired, False if already held
        """
        query = """
            DECLARE @lock_acquired BIT = 0;

            -- Clean up expired locks first
            DELETE FROM engage360.system_locks
            WHERE lock_expiry <= SYSDATETIMEOFFSET();

            -- Try to acquire new lock
            IF NOT EXISTS (
                SELECT 1 FROM engage360.system_locks
                WHERE lock_name = %s
            )
            BEGIN
                INSERT INTO engage360.system_locks (
                    lock_name,
                    lock_expiry,
                    locked_by,
                    created_ts
                )
                VALUES (
                    %s,
                    DATEADD(minute, %s, SYSDATETIMEOFFSET()),
                    %s,
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

            acquired = result[0]["acquired"] == 1

            if acquired:
                logger.info(
                    f"🔓 [DA-CLOSURE-SVC] Successfully acquired lock '{operation_name}' "
                    f"for {max_duration_minutes} minutes"
                )
            else:
                logger.info(
                    f"🔒 [DA-CLOSURE-SVC] Lock '{operation_name}' already held by another process"
                )

            return acquired

        except Exception as e:
            logger.error(f"🚨 [DA-CLOSURE-SVC] Error acquiring lock: {str(e)}")
            return False

    def _release_lock(self, operation_name: str) -> None:
        """
        Release distributed lock

        Args:
            operation_name: Lock name to release
        """
        query = "DELETE FROM engage360.system_locks WHERE lock_name = %s"

        try:
            result = self.db_service.execute_query(query, (operation_name,), fetch_results=False)
            # execute_query returns cursor.rowcount (int) when fetch_results=False
            rows_affected = result if isinstance(result, int) else 0

            if rows_affected > 0:
                logger.info(f"🔓 [DA-CLOSURE-SVC] Successfully released lock '{operation_name}'")
            else:
                logger.warning(
                    f"⚠️ [DA-CLOSURE-SVC] Lock '{operation_name}' was not found (may have expired)"
                )

        except Exception as e:
            logger.error(f"🚨 [DA-CLOSURE-SVC] Error releasing lock: {str(e)}")
