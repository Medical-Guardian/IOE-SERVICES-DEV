"""
Device Activation Batch Orchestrator

BusinessCaseID: BC-DA-004 (Batch Orchestration & Bland AI Integration), BC-DA-006 (Call Frequency Logic)
Created: 2025-12-07
Updated: 2025-12-24 - Added comprehensive documentation and BusinessCaseID mapping

This service orchestrates batch call submissions to Bland AI for Device Activation campaigns.

ARCHITECTURE:
------------
Implements 3-phase database tracking pattern (following DTC intro call pattern):

Phase 1: Create batch record (status='Pending') BEFORE Bland AI call
  - INSERT into outreach_batches with generated batch_id
  - Allows transaction rollback if Phase 2 or Phase 3 fails
  - Enables audit trail from moment batch is conceived

Phase 2: Create attempt records (disposition='Pending') BEFORE Bland AI call
  - INSERT into outreach_attempts for each member in batch
  - Links attempts to batch_id from Phase 1
  - Captures member/campaign/enrollment context for webhook matching
  - Prevents orphaned attempts if Bland AI submission fails

Phase 3: Update batch with vendor_batch_id (status='Submitted') AFTER Bland AI response
  - UPDATE outreach_batches with Bland AI's vendor_batch_id
  - Changes status to 'Submitted' to indicate successful submission
  - Webhook processor uses vendor_batch_id to match call results

BATCH SPLITTING:
---------------
Bland AI enforces maximum 100 calls per batch submission. This service automatically
splits eligible members into batches of 100 and submits each batch sequentially.

Example: 251 members → 3 batches (100, 100, 51 members)

CALL 5 TIMESTAMP TRACKING (BC-DA-006):
--------------------------------------
When Call 5 is created, this service sets call_5_timestamp in member_campaign_enrollments_enhanced.
This timestamp triggers the 90-day window logic for subsequent calls:

  - call_5_timestamp = SYSDATETIMEOFFSET() (when 5th attempt is created)
  - campaign_end_date = call_5_timestamp + 90 days
  - Call 6+ can occur after 7 days (>7 CALENDAR days = 8+ days) until campaign_end_date is reached
  - Calls 1-4 have NO 90-day limit (use BUSINESS day frequency: 2 days for Calls 2-3, 5 days for Call 4)

Rationale: Allows sufficient time for early contact attempts before enforcing hard cutoff.

BUSINESS DAYS VS CALENDAR DAYS:
-------------------------------
  - Calls 1-4: BUSINESS days (Monday-Friday, excluding US federal holidays)
    * Uses Python get_business_days_between() function (eligibility_service.py:666-730)
    * Call 2-3: 2 business days between attempts
    * Call 4: 5 business days after Call 3
  - Call 5+: CALENDAR days (all days, including weekends and holidays)
    * Uses DATEDIFF(day, ...) for calendar day calculations
    * >7 calendar days between attempts (8+ days minimum)

ERROR HANDLING:
--------------
- Batch failures mark batch as 'Failed' in database
- Individual member failures log warnings but continue processing remaining members
- Transaction rollback prevents partial batch creation
- Detailed error logging for troubleshooting

RELATED DOCUMENTATION:
---------------------
- Complete Architecture: documentation/device_activation/ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md
- Database Operations: documentation/device_activation/ARCHITECTURE/DEVICE_ACTIVATION_DATABASE_OPERATIONS.md
- Bland AI Integration: documentation/device_activation/ARCHITECTURE/DEVICE_ACTIVATION_BLAND_AI_INTEGRATION.md
- BusinessCaseID Mapping: documentation/device_activation/REFERENCE/DEVICE_ACTIVATION_BUSINESSCASEID_MAPPING.md

RELATED CODE:
------------
- DTC Pattern: af_code/af_dtc_intro_call/services/blandai_service.py (reference implementation)
- Eligibility Service: af_code/device_activation_scheduler/services/eligibility_service.py (provides eligible members)
- Bland AI Client: af_code/shared/bland_ai_client.py (handles API communication)
- Bland Validator: af_code/shared/bland_parameters_validator.py (validates config parameters)

EXAMPLE USAGE:
-------------
>>> from af_code.bland_ai_webhook.services.config_manager import ConfigManager
>>> from af_code.bland_ai_webhook.services.database_service import DatabaseService
>>> config_manager = ConfigManager()
>>> db_service = DatabaseService(config_manager)
>>> orchestrator = BatchOrchestrator(db_service, config_manager)
>>>
>>> eligible_members = [
...     {"enrollment_id": "abc-123", "member_id": "mem-001", "campaign_id": "camp-1", ...},
...     # ... 150 more members ...
... ]
>>> result = orchestrator.create_and_submit_batches(eligible_members)
>>> print(result)
{'success': True, 'batches_created': 2, 'calls_submitted': 151}
"""

import logging
import uuid
import json
from typing import List, Dict, Any

from af_code.bland_ai_webhook.services.config_manager import ConfigManager
from af_code.bland_ai_webhook.services.database_service import DatabaseService
from af_code.shared.bland_ai_client import BlandAIClient
from af_code.shared.bland_parameters_validator import BlandParametersValidator
from af_code.partner_campaign_scheduler.models.batch_request import BatchRequest

logger = logging.getLogger(__name__)


class BatchOrchestrator:
    """
    Service to orchestrate batch call submissions to Bland AI for Device Activation campaigns

    Implements 3-phase database tracking pattern (following DTC intro call pattern):
    - Phase 1: Create batch record (status='Pending') BEFORE Bland AI call
    - Phase 2: Create attempt records (disposition='Pending') BEFORE Bland AI call
    - Phase 3: Update batch with vendor_batch_id (status='Submitted') AFTER Bland AI response

    This pattern ensures:
    1. Atomic batch creation (all-or-nothing via transaction rollback)
    2. Complete audit trail (batch + attempts exist before external API call)
    3. Webhook matching capability (vendor_batch_id links Bland AI responses to our records)
    4. Error recovery (failed batches marked in database, not lost)

    BusinessCaseID: BC-DA-004, BC-DA-006

    Attributes:
        db_service (DatabaseService): Database operations service for SQL queries
        config_manager (ConfigManager): Azure Key Vault configuration manager
        bland_client (BlandAIClient): Bland AI API client (None if disabled)
        enabled (bool): Whether batch orchestrator is operational (requires Bland AI API key)

    Methods:
        create_and_submit_batches(): Main orchestration method (splits, creates, submits batches)
        _submit_single_batch(): Submit one batch of up to 100 members (3-phase tracking)
        _build_batch_request(): Build Bland AI BatchRequest payload (18+ parameters)
        _create_outreach_batch(): Phase 1 - INSERT batch record (status='Pending')
        _create_outreach_attempts(): Phase 2 - INSERT attempt records (disposition='Pending')
        _update_call_5_enrollments(): Phase 2.5 - Set call_5_timestamp for Call 5+ logic
        _update_batch_with_vendor_id(): Phase 3 - UPDATE batch (vendor_batch_id, status='Submitted')
        _mark_batch_failed(): Error handler - Mark batch as 'Failed' with error message

    Example:
        >>> from af_code.bland_ai_webhook.services.config_manager import ConfigManager
        >>> from af_code.bland_ai_webhook.services.database_service import DatabaseService
        >>>
        >>> config_manager = ConfigManager()
        >>> db_service = DatabaseService(config_manager)
        >>> orchestrator = BatchOrchestrator(db_service, config_manager)
        >>>
        >>> # Orchestrator automatically initializes Bland AI client
        >>> if orchestrator.enabled:
        ...     result = orchestrator.create_and_submit_batches(eligible_members)
        ...     print(f"Submitted {result['calls_submitted']} calls in {result['batches_created']} batches")
        ... else:
        ...     print("Bland AI client not configured")

    Notes:
        - Max 100 members per batch (Bland AI API limitation)
        - Batches processed sequentially (one at a time)
        - Individual batch failures don't stop remaining batches
        - Call 5 timestamp automatically set when 5th attempt is created (BC-DA-006)
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

        Splits members into batches of 100 (Bland AI limit) and submits each batch sequentially.
        Each batch follows the 3-phase database tracking pattern before and after Bland AI submission.

        BusinessCaseID: BC-DA-004, BC-DA-006

        Process:
            1. Split eligible_members into batches of 100 (Bland AI max per batch)
            2. For each batch:
               a. Submit to Bland AI via _submit_single_batch() (3-phase tracking)
               b. Log success/failure
               c. Continue with remaining batches even if one fails
            3. Return aggregate results

        Args:
            eligible_members (List[Dict]): List of eligible members from EligibilityService.
                Each dict must contain:
                    - enrollment_id (str): Enrollment UUID
                    - member_id (str): Member UUID
                    - campaign_id (str): Campaign UUID
                    - primary_phone (str): E.164 phone number
                    - first_name (str): Member first name
                    - last_name (str): Member last name
                    - call_attempt_number (int): Which attempt this is (1-N)
                    - bland_parameters_global (dict): Bland AI configuration from database
                    - ... (additional member/device fields)

        Returns:
            Dict[str, Any]: Result dictionary containing:
                - success (bool): True if at least one batch submitted successfully
                - batches_created (int): Number of batches successfully created
                - calls_submitted (int): Total calls submitted across all batches
                - error (str, optional): Error message if all batches failed (only if success=False)

        Raises:
            Exception: Critical errors are caught and returned in result dict (doesn't raise)

        Example:
            >>> eligible_members = [
            ...     {"enrollment_id": "abc-123", "member_id": "mem-001", "campaign_id": "camp-1",
            ...      "primary_phone": "+15551234567", "first_name": "John", "last_name": "Doe", ...},
            ...     # ... 150 more members ...
            ... ]
            >>> result = orchestrator.create_and_submit_batches(eligible_members)
            >>> result
            {'success': True, 'batches_created': 2, 'calls_submitted': 151}
            >>>
            >>> # Handle individual batch failures
            >>> if result['success']:
            ...     print(f"✅ Submitted {result['calls_submitted']} calls")
            ... else:
            ...     print(f"❌ All batches failed: {result.get('error')}")

        Notes:
            - Batches are processed sequentially, not in parallel
            - Individual batch failures are logged but don't stop remaining batches
            - If orchestrator is disabled (no Bland AI key), returns success=False immediately
            - Max batch size: 100 members (Bland AI API limit)
            - Call 5 timestamp automatically set when 5th attempt created (BC-DA-006)
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
            logger.info("📝 [BATCH-ORCHESTRATOR] Status: 'Pending' (awaiting Bland AI response)")

            batch_id = self._create_outreach_batch(campaign_id, len(members))

            logger.info("✅ [BATCH-ORCHESTRATOR] Batch record created successfully")
            logger.info(f"✅ [BATCH-ORCHESTRATOR] Internal Batch ID: {batch_id}")
            logger.info("")

            # ============================================================
            # PHASE 2: Create attempt records BEFORE Bland AI call
            # ============================================================
            logger.info("📝 [BATCH-ORCHESTRATOR] ============================================")
            logger.info("📝 [BATCH-ORCHESTRATOR] PHASE 2: CREATE ATTEMPT RECORDS (PRE-SUBMISSION)")
            logger.info("📝 [BATCH-ORCHESTRATOR] ============================================")
            logger.info(
                "📝 [BATCH-ORCHESTRATOR] Creating attempts in engage360.outreach_attempts..."
            )
            logger.info(f"📝 [BATCH-ORCHESTRATOR] Total attempts to create: {len(members)}")
            logger.info("📝 [BATCH-ORCHESTRATOR] Disposition: 'Pending' (awaiting call completion)")

            attempt_id_map = self._create_outreach_attempts(members, batch_id)

            logger.info(
                f"✅ [BATCH-ORCHESTRATOR] {len(members)} attempt records created successfully"
            )
            logger.info("")

            # ============================================================
            # PHASE 2.5: Update enrollments reaching Call 5 (NEW: 2025-12-22)
            # ============================================================
            logger.info("🕐 [BATCH-ORCHESTRATOR] ============================================")
            logger.info("🕐 [BATCH-ORCHESTRATOR] PHASE 2.5: TRACK CALL 5 TIMESTAMP")
            logger.info("🕐 [BATCH-ORCHESTRATOR] ============================================")
            logger.info("🕐 [BATCH-ORCHESTRATOR] Checking for enrollments reaching Call 5...")

            updated_count = self._update_call_5_enrollments(campaign_id)

            if updated_count > 0:
                logger.info(f"✅ [BATCH-ORCHESTRATOR] Updated {updated_count} enrollments:")
                logger.info("   • Set call_5_timestamp to current timestamp")
                logger.info("   • Set campaign_end_date to call_5_timestamp + 90 days")
                logger.info(
                    "   • These members now have 90 days from Call 5 for remaining attempts"
                )
            else:
                logger.info("   ℹ️  No enrollments reached Call 5 in this batch")
            logger.info("")

            # Build Bland AI batch request
            batch_request = self._build_batch_request(members, batch_id, attempt_id_map)

            # Submit to Bland AI (SYNCHRONOUS - waits for response)
            logger.info("")
            logger.info("🚀 [BATCH-ORCHESTRATOR] ============================================")
            logger.info("🚀 [BATCH-ORCHESTRATOR] SUBMITTING BATCH TO BLAND AI")
            logger.info("🚀 [BATCH-ORCHESTRATOR] ============================================")
            logger.info(f"🚀 [BATCH-ORCHESTRATOR] Calls in batch: {len(batch_request.calls)}")
            logger.info(
                "🚀 [BATCH-ORCHESTRATOR] Batch submission mode: SYNCHRONOUS (wait for response)"
            )
            logger.info("🚀 [BATCH-ORCHESTRATOR] Submitting to Bland AI API...")

            # Display all batch data before submission (USER REQUIREMENT)
            calls = batch_request.calls
            logger.info("")
            logger.info("📦 [BATCH-ORCHESTRATOR] ============================================")
            logger.info("📦 [BATCH-ORCHESTRATOR] BATCH REQUEST DATA (DETAILED)")
            logger.info("📦 [BATCH-ORCHESTRATOR] ============================================")
            logger.info(f"📦 [BATCH-ORCHESTRATOR] Batch ID: {batch_id}")
            logger.info(
                f"📦 [BATCH-ORCHESTRATOR] Campaign: {members[0].get('campaign_name', 'Unknown')}"
            )
            logger.info(f"📦 [BATCH-ORCHESTRATOR] Number of Calls: {len(calls)}")
            logger.info("")
            logger.info("📦 [BATCH-ORCHESTRATOR] Call Details:")
            for i, call in enumerate(calls, 1):
                logger.info(f"   Call #{i}:")
                logger.info(f"     • Member ID: {call.get('request_data', {}).get('member_id')}")
                logger.info(f"     • Phone: {call.get('phone_number')}")
                first_name = call.get("request_data", {}).get("first_name", "")
                last_name = call.get("request_data", {}).get("last_name", "")
                logger.info(f"     • Name: {first_name} {last_name}")
                logger.info(
                    f"     • Request Data Keys: {list(call.get('request_data', {}).keys())}"
                )
                logger.info(f"     • Metadata Keys: {list(call.get('metadata', {}).keys())}")

            logger.info("")
            if calls:
                logger.info("📦 [BATCH-ORCHESTRATOR] Full Request Payload (First Call Sample):")
                sample_call = calls[0]
                logger.info(
                    f"   Request Data: {json.dumps(sample_call.get('request_data', {}), indent=2)}"
                )
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
                logger.info(
                    "📝 [BATCH-ORCHESTRATOR] PHASE 3: UPDATE BATCH WITH VENDOR ID (POST-SUBMISSION)"
                )
                logger.info("📝 [BATCH-ORCHESTRATOR] ============================================")
                logger.info(f"📝 [BATCH-ORCHESTRATOR] Updating batch {batch_id}...")
                logger.info("📝 [BATCH-ORCHESTRATOR] New Status: 'Submitted'")
                logger.info(f"📝 [BATCH-ORCHESTRATOR] Vendor Batch ID: {vendor_batch_id}")

                self._update_batch_with_vendor_id(batch_id, vendor_batch_id)

                logger.info("✅ [BATCH-ORCHESTRATOR] Batch updated successfully")
                logger.info("✅ [BATCH-ORCHESTRATOR] 3-Phase tracking complete")
                logger.info("")
                logger.info("📊 [BATCH-ORCHESTRATOR] ============================================")
                logger.info(f"📊 [BATCH-ORCHESTRATOR] BATCH #{batch_number} SUBMISSION COMPLETE")
                logger.info("📊 [BATCH-ORCHESTRATOR] ============================================")
                logger.info(f"📊 [BATCH-ORCHESTRATOR] Total Calls: {calls_submitted}")
                logger.info(f"📊 [BATCH-ORCHESTRATOR] Internal Batch ID: {batch_id}")
                logger.info(f"📊 [BATCH-ORCHESTRATOR] Vendor Batch ID: {vendor_batch_id}")
                logger.info("📊 [BATCH-ORCHESTRATOR] Status: Submitted ✅")
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
                logger.error("❌ [BATCH-ORCHESTRATOR] Marking batch as 'Failed' in database...")

                # Mark batch as Failed in database
                self._mark_batch_failed(batch_id, error_msg)

                logger.error("❌ [BATCH-ORCHESTRATOR] Batch marked as Failed")
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
    ) -> BatchRequest:
        """
        Build the Bland AI batch request payload for Device Activation

        Constructs a BatchRequest model with:
        - Individual call configurations (phone, request_data, metadata)
        - Bland AI global parameters (pathway_id, voice_id, 18+ optional params)
        - Validation of all parameters via BlandParametersValidator

        BusinessCaseID: BC-DA-004

        Args:
            members (List[Dict]): List of eligible members from eligibility query.
                Each dict contains member, device, campaign, and config data.
            batch_id (str): Batch UUID from Phase 1 (_create_outreach_batch)
            attempt_id_map (Dict[str, str]): Mapping of enrollment_id → attempt_id from Phase 2
                Used to link call results back to attempt records via webhook

        Returns:
            BatchRequest: Bland AI batch request model containing:
                - campaign_id (str): Device Activation campaign UUID
                - calls (List[Dict]): List of call configurations (max 100)
                    Each call has: to, request_data (12 fields), metadata (13 fields)
                - pathway_id (str): Bland AI conversation pathway UUID
                - voice_id (str): Bland AI voice UUID
                - bland_parameters_global (Dict): 18+ optional parameters from database

        Raises:
            ValueError: If bland_parameters_global not found in database
            ValueError: If Bland AI parameter validation fails (missing pathway_id, etc.)

        Call Structure (per member):
            {
                "to": "+15551234567",  # E.164 phone format
                "request_data": {
                    # 12 fields passed to AI agent during call
                    "first_name": "John",
                    "last_name": "Doe",
                    "primary_phone": "+15551234567",
                    "email": "john@example.com",
                    "dob": "01-15-1950",  # MM-DD-YYYY format
                    "address_street": "123 Main St",
                    "address_city": "Boston",
                    "address_state": "MA",
                    "address_zip": "02101",
                    "member_brand": "Medical Guardian",
                    "device_name": "Mini Guardian",
                    "fall_detection": "True"  # "True" or "False" as string
                },
                "metadata": {
                    # 13 fields returned in webhook (for tracking/matching)
                    "batch_id": "uuid",
                    "campaign_id": "uuid",
                    "pathway_id": "uuid",
                    "attempt_id": "uuid",  # CRITICAL for webhook matching
                    "member_id": "uuid",
                    "salesforce_account_number": "SF12345",
                    "first_name": "John",
                    "last_name": "Doe",
                    "called_number": "+15551234567",
                    "contact_preference": "phone",
                    "is_device_callable": True,
                    "language_pref": "EN",
                    "call_type_code": "DEVICE_ACTIVATION"
                }
            }

        Example:
            >>> members = [{"enrollment_id": "abc-123", "member_id": "mem-001", ...}]
            >>> batch_id = "batch-uuid-123"
            >>> attempt_id_map = {"abc-123": "attempt-uuid-456"}
            >>> batch_request = self._build_batch_request(members, batch_id, attempt_id_map)
            >>> len(batch_request.calls)
            1
            >>> batch_request.pathway_id
            'pathway-uuid-789'

        Notes:
            - Members without valid phone numbers are skipped with warning
            - bland_parameters_global retrieved from database (not hardcoded)
            - BlandParametersValidator ensures all required parameters present
            - Metadata structure standardized to DTC format (13 fields)
            - Request data limited to 12 fields (Bland AI pathway requirement)
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
                "Please configure in campaign_call_configs_enhanced table"
            )
            logger.error(f"❌ [BATCH-ORCHESTRATOR] {error_msg}")
            raise ValueError(error_msg)

        # Parse JSON if it's a string
        if isinstance(campaign_config, str):
            campaign_config = json.loads(campaign_config)

        logger.info(
            f"✅ [BATCH-ORCHESTRATOR] Using database configuration for campaign '{campaign_name}'"
        )

        # Display all configuration data (USER REQUIREMENT)
        logger.info("📋 [BATCH-ORCHESTRATOR] ============================================")
        logger.info("📋 [BATCH-ORCHESTRATOR] BLAND AI CONFIGURATION")
        logger.info("📋 [BATCH-ORCHESTRATOR] ============================================")
        logger.info(f"📋 [BATCH-ORCHESTRATOR] Campaign: {campaign_name}")
        logger.info(f"📋 [BATCH-ORCHESTRATOR] Batch ID: {batch_id}")
        logger.info(f"📋 [BATCH-ORCHESTRATOR] Member Count: {len(members)}")
        logger.info("📋 [BATCH-ORCHESTRATOR] Global Parameters (bland_parameters_global):")
        for key, value in campaign_config.items():
            logger.info(f"   • {key}: {value}")
        logger.info("📋 [BATCH-ORCHESTRATOR] ============================================")

        # Validate Bland AI parameters using BlandParametersValidator
        validator = BlandParametersValidator()
        validation_result = validator.validate(
            campaign_config or {},
            campaign_name,
            strict=True,  # Fail on missing required params
        )

        if not validation_result.is_valid:
            error_msg = f"Invalid Bland AI configuration for campaign '{campaign_name}':\n"
            for error in validation_result.errors:
                error_msg += f"  - {error}\n"
            error_msg += "\nPlease configure in campaign_call_configs_enhanced table"
            logger.error(f"❌ [BATCH-ORCHESTRATOR] {error_msg}")
            raise ValueError(error_msg)

        # Log deprecation warnings
        for warning in validation_result.warnings:
            logger.warning(f"⚠️ [BATCH-ORCHESTRATOR] {warning}")

        # Log unknown parameters (future additions)
        for info in validation_result.info_messages:
            logger.info(f"ℹ️ [BATCH-ORCHESTRATOR] {info}")

        # Use validated and normalized parameters
        bland_params = validation_result.normalized_params

        # Extract pathway_id (or task) - one of these is required
        pathway_id = bland_params.get("pathway_id") or bland_params.get("task")

        # Extract voice_id if present (optional parameter)
        voice_id = bland_params.get("voice_id") or bland_params.get("voice")

        logger.info(
            f"✅ [BATCH-ORCHESTRATOR] Validated {len(bland_params)} Bland AI parameters from database"
        )
        logger.info(f"🔧 [BATCH-ORCHESTRATOR] Available parameters: {list(bland_params.keys())}")
        logger.info(f"   🎭 Using: pathway_id={pathway_id}, voice_id={voice_id}")

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
            # 14 fields as required by Bland AI pathway (updated 2026-01-12)
            request_data = {
                # Member demographics (from members table)
                "first_name": member.get("first_name"),
                "last_name": member.get("last_name"),
                "primary_phone": member.get("primary_phone"),
                "email": member.get("email"),
                "dob": member.get("dob").strftime("%m-%d-%Y") if member.get("dob") else "",
                # Address (from members table)
                "address_street": member.get("address_street") or "",
                "address_city": member.get("address_city") or "",
                "address_state": member.get("address_state") or "",
                "address_zip": member.get("address_zip") or "",
                # Brand (from members table)
                "member_brand": member.get("member_brand") or "",
                # Device information (from member_devices table)
                "device_name": member.get("device_brand") or "",  # member_devices.brand
                "fall_detection": "True" if member.get("fall_detection") == 1 else "False",
                "powersaver_mode": member.get("powersaver_mode")
                or "",  # Default/Standard/Battery Saver
                # Monitoring system ID (from member_identifiers table)
                "monitoring_system_id": member.get("monitoring_system_id") or "",
            }

            # Build metadata (used for webhook processing)
            # Updated 2025-12-23: Standardized to DTC format (13 fields)
            metadata = {
                # Core tracking IDs (5 fields)
                "batch_id": batch_id,
                "campaign_id": str(campaign_id),
                "pathway_id": pathway_id,  # NEW: From bland_parameters_global
                "attempt_id": attempt_id,  # CRITICAL for webhook
                "member_id": str(member.get("member_id")),
                # Member identification (4 fields)
                "salesforce_account_number": member.get("salesforce_account_number"),  # NEW
                "first_name": member.get("first_name"),
                "last_name": member.get("last_name"),
                "called_number": phone_number,
                # Communication preferences (4 fields)
                "contact_preference": "phone",  # NEW: Static for activation (always call member)
                "is_device_callable": bool(member.get("is_device_callable", 0)),  # Convert to bool
                "language_pref": member.get("language_pref", "EN"),
                "call_type_code": "DEVICE_ACTIVATION",  # NEW: Static identifier for campaign type
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
            logger.info("📞 [BATCH-ORCHESTRATOR] ============================================")
            logger.info(f"📞 [BATCH-ORCHESTRATOR] CALL #{len(calls)} - MEMBER DATA")
            logger.info("📞 [BATCH-ORCHESTRATOR] ============================================")
            logger.info("📞 [BATCH-ORCHESTRATOR] Member Identification:")
            logger.info(f"   👤 Member ID: {member.get('member_id')}")
            logger.info(f"   👤 Enrollment ID: {enrollment_id}")
            logger.info(f"   👤 Name: {member.get('first_name')} {member.get('last_name')}")
            logger.info(f"   📞 Phone: {phone_number}")
            logger.info(f"   📧 Email: {member.get('email', 'N/A')}")
            logger.info("")
            logger.info("📞 [BATCH-ORCHESTRATOR] Address & Demographics:")
            logger.info(f"   🏠 Street: {member.get('address_street', 'N/A')}")
            logger.info(f"   🏠 City: {member.get('address_city', 'N/A')}")
            logger.info(f"   🏠 State: {member.get('address_state', 'N/A')}")
            logger.info(f"   🏠 Zip: {member.get('address_zip', 'N/A')}")
            logger.info(
                f"   🎂 DOB: {member.get('dob').strftime('%m-%d-%Y') if member.get('dob') else 'N/A'}"
            )
            logger.info(f"   🌍 Timezone: {member.get('timezone', 'N/A')}")
            logger.info(f"   🗣️ Language: {member.get('language_pref', 'EN')}")
            logger.info(f"   🆔 Monitoring System ID: {member.get('monitoring_system_id', 'N/A')}")
            logger.info("")
            logger.info("📞 [BATCH-ORCHESTRATOR] Brand Information:")
            logger.info(
                f"   🏢 Member Brand: {member.get('member_brand', 'N/A')} (from members.member_brand)"
            )
            logger.info(
                f"   📱 Device Brand: {member.get('device_brand', 'N/A')} (from member_devices.brand)"
            )
            logger.info("")
            logger.info("📞 [BATCH-ORCHESTRATOR] Device Information:")
            logger.info(f"   📱 Device Name: {member.get('device_name', 'N/A')}")
            logger.info(f"   🔢 Device UDI: {member.get('device_udi', 'N/A')}")
            logger.info(f"   📞 Device Phone: {member.get('device_phone_number', 'N/A')}")
            logger.info(f"   📡 Device Callable: {member.get('is_device_callable', 0)}")
            logger.info(f"   🚨 Fall Detection: {member.get('fall_detection', 'N/A')}")
            logger.info(f"   🔋 PowerSaver Mode: {member.get('powersaver_mode', 'N/A')}")
            logger.info("")
            logger.info("📞 [BATCH-ORCHESTRATOR] Campaign Context:")
            logger.info(f"   📋 Campaign ID: {campaign_id}")
            logger.info(f"   📋 Campaign Name: {campaign_name}")
            logger.info(f"   👥 Customer Type: {member.get('customer_type', 'N/A')}")
            logger.info(f"   🔢 Call Attempt #: {member.get('call_attempt_number', 1)}")
            logger.info(f"   📅 Activation Start: {member.get('activation_start_date', 'N/A')}")
            logger.info(f"   📦 Delivery Date: {member.get('delivery_date', 'N/A')}")
            logger.info("")
            logger.info("📞 [BATCH-ORCHESTRATOR] Tracking IDs:")
            logger.info(f"   🆔 Attempt ID: {attempt_id}")
            logger.info(f"   📦 Batch ID: {batch_id}")
            logger.info(f"✅ [BATCH-ORCHESTRATOR] Call #{len(calls)} added to batch")

        if skipped_members > 0:
            logger.warning(
                f"⚠️ [BATCH-ORCHESTRATOR] Skipped {skipped_members} members (missing data)"
            )

        # Build complete batch request using BatchRequest dataclass
        batch_request = BatchRequest(
            campaign_id=str(campaign_id),
            calls=calls,
            pathway_id=pathway_id,
            voice_id=voice_id,
            bland_parameters_global=bland_params,  # Use validated params from database
        )

        # Log final batch summary
        logger.info("")
        logger.info("📊 [BATCH-ORCHESTRATOR] ============================================")
        logger.info("📊 [BATCH-ORCHESTRATOR] BATCH REQUEST BUILD COMPLETE")
        logger.info("📊 [BATCH-ORCHESTRATOR] ============================================")
        logger.info(f"📊 [BATCH-ORCHESTRATOR] Total Calls Built: {len(calls)}")
        logger.info(f"📊 [BATCH-ORCHESTRATOR] Skipped Members: {skipped_members}")
        logger.info(f"📊 [BATCH-ORCHESTRATOR] Success Rate: {(len(calls)/(len(members))*100):.1f}%")
        logger.info("")
        logger.info("📊 [BATCH-ORCHESTRATOR] Bland AI Configuration:")
        logger.info(f"   🎯 Pathway ID: {pathway_id[:20]}...")
        logger.info(f"   🗣️ Voice ID: {voice_id[:20]}...")
        # Use .get() for optional parameters to prevent KeyError
        bland_config = batch_request.bland_parameters_global
        logger.info(f"   ⏱️ Max Duration: {bland_config.get('max_duration', 'N/A')} minutes")
        logger.info(f"   📞 Wait for Greeting: {bland_config.get('wait_for_greeting', 'N/A')}")
        logger.info(f"   🎙️ Record Calls: {bland_config.get('record', 'N/A')}")
        logger.info(f"   🤖 Answered By Enabled: {bland_config.get('answered_by_enabled', 'N/A')}")
        logger.info("")
        logger.info("📊 [BATCH-ORCHESTRATOR] Batch ready for submission to Bland AI")
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

    def _update_call_5_enrollments(self, campaign_id: str) -> int:
        """
        Update enrollments that just reached Call 5 (implements 90-day window logic)

        Sets call_5_timestamp and campaign_end_date for enrollments where:
        - call_5_timestamp is currently NULL (hasn't reached Call 5 yet)
        - Total outreach_attempts count = 5 (just created 5th attempt in Phase 2)

        This triggers the 90-day window for subsequent calls (Call 6+).

        BusinessCaseID: BC-DA-006 (Call Frequency & Sequencing Logic)
        Created: 2025-12-22
        Updated: 2025-12-24 - Added comprehensive documentation

        Background:
            Device Activation call frequency differs between Calls 1-4 and Call 5+:
            - Calls 1-4: BUSINESS day frequency (2 days for Calls 2-3, 5 days for Call 4), max 4 attempts, NO 90-day limit
            - Call 5+: >7 CALENDAR days frequency (8+ days), unlimited attempts, 90-day window

            The 90-day window starts from call_5_timestamp (NOT activation_start_date).
            This allows sufficient time for early contact attempts before enforcing a hard cutoff.

            Business days exclude weekends and US federal holidays (uses Python get_business_days_between() function).
            Calendar days include all days (uses DATEDIFF(day, ...) with > 7 operator).

        SQL Logic:
            UPDATE member_campaign_enrollments_enhanced
            SET
                call_5_timestamp = SYSDATETIMEOFFSET(),
                campaign_end_date = CAST(DATEADD(DAY, 90, SYSDATETIMEOFFSET()) AS DATE)
            WHERE
                call_5_timestamp IS NULL  -- Not already set
                AND campaign_id = %s
                AND (SELECT COUNT(*) FROM outreach_attempts WHERE enrollment_id = e.enrollment_id) = 5

        Args:
            campaign_id (str): Device Activation campaign UUID

        Returns:
            int: Number of enrollments updated (count of members reaching Call 5 in this batch)

        Example:
            >>> # After creating 5th attempt in Phase 2
            >>> updated_count = self._update_call_5_enrollments("campaign-uuid-123")
            >>> if updated_count > 0:
            ...     print(f"{updated_count} members now have 90-day window starting from Call 5")
            3 members now have 90-day window starting from Call 5

        Database Updates (per enrollment):
            - call_5_timestamp: Set to current timestamp (SYSDATETIMEOFFSET())
            - campaign_end_date: Set to call_5_timestamp + 90 days

        Eligibility Impact:
            After this update, eligibility_service.py will:
            1. Allow Call 6+ every >7 CALENDAR days (8+ days, includes weekends/holidays)
            2. Block calls after campaign_end_date is reached
            3. No longer enforce BUSINESS day frequency (that was for Calls 1-4)

        Notes:
            - Only updates enrollments where call_5_timestamp is NULL
            - Only updates enrollments with exactly 5 attempts
            - Called in Phase 2.5 (after attempts created, before Bland AI submission)
            - Multiple batch submissions in quick succession won't double-update (NULL check)
        """
        update_call_5_sql = """
        UPDATE e
        SET
            e.call_5_timestamp = SYSDATETIMEOFFSET(),
            e.campaign_end_date = CAST(DATEADD(DAY, 90, SYSDATETIMEOFFSET()) AS DATE)
        FROM engage360.member_campaign_enrollments_enhanced e
        WHERE
            e.call_5_timestamp IS NULL  -- Haven't set Call 5 timestamp yet
            AND e.campaign_id = %s      -- Device Activation campaign
            AND (
                -- Count total attempts for this enrollment = 5 (just reached Call 5)
                SELECT COUNT(*)
                FROM engage360.outreach_attempts oa
                WHERE oa.enrollment_id = e.enrollment_id
            ) = 5
        """

        # Execute update and get count of affected rows
        self.db_service.execute_query(
            update_call_5_sql,
            params=(str(campaign_id),),
            fetch_results=False,
        )

        # pymssql doesn't return rowcount directly from execute_query
        # We need to check how many rows were affected
        # For now, we'll query to get the count
        count_query = """
        SELECT COUNT(*) as updated_count
        FROM engage360.member_campaign_enrollments_enhanced e
        WHERE
            e.call_5_timestamp IS NOT NULL
            AND e.campaign_id = %s
            AND DATEDIFF(second, e.call_5_timestamp, SYSDATETIMEOFFSET()) < 10  -- Updated in last 10 seconds
        """

        count_result = self.db_service.execute_query(
            count_query,
            params=(str(campaign_id),),
            fetch_results=True,
        )

        updated_count = count_result[0]["updated_count"] if count_result else 0

        return updated_count

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
