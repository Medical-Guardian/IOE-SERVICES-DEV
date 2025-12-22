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
import json
from typing import List, Dict, Any

from af_code.bland_ai_webhook.services.config_manager import ConfigManager
from af_code.bland_ai_webhook.services.database_service import DatabaseService
from af_code.shared.bland_ai_client import BlandAIClient
from af_code.shared.bland_parameters_validator import BlandParametersValidator

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
            campaign_name = members[0].get("campaign_name", "Device Activation")

            logger.info("")
            logger.info("🔄 [BATCH-ORCHESTRATOR] ============================================")
            logger.info(f"🔄 [BATCH-ORCHESTRATOR] BATCH #{batch_number} - 3-PHASE SUBMISSION")
            logger.info("🔄 [BATCH-ORCHESTRATOR] ============================================")
            logger.info(f"🔄 [BATCH-ORCHESTRATOR] Campaign: {campaign_name}")
            logger.info(f"🔄 [BATCH-ORCHESTRATOR] Campaign ID: {campaign_id}")
            logger.info(f"🔄 [BATCH-ORCHESTRATOR] Members in batch: {len(members)}")
            logger.info("")

            # ============================================================
            # PHASE 1: Create batch record BEFORE Bland AI call
            # ============================================================
            logger.info("📝 [BATCH-ORCHESTRATOR] ============================================")
            logger.info("📝 [BATCH-ORCHESTRATOR] PHASE 1: CREATE BATCH RECORD (PRE-SUBMISSION)")
            logger.info("📝 [BATCH-ORCHESTRATOR] ============================================")
            logger.info("📝 [BATCH-ORCHESTRATOR] Creating batch in engage360.outreach_batches...")
            logger.info(f"📝 [BATCH-ORCHESTRATOR] Status: 'Pending' (awaiting Bland AI response)")

            batch_id = self._create_outreach_batch(campaign_id, len(members))

            logger.info(f"✅ [BATCH-ORCHESTRATOR] Batch record created successfully")
            logger.info(f"✅ [BATCH-ORCHESTRATOR] Internal Batch ID: {batch_id}")
            logger.info("")

            # ============================================================
            # PHASE 2: Create attempt records BEFORE Bland AI call
            # ============================================================
            logger.info("📝 [BATCH-ORCHESTRATOR] ============================================")
            logger.info("📝 [BATCH-ORCHESTRATOR] PHASE 2: CREATE ATTEMPT RECORDS (PRE-SUBMISSION)")
            logger.info("📝 [BATCH-ORCHESTRATOR] ============================================")
            logger.info("📝 [BATCH-ORCHESTRATOR] Creating attempts in engage360.outreach_attempts...")
            logger.info(f"📝 [BATCH-ORCHESTRATOR] Total attempts to create: {len(members)}")
            logger.info(f"📝 [BATCH-ORCHESTRATOR] Disposition: 'Pending' (awaiting call completion)")

            attempt_id_map = self._create_outreach_attempts(members, batch_id)

            logger.info(f"✅ [BATCH-ORCHESTRATOR] {len(members)} attempt records created successfully")
            logger.info("")

            # Build Bland AI batch request
            batch_request = self._build_batch_request(members, batch_id, attempt_id_map)

            # Submit to Bland AI (SYNCHRONOUS - waits for response)
            logger.info("")
            logger.info("🚀 [BATCH-ORCHESTRATOR] ============================================")
            logger.info("🚀 [BATCH-ORCHESTRATOR] SUBMITTING BATCH TO BLAND AI")
            logger.info("🚀 [BATCH-ORCHESTRATOR] ============================================")
            logger.info(f"🚀 [BATCH-ORCHESTRATOR] Calls in batch: {len(batch_request['calls'])}")
            logger.info(f"🚀 [BATCH-ORCHESTRATOR] Batch submission mode: SYNCHRONOUS (wait for response)")
            logger.info(f"🚀 [BATCH-ORCHESTRATOR] Submitting to Bland AI API...")

            # Display all batch data before submission (USER REQUIREMENT)
            calls = batch_request.get('calls', [])
            logger.info("")
            logger.info("📦 [BATCH-ORCHESTRATOR] ============================================")
            logger.info("📦 [BATCH-ORCHESTRATOR] BATCH REQUEST DATA (DETAILED)")
            logger.info("📦 [BATCH-ORCHESTRATOR] ============================================")
            logger.info(f"📦 [BATCH-ORCHESTRATOR] Batch ID: {batch_id}")
            logger.info(f"📦 [BATCH-ORCHESTRATOR] Campaign: {members[0].get('campaign_name', 'Unknown')}")
            logger.info(f"📦 [BATCH-ORCHESTRATOR] Number of Calls: {len(calls)}")
            logger.info("")
            logger.info("📦 [BATCH-ORCHESTRATOR] Call Details:")
            for i, call in enumerate(calls, 1):
                logger.info(f"   Call #{i}:")
                logger.info(f"     • Member ID: {call.get('request_data', {}).get('member_id')}")
                logger.info(f"     • Phone: {call.get('phone_number')}")
                first_name = call.get('request_data', {}).get('first_name', '')
                last_name = call.get('request_data', {}).get('last_name', '')
                logger.info(f"     • Name: {first_name} {last_name}")
                logger.info(f"     • Request Data Keys: {list(call.get('request_data', {}).keys())}")
                logger.info(f"     • Metadata Keys: {list(call.get('metadata', {}).keys())}")

            logger.info("")
            if calls:
                logger.info(f"📦 [BATCH-ORCHESTRATOR] Full Request Payload (First Call Sample):")
                sample_call = calls[0]
                logger.info(f"   Request Data: {json.dumps(sample_call.get('request_data', {}), indent=2)}")
                logger.info(f"   Metadata: {json.dumps(sample_call.get('metadata', {}), indent=2)}")
            logger.info("📦 [BATCH-ORCHESTRATOR] ============================================")
            logger.info("")

            response = self.bland_client.submit_batch_calls(batch_request)

            if response.get("success"):
                vendor_batch_id = response.get("batch_id")
                calls_submitted = response.get("calls_submitted", len(members))

                logger.info("")
                logger.info("✅ [BATCH-ORCHESTRATOR] ============================================")
                logger.info("✅ [BATCH-ORCHESTRATOR] BLAND AI ACCEPTED BATCH")
                logger.info("✅ [BATCH-ORCHESTRATOR] ============================================")
                logger.info(f"✅ [BATCH-ORCHESTRATOR] Vendor Batch ID: {vendor_batch_id}")
                logger.info(f"✅ [BATCH-ORCHESTRATOR] Calls Submitted: {calls_submitted}")
                logger.info(f"✅ [BATCH-ORCHESTRATOR] Internal Batch ID: {batch_id}")
                logger.info("")

                # ============================================================
                # PHASE 3: Update batch with vendor_batch_id AFTER Bland AI response
                # ============================================================
                logger.info("📝 [BATCH-ORCHESTRATOR] ============================================")
                logger.info("📝 [BATCH-ORCHESTRATOR] PHASE 3: UPDATE BATCH WITH VENDOR ID (POST-SUBMISSION)")
                logger.info("📝 [BATCH-ORCHESTRATOR] ============================================")
                logger.info(f"📝 [BATCH-ORCHESTRATOR] Updating batch {batch_id}...")
                logger.info(f"📝 [BATCH-ORCHESTRATOR] New Status: 'Submitted'")
                logger.info(f"📝 [BATCH-ORCHESTRATOR] Vendor Batch ID: {vendor_batch_id}")

                self._update_batch_with_vendor_id(batch_id, vendor_batch_id)

                logger.info(f"✅ [BATCH-ORCHESTRATOR] Batch updated successfully")
                logger.info(f"✅ [BATCH-ORCHESTRATOR] 3-Phase tracking complete")
                logger.info("")
                logger.info("📊 [BATCH-ORCHESTRATOR] ============================================")
                logger.info(f"📊 [BATCH-ORCHESTRATOR] BATCH #{batch_number} SUBMISSION COMPLETE")
                logger.info("📊 [BATCH-ORCHESTRATOR] ============================================")
                logger.info(f"📊 [BATCH-ORCHESTRATOR] Total Calls: {calls_submitted}")
                logger.info(f"📊 [BATCH-ORCHESTRATOR] Internal Batch ID: {batch_id}")
                logger.info(f"📊 [BATCH-ORCHESTRATOR] Vendor Batch ID: {vendor_batch_id}")
                logger.info(f"📊 [BATCH-ORCHESTRATOR] Status: Submitted ✅")
                logger.info("📊 [BATCH-ORCHESTRATOR] ============================================")

                return {
                    "success": True,
                    "batch_id": vendor_batch_id,
                    "calls_submitted": calls_submitted,
                }
            else:
                error_msg = response.get("error", "Unknown error")
                status_code = response.get("status_code", "Unknown")

                logger.error("")
                logger.error("❌ [BATCH-ORCHESTRATOR] ============================================")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] BATCH #{batch_number} SUBMISSION FAILED")
                logger.error("❌ [BATCH-ORCHESTRATOR] ============================================")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] Error Message: {error_msg}")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] HTTP Status Code: {status_code}")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] Internal Batch ID: {batch_id}")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] Calls Attempted: {len(members)}")
                logger.error("")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] Marking batch as 'Failed' in database...")

                # Mark batch as Failed in database
                self._mark_batch_failed(batch_id, error_msg)

                logger.error(f"❌ [BATCH-ORCHESTRATOR] Batch marked as Failed")
                logger.error("❌ [BATCH-ORCHESTRATOR] ============================================")

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
        logger.info("")
        logger.info("🔨 [BATCH-ORCHESTRATOR] ============================================")
        logger.info("🔨 [BATCH-ORCHESTRATOR] BLAND AI BATCH REQUEST BUILDER")
        logger.info("🔨 [BATCH-ORCHESTRATOR] ============================================")
        logger.info(f"🔨 [BATCH-ORCHESTRATOR] Building batch request for {len(members)} members")
        logger.info(f"🔨 [BATCH-ORCHESTRATOR] Internal Batch ID: {batch_id}")

        # Get campaign details from first member
        campaign_name = members[0].get("campaign_name", "Device Activation")
        campaign_id = members[0].get("campaign_id")

        # Get Bland AI configuration from database (DTC pattern - database only)
        # Members from same campaign share the same bland_parameters_global
        first_member = members[0]
        campaign_config = first_member.get("bland_parameters_global")

        if not campaign_config:
            error_msg = (
                f"bland_parameters_global not found for campaign '{campaign_name}'. "
                "Please configure in campaign_call_configs_enhanced table:\n"
                "  INSERT INTO engage360.campaign_call_configs_enhanced\n"
                "  (campaign_id, call_type, bland_parameters_global, config_status)\n"
                "  VALUES ('{campaign_id}', 'DeviceActivation', '{{\"pathway_id\":\"...\"}}', 'active')"
            )
            logger.error(f"❌ [BATCH-ORCHESTRATOR] {error_msg}")
            raise ValueError(error_msg)

        # Parse JSON if it's a string
        if isinstance(campaign_config, str):
            campaign_config = json.loads(campaign_config)

        logger.info(f"✅ [BATCH-ORCHESTRATOR] Using database configuration for campaign '{campaign_name}'")

        # Display all configuration data (USER REQUIREMENT)
        logger.info("📋 [BATCH-ORCHESTRATOR] ============================================")
        logger.info("📋 [BATCH-ORCHESTRATOR] BLAND AI CONFIGURATION")
        logger.info("📋 [BATCH-ORCHESTRATOR] ============================================")
        logger.info(f"📋 [BATCH-ORCHESTRATOR] Campaign: {campaign_name}")
        logger.info(f"📋 [BATCH-ORCHESTRATOR] Batch ID: {batch_id}")
        logger.info(f"📋 [BATCH-ORCHESTRATOR] Member Count: {len(members)}")
        logger.info(f"📋 [BATCH-ORCHESTRATOR] Global Parameters (bland_parameters_global):")
        for key, value in campaign_config.items():
            logger.info(f"   • {key}: {value}")
        logger.info("📋 [BATCH-ORCHESTRATOR] ============================================")

        # Validate and extract pathway_id using BlandParametersValidator
        validator = BlandParametersValidator(campaign_config)
        pathway_id = validator.get_pathway_id()  # Handles both 'pathway_id' and 'task' fields

        # Extract voice_id (optional - Bland AI will use default if not provided)
        voice_id = campaign_config.get("voice_id") or campaign_config.get("voice")

        if voice_id:
            logger.info(f"🎤 [BATCH-ORCHESTRATOR] Using voice_id: {voice_id}")
        else:
            logger.info(f"🎤 [BATCH-ORCHESTRATOR] No voice_id specified, Bland AI will use default")

        logger.info(f"🛤️ [BATCH-ORCHESTRATOR] Using pathway_id: {pathway_id}")

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
                # Address and demographics (updated 2025-12-21 to match user requirements)
                "address_street": member.get("address_street") or "",
                "address_city": member.get("address_city") or "",
                "address_state": member.get("address_state") or "",
                "address_zip": member.get("address_zip") or "",
                "dob": member.get("dob").strftime("%m-%d-%Y") if member.get("dob") else "",
                # Member brand (added 2025-12-21 - from members.member_brand)
                "member_brand": member.get("member_brand") or "",
                # Device information (device_name now from member_devices.brand)
                "device_name": member.get("device_brand") or "",
                "device_udi": member.get("device_udi"),
                "device_phone_number": member.get("device_phone_number"),
                "is_device_callable": member.get("is_device_callable", 0),
                "fall_detection": member.get("fall_detection_status"),
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

            # Log detailed member data (following DTC/Partner campaign format)
            logger.info("")
            logger.info(f"📞 [BATCH-ORCHESTRATOR] ============================================")
            logger.info(f"📞 [BATCH-ORCHESTRATOR] CALL #{len(calls)} - MEMBER DATA")
            logger.info(f"📞 [BATCH-ORCHESTRATOR] ============================================")
            logger.info(f"📞 [BATCH-ORCHESTRATOR] Member Identification:")
            logger.info(f"   👤 Member ID: {member.get('member_id')}")
            logger.info(f"   👤 Enrollment ID: {enrollment_id}")
            logger.info(f"   👤 Name: {member.get('first_name')} {member.get('last_name')}")
            logger.info(f"   📞 Phone: {phone_number}")
            logger.info(f"   📧 Email: {member.get('email', 'N/A')}")
            logger.info("")
            logger.info(f"📞 [BATCH-ORCHESTRATOR] Address & Demographics:")
            logger.info(f"   🏠 Street: {member.get('address_street', 'N/A')}")
            logger.info(f"   🏠 City: {member.get('address_city', 'N/A')}")
            logger.info(f"   🏠 State: {member.get('address_state', 'N/A')}")
            logger.info(f"   🏠 Zip: {member.get('address_zip', 'N/A')}")
            logger.info(f"   🎂 DOB: {member.get('dob').strftime('%m-%d-%Y') if member.get('dob') else 'N/A'}")
            logger.info(f"   🌍 Timezone: {member.get('timezone', 'N/A')}")
            logger.info(f"   🗣️ Language: {member.get('language_pref', 'EN')}")
            logger.info("")
            logger.info(f"📞 [BATCH-ORCHESTRATOR] Brand Information:")
            logger.info(f"   🏢 Member Brand: {member.get('member_brand', 'N/A')} (from members.member_brand)")
            logger.info(f"   📱 Device Brand: {member.get('device_brand', 'N/A')} (from member_devices.brand)")
            logger.info("")
            logger.info(f"📞 [BATCH-ORCHESTRATOR] Device Information:")
            logger.info(f"   📱 Device Name: {member.get('device_name', 'N/A')}")
            logger.info(f"   🔢 Device UDI: {member.get('device_udi', 'N/A')}")
            logger.info(f"   📞 Device Phone: {member.get('device_phone_number', 'N/A')}")
            logger.info(f"   📡 Device Callable: {member.get('is_device_callable', 0)}")
            logger.info(f"   🚨 Fall Detection: {member.get('fall_detection_status', 'N/A')}")
            logger.info(f"   🔋 Battery Status: {member.get('battery_status', 'N/A')}")
            logger.info("")
            logger.info(f"📞 [BATCH-ORCHESTRATOR] Campaign Context:")
            logger.info(f"   📋 Campaign ID: {campaign_id}")
            logger.info(f"   📋 Campaign Name: {campaign_name}")
            logger.info(f"   👥 Customer Type: {member.get('customer_type', 'N/A')}")
            logger.info(f"   🔢 Call Attempt #: {member.get('call_attempt_number', 1)}")
            logger.info(f"   📅 Activation Start: {member.get('activation_start_date', 'N/A')}")
            logger.info(f"   📦 Delivery Date: {member.get('delivery_date', 'N/A')}")
            logger.info("")
            logger.info(f"📞 [BATCH-ORCHESTRATOR] Tracking IDs:")
            logger.info(f"   🆔 Attempt ID: {attempt_id}")
            logger.info(f"   📦 Batch ID: {batch_id}")
            logger.info("")
            logger.info(f"📞 [BATCH-ORCHESTRATOR] request_data Payload (sent to Bland AI):")
            logger.info(f"   {{")
            logger.info(f"     'first_name': '{request_data.get('first_name')}'")
            logger.info(f"     'last_name': '{request_data.get('last_name')}'")
            logger.info(f"     'primary_phone': '{request_data.get('primary_phone')}'")
            logger.info(f"     'email': '{request_data.get('email')}'")
            logger.info(f"     'language_pref': '{request_data.get('language_pref')}'")
            logger.info(f"     'address_street': '{request_data.get('address_street')}'")
            logger.info(f"     'address_city': '{request_data.get('address_city')}'")
            logger.info(f"     'address_state': '{request_data.get('address_state')}'")
            logger.info(f"     'address_zip': '{request_data.get('address_zip')}'")
            logger.info(f"     'dob': '{request_data.get('dob')}'")
            logger.info(f"     'member_brand': '{request_data.get('member_brand')}' ← FROM members.member_brand")
            logger.info(f"     'device_name': '{request_data.get('device_name')}' ← FROM member_devices.brand")
            logger.info(f"     'device_udi': '{request_data.get('device_udi')}'")
            logger.info(f"     'device_phone_number': '{request_data.get('device_phone_number')}'")
            logger.info(f"     'is_device_callable': {request_data.get('is_device_callable')}")
            logger.info(f"     'fall_detection': '{request_data.get('fall_detection')}'")
            logger.info(f"     'battery_status': '{request_data.get('battery_status')}'")
            logger.info(f"     'customer_type': '{request_data.get('customer_type')}'")
            logger.info(f"     'call_attempt_number': {request_data.get('call_attempt_number')}")
            logger.info(f"     'activation_start_date': '{request_data.get('activation_start_date')}'")
            logger.info(f"     'delivery_date': '{request_data.get('delivery_date')}'")
            logger.info(f"   }}")
            logger.info(f"✅ [BATCH-ORCHESTRATOR] Call #{len(calls)} added to batch")

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

        # Log final batch summary
        logger.info("")
        logger.info("📊 [BATCH-ORCHESTRATOR] ============================================")
        logger.info("📊 [BATCH-ORCHESTRATOR] BATCH REQUEST BUILD COMPLETE")
        logger.info("📊 [BATCH-ORCHESTRATOR] ============================================")
        logger.info(f"📊 [BATCH-ORCHESTRATOR] Total Calls Built: {len(calls)}")
        logger.info(f"📊 [BATCH-ORCHESTRATOR] Skipped Members: {skipped_members}")
        logger.info(f"📊 [BATCH-ORCHESTRATOR] Success Rate: {(len(calls)/(len(members))*100):.1f}%")
        logger.info("")
        logger.info(f"📊 [BATCH-ORCHESTRATOR] Bland AI Configuration:")
        logger.info(f"   🎯 Pathway ID: {pathway_id[:20]}...")
        logger.info(f"   🗣️ Voice ID: {voice_id[:20]}...")
        logger.info(f"   ⏱️ Max Duration: {batch_request['bland_parameters_global']['max_duration']} minutes")
        logger.info(f"   📞 Wait for Greeting: {batch_request['bland_parameters_global']['wait_for_greeting']}")
        logger.info(f"   🎙️ Record Calls: {batch_request['bland_parameters_global']['record']}")
        logger.info(f"   🤖 AMD Enabled: {batch_request['bland_parameters_global']['amd']}")
        logger.info("")
        logger.info(f"📊 [BATCH-ORCHESTRATOR] Batch ready for submission to Bland AI")
        logger.info("📊 [BATCH-ORCHESTRATOR] ============================================")

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
            batch_id, campaign_id, batch_status,
            total_calls_intended, created_ts
        ) VALUES (%s, %s, %s, %s, SYSDATETIMEOFFSET())
        """

        self.db_service.execute_query(
            insert_batch_sql,
            (batch_id, str(campaign_id), "Pending", total_calls),
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
            attempt_id, enrollment_id, batch_id, channel,
            disposition, attempt_ts
        ) VALUES (%s, %s, %s, %s, %s, SYSDATETIMEOFFSET())
        """

        for member in members:
            enrollment_id = str(member.get("enrollment_id"))
            attempt_id = str(uuid.uuid4())

            self.db_service.execute_query(
                insert_attempt_sql,
                (attempt_id, enrollment_id, batch_id, "Voice", "Pending"),
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
        SET vendor_batch_id = %s, batch_status = %s, updated_ts = SYSDATETIMEOFFSET()
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
        SET batch_status = %s, error_message = %s, updated_ts = SYSDATETIMEOFFSET()
        WHERE batch_id = %s
        """

        self.db_service.execute_query(
            update_batch_sql, ("Failed", error_message[:500], batch_id), fetch_results=False
        )

        logger.error(f"❌ [BATCH-ORCHESTRATOR] Marked batch {batch_id} as Failed")
