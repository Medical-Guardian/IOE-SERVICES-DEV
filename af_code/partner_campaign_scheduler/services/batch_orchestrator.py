import logging
import json
import uuid
from typing import List, Dict, Any
from datetime import datetime
import pytz
from ..models.qualified_campaign import QualifiedCampaign
from ..models.eligible_member import EligibleMember
from ..models.batch_request import BatchRequest, BatchResult
from ...shared.bland_ai_client import BlandAIClient
from ...bland_ai_webhook.services.config_manager import ConfigManager
from ...bland_ai_webhook.services.database_service import DatabaseService
from ...shared.timezone_utils import TimezoneConverter
from ...shared.phone_utils import standardize_phone
from .care_gap_mapper import CareGapMapper

logger = logging.getLogger(__name__)


class BatchOrchestrator:
    """
    Service to orchestrate batch call submissions to Bland AI
    """

    def __init__(self, config_manager: ConfigManager, db_service: DatabaseService):
        self.config_manager = config_manager
        self.db_service = db_service
        self.enabled = False

        # Initialize CareGapMapper for care gap completion flag mapping
        self.care_gap_mapper = CareGapMapper(db_service)
        logger.info("🔧 [BATCH-ORCHESTRATOR] CareGapMapper initialized")

        try:
            self.bland_client = BlandAIClient(config_manager)
            self.enabled = True
            logger.info("🔧 [BATCH-ORCHESTRATOR] Service initialized with Bland AI client")
        except ValueError as e:
            logger.warning(f"⚠️ [BATCH-ORCHESTRATOR] Bland AI client unavailable: {str(e)}")
            logger.info("🔧 [BATCH-ORCHESTRATOR] Service initialized in disabled mode")
            self.bland_client = None

    def submit_batch(
        self, campaign: QualifiedCampaign, members: List[EligibleMember]
    ) -> BatchResult:
        """
        Submit a batch of members to Bland AI for calling (SYNCHRONOUS)

        Implements 3-phase database tracking (following DTC pattern):
        Phase 1: Create batch record (status='Pending') BEFORE Bland AI call
        Phase 2: Create attempt records (disposition='Pending') BEFORE Bland AI call
        Phase 3: Update batch with vendor_batch_id (status='Submitted') AFTER Bland AI response

        Args:
            campaign: The campaign configuration
            members: List of eligible members to call

        Returns:
            BatchResult with success status and details
        """
        logger.info(
            f"🚀 [BATCH-ORCHESTRATOR] Submitting batch of {len(members)} members for campaign: {campaign.name}"
        )

        if not self.enabled:
            logger.warning(
                "⚠️ [BATCH-ORCHESTRATOR] Batch orchestrator disabled - skipping submission"
            )
            return BatchResult(
                success=False,
                error="Batch orchestrator disabled (Bland AI API key not configured)",
                members_count=len(members),
                campaign_id=str(campaign.campaign_id),  # Convert UUID to string
            )

        try:
            # ============================================================
            # PHASE 1: Create batch record BEFORE Bland AI call
            # ============================================================
            batch_id = self._create_outreach_batch(campaign.campaign_id, len(members))
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

            # Build Bland AI batch request with attempt_id mapping
            batch_request = self._build_batch_request(campaign, members, batch_id, attempt_id_map)

            logger.info(
                f"📞 [BATCH-ORCHESTRATOR] Built batch request with {len(batch_request.calls)} calls"
            )
            logger.info(f"🎭 [BATCH-ORCHESTRATOR] Using pathway: {batch_request.pathway_id}")
            logger.info(f"🎤 [BATCH-ORCHESTRATOR] Using voice: {batch_request.voice_id}")

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

                return BatchResult(
                    success=True,
                    batch_id=vendor_batch_id,  # Return Bland AI batch ID
                    members_count=len(members),
                    campaign_id=str(campaign.campaign_id),  # Convert UUID to string
                    submitted_members=[
                        str(m.member_id) for m in members
                    ],  # Convert UUIDs to strings
                )
            else:
                error_msg = response.get("error", "Unknown error")
                status_code = response.get("status_code", "Unknown")

                logger.error("❌ [BATCH-ORCHESTRATOR] Batch submission failed")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] Error: {error_msg}")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] Status code: {status_code}")

                # Mark batch as Failed in database
                self._mark_batch_failed(batch_id, error_msg)

                return BatchResult(
                    success=False,
                    error=f"Status {status_code}: {error_msg}",
                    members_count=len(members),
                    campaign_id=str(campaign.campaign_id),  # Convert UUID to string
                )

        except Exception as e:
            logger.error(f"🚨 [BATCH-ORCHESTRATOR] Exception during batch submission: {str(e)}")

            # Mark batch as Failed if it was created
            if "batch_id" in locals():
                self._mark_batch_failed(batch_id, str(e))

            return BatchResult(
                success=False,
                error=f"Exception: {str(e)}",
                members_count=len(members),
                campaign_id=str(campaign.campaign_id),  # Convert UUID to string
            )

    def _build_batch_request(
        self,
        campaign: QualifiedCampaign,
        members: List[EligibleMember],
        batch_id: str,
        attempt_id_map: Dict[str, str],
    ) -> BatchRequest:
        """
        Build the Bland AI batch request payload with DTC-style request_data and complete metadata

        Args:
            campaign: Qualified campaign configuration
            members: List of eligible members
            batch_id: Batch UUID from Phase 1
            attempt_id_map: Mapping of enrollment_id to attempt_id from Phase 2
        """
        logger.info(f"🔨 [BATCH-ORCHESTRATOR] Building batch request for {len(members)} members")

        calls = []
        skipped_members = 0

        for member in members:
            # Get attempt_id for this member
            enrollment_id = str(member.enrollment_id)
            attempt_id = attempt_id_map.get(enrollment_id)

            if not attempt_id:
                logger.error(
                    f"❌ [BATCH-ORCHESTRATOR] No attempt_id found for enrollment {enrollment_id}"
                )
                skipped_members += 1
                continue

            # Determine phone number based on contact preference
            phone_number = self._get_target_phone(member, campaign.contact_pref)

            if not phone_number:
                logger.warning(
                    f"⚠️ [BATCH-ORCHESTRATOR] No valid phone for member: {member.member_id}"
                )
                skipped_members += 1
                continue

            # Build DTC-style request_data with care gaps and demographics
            logger.info(
                f"📋 [BATCH-ORCHESTRATOR] Building request_data for member: {member.member_id}"
            )
            request_data = self._build_request_data(member, campaign)

            # ============================================================
            # TIME DISPLAY - Show current time and member's local time
            # ============================================================
            # Get current UTC time
            now_utc = datetime.now(pytz.UTC)

            # Convert to campaign timezone for comparison
            campaign_tz = TimezoneConverter.to_pytz(campaign.operating_tz)
            now_in_campaign_tz = now_utc.astimezone(campaign_tz)

            # Log time comparison (similar to campaign_qualifier.py pattern)
            logger.info(f"🕐 [BATCH-ORCHESTRATOR] ⏰ TIME CHECK for member {member.member_id}")
            logger.info(
                f"   📍 Campaign timezone: {campaign.operating_tz} (mode: {campaign.timezone_flag})"
            )
            logger.info(f"   🌍 Current time (UTC): {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            logger.info(
                f"   🌍 Current time ({campaign.operating_tz}): {now_in_campaign_tz.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )
            logger.info(f"   👤 Member timezone: {member.timezone}")
            logger.info(f"   ⏰ Member current time (from SQL): {member.member_current_time}")

            # Log complete request_data for traceability
            logger.info(f"📦 [BATCH-ORCHESTRATOR] Member {member.member_id} request_data:")
            logger.info(
                f"   👤 Demographics: name={request_data.get('first_name')} {request_data.get('last_name')}, "
                f"language={request_data.get('language_pref')}, dob={request_data.get('dob')}"
            )
            logger.info(
                f"   📍 Address: {request_data.get('service_address')}, "
                f"{request_data.get('city')}, {request_data.get('state')} {request_data.get('zip_code')}"
            )
            logger.info(f"   📞 Phone: {request_data.get('primary_phone')}")
            logger.info(
                f"   🏥 Partner: {request_data.get('partner_contact_name')} - {request_data.get('org_name')}"
            )

            # Log care gap flags
            care_gap_flags = {
                k: v
                for k, v in request_data.items()
                if k.endswith("_import_flag") or k.endswith("_completion_flag")
            }
            if care_gap_flags:
                logger.info(
                    f"   🩺 Care gaps ({len(care_gap_flags)//2} active): {json.dumps(care_gap_flags, indent=2)}"
                )
            else:
                logger.info("   🩺 Care gaps: None")

            # Build complete metadata (DTC fields + Partner fields)
            call_data = {
                "to": phone_number,
                "request_data": request_data,  # DTC-style request_data
                "metadata": {
                    # Core Tracking IDs (DTC + Partner)
                    "attempt_id": attempt_id,  # FROM DTC - CRITICAL for webhook
                    "batch_id": batch_id,  # FROM DTC - Batch tracking
                    "campaign_id": str(campaign.campaign_id),  # Both have this
                    "member_id": str(member.member_id),  # Both have this
                    "enrollment_id": enrollment_id,  # Partner-specific
                    "org_id": str(campaign.org_id),  # Partner-specific
                    "call_type_id": str(campaign.call_type_id) if campaign.call_type_id else None,
                    # Bland AI Configuration
                    "pathway_id": campaign.pathway_id
                    or (
                        campaign.bland_parameters_global.get("pathway_id")
                        if campaign.bland_parameters_global
                        else None
                    ),
                    # Member Identification (DTC + Partner)
                    "first_name": member.first_name,  # Both have this
                    "last_name": member.last_name,  # Both have this
                    "called_number": phone_number,  # FROM DTC - Phone actually called
                    "salesforce_account_number": getattr(
                        member, "salesforce_account_number", None
                    ),  # FROM DTC - if available
                    # Communication Preferences
                    "language_pref": getattr(member, "language_pref", None)
                    or request_data.get("language_pref"),  # FROM DTC
                    "contact_preference": campaign.contact_pref,  # Partner-specific
                    # Partner-Specific Context
                    "campaign_type": "Partner",
                    "audience_file_batch": campaign.audience_file_batch,
                    "member_timezone": member.timezone,
                    "is_device_callable": member.is_device_callable,
                    "total_previous_attempts": member.total_attempts,
                },
            }
            calls.append(call_data)

        if skipped_members > 0:
            logger.warning(
                f"⚠️ [BATCH-ORCHESTRATOR] Skipped {skipped_members} members due to missing phone numbers"
            )

        logger.info(
            f"📞 [BATCH-ORCHESTRATOR] Successfully built {len(calls)} calls with complete request_data"
        )

        # Handle NULL bland_parameters_global - fall back to environment variables
        if not campaign.bland_parameters_global:
            logger.warning(
                f"⚠️ [BATCH-ORCHESTRATOR] bland_parameters_global is NULL for campaign '{campaign.name}'"
            )
            logger.warning("⚠️ [BATCH-ORCHESTRATOR] Falling back to environment variables")

            # Construct config from environment variables
            bland_params_from_env = {
                "pathway_id": self.config_manager.get_config("PARTNER_CAMPAIGN_PATHWAY_ID"),
                "voice_id": self.config_manager.get_config("PARTNER_CAMPAIGN_VOICE_ID"),
                "webhook_url": self.config_manager.get_config("BLAND_WEBHOOK_URL"),
                "max_duration": self.config_manager.get_config("BLAND_MAX_DURATION", "300"),
            }

            # Remove None values
            campaign.bland_parameters_global = {k: v for k, v in bland_params_from_env.items() if v}

            if not campaign.bland_parameters_global:
                raise ValueError(
                    f"bland_parameters_global is NULL and no environment variables configured for campaign '{campaign.name}'"
                )

        # Import and validate bland_parameters_global from database
        from af_code.shared.bland_parameters_validator import BlandParametersValidator

        validator = BlandParametersValidator()
        validation_result = validator.validate(
            campaign.bland_parameters_global or {},
            campaign.name,
            strict=True,  # Fail on missing required params
        )

        if not validation_result.is_valid:
            error_msg = f"Invalid Bland AI configuration for campaign '{campaign.name}':\n"
            for error in validation_result.errors:
                error_msg += f"  - {error}\n"
            error_msg += (
                "\nFix by updating bland_parameters_global in campaign_call_configs_enhanced table"
            )
            logger.error(f"🚨 [BATCH-ORCHESTRATOR] {error_msg}")
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

        return BatchRequest(
            campaign_id=str(campaign.campaign_id),  # Convert UUID to string for JSON serialization
            calls=calls,
            pathway_id=pathway_id,
            voice_id=voice_id,
            bland_parameters_global=bland_params,  # Pass complete JSON
        )

    def _build_request_data(
        self, member: EligibleMember, campaign: QualifiedCampaign
    ) -> Dict[str, Any]:
        """
        Build DTC-style request_data with demographics, partner info, and care gaps

        Returns a dictionary with:
        - Demographic fields (language_pref, first_name, last_name, service_address, etc.)
        - Partner organization fields (partner_contact_name, org_name)
        - Care gap import flags (only "Y" values)
        - Care gap completion flags (empty string values)
        """
        logger.debug(f"🔨 [BATCH-ORCHESTRATOR] Building request_data for member {member.member_id}")

        # Extract care gaps with completion flags
        care_gaps_data = self._extract_care_gaps_with_completion(member.member_care_gap_parameters)

        # Build complete request_data
        request_data = {
            # DTC-style demographic fields
            "language_pref": member.language_pref or "",
            "first_name": member.first_name or "",
            "last_name": member.last_name or "",
            "service_address": member.address_street or "",
            "zip_code": member.address_zip or "",
            "primary_phone": member.primary_phone or "",
            "city": member.address_city or "",
            "state": member.address_state or "",
            "dob": member.dob.strftime("%Y-%m-%d") if member.dob else "",
            # Partner organization fields
            "partner_contact_name": campaign.partner_contact_name or "",
            "org_name": campaign.org_name or "",
            # Care gap flags (import + completion)
            **care_gaps_data,
        }

        logger.debug(
            f"✅ [BATCH-ORCHESTRATOR] Built request_data with {len(care_gaps_data)//2} care gaps"
        )
        return request_data

    def _extract_care_gaps_with_completion(self, member_care_gap_parameters: str) -> Dict[str, str]:
        """
        Extract care gap import flags and add corresponding completion flags

        Args:
            member_care_gap_parameters: JSON string from member_campaign_enrollments_enhanced

        Returns:
            Dictionary with import flags (value "Y") and completion flags (value "")

        Example:
            Input: {"awv_import_flag": "Y", "dental_exam_import_flag": "Y", "other_flag": "N"}
            Output: {
                "awv_import_flag": "Y",
                "awv_completion_flag": "",
                "dental_exam_import_flag": "Y",
                "dental_exam_completion_flag": ""
            }
        """
        care_gaps_data = {}

        if not member_care_gap_parameters:
            logger.debug("🩺 [BATCH-ORCHESTRATOR] No care gap parameters for member")
            return care_gaps_data

        try:
            # Parse JSON string
            care_gap_flags = json.loads(member_care_gap_parameters)
            logger.debug(
                f"🩺 [BATCH-ORCHESTRATOR] Parsed {len(care_gap_flags)} care gap flags from JSON"
            )

            # Filter for "Y" values and add completion flags
            for flag_name, flag_value in care_gap_flags.items():
                if flag_value == "Y":
                    # Add import flag
                    care_gaps_data[flag_name] = "Y"
                    logger.debug(f"   ✅ [BATCH-ORCHESTRATOR] Added import flag: {flag_name} = Y")

                    # Get corresponding completion flag name from CareGapMapper
                    completion_flag_name = self.care_gap_mapper.get_completion_flag_name(flag_name)

                    if completion_flag_name:
                        # Add completion flag with empty string value
                        care_gaps_data[completion_flag_name] = ""
                        logger.debug(
                            f'   📋 [BATCH-ORCHESTRATOR] Added completion flag: {completion_flag_name} = ""'
                        )
                    else:
                        logger.warning(
                            f"   ⚠️ [BATCH-ORCHESTRATOR] No completion flag mapping found for: {flag_name}"
                        )

            logger.info(
                f"🩺 [BATCH-ORCHESTRATOR] Extracted {len(care_gaps_data)//2} active care gaps"
            )

        except json.JSONDecodeError as e:
            logger.error(f"🚨 [BATCH-ORCHESTRATOR] Failed to parse care gap JSON: {str(e)}")
            logger.error(f"🚨 [BATCH-ORCHESTRATOR] Raw value: {member_care_gap_parameters}")
        except Exception as e:
            logger.error(f"🚨 [BATCH-ORCHESTRATOR] Error extracting care gaps: {str(e)}")
            import traceback

            logger.error(f"🚨 [BATCH-ORCHESTRATOR] Traceback: {traceback.format_exc()}")

        return care_gaps_data

    def _create_outreach_batch(self, campaign_id: str, member_count: int) -> str:
        """
        PHASE 1: Create outreach batch record in database BEFORE Bland AI call

        Following DTC pattern - creates batch with status='Pending'

        Args:
            campaign_id: UUID of the campaign
            member_count: Number of members in this batch

        Returns:
            batch_id: UUID of the created batch record
        """
        # Generate UUID for batch (Python-side generation, not database)
        batch_id = str(uuid.uuid4())
        logger.info(f"📦 [BATCH-ORCHESTRATOR] Phase 1: Creating batch record with ID: {batch_id}")

        query = """
            INSERT INTO engage360.outreach_batches
            (batch_id, campaign_id, batch_status, total_calls_intended, submitted_ts)
            VALUES (%s, %s, 'Pending', %s, SYSDATETIMEOFFSET())
        """

        params = (batch_id, campaign_id, member_count)

        try:
            self.db_service.execute_query(query, params, fetch_results=False)
            logger.info("✅ [BATCH-ORCHESTRATOR] Phase 1: Batch record created successfully")
            return batch_id
        except Exception as e:
            logger.error(
                f"🚨 [BATCH-ORCHESTRATOR] Phase 1 FAILED: Error creating batch record: {str(e)}"
            )
            raise

    def _create_outreach_attempts(
        self, members: List[EligibleMember], batch_id: str
    ) -> Dict[str, str]:
        """
        PHASE 2: Create outreach attempt records in database BEFORE Bland AI call

        Following DTC pattern - creates N attempt records with disposition='Pending'

        Args:
            members: List of eligible members
            batch_id: UUID of the batch (from Phase 1)

        Returns:
            Dict mapping enrollment_id (str) to attempt_id (str)
        """
        logger.info(f"📝 [BATCH-ORCHESTRATOR] Phase 2: Creating {len(members)} attempt records")

        # Build bulk insert for better performance
        attempt_id_map = {}  # Store enrollment_id -> attempt_id mapping
        values_list = []
        params = []

        for member in members:
            attempt_id = str(uuid.uuid4())
            enrollment_id = str(member.enrollment_id)

            # Store mapping for metadata inclusion
            attempt_id_map[enrollment_id] = attempt_id

            values_list.append("(%s, %s, 'Voice', SYSUTCDATETIME(), 'Pending', 0, %s)")
            params.extend(
                [
                    attempt_id,
                    enrollment_id,  # FK to member_campaign_enrollments_enhanced
                    batch_id,  # FK to outreach_batches
                ]
            )

        query = f"""
            INSERT INTO engage360.outreach_attempts
            (attempt_id, enrollment_id, channel, attempt_ts, disposition, retry_seq, batch_id)
            VALUES {', '.join(values_list)}
        """

        try:
            self.db_service.execute_query(query, params, fetch_results=False)
            logger.info(
                f"✅ [BATCH-ORCHESTRATOR] Phase 2: {len(members)} attempt records created successfully"
            )
            logger.info(
                f"🔑 [BATCH-ORCHESTRATOR] Generated {len(attempt_id_map)} attempt_id mappings for metadata"
            )
            return attempt_id_map
        except Exception as e:
            logger.error(
                f"🚨 [BATCH-ORCHESTRATOR] Phase 2 FAILED: Error creating attempt records: {str(e)}"
            )
            raise

    def _update_batch_with_vendor_id(self, batch_id: str, vendor_batch_id: str) -> None:
        """
        PHASE 3: Update batch with vendor_batch_id AFTER Bland AI response

        Following DTC pattern - updates batch_status from 'Pending' to 'Submitted'

        Args:
            batch_id: UUID of our batch record (from Phase 1)
            vendor_batch_id: Batch ID returned by Bland AI
        """
        logger.info(
            f"🔄 [BATCH-ORCHESTRATOR] Phase 3: Updating batch {batch_id} with vendor ID: {vendor_batch_id}"
        )

        query = """
            UPDATE engage360.outreach_batches
            SET vendor_batch_id = %s,
                batch_status = 'Submitted',
                updated_ts = SYSDATETIMEOFFSET()
            WHERE batch_id = %s
        """

        params = (vendor_batch_id, batch_id)

        try:
            self.db_service.execute_query(query, params, fetch_results=False)
            logger.info("✅ [BATCH-ORCHESTRATOR] Phase 3: Batch updated successfully")
        except Exception as e:
            logger.error(f"🚨 [BATCH-ORCHESTRATOR] Phase 3 FAILED: Error updating batch: {str(e)}")
            raise

    def _mark_batch_failed(self, batch_id: str, error_message: str) -> None:
        """
        Mark batch as Failed in database when Bland AI submission fails

        Args:
            batch_id: UUID of our batch record
            error_message: Error message to store
        """
        logger.warning(f"⚠️ [BATCH-ORCHESTRATOR] Marking batch {batch_id} as Failed")

        query = """
            UPDATE engage360.outreach_batches
            SET batch_status = 'Failed',
                status_reason = %s,
                updated_ts = SYSDATETIMEOFFSET()
            WHERE batch_id = %s
        """

        params = (error_message[:500], batch_id)  # Limit error message length

        try:
            self.db_service.execute_query(query, params, fetch_results=False)
            logger.info("✅ [BATCH-ORCHESTRATOR] Batch marked as Failed")
        except Exception as e:
            logger.error(f"🚨 [BATCH-ORCHESTRATOR] Error marking batch as Failed: {str(e)}")
            # Don't raise - this is cleanup code

    def _get_target_phone(self, member: EligibleMember, contact_pref: str) -> str:
        """
        Enhanced contact preference logic supporting member_preference with E.164 validation.

        All phone numbers (primary_phone and device_phone_number) are validated
        and standardized to E.164 format before returning.

        Returns:
            Validated E.164 phone number or None if invalid/unavailable
        """
        logger.debug(f"📞 [BATCH-ORCHESTRATOR] Determining phone for member {member.member_id}")
        logger.debug(f"📞 [BATCH-ORCHESTRATOR] Campaign contact_pref: {contact_pref}")
        logger.debug(f"📞 [BATCH-ORCHESTRATOR] Member channel: {member.channel}")
        logger.debug(f"📞 [BATCH-ORCHESTRATOR] Device callable: {member.is_device_callable}")

        # Handle auto -> member_preference conversion
        if contact_pref == "auto":
            contact_pref = "member_preference"
            logger.debug("📞 [BATCH-ORCHESTRATOR] Converted 'auto' to 'member_preference'")

        if contact_pref == "phone":
            if member.primary_phone:
                validated_phone = standardize_phone(member.primary_phone)
                if validated_phone:
                    logger.debug(
                        f"📞 [BATCH-ORCHESTRATOR] Using validated primary phone: {validated_phone}"
                    )
                    return validated_phone
                else:
                    logger.warning(
                        f"⚠️ [BATCH-ORCHESTRATOR] Invalid primary phone format for member {member.member_id}: {member.primary_phone}"
                    )
                    return None
            return None

        elif contact_pref == "device":
            # Use device only if callable
            if member.device_phone_number and member.is_device_callable:
                validated_phone = standardize_phone(member.device_phone_number)
                if validated_phone:
                    logger.debug(
                        f"📞 [BATCH-ORCHESTRATOR] Using validated device number: {validated_phone}"
                    )
                    return validated_phone
                else:
                    logger.warning(
                        f"⚠️ [BATCH-ORCHESTRATOR] Invalid device phone format for member {member.member_id}: {member.device_phone_number}"
                    )
                    return None
            else:
                logger.debug("📞 [BATCH-ORCHESTRATOR] Device not callable or missing number")
                return None

        elif contact_pref == "member_preference":
            # Use member's existing Channel field
            if member.channel == "phone" and member.primary_phone:
                validated_phone = standardize_phone(member.primary_phone)
                if validated_phone:
                    logger.debug(
                        f"📞 [BATCH-ORCHESTRATOR] Member prefers phone, using validated: {validated_phone}"
                    )
                    return validated_phone
                else:
                    logger.warning(
                        f"⚠️ [BATCH-ORCHESTRATOR] Invalid primary phone format for member {member.member_id}: {member.primary_phone}"
                    )

            elif (
                member.channel == "device"
                and member.device_phone_number
                and member.is_device_callable
            ):
                validated_phone = standardize_phone(member.device_phone_number)
                if validated_phone:
                    logger.debug(
                        f"📞 [BATCH-ORCHESTRATOR] Member prefers device, using validated: {validated_phone}"
                    )
                    return validated_phone
                else:
                    logger.warning(
                        f"⚠️ [BATCH-ORCHESTRATOR] Invalid device phone format for member {member.member_id}: {member.device_phone_number}"
                    )

            # No fallback - return None with clear warning
            logger.warning(
                f"⚠️ [BATCH-ORCHESTRATOR] Member {member.member_id} INELIGIBLE: "
                f"Enrollment channel='{member.channel}' but channel unavailable. "
                f"primary_phone={bool(member.primary_phone)}, "
                f"device_phone={bool(member.device_phone_number)}, "
                f"device_callable={bool(member.is_device_callable)}. "
                f"No fallback - respecting enrollment preference."
            )
            return None

        logger.warning(
            f"⚠️ [BATCH-ORCHESTRATOR] No valid phone found for member: {member.member_id}"
        )
        return None
