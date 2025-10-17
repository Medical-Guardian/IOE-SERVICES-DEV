import logging
from typing import List, Dict, Any
from ..models.qualified_campaign import QualifiedCampaign
from ..models.eligible_member import EligibleMember
from ...bland_ai_webhook.services.database_service import DatabaseService
from ...shared.timezone_utils import TimezoneConverter

logger = logging.getLogger(__name__)

class MemberEligibilityService:
    """
    Enhanced service with timezone-aware member eligibility and frequency protection
    """
    
    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        logger.info("🔧 [MEMBER-ELIGIBILITY] Service initialized")
    
    def get_eligible_members(self, campaign: QualifiedCampaign) -> List[EligibleMember]:
        """
        Find eligible members with timezone-aware filtering and enhanced frequency protection
        """
        logger.info(f"👥 [MEMBER-ELIGIBILITY] Finding eligible members for campaign: {campaign.name}")
        logger.info(f"🌍 [MEMBER-ELIGIBILITY] Timezone mode: {campaign.timezone_flag}")
        logger.info(f"📋 [MEMBER-ELIGIBILITY] Audience batch: {campaign.audience_file_batch}")
        logger.info(f"📞 [MEMBER-ELIGIBILITY] Contact preference: {campaign.contact_pref}")
        logger.info(f"⏰ [MEMBER-ELIGIBILITY] Frequency: {campaign.frequency_value} per {campaign.frequency_unit}")
        
        # Build timezone-aware member eligibility query with enhanced frequency checks
        query = self._build_enhanced_frequency_query()
        params = self._build_query_parameters(campaign)
        
        logger.info(f"🔍 [MEMBER-ELIGIBILITY] Executing enhanced member eligibility query...")
        members_data = self.db_service.execute_query(query, params, fetch_results=True)
        
        eligible_members = []
        timezone_stats = {}
        contact_method_stats = {}
        
        for member_data in members_data:
            member_timezone = member_data['timezone']
            contact_method = member_data['contact_pref'] or 'unspecified'
            
            # Track statistics
            if member_timezone not in timezone_stats:
                timezone_stats[member_timezone] = 0
            timezone_stats[member_timezone] += 1
            
            if contact_method not in contact_method_stats:
                contact_method_stats[contact_method] = 0
            contact_method_stats[contact_method] += 1
            
            eligible_member = EligibleMember(
                member_id=member_data['member_id'],
                campaign_id=campaign.campaign_id,
                enrollment_id=member_data['enrollment_id'],  # New field
                first_name=member_data['first_name'],
                last_name=member_data['last_name'],
                primary_phone=member_data['primary_phone'],
                device_phone_number=member_data['device_phone_number'],  # From member_devices
                contact_pref=member_data['contact_pref'],  # Use existing field
                is_device_callable=member_data.get('is_device_callable'),
                timezone=member_timezone,
                preferred_window=member_data['preferred_window'],
                enrollment_status=member_data['current_status'],
                last_attempt_ts=member_data.get('last_attempt_ts'),
                total_attempts=member_data.get('total_attempts', 0),
                member_current_time=member_data.get('member_current_time'),
                member_current_day=member_data.get('member_current_day')
            )
            eligible_members.append(eligible_member)
        
        # Log comprehensive statistics
        logger.info(f"📊 [MEMBER-ELIGIBILITY] Found {len(eligible_members)} eligible members")
        logger.info(f"🌍 [MEMBER-ELIGIBILITY] Timezone distribution:")
        for tz, count in timezone_stats.items():
            logger.info(f"   🕒 {tz}: {count} members")
        
        logger.info(f"📞 [MEMBER-ELIGIBILITY] Contact method distribution:")
        for method, count in contact_method_stats.items():
            logger.info(f"   📱 {method}: {count} members")
        
        return eligible_members
    
    def create_batches(self, members: List[EligibleMember], batch_size: int = 1000) -> List[List[EligibleMember]]:
        """
        Split eligible members into batches for Bland AI submission
        """
        batches = []
        for i in range(0, len(members), batch_size):
            batch = members[i:i + batch_size]
            batches.append(batch)
        
        logger.info(f"📦 [MEMBER-ELIGIBILITY] Created {len(batches)} batches from {len(members)} members")
        return batches
    
    def _build_enhanced_frequency_query(self) -> str:
        """
        Enhanced query using existing tables: members, member_devices, outreach_batches, outreach_attempts
        """
        return """
            DECLARE @campaign_id UNIQUEIDENTIFIER = %s;
            DECLARE @frequency_unit VARCHAR(10) = %s;
            DECLARE @frequency_value INT = %s;
            DECLARE @timezone_flag VARCHAR(20) = %s;
            DECLARE @operating_tz VARCHAR(50) = %s;
            DECLARE @contact_pref VARCHAR(50) = %s;
            DECLARE @audience_batch VARCHAR(255) = %s;
            DECLARE @start_time TIME = %s;
            DECLARE @end_time TIME = %s;
            DECLARE @call_days NVARCHAR(255) = %s;
            
            WITH LastAttempts AS (
                SELECT 
                    mce.member_id,
                    MAX(oa.attempt_ts) as last_attempt_ts,
                    COUNT(*) as total_attempts,
                    -- Check if attempted today using existing attempt_ts field
                    MAX(CASE 
                        WHEN CAST(oa.attempt_ts AS DATE) = CAST(SYSDATETIMEOFFSET() AS DATE) 
                        THEN 1 ELSE 0 
                    END) as attempted_today
                FROM engage360.member_campaign_enrollments_enhanced mce
                INNER JOIN engage360.outreach_attempts oa ON mce.enrollment_id = oa.enrollment_id
                INNER JOIN engage360.outreach_batches ob ON oa.batch_id = ob.batch_id
                WHERE ob.campaign_id = @campaign_id
                GROUP BY mce.member_id
            ),
            FrequencyCheck AS (
                SELECT 
                    la.*,
                    CASE 
                        WHEN @frequency_unit = 'day' THEN DATEDIFF(day, la.last_attempt_ts, SYSDATETIMEOFFSET())
                        WHEN @frequency_unit = 'week' THEN DATEDIFF(week, la.last_attempt_ts, SYSDATETIMEOFFSET())
                        WHEN @frequency_unit = 'month' THEN DATEDIFF(month, la.last_attempt_ts, SYSDATETIMEOFFSET())
                    END as time_since_last_attempt
                FROM LastAttempts la
            ),
            TodaySubmissions AS (
                -- Check existing batches submitted today using outreach_batches
                SELECT DISTINCT mce.member_id
                FROM engage360.member_campaign_enrollments_enhanced mce
                INNER JOIN engage360.outreach_attempts oa ON mce.enrollment_id = oa.enrollment_id  
                INNER JOIN engage360.outreach_batches ob ON oa.batch_id = ob.batch_id
                WHERE ob.campaign_id = @campaign_id
                  AND CAST(ob.submitted_ts AS DATE) = CAST(SYSDATETIMEOFFSET() AS DATE)
                  AND ob.batch_status IN ('Submitted', 'Pending')
            ),
            TimezoneEligible AS (
                SELECT 
                    m.member_id,
                    m.timezone,
                    m.first_name,
                    m.last_name,
                    m.primary_phone,
                    m.contact_pref,  -- Use existing contact_pref field
                    md.device_phone_number,  -- From member_devices table
                    md.is_device_callable,
                    -- Calculate member's current time based on timezone_flag
                    CASE 
                        WHEN @timezone_flag = 'member_tz' THEN
                            CAST(SYSDATETIMEOFFSET() AT TIME ZONE m.timezone AS TIME)
                        ELSE
                            CAST(SYSDATETIMEOFFSET() AT TIME ZONE @operating_tz AS TIME)
                    END as member_current_time,
                    -- Calculate member's current day based on timezone_flag
                    CASE 
                        WHEN @timezone_flag = 'member_tz' THEN
                            DATENAME(WEEKDAY, SYSDATETIMEOFFSET() AT TIME ZONE m.timezone)
                        ELSE
                            DATENAME(WEEKDAY, SYSDATETIMEOFFSET() AT TIME ZONE @operating_tz)
                    END as member_current_day
                FROM engage360.members m
                LEFT JOIN engage360.member_devices md ON m.member_id = md.member_id 
                    AND md.is_device_callable = 1
                WHERE m.timezone IS NOT NULL
            )
            SELECT TOP 1000
                mce.member_id,
                mce.campaign_id,
                mce.enrollment_id,  -- Need this for outreach_attempts FK
                mce.current_status,
                mce.preferred_window,
                te.first_name,
                te.last_name,
                te.primary_phone,
                te.contact_pref,  -- Use existing field
                te.device_phone_number,  -- From member_devices
                te.is_device_callable,
                te.timezone,
                te.member_current_time,
                te.member_current_day,
                fc.last_attempt_ts,
                fc.total_attempts
            FROM engage360.member_campaign_enrollments_enhanced mce
            INNER JOIN TimezoneEligible te ON mce.member_id = te.member_id
            LEFT JOIN FrequencyCheck fc ON mce.member_id = fc.member_id
            LEFT JOIN TodaySubmissions ts ON mce.member_id = ts.member_id
            WHERE mce.campaign_id = @campaign_id
              AND mce.current_status = 'ENROLLED'
              AND ts.member_id IS NULL  -- Not submitted today
              AND (
                  fc.member_id IS NULL  -- Never attempted
                  OR (
                      fc.time_since_last_attempt >= @frequency_value  -- Frequency check
                      AND fc.attempted_today = 0  -- Same-day protection
                  )
              )
              AND (
                  -- Enhanced contact preference logic using existing contact_pref
                  (@contact_pref = 'phone' AND te.primary_phone IS NOT NULL)
                  OR (@contact_pref = 'device' AND te.device_phone_number IS NOT NULL AND te.is_device_callable = 1)
                  OR (@contact_pref = 'member_preference' AND (
                      (te.contact_pref = 'phone' AND te.primary_phone IS NOT NULL)
                      OR (te.contact_pref = 'device' AND te.device_phone_number IS NOT NULL AND te.is_device_callable = 1)
                      OR (te.contact_pref IS NULL AND (te.primary_phone IS NOT NULL OR (te.device_phone_number IS NOT NULL AND te.is_device_callable = 1)))
                  ))
              )
              -- Timezone-aware operating hours check
              AND te.member_current_time BETWEEN @start_time AND @end_time
              -- Timezone-aware day of week check
              AND te.member_current_day IN (SELECT value FROM STRING_SPLIT(@call_days, ','))
            ORDER BY 
                CASE WHEN fc.member_id IS NULL THEN 0 ELSE 1 END,  -- Never attempted first
                fc.last_attempt_ts ASC  -- Oldest attempts first
        """
    
    def _build_query_parameters(self, campaign: QualifiedCampaign) -> tuple:
        """Build parameters for the enhanced timezone-aware query"""
        # Handle auto contact preference conversion
        contact_pref = campaign.contact_pref
        if contact_pref == 'auto':
            contact_pref = 'member_preference'

        # Convert operating_tz to Windows timezone name for SQL Server AT TIME ZONE clause
        # This handles: EST → Eastern Standard Time, America/New_York → Eastern Standard Time
        operating_tz = campaign.operating_tz or 'EST'
        operating_tz_windows = TimezoneConverter.to_windows(operating_tz)

        logger.debug(f"🔄 [MEMBER-ELIGIBILITY] Timezone conversion: '{operating_tz}' → '{operating_tz_windows}' (for SQL)")

        return (
            campaign.campaign_id,                    # @campaign_id
            campaign.frequency_unit,                 # @frequency_unit
            campaign.frequency_value,                # @frequency_value
            campaign.timezone_flag or 'operating_tz', # @timezone_flag (default to operating_tz)
            operating_tz_windows,                    # @operating_tz (SQL Server Windows timezone name)
            contact_pref,                            # @contact_pref (with auto conversion)
            campaign.audience_file_batch,            # @audience_batch
            campaign.operating_start_time,           # @start_time
            campaign.operating_end_time,             # @end_time
            campaign.call_days_of_week              # @call_days
        )