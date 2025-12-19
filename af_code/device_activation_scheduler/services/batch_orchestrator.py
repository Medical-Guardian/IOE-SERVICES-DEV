"""
Device Activation Batch Orchestrator
BusinessCaseID: BC-TBD (Device Activation System)
Created: 2025-12-07

This service orchestrates batch call submissions to Bland AI for Device Activation campaign.
It handles:
1. Batch creation in database (3-phase tracking)
2. Bland AI payload building
3. Batch submission to Bland AI
4. Result tracking and error handling

Pattern: Follows partner_campaign_scheduler/services/batch_orchestrator.py structure
"""

import logging
import uuid
from typing import List, Dict, Any

from af_code.bland_ai_webhook.services.config_manager import ConfigManager
from af_code.bland_ai_webhook.services.database_service import DatabaseService
from af_code.shared.bland_ai_client import BlandAIClient

logger = logging.getLogger(__name__)


class BatchOrchestrator:
    """
    Service to orchestrate batch call submissions to Bland AI for Device Activation

    Implements 3-phase database tracking (following DTC pattern):
    Phase 1: Create batch record (status='Pending') BEFORE Bland AI call
    Phase 2: Create attempt records (disposition='Pending') BEFORE Bland AI call
    Phase 3: Update batch with vendor_batch_id (status='Submitted') AFTER Bland AI response
    """

    def __init__(self, db_service: DatabaseService, config_manager: ConfigManager):
        """
        Initialize BatchOrchestrator

        Args:
            db_service: DatabaseService instance for database operations
            config_manager: ConfigManager instance for Bland AI client
        """
        self.db_service = db_service
        self.config_manager = config_manager
        self.enabled = False

        try:
            self.bland_client = BlandAIClient(config_manager)
            self.enabled = True
            logger.info("🔧 [BATCH-ORCHESTRATOR] Service initialized with Bland AI client")
        except ValueError as e:
            logger.warning(f"⚠️ [BATCH-ORCHESTRATOR] Bland AI client unavailable: {str(e)}")
            logger.info("🔧 [BATCH-ORCHESTRATOR] Service initialized in disabled mode")
            self.bland_client = None

    def create_and_submit_batches(self, eligible_members: List[Dict]) -> Dict[str, Any]:
        """
        Create batches and submit to Bland AI

        Splits members into batches of 100 (Bland AI limit) and submits each batch.

        Args:
            eligible_members: List of eligible members from EligibilityService

        Returns:
            Dict with:
                - success (bool): Whether all batches submitted successfully
                - batches_created (int): Number of batches created
                - calls_submitted (int): Total calls submitted to Bland AI
                - error (str): Error message if failed

        BusinessCaseID: BC-TBD (Device Activation System)
        """
        logger.info(
            f"🚀 [BATCH-ORCHESTRATOR] Starting batch creation for {len(eligible_members)} members"
        )

        if not self.enabled:
            logger.warning(
                "⚠️ [BATCH-ORCHESTRATOR] Batch orchestrator disabled - skipping submission"
            )
            return {
                "success": False,
                "batches_created": 0,
                "calls_submitted": 0,
                "error": "Batch orchestrator disabled (Bland AI API key not configured)",
            }

        try:
            # Split into batches of 100 (Bland AI max per batch)
            batch_size = 100
            member_batches = [
                eligible_members[i : i + batch_size]
                for i in range(0, len(eligible_members), batch_size)
            ]

            logger.info(
                f"📦 [BATCH-ORCHESTRATOR] Split {len(eligible_members)} members into {len(member_batches)} batches"
            )

            total_batches_created = 0
            total_calls_submitted = 0

            for batch_num, member_batch in enumerate(member_batches, 1):
                logger.info(
                    f"📦 [BATCH-ORCHESTRATOR] Processing batch {batch_num}/{len(member_batches)} "
                    f"({len(member_batch)} members)"
                )

                # Submit batch
                result = self._submit_single_batch(member_batch, batch_num)

                if result.get("success"):
                    total_batches_created += 1
                    total_calls_submitted += result.get("calls_submitted", 0)
                    logger.info(
                        f"✅ [BATCH-ORCHESTRATOR] Batch {batch_num} submitted successfully "
                        f"({result.get('calls_submitted', 0)} calls)"
                    )
                else:
                    logger.error(
                        f"❌ [BATCH-ORCHESTRATOR] Batch {batch_num} failed: {result.get('error')}"
                    )
                    # Continue with remaining batches even if one fails

            logger.info(
                f"✅ [BATCH-ORCHESTRATOR] Batch creation complete: "
                f"{total_batches_created} batches, {total_calls_submitted} calls"
            )

            return {
                "success": total_batches_created > 0,
                "batches_created": total_batches_created,
                "calls_submitted": total_calls_submitted,
            }

        except Exception as e:
            logger.error(
                f"💥 [BATCH-ORCHESTRATOR] Critical error in batch creation: {str(e)}",
                exc_info=True,
            )
            return {
                "success": False,
                "batches_created": 0,
                "calls_submitted": 0,
                "error": str(e),
            }

    def _submit_single_batch(self, members: List[Dict], batch_number: int) -> Dict[str, Any]:
        """
        Submit a single batch to Bland AI (max 100 members)

        Implements 3-phase database tracking:
        Phase 1: Create batch record
        Phase 2: Create attempt records
        Phase 3: Update batch with vendor_batch_id

        Args:
            members: List of members (max 100)
            batch_number: Batch number for logging

        Returns:
            Dict with success status and details
        """
        try:
            # Get campaign_id from first member (all members have same campaign)
            campaign_id = members[0].get("campaign_id")

            # ============================================================
            # PHASE 1: Create batch record BEFORE Bland AI call
            # ============================================================
            batch_id = self._create_outreach_batch(campaign_id, len(members))
            logger.info(
                f"✅ [BATCH-ORCHESTRATOR] Phase 1 Complete: Batch record created with ID: {batch_id}"
            )

            # ============================================================
            # PHASE 2: Create attempt records BEFORE Bland AI call
            # ============================================================
            attempt_id_map = self._create_outreach_attempts(members, batch_id)
            logger.info(
                f"✅ [BATCH-ORCHESTRATOR] Phase 2 Complete: {len(members)} attempt records created"
            )

            # Build Bland AI batch request
            batch_request = self._build_batch_request(members, batch_id, attempt_id_map)

            logger.info(
                f"📞 [BATCH-ORCHESTRATOR] Built batch request with {len(batch_request['calls'])} calls"
            )

            # Submit to Bland AI (SYNCHRONOUS - waits for response)
            response = self.bland_client.submit_batch_calls(batch_request)

            if response.get("success"):
                vendor_batch_id = response.get("batch_id")
                calls_submitted = response.get("calls_submitted", len(members))

                logger.info("✅ [BATCH-ORCHESTRATOR] Bland AI accepted batch")
                logger.info(f"📦 [BATCH-ORCHESTRATOR] Vendor Batch ID: {vendor_batch_id}")
                logger.info(f"📊 [BATCH-ORCHESTRATOR] Calls submitted: {calls_submitted}")

                # ============================================================
                # PHASE 3: Update batch with vendor_batch_id AFTER Bland AI response
                # ============================================================
                self._update_batch_with_vendor_id(batch_id, vendor_batch_id)
                logger.info(
                    "✅ [BATCH-ORCHESTRATOR] Phase 3 Complete: Batch updated with vendor ID"
                )

                return {
                    "success": True,
                    "batch_id": vendor_batch_id,
                    "calls_submitted": calls_submitted,
                }
            else:
                error_msg = response.get("error", "Unknown error")
                status_code = response.get("status_code", "Unknown")

                logger.error("❌ [BATCH-ORCHESTRATOR] Batch submission failed")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] Error: {error_msg}")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] Status code: {status_code}")

                # Mark batch as Failed in database
                self._mark_batch_failed(batch_id, error_msg)

                return {
                    "success": False,
                    "error": f"Status {status_code}: {error_msg}",
                }

        except Exception as e:
            logger.error(
                f"🚨 [BATCH-ORCHESTRATOR] Exception during batch submission: {str(e)}",
                exc_info=True,
            )

            # Mark batch as Failed if it was created
            if "batch_id" in locals():
                self._mark_batch_failed(batch_id, str(e))

            return {
                "success": False,
                "error": f"Exception: {str(e)}",
            }

    def _build_batch_request(
        self, members: List[Dict], batch_id: str, attempt_id_map: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Build the Bland AI batch request payload for Device Activation

        Args:
            members: List of eligible members
            batch_id: Batch UUID from Phase 1
            attempt_id_map: Mapping of enrollment_id to attempt_id from Phase 2

        Returns:
            BatchRequest dict for Bland AI API

        BusinessCaseID: BC-TBD (Device Activation System)
        """
        logger.info(f"🔨 [BATCH-ORCHESTRATOR] Building batch request for {len(members)} members")

        # Get campaign details from first member
        campaign_name = members[0].get("campaign_name", "Device Activation")
        campaign_id = members[0].get("campaign_id")

        # Get Bland AI configuration from environment variables
        import os

        pathway_id = os.environ.get("DEVICE_ACTIVATION_PATHWAY_ID")
        voice_id = os.environ.get("DEVICE_ACTIVATION_VOICE_ID")

        # Validate required environment variables
        if not pathway_id:
            raise ValueError(
                "DEVICE_ACTIVATION_PATHWAY_ID environment variable is not set. "
                "Please configure it in Azure Function App Configuration."
            )
        if not voice_id:
            raise ValueError(
                "DEVICE_ACTIVATION_VOICE_ID environment variable is not set. "
                "Please configure it in Azure Function App Configuration."
            )

        logger.info(f"🔧 [BATCH-ORCHESTRATOR] Using pathway_id: {pathway_id[:20]}...")
        logger.info(f"🔧 [BATCH-ORCHESTRATOR] Using voice_id: {voice_id[:20]}...")

        calls = []
        skipped_members = 0

        for member in members:
            enrollment_id = str(member.get("enrollment_id"))
            attempt_id = attempt_id_map.get(enrollment_id)

            if not attempt_id:
                logger.error(
                    f"❌ [BATCH-ORCHESTRATOR] No attempt_id found for enrollment {enrollment_id}"
                )
                skipped_members += 1
                continue

            # Determine phone number (prefer member primary_phone)
            phone_number = member.get("primary_phone")

            if not phone_number:
                logger.warning(
                    f"⚠️ [BATCH-ORCHESTRATOR] No valid phone for member: {member.get('member_id')}"
                )
                skipped_members += 1
                continue

            # Build request_data (data passed to AI agent during call)
            request_data = {
                # Member identification
                "first_name": member.get("first_name"),
                "last_name": member.get("last_name"),
                "primary_phone": phone_number,
                "email": member.get("email"),
                "language_pref": member.get("language_pref", "EN"),
                # Address and demographics (added 2025-12-19 for Bland AI context)
                "service_address": member.get("address_street") or "",
                "city": member.get("address_city") or "",
                "state": member.get("address_state") or "",
                "zip_code": member.get("address_zip") or "",
                "dob": member.get("dob").strftime("%Y-%m-%d") if member.get("dob") else "",
                # Device information
                "device_name": member.get("device_name"),
                "device_udi": member.get("device_udi"),
                "brand": member.get("brand"),
                "device_phone_number": member.get("device_phone_number"),
                "is_device_callable": member.get("is_device_callable", 0),
                "fall_detection_status": member.get("fall_detection_status"),
                "battery_status": member.get("battery_status"),
                # Campaign information
                "customer_type": member.get("customer_type"),
                "call_attempt_number": member.get("call_attempt_number", 1),
                "activation_start_date": str(member.get("activation_start_date")),
                "delivery_date": str(member.get("delivery_date")),
            }

            # Build metadata (used for webhook processing)
            metadata = {
                # Core tracking IDs
                "attempt_id": attempt_id,  # CRITICAL for webhook
                "batch_id": batch_id,
                "campaign_id": str(campaign_id),
                "member_id": str(member.get("member_id")),
                "enrollment_id": enrollment_id,
                # Member identification
                "first_name": member.get("first_name"),
                "last_name": member.get("last_name"),
                "called_number": phone_number,
                # Campaign context
                "campaign_type": "Device Activation",
                "customer_type": member.get("customer_type"),
                "call_attempt_number": member.get("call_attempt_number", 1),
                # Device information
                "device_udi": member.get("device_udi"),
                "device_name": member.get("device_name"),
                "is_device_callable": member.get("is_device_callable", 0),
                # Communication preferences
                "language_pref": member.get("language_pref", "EN"),
                "member_timezone": member.get("timezone"),
                # Address and demographics (added 2025-12-19 - matches DTC pattern)
                "service_address": member.get("address_street") or "",
                "city": member.get("address_city") or "",
                "state": member.get("address_state") or "",
                "zip_code": member.get("address_zip") or "",
                "dob": member.get("dob").strftime("%Y-%m-%d") if member.get("dob") else "",
            }

            # Build call data
            call_data = {
                "to": phone_number,
                "request_data": request_data,
                "metadata": metadata,
            }

            calls.append(call_data)

            # Log call details
            logger.info(
                f"📞 [BATCH-ORCHESTRATOR] Member {member.get('member_id')}: "
                f"{member.get('first_name')} {member.get('last_name')}, "
                f"Call #{member.get('call_attempt_number', 1)}, "
                f"Device: {member.get('device_name')}, "
                f"Customer Type: {member.get('customer_type')}"
            )

        if skipped_members > 0:
            logger.warning(
                f"⚠️ [BATCH-ORCHESTRATOR] Skipped {skipped_members} members (missing data)"
            )

        # Build complete batch request
        batch_request = {
            "campaign_id": str(campaign_id),
            "calls": calls,
            "pathway_id": pathway_id,
            "voice_id": voice_id,
            "bland_parameters_global": {
                "max_duration": 10,  # 10 minutes max per call
                "wait_for_greeting": True,
                "record": True,
                "amd": True,  # Answering machine detection
            },
        }

        logger.info(f"✅ [BATCH-ORCHESTRATOR] Built batch request with {len(calls)} calls")

        return batch_request

    def _create_outreach_batch(self, campaign_id: str, total_calls: int) -> str:
        """
        Create batch record in engage360.outreach_batches (Phase 1)

        Args:
            campaign_id: Campaign UUID
            total_calls: Number of calls in this batch

        Returns:
            Batch UUID (as string)
        """
        batch_id = str(uuid.uuid4())

        insert_batch_sql = """
        INSERT INTO engage360.outreach_batches (
            batch_id, campaign_id, batch_type, status,
            total_calls, created_ts
        ) VALUES (%s, %s, %s, %s, %s, SYSDATETIMEOFFSET())
        """

        self.db_service.execute_query(
            insert_batch_sql,
            (batch_id, str(campaign_id), "DEVICE_ACTIVATION", "Pending", total_calls),
            fetch_results=False,
        )

        logger.info(f"✅ [BATCH-ORCHESTRATOR] Created batch record: {batch_id}")

        return batch_id

    def _create_outreach_attempts(self, members: List[Dict], batch_id: str) -> Dict[str, str]:
        """
        Create attempt records in engage360.outreach_attempts (Phase 2)

        Args:
            members: List of members
            batch_id: Batch UUID from Phase 1

        Returns:
            Dict mapping enrollment_id to attempt_id
        """
        attempt_id_map = {}

        insert_attempt_sql = """
        INSERT INTO engage360.outreach_attempts (
            attempt_id, enrollment_id, batch_id, call_attempt_number,
            disposition, status, created_ts
        ) VALUES (%s, %s, %s, %s, %s, %s, SYSDATETIMEOFFSET())
        """

        for member in members:
            enrollment_id = str(member.get("enrollment_id"))
            call_attempt_number = member.get("call_attempt_number", 1)
            attempt_id = str(uuid.uuid4())

            self.db_service.execute_query(
                insert_attempt_sql,
                (attempt_id, enrollment_id, batch_id, call_attempt_number, "Pending", "Pending"),
                fetch_results=False,
            )

            attempt_id_map[enrollment_id] = attempt_id

        logger.info(f"✅ [BATCH-ORCHESTRATOR] Created {len(attempt_id_map)} attempt records")

        return attempt_id_map

    def _update_batch_with_vendor_id(self, batch_id: str, vendor_batch_id: str):
        """
        Update batch with vendor_batch_id from Bland AI (Phase 3)

        Args:
            batch_id: Internal batch UUID
            vendor_batch_id: Bland AI batch ID
        """
        update_batch_sql = """
        UPDATE engage360.outreach_batches
        SET vendor_batch_id = %s, status = %s, updated_ts = SYSDATETIMEOFFSET()
        WHERE batch_id = %s
        """

        self.db_service.execute_query(
            update_batch_sql, (vendor_batch_id, "Submitted", batch_id), fetch_results=False
        )

        logger.info(f"✅ [BATCH-ORCHESTRATOR] Updated batch {batch_id} with vendor ID")

    def _mark_batch_failed(self, batch_id: str, error_message: str):
        """
        Mark batch as Failed in database

        Args:
            batch_id: Internal batch UUID
            error_message: Error message to store
        """
        update_batch_sql = """
        UPDATE engage360.outreach_batches
        SET status = %s, error_message = %s, updated_ts = SYSDATETIMEOFFSET()
        WHERE batch_id = %s
        """

        self.db_service.execute_query(
            update_batch_sql, ("Failed", error_message[:500], batch_id), fetch_results=False
        )

        logger.error(f"❌ [BATCH-ORCHESTRATOR] Marked batch {batch_id} as Failed")
