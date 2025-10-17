import logging
import json
import uuid
from typing import List, Dict, Any
from ..models.qualified_campaign import QualifiedCampaign
from ..models.eligible_member import EligibleMember
from ..models.batch_request import BatchRequest, BatchResult
from ...shared.bland_ai_client import BlandAIClient
from ...bland_ai_webhook.services.config_manager import ConfigManager
from ...bland_ai_webhook.services.database_service import DatabaseService
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
    
    def submit_batch(self, campaign: QualifiedCampaign, members: List[EligibleMember]) -> BatchResult:
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
        logger.info(f"🚀 [BATCH-ORCHESTRATOR] Submitting batch of {len(members)} members for campaign: {campaign.name}")

        if not self.enabled:
            logger.warning("⚠️ [BATCH-ORCHESTRATOR] Batch orchestrator disabled - skipping submission")
            return BatchResult(
                success=False,
                error="Batch orchestrator disabled (Bland AI API key not configured)",
                members_count=len(members),
                campaign_id=str(campaign.campaign_id)  # Convert UUID to string
            )

        try:
            # ============================================================
            # PHASE 1: Create batch record BEFORE Bland AI call
            # ============================================================
            batch_id = self._create_outreach_batch(campaign.campaign_id, len(members))
            logger.info(f"✅ [BATCH-ORCHESTRATOR] Phase 1 Complete: Batch record created with ID: {batch_id}")

            # ============================================================
            # PHASE 2: Create attempt records BEFORE Bland AI call
            # ============================================================
            self._create_outreach_attempts(members, batch_id)
            logger.info(f"✅ [BATCH-ORCHESTRATOR] Phase 2 Complete: {len(members)} attempt records created")

            # Build Bland AI batch request
            batch_request = self._build_batch_request(campaign, members, batch_id)

            logger.info(f"📞 [BATCH-ORCHESTRATOR] Built batch request with {len(batch_request.calls)} calls")
            logger.info(f"🎭 [BATCH-ORCHESTRATOR] Using pathway: {batch_request.pathway_id}")
            logger.info(f"🎤 [BATCH-ORCHESTRATOR] Using voice: {batch_request.voice_id}")

            # Submit to Bland AI (SYNCHRONOUS - waits for response)
            response = self.bland_client.submit_batch_calls(batch_request)

            if response.get('success'):
                vendor_batch_id = response.get('batch_id')
                calls_submitted = response.get('calls_submitted', len(members))

                logger.info(f"✅ [BATCH-ORCHESTRATOR] Bland AI accepted batch")
                logger.info(f"📦 [BATCH-ORCHESTRATOR] Vendor Batch ID: {vendor_batch_id}")
                logger.info(f"📊 [BATCH-ORCHESTRATOR] Calls submitted: {calls_submitted}")

                # ============================================================
                # PHASE 3: Update batch with vendor_batch_id AFTER Bland AI response
                # ============================================================
                self._update_batch_with_vendor_id(batch_id, vendor_batch_id)
                logger.info(f"✅ [BATCH-ORCHESTRATOR] Phase 3 Complete: Batch updated with vendor ID")

                return BatchResult(
                    success=True,
                    batch_id=vendor_batch_id,  # Return Bland AI batch ID
                    members_count=len(members),
                    campaign_id=str(campaign.campaign_id),  # Convert UUID to string
                    submitted_members=[str(m.member_id) for m in members]  # Convert UUIDs to strings
                )
            else:
                error_msg = response.get('error', 'Unknown error')
                status_code = response.get('status_code', 'Unknown')

                logger.error(f"❌ [BATCH-ORCHESTRATOR] Batch submission failed")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] Error: {error_msg}")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] Status code: {status_code}")

                # Mark batch as Failed in database
                self._mark_batch_failed(batch_id, error_msg)

                return BatchResult(
                    success=False,
                    error=f"Status {status_code}: {error_msg}",
                    members_count=len(members),
                    campaign_id=str(campaign.campaign_id)  # Convert UUID to string
                )

        except Exception as e:
            logger.error(f"🚨 [BATCH-ORCHESTRATOR] Exception during batch submission: {str(e)}")

            # Mark batch as Failed if it was created
            if 'batch_id' in locals():
                self._mark_batch_failed(batch_id, str(e))

            return BatchResult(
                success=False,
                error=f"Exception: {str(e)}",
                members_count=len(members),
                campaign_id=str(campaign.campaign_id)  # Convert UUID to string
            )
    
    def _build_batch_request(self, campaign: QualifiedCampaign, members: List[EligibleMember], batch_id: str) -> BatchRequest:
        """
        Build the Bland AI batch request payload with DTC-style request_data
        """
        logger.info(f"🔨 [BATCH-ORCHESTRATOR] Building batch request for {len(members)} members")

        calls = []
        skipped_members = 0

        for member in members:
            # Determine phone number based on contact preference
            phone_number = self._get_target_phone(member, campaign.contact_pref)

            if not phone_number:
                logger.warning(f"⚠️ [BATCH-ORCHESTRATOR] No valid phone for member: {member.member_id}")
                skipped_members += 1
                continue

            # Build DTC-style request_data with care gaps and demographics
            logger.info(f"📋 [BATCH-ORCHESTRATOR] Building request_data for member: {member.member_id}")
            request_data = self._build_request_data(member, campaign)

            # Log complete request_data for traceability
            logger.info(f"📦 [BATCH-ORCHESTRATOR] Member {member.member_id} request_data:")
            logger.info(f"   👤 Demographics: name={request_data.get('first_name')} {request_data.get('last_name')}, "
                       f"language={request_data.get('language_pref')}, dob={request_data.get('dob')}")
            logger.info(f"   📍 Address: {request_data.get('service_address')}, "
                       f"{request_data.get('city')}, {request_data.get('state')} {request_data.get('zip_code')}")
            logger.info(f"   📞 Phone: {request_data.get('primary_phone')}")
            logger.info(f"   🏥 Partner: {request_data.get('partner_contact_name')} - {request_data.get('org_name')}")

            # Log care gap flags
            care_gap_flags = {k: v for k, v in request_data.items()
                            if k.endswith('_import_flag') or k.endswith('_completion_flag')}
            if care_gap_flags:
                logger.info(f"   🩺 Care gaps ({len(care_gap_flags)//2} active): {json.dumps(care_gap_flags, indent=2)}")
            else:
                logger.info(f"   🩺 Care gaps: None")

            call_data = {
                "to": phone_number,
                "request_data": request_data,  # DTC-style request_data
                "metadata": {
                    "member_id": str(member.member_id),  # Convert UUID to string
                    "campaign_id": str(campaign.campaign_id),  # Convert UUID to string
                    "enrollment_id": str(member.enrollment_id),  # Convert UUID to string
                    "first_name": member.first_name,
                    "last_name": member.last_name,
                    "campaign_type": "Partner",
                    "org_id": str(campaign.org_id),  # Convert UUID to string
                    "call_type_id": str(campaign.call_type_id) if campaign.call_type_id else None,  # Convert UUID to string
                    "preferred_window": member.preferred_window,
                    "member_timezone": member.timezone,
                    "audience_file_batch": campaign.audience_file_batch,  # From campaign
                    "contact_preference": campaign.contact_pref,
                    "member_contact_pref": member.contact_pref,  # Member's preference
                    "is_device_callable": member.is_device_callable,
                    "total_previous_attempts": member.total_attempts,
                    "last_attempt_ts": str(member.last_attempt_ts) if member.last_attempt_ts else None
                }
            }
            calls.append(call_data)

        if skipped_members > 0:
            logger.warning(f"⚠️ [BATCH-ORCHESTRATOR] Skipped {skipped_members} members due to missing phone numbers")

        logger.info(f"📞 [BATCH-ORCHESTRATOR] Successfully built {len(calls)} calls with complete request_data")

        # Get Bland AI parameters (campaign-specific or fallback to environment)
        pathway_id = self._get_pathway_id(campaign)
        voice_id = self._get_voice_id(campaign)

        # Pass the complete bland_parameters_global JSON (like DTC implementation)
        # This includes all 18+ parameters: pathway_version, wait_for_greeting, record, etc.
        bland_params = campaign.bland_parameters_global if campaign.bland_parameters_global else {}

        logger.info(f"📋 [BATCH-ORCHESTRATOR] Passing {len(bland_params)} Bland AI parameters from campaign configuration")
        if bland_params:
            logger.info(f"🔧 [BATCH-ORCHESTRATOR] Available parameters: {list(bland_params.keys())}")

        return BatchRequest(
            campaign_id=str(campaign.campaign_id),  # Convert UUID to string for JSON serialization
            calls=calls,
            pathway_id=pathway_id,
            voice_id=voice_id,
            bland_parameters_global=bland_params  # Pass complete JSON
        )

    def _build_request_data(self, member: EligibleMember, campaign: QualifiedCampaign) -> Dict[str, Any]:
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
            **care_gaps_data
        }

        logger.debug(f"✅ [BATCH-ORCHESTRATOR] Built request_data with {len(care_gaps_data)//2} care gaps")
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
            logger.debug(f"🩺 [BATCH-ORCHESTRATOR] No care gap parameters for member")
            return care_gaps_data

        try:
            # Parse JSON string
            care_gap_flags = json.loads(member_care_gap_parameters)
            logger.debug(f"🩺 [BATCH-ORCHESTRATOR] Parsed {len(care_gap_flags)} care gap flags from JSON")

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
                        logger.debug(f"   📋 [BATCH-ORCHESTRATOR] Added completion flag: {completion_flag_name} = \"\"")
                    else:
                        logger.warning(f"   ⚠️ [BATCH-ORCHESTRATOR] No completion flag mapping found for: {flag_name}")

            logger.info(f"🩺 [BATCH-ORCHESTRATOR] Extracted {len(care_gaps_data)//2} active care gaps")

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
            logger.info(f"✅ [BATCH-ORCHESTRATOR] Phase 1: Batch record created successfully")
            return batch_id
        except Exception as e:
            logger.error(f"🚨 [BATCH-ORCHESTRATOR] Phase 1 FAILED: Error creating batch record: {str(e)}")
            raise

    def _create_outreach_attempts(self, members: List[EligibleMember], batch_id: str) -> None:
        """
        PHASE 2: Create outreach attempt records in database BEFORE Bland AI call

        Following DTC pattern - creates N attempt records with disposition='Pending'

        Args:
            members: List of eligible members
            batch_id: UUID of the batch (from Phase 1)
        """
        logger.info(f"📝 [BATCH-ORCHESTRATOR] Phase 2: Creating {len(members)} attempt records")

        # Build bulk insert for better performance
        values_list = []
        params = []

        for member in members:
            attempt_id = str(uuid.uuid4())
            values_list.append("(%s, %s, 'Voice', SYSDATETIMEOFFSET(), 'Pending', 0, %s)")
            params.extend([
                attempt_id,
                member.enrollment_id,  # FK to member_campaign_enrollments_enhanced
                batch_id               # FK to outreach_batches
            ])

        query = f"""
            INSERT INTO engage360.outreach_attempts
            (attempt_id, enrollment_id, channel, attempt_ts, disposition, retry_seq, batch_id)
            VALUES {', '.join(values_list)}
        """

        try:
            self.db_service.execute_query(query, params, fetch_results=False)
            logger.info(f"✅ [BATCH-ORCHESTRATOR] Phase 2: {len(members)} attempt records created successfully")
        except Exception as e:
            logger.error(f"🚨 [BATCH-ORCHESTRATOR] Phase 2 FAILED: Error creating attempt records: {str(e)}")
            raise

    def _update_batch_with_vendor_id(self, batch_id: str, vendor_batch_id: str) -> None:
        """
        PHASE 3: Update batch with vendor_batch_id AFTER Bland AI response

        Following DTC pattern - updates batch_status from 'Pending' to 'Submitted'

        Args:
            batch_id: UUID of our batch record (from Phase 1)
            vendor_batch_id: Batch ID returned by Bland AI
        """
        logger.info(f"🔄 [BATCH-ORCHESTRATOR] Phase 3: Updating batch {batch_id} with vendor ID: {vendor_batch_id}")

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
            logger.info(f"✅ [BATCH-ORCHESTRATOR] Phase 3: Batch updated successfully")
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
            logger.info(f"✅ [BATCH-ORCHESTRATOR] Batch marked as Failed")
        except Exception as e:
            logger.error(f"🚨 [BATCH-ORCHESTRATOR] Error marking batch as Failed: {str(e)}")
            # Don't raise - this is cleanup code

    def _get_target_phone(self, member: EligibleMember, contact_pref: str) -> str:
        """
        Enhanced contact preference logic supporting member_preference
        """
        logger.debug(f"📞 [BATCH-ORCHESTRATOR] Determining phone for member {member.member_id}")
        logger.debug(f"📞 [BATCH-ORCHESTRATOR] Campaign contact_pref: {contact_pref}")
        logger.debug(f"📞 [BATCH-ORCHESTRATOR] Member contact_pref: {member.contact_pref}")
        logger.debug(f"📞 [BATCH-ORCHESTRATOR] Device callable: {member.is_device_callable}")
        
        # Handle auto -> member_preference conversion
        if contact_pref == 'auto':
            contact_pref = 'member_preference'
            logger.debug(f"📞 [BATCH-ORCHESTRATOR] Converted 'auto' to 'member_preference'")
        
        if contact_pref == 'phone':
            target_phone = member.primary_phone
            if target_phone:
                logger.debug(f"📞 [BATCH-ORCHESTRATOR] Using primary phone: {target_phone}")
            return target_phone
            
        elif contact_pref == 'device':
            # Use device only if callable
            if member.device_phone_number and member.is_device_callable:
                target_phone = member.device_phone_number
                logger.debug(f"📞 [BATCH-ORCHESTRATOR] Using device number: {target_phone}")
                return target_phone
            else:
                logger.debug(f"📞 [BATCH-ORCHESTRATOR] Device not callable or missing number")
                return None
            
        elif contact_pref == 'member_preference':
            # Use member's existing contact_pref field
            if member.contact_pref == 'phone' and member.primary_phone:
                target_phone = member.primary_phone
                logger.debug(f"📞 [BATCH-ORCHESTRATOR] Member prefers phone, using: {target_phone}")
                return target_phone
                
            elif member.contact_pref == 'device' and member.device_phone_number and member.is_device_callable:
                target_phone = member.device_phone_number  
                logger.debug(f"📞 [BATCH-ORCHESTRATOR] Member prefers device, using: {target_phone}")
                return target_phone
                
            else:
                # Fallback to available number (phone first, then device if callable)
                if member.primary_phone:
                    target_phone = member.primary_phone
                    logger.debug(f"📞 [BATCH-ORCHESTRATOR] Fallback to primary phone: {target_phone}")
                    return target_phone
                elif member.device_phone_number and member.is_device_callable:
                    target_phone = member.device_phone_number
                    logger.debug(f"📞 [BATCH-ORCHESTRATOR] Fallback to device: {target_phone}")
                    return target_phone
                else:
                    logger.debug(f"📞 [BATCH-ORCHESTRATOR] No fallback options available")
                    return None
        
        logger.warning(f"⚠️ [BATCH-ORCHESTRATOR] No valid phone found for member: {member.member_id}")
        return None
    
    def _get_pathway_id(self, campaign: QualifiedCampaign) -> str:
        """
        Get pathway ID from campaign bland_parameters_global or fallback to environment

        Priority:
        1. campaign.pathway_id (from bland_parameters_global)
        2. Environment variable PARTNER_CAMPAIGN_PATHWAY_ID
        3. Default: "default-partner-pathway"
        """
        if campaign.pathway_id:
            logger.info(f"🎭 [BATCH-ORCHESTRATOR] Using campaign-specific pathway ID: {campaign.pathway_id}")
            return campaign.pathway_id

        # Fallback to environment variable
        pathway_id = self.config_manager.get_config("PARTNER_CAMPAIGN_PATHWAY_ID", "default-partner-pathway")
        logger.info(f"🎭 [BATCH-ORCHESTRATOR] Using fallback pathway ID from environment: {pathway_id}")
        return pathway_id

    def _get_voice_id(self, campaign: QualifiedCampaign) -> str:
        """
        Get voice ID from campaign bland_parameters_global or fallback to environment

        Priority:
        1. campaign.voice_id (from bland_parameters_global)
        2. Environment variable PARTNER_CAMPAIGN_VOICE_ID
        3. Default: "default-voice"
        """
        if campaign.voice_id:
            logger.info(f"🎤 [BATCH-ORCHESTRATOR] Using campaign-specific voice ID: {campaign.voice_id}")
            return campaign.voice_id

        # Fallback to environment variable
        voice_id = self.config_manager.get_config("PARTNER_CAMPAIGN_VOICE_ID", "default-voice")
        logger.info(f"🎤 [BATCH-ORCHESTRATOR] Using fallback voice ID from environment: {voice_id}")
        return voice_id

    def _get_webhook_url(self, campaign: QualifiedCampaign) -> str:
        """
        Get webhook URL from campaign bland_parameters_global or fallback to environment

        Priority:
        1. campaign.webhook_url (from bland_parameters_global)
        2. Environment variable BLAND_WEBHOOK_URL
        3. No default - will raise error if not found

        This is the key improvement: webhook URL now comes from database configuration
        """
        if campaign.webhook_url:
            logger.info(f"🔗 [BATCH-ORCHESTRATOR] Using campaign-specific webhook URL: {campaign.webhook_url}")
            return campaign.webhook_url

        # Fallback to environment variable
        webhook_url = self.config_manager.get_config("BLAND_WEBHOOK_URL")
        if webhook_url:
            logger.warning(f"⚠️ [BATCH-ORCHESTRATOR] Using fallback webhook URL from environment: {webhook_url}")
            logger.warning(f"⚠️ [BATCH-ORCHESTRATOR] Consider configuring webhook_url in bland_parameters_global for campaign: {campaign.name}")
            return webhook_url

        # No webhook URL configured
        logger.error(f"🚨 [BATCH-ORCHESTRATOR] No webhook URL configured for campaign: {campaign.name}")
        logger.error(f"🚨 [BATCH-ORCHESTRATOR] Please configure webhook_url in bland_parameters_global or BLAND_WEBHOOK_URL environment variable")
        raise ValueError(f"No webhook URL configured for campaign: {campaign.name}")

    def _get_max_duration(self, campaign: QualifiedCampaign) -> str:
        """
        Get max duration from campaign bland_parameters_global or fallback to environment

        Priority:
        1. campaign.max_duration (from bland_parameters_global)
        2. Environment variable BLAND_MAX_DURATION
        3. Default: "300" (5 minutes)
        """
        if campaign.max_duration:
            logger.info(f"⏱️ [BATCH-ORCHESTRATOR] Using campaign-specific max duration: {campaign.max_duration}s")
            return campaign.max_duration

        # Fallback to environment variable
        max_duration = self.config_manager.get_config("BLAND_MAX_DURATION", "300")
        logger.info(f"⏱️ [BATCH-ORCHESTRATOR] Using fallback max duration from environment: {max_duration}s")
        return max_duration