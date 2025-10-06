import logging
import json
from typing import List
from ..models.qualified_campaign import QualifiedCampaign
from ..models.eligible_member import EligibleMember
from ..models.batch_request import BatchRequest, BatchResult
from ...shared.bland_ai_client import BlandAIClient
from ...shared.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class BatchOrchestrator:
    """
    Service to orchestrate batch call submissions to Bland AI
    """
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.bland_client = BlandAIClient(config_manager)
        logger.info("🔧 [BATCH-ORCHESTRATOR] Service initialized")
    
    async def submit_batch(self, campaign: QualifiedCampaign, members: List[EligibleMember]) -> BatchResult:
        """
        Submit a batch of members to Bland AI for calling
        
        Args:
            campaign: The campaign configuration
            members: List of eligible members to call
            
        Returns:
            BatchResult with success status and details
        """
        logger.info(f"🚀 [BATCH-ORCHESTRATOR] Submitting batch of {len(members)} members for campaign: {campaign.name}")
        
        try:
            # Build Bland AI batch request
            batch_request = self._build_batch_request(campaign, members)
            
            logger.info(f"📞 [BATCH-ORCHESTRATOR] Built batch request with {len(batch_request.calls)} calls")
            logger.info(f"🎭 [BATCH-ORCHESTRATOR] Using pathway: {batch_request.pathway_id}")
            logger.info(f"🎤 [BATCH-ORCHESTRATOR] Using voice: {batch_request.voice_id}")
            
            # Submit to Bland AI
            response = await self.bland_client.submit_batch_calls(batch_request)
            
            if response.get('success'):
                batch_id = response.get('batch_id')
                calls_submitted = response.get('calls_submitted', len(members))
                
                logger.info(f"✅ [BATCH-ORCHESTRATOR] Batch submitted successfully")
                logger.info(f"📦 [BATCH-ORCHESTRATOR] Bland Batch ID: {batch_id}")
                logger.info(f"📊 [BATCH-ORCHESTRATOR] Calls submitted: {calls_submitted}")
                
                return BatchResult(
                    success=True,
                    batch_id=batch_id,
                    members_count=len(members),
                    campaign_id=campaign.campaign_id,
                    submitted_members=[m.member_id for m in members]
                )
            else:
                error_msg = response.get('error', 'Unknown error')
                status_code = response.get('status_code', 'Unknown')
                
                logger.error(f"❌ [BATCH-ORCHESTRATOR] Batch submission failed")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] Error: {error_msg}")
                logger.error(f"❌ [BATCH-ORCHESTRATOR] Status code: {status_code}")
                
                return BatchResult(
                    success=False,
                    error=f"Status {status_code}: {error_msg}",
                    members_count=len(members),
                    campaign_id=campaign.campaign_id
                )
                
        except Exception as e:
            logger.error(f"🚨 [BATCH-ORCHESTRATOR] Exception during batch submission: {str(e)}")
            return BatchResult(
                success=False,
                error=f"Exception: {str(e)}",
                members_count=len(members),
                campaign_id=campaign.campaign_id
            )
    
    def _build_batch_request(self, campaign: QualifiedCampaign, members: List[EligibleMember]) -> BatchRequest:
        """
        Build the Bland AI batch request payload
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
            
            call_data = {
                "to": phone_number,
                "metadata": {
                    "member_id": member.member_id,
                    "campaign_id": campaign.campaign_id,
                    "enrollment_id": member.enrollment_id,  # For outreach_attempts FK
                    "first_name": member.first_name,
                    "last_name": member.last_name,
                    "campaign_type": "Partner",
                    "org_id": campaign.org_id,
                    "call_type_id": campaign.call_type_id,
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
        
        logger.info(f"📞 [BATCH-ORCHESTRATOR] Successfully built {len(calls)} calls")
        
        return BatchRequest(
            campaign_id=campaign.campaign_id,
            calls=calls,
            pathway_id=self._get_pathway_id(campaign),
            voice_id=self._get_voice_id(campaign)
        )
    
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
        """Get the appropriate pathway ID for the campaign"""
        # Check if campaign has specific pathway configuration
        if campaign.config_id:
            # Could fetch pathway from campaign_call_configs_enhanced table
            # For now, use a default Partner campaign pathway
            pathway_id = self.config_manager.get_config("PARTNER_CAMPAIGN_PATHWAY_ID", "default-partner-pathway")
        else:
            # Fallback to default pathway
            pathway_id = self.config_manager.get_config("DEFAULT_PARTNER_PATHWAY_ID", "default-partner-pathway")
        
        logger.info(f"🎭 [BATCH-ORCHESTRATOR] Selected pathway ID: {pathway_id}")
        return pathway_id
    
    def _get_voice_id(self, campaign: QualifiedCampaign) -> str:
        """Get the appropriate voice ID for the campaign"""
        # Check campaign configuration for specific voice
        voice_id = self.config_manager.get_config("PARTNER_CAMPAIGN_VOICE_ID", "default-voice")
        
        logger.info(f"🎤 [BATCH-ORCHESTRATOR] Selected voice ID: {voice_id}")
        return voice_id