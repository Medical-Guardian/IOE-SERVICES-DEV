import logging
from typing import List, Dict, Tuple
from datetime import datetime
import pytz

# Corrected absolute import paths
from .database_service import DatabaseService
from ..utils.time_window_helper import TimeWindowHelper
from ..utils.config import ELIGIBLE_MEMBERS_QUERY

logger = logging.getLogger(__name__)

class MemberQualificationService:
    """Service to qualify members using DTC logic"""
    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        logger.info("👥 [MemberQualificationService] Initializing member qualification service")

    def get_qualified_members(self, campaign_id: str) -> List[Dict]:
        """Get qualified members for campaign using DTC logic"""
        logger.info(f"🔍 [MemberQualificationService] Starting member qualification for campaign: {campaign_id}")
        try:
            potential_members = self.db_service.execute_query(ELIGIBLE_MEMBERS_QUERY, (campaign_id,))
            if not potential_members:
                logger.warning("⚠️ [MemberQualificationService] No potential members found")
                return []

            logger.info(f"📈 [MemberQualificationService] Found {len(potential_members)} potential members")
            qualified_members = self._filter_eligible_members(potential_members, datetime.utcnow())
            logger.info(f"✅ [MemberQualificationService] Qualified {len(qualified_members)} members")
            return qualified_members

        except Exception as e:
            logger.error(f"💥 [MemberQualificationService] Error getting qualified members: {str(e)}")
            raise

    def _filter_eligible_members(self, potential_members: List[Dict], current_utc: datetime) -> List[Dict]:
        """Filter members based on timezone and time window eligibility"""
        logger.info(f"🔍 [MemberQualificationService] Filtering {len(potential_members)} potential members")
        eligible_members = []

        for member in potential_members:
            is_eligible, reason = self._is_member_eligible_now(member, current_utc)
            if is_eligible:
                eligible_members.append(member)
                logger.info(f"✅ [MemberQualificationService] Member {member['member_id']} is eligible: {reason}")
            else:
                logger.info(f"❌ [MemberQualificationService] Member {member['member_id']} is not eligible: {reason}")

        return eligible_members

    def _is_member_eligible_now(self, member_data: Dict, current_utc: datetime) -> Tuple[bool, str]:
        """Check if a member is eligible for a call right now"""
        member_id = member_data.get('member_id')
        logger.debug(f"🔍 [MemberQualificationService] Checking eligibility for member: {member_id}")

        try:
            # Check timezone
            iana_timezone = member_data.get('timezone')
            if not iana_timezone:
                return False, "No timezone specified"

            try:
                member_tz = pytz.timezone(iana_timezone)
                member_local_time = current_utc.replace(tzinfo=pytz.UTC).astimezone(member_tz)
            except Exception as tz_error:
                return False, f"Invalid timezone: {iana_timezone} - {str(tz_error)}"

            # Check call days
            call_days_of_week = member_data.get('call_days_of_week', '')
            current_day_name = member_local_time.strftime('%A')
            if current_day_name not in call_days_of_week:
                return False, f"Today ({current_day_name}) not in call_days_of_week ({call_days_of_week})"

            # Check failed attempts
            failed_attempts = member_data.get('todays_failed_attempts', 0)
            if failed_attempts > 3:
                return False, f"Too many failed attempts today ({failed_attempts} > 3)"

            # Check time window
            preferred_window = member_data.get('preferred_window')
            start_time, end_time = TimeWindowHelper.get_time_window_bounds(preferred_window)
            if not start_time or not end_time:
                return False, f"No valid preferred window specified ({preferred_window})"

            current_time = member_local_time.time()
            if not (start_time <= current_time <= end_time):
                return False, f"Current time ({current_time.strftime('%H:%M:%S')}) outside window ({start_time.strftime('%H:%M:%S')}-{end_time.strftime('%H:%M:%S')})"

            return True, f"Eligible - Day: {current_day_name}, Time: {current_time.strftime('%H:%M:%S')} in window {start_time.strftime('%H:%M:%S')}-{end_time.strftime('%H:%M:%S')}, Failed attempts: {failed_attempts}"

        except Exception as e:
            return False, f"Error checking eligibility: {str(e)}"