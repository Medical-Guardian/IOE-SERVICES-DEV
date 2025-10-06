import logging
from typing import List, Optional
from datetime import datetime, time
from ..models.qualified_campaign import QualifiedCampaign
from ...shared.database_service import DatabaseService

logger = logging.getLogger(__name__)

class CampaignQualifier:
    """
    Service to identify Partner campaigns that are currently qualified to run
    Following existing IOE logging and error handling patterns
    """
    
    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        logger.info("🔧 [CAMPAIGN-QUALIFIER] Service initialized")
    
    async def get_qualified_campaigns(self) -> List[QualifiedCampaign]:
        """
        Find all Partner campaigns that are qualified to run right now
        """
        logger.info("🔍 [CAMPAIGN-QUALIFIER] Starting campaign qualification check...")
        
        try:
            # Get current time info for qualification logic
            current_time = datetime.now().time()
            current_day = datetime.now().strftime('%A')  # Monday, Tuesday, etc.
            
            logger.info(f"⏰ [CAMPAIGN-QUALIFIER] Current time: {current_time}, Day: {current_day}")
            
            # Query for active Partner campaigns with enhanced fields
            query = """
                SELECT 
                    c.campaign_id,
                    c.org_id,
                    c.name,
                    c.campaign_description,
                    c.contact_pref,
                    c.call_days_of_week,
                    c.operating_start_time,
                    c.operating_end_time,
                    c.operating_tz,
                    c.scheduling_mode,
                    c.frequency_value,
                    c.frequency_unit,
                    c.timezone_flag,
                    c.max_care_gaps_per_member,
                    c.audience_file_batch,
                    cc.config_id,
                    cc.call_type_id,
                    o.org_type
                FROM engage360.campaigns_enhanced c
                LEFT JOIN engage360.campaign_call_configs_enhanced cc 
                    ON c.campaign_id = cc.campaign_id 
                    AND cc.config_status = 'active'
                LEFT JOIN engage360.orgs o ON c.org_id = o.org_id
                WHERE c.campaign_type = 'Partner'
                  AND c.status = 'Active'
                  AND c.primary_channel = 'voice'
                  AND (c.start_ts IS NULL OR c.start_ts <= SYSDATETIMEOFFSET())
                  AND (c.end_ts IS NULL OR c.end_ts >= SYSDATETIMEOFFSET())
                  AND c.audience_file_batch IS NOT NULL
            """
            
            logger.info("📊 [CAMPAIGN-QUALIFIER] Executing campaign query...")
            campaigns_data = self.db_service.execute_query(query, fetch_results=True)
            logger.info(f"📊 [CAMPAIGN-QUALIFIER] Found {len(campaigns_data)} total Partner campaigns in database")
            
            qualified_campaigns = []
            
            for campaign_data in campaigns_data:
                campaign_name = campaign_data.get('name', 'Unknown')
                logger.info(f"🔍 [CAMPAIGN-QUALIFIER] Evaluating campaign: {campaign_name}")
                
                # Check if campaign is qualified for current time and has valid configuration
                if (self._is_campaign_qualified_now(campaign_data, current_time, current_day) and 
                    self._validate_flexible_scheduling(campaign_data)):
                    # Handle auto contact preference conversion
                    contact_pref = campaign_data['contact_pref']
                    if contact_pref == 'auto':
                        logger.info(f"🔄 [CAMPAIGN-QUALIFIER] Converting contact_pref 'auto' to 'member_preference' for campaign: {campaign_name}")
                        contact_pref = 'member_preference'
                    
                    qualified_campaign = QualifiedCampaign(
                        campaign_id=campaign_data['campaign_id'],
                        org_id=campaign_data['org_id'],
                        name=campaign_data['name'],
                        description=campaign_data['campaign_description'],
                        contact_pref=contact_pref,  # Use converted value
                        call_days_of_week=campaign_data['call_days_of_week'],
                        operating_start_time=campaign_data['operating_start_time'],
                        operating_end_time=campaign_data['operating_end_time'],
                        operating_tz=campaign_data['operating_tz'],
                        scheduling_mode=campaign_data['scheduling_mode'],
                        frequency_value=campaign_data['frequency_value'],
                        frequency_unit=campaign_data['frequency_unit'],
                        timezone_flag=campaign_data['timezone_flag'],
                        max_care_gaps=campaign_data['max_care_gaps_per_member'],
                        config_id=campaign_data['config_id'],
                        call_type_id=campaign_data['call_type_id'],
                        org_type=campaign_data['org_type'],
                        audience_file_batch=campaign_data['audience_file_batch']
                    )
                    qualified_campaigns.append(qualified_campaign)
                    
                    logger.info(f"✅ [CAMPAIGN-QUALIFIER] Campaign QUALIFIED: {campaign_name}")
                    logger.info(f"   📋 Operating hours: {campaign_data['operating_start_time']} - {campaign_data['operating_end_time']}")
                    logger.info(f"   📅 Days: {campaign_data['call_days_of_week']}")
                    logger.info(f"   🔄 Schedule: {campaign_data['scheduling_mode']}")
                    logger.info(f"   🌍 Timezone mode: {campaign_data['timezone_flag']}")
                    logger.info(f"   📦 Audience batch: {campaign_data['audience_file_batch']}")
                else:
                    logger.info(f"❌ [CAMPAIGN-QUALIFIER] Campaign NOT qualified: {campaign_name}")
                    logger.info(f"   ⏰ Operating hours: {campaign_data['operating_start_time']} - {campaign_data['operating_end_time']}")
                    logger.info(f"   📅 Allowed days: {campaign_data['call_days_of_week']}")
            
            logger.info(f"📊 [CAMPAIGN-QUALIFIER] QUALIFICATION COMPLETE: {len(qualified_campaigns)} campaigns qualified out of {len(campaigns_data)} total")
            return qualified_campaigns
            
        except Exception as e:
            logger.error(f"🚨 [CAMPAIGN-QUALIFIER] Error during qualification: {str(e)}")
            raise
    
    def _is_campaign_qualified_now(self, campaign_data: dict, current_time: time, current_day: str) -> bool:
        """
        Check if a campaign is qualified to run at the current time
        Enhanced logging for debugging
        """
        campaign_name = campaign_data.get('name', 'Unknown')
        
        try:
            # Check day of week
            call_days_str = campaign_data.get('call_days_of_week', '')
            if not call_days_str:
                logger.warning(f"⚠️ [CAMPAIGN-QUALIFIER] No call days defined for campaign: {campaign_name}")
                return False
                
            call_days = [day.strip() for day in call_days_str.split(',')]
            if current_day not in call_days:
                logger.info(f"📅 [CAMPAIGN-QUALIFIER] Day check FAILED: {campaign_name} (current: {current_day}, allowed: {call_days})")
                return False
            
            logger.info(f"📅 [CAMPAIGN-QUALIFIER] Day check PASSED: {campaign_name}")
            
            # Check operating hours - Note: This is a basic check, timezone-aware filtering happens in member eligibility
            start_time = campaign_data.get('operating_start_time')
            end_time = campaign_data.get('operating_end_time')
            
            if not start_time or not end_time:
                logger.warning(f"⚠️ [CAMPAIGN-QUALIFIER] Missing operating hours for campaign: {campaign_name}")
                return False
            
            # Convert string times to time objects if needed
            if isinstance(start_time, str):
                start_time = datetime.strptime(start_time, '%H:%M:%S').time()
            if isinstance(end_time, str):
                end_time = datetime.strptime(end_time, '%H:%M:%S').time()
            
            # For campaigns with timezone_flag = 'member_tz', we allow qualification 
            # during a wider time window since members could be in different timezones
            timezone_flag = campaign_data.get('timezone_flag', 'operating_tz')
            
            if timezone_flag == 'member_tz':
                # For member timezone mode, qualify during extended hours to account for all US timezones
                # This is a broad qualification - precise timezone filtering happens in member eligibility
                extended_start = datetime.strptime('06:00:00', '%H:%M:%S').time()  # 6 AM
                extended_end = datetime.strptime('20:00:00', '%H:%M:%S').time()    # 8 PM
                
                if not (extended_start <= current_time <= extended_end):
                    logger.info(f"⏰ [CAMPAIGN-QUALIFIER] Extended time check FAILED: {campaign_name} (current: {current_time}, extended window: {extended_start}-{extended_end})")
                    return False
            else:
                # For operating timezone mode, use the campaign's specific hours
                if not (start_time <= current_time <= end_time):
                    logger.info(f"⏰ [CAMPAIGN-QUALIFIER] Time check FAILED: {campaign_name} (current: {current_time}, window: {start_time}-{end_time})")
                    return False
            
            logger.info(f"⏰ [CAMPAIGN-QUALIFIER] Time check PASSED: {campaign_name}")
            return True
            
        except Exception as e:
            logger.error(f"🚨 [CAMPAIGN-QUALIFIER] Error checking qualification for {campaign_name}: {str(e)}")
            return False
    
    def _validate_flexible_scheduling(self, campaign_data: dict) -> bool:
        """
        Validate that Flexible scheduling mode has required frequency values
        """
        campaign_name = campaign_data.get('name', 'Unknown')
        scheduling_mode = campaign_data.get('scheduling_mode')
        
        if scheduling_mode == 'Flexible':
            frequency_value = campaign_data.get('frequency_value')
            frequency_unit = campaign_data.get('frequency_unit')
            
            if not frequency_value or not frequency_unit:
                logger.warning(f"⚠️ [CAMPAIGN-QUALIFIER] Flexible scheduling requires frequency_value and frequency_unit for campaign: {campaign_name}")
                logger.warning(f"   Current values: frequency_value={frequency_value}, frequency_unit={frequency_unit}")
                return False
            
            if frequency_value <= 0:
                logger.warning(f"⚠️ [CAMPAIGN-QUALIFIER] Invalid frequency_value: {frequency_value} for campaign: {campaign_name}")
                return False
            
            if frequency_unit not in ['day', 'week', 'month']:
                logger.warning(f"⚠️ [CAMPAIGN-QUALIFIER] Invalid frequency_unit: {frequency_unit} for campaign: {campaign_name}")
                return False
            
            logger.info(f"✅ [CAMPAIGN-QUALIFIER] Flexible scheduling validation passed: {frequency_value} per {frequency_unit}")
        
        return True