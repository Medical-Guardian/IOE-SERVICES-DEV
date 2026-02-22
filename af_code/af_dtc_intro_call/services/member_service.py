import logging
from typing import List, Dict, Tuple
from datetime import datetime
import pytz

# Corrected absolute import paths
from .database_service import DatabaseService
from ..utils.time_window_helper import TimeWindowHelper
from ..utils.config import ELIGIBLE_MEMBERS_QUERY_INTRO, ELIGIBLE_MEMBERS_QUERY_WELLNESS

logger = logging.getLogger(__name__)


class MemberQualificationService:
    """Service to qualify members using DTC logic"""

    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service
        logger.info("👥 [MemberQualificationService] Initializing member qualification service")

    def get_qualified_members(self, campaign_id: str) -> List[Dict]:
        """Get qualified members for campaign using DTC logic"""
        WELLNESS_CAMPAIGN_ID = "E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B"
        is_wellness_campaign = campaign_id.upper() == WELLNESS_CAMPAIGN_ID.upper()

        logger.info(
            f"🔍 [MemberQualificationService] Starting member qualification for campaign: {campaign_id}"
        )

        # Choose the correct query based on campaign type
        if is_wellness_campaign:
            logger.info("🩺 [MemberQualificationService-DEBUG] WELLNESS CAMPAIGN detected")
            logger.info(
                "🩺 [MemberQualificationService-DEBUG] About to execute ELIGIBLE_MEMBERS_QUERY_WELLNESS"
            )
            query_to_use = ELIGIBLE_MEMBERS_QUERY_WELLNESS
        else:
            logger.info("📞 [MemberQualificationService-DEBUG] INTRO CAMPAIGN detected")
            logger.info(
                "📞 [MemberQualificationService-DEBUG] About to execute ELIGIBLE_MEMBERS_QUERY_INTRO"
            )
            query_to_use = ELIGIBLE_MEMBERS_QUERY_INTRO

        try:
            potential_members = self.db_service.execute_query(query_to_use, (campaign_id,))

            if is_wellness_campaign:
                logger.info(
                    f"🩺 [MemberQualificationService-DEBUG] Database query returned {len(potential_members) if potential_members else 0} potential members"
                )
                if potential_members:
                    for i, member in enumerate(potential_members):
                        logger.info(
                            f"🩺 [MemberQualificationService-DEBUG] Potential member {i+1}:"
                        )
                        logger.info(
                            f"🩺 [MemberQualificationService-DEBUG]   - member_id: {member.get('member_id')}"
                        )
                        logger.info(
                            f"🩺 [MemberQualificationService-DEBUG]   - campaign_id: {member.get('campaign_id')}"
                        )
                        logger.info(
                            f"🩺 [MemberQualificationService-DEBUG]   - campaign_name: {member.get('campaign_name')}"
                        )
                        logger.info(
                            f"🩺 [MemberQualificationService-DEBUG]   - call_days_of_week: {member.get('call_days_of_week')}"
                        )
                        logger.info(
                            f"🩺 [MemberQualificationService-DEBUG]   - preferred_window: {member.get('preferred_window')}"
                        )
                        logger.info(
                            f"🩺 [MemberQualificationService-DEBUG]   - timezone: {member.get('timezone')}"
                        )
                        logger.info(
                            f"🩺 [MemberQualificationService-DEBUG]   - todays_failed_attempts: {member.get('todays_failed_attempts')}"
                        )

            if not potential_members:
                logger.warning("⚠️ [MemberQualificationService] No potential members found")

                if is_wellness_campaign:
                    logger.warning(
                        "🩺 [MemberQualificationService-DEBUG] WELLNESS CAMPAIGN - No potential members from database!"
                    )
                    logger.warning(
                        "🩺 [MemberQualificationService-DEBUG] This means the SQL query returned empty results"
                    )
                    logger.warning("🩺 [MemberQualificationService-DEBUG] Possible reasons:")
                    logger.warning(
                        f"🩺 [MemberQualificationService-DEBUG] 1. No members enrolled in wellness campaign ({campaign_id})"
                    )
                    logger.warning(
                        "🩺 [MemberQualificationService-DEBUG] 2. No members with current_status = 'ENROLLED' in wellness campaign"
                    )
                    logger.warning(
                        "🩺 [MemberQualificationService-DEBUG] 3. Campaign status is not 'Active'"
                    )
                    logger.warning(
                        "🩺 [MemberQualificationService-DEBUG] 4. Members have attempts today and are excluded by NOT EXISTS clause"
                    )

                return []

            logger.info(
                f"📈 [MemberQualificationService] Found {len(potential_members)} potential members"
            )
            qualified_members = self._filter_eligible_members(potential_members, datetime.utcnow())
            logger.info(
                f"✅ [MemberQualificationService] Qualified {len(qualified_members)} members"
            )
            return qualified_members

        except Exception as e:
            logger.error(
                f"💥 [MemberQualificationService] Error getting qualified members: {str(e)}"
            )
            raise

    def _filter_eligible_members(
        self, potential_members: List[Dict], current_utc: datetime
    ) -> List[Dict]:
        """Filter members based on timezone and time window eligibility"""
        WELLNESS_CAMPAIGN_ID = "E5ABE3F0-A4D8-4AB3-81CD-96DD6394833B"

        logger.info(
            f"🔍 [MemberQualificationService] Filtering {len(potential_members)} potential members"
        )

        # Check if this is wellness campaign
        is_wellness_campaign = False
        if potential_members:
            first_member_campaign = potential_members[0].get("campaign_id", "")
            # Convert UUID to string if needed
            first_member_campaign_str = str(first_member_campaign) if first_member_campaign else ""
            is_wellness_campaign = first_member_campaign_str.upper() == WELLNESS_CAMPAIGN_ID.upper()

        if is_wellness_campaign:
            logger.info(
                "🩺 [MemberQualificationService-DEBUG] Filtering members for WELLNESS campaign"
            )
            logger.info(f"🩺 [MemberQualificationService-DEBUG] Current UTC time: {current_utc}")

        eligible_members = []

        for i, member in enumerate(potential_members):
            if is_wellness_campaign:
                logger.info(
                    f"🩺 [MemberQualificationService-DEBUG] === Processing member {i+1}/{len(potential_members)} ==="
                )
                logger.info(
                    f"🩺 [MemberQualificationService-DEBUG] Member ID: {member['member_id']}"
                )

            is_eligible, reason = self._is_member_eligible_now(member, current_utc)

            if is_eligible:
                eligible_members.append(member)
                logger.info(
                    f"✅ [MemberQualificationService] Member {member['member_id']} is eligible: {reason}"
                )
                if is_wellness_campaign:
                    logger.info(
                        "🩺 [MemberQualificationService-DEBUG] ✅ WELLNESS member QUALIFIED!"
                    )
            else:
                logger.info(
                    f"❌ [MemberQualificationService] Member {member['member_id']} is not eligible: {reason}"
                )
                if is_wellness_campaign:
                    logger.warning(
                        f"🩺 [MemberQualificationService-DEBUG] ❌ WELLNESS member NOT qualified: {reason}"
                    )

        if is_wellness_campaign:
            logger.info("🩺 [MemberQualificationService-DEBUG] === WELLNESS FILTERING COMPLETE ===")
            logger.info(
                f"🩺 [MemberQualificationService-DEBUG] Total potential members: {len(potential_members)}"
            )
            logger.info(
                f"🩺 [MemberQualificationService-DEBUG] Qualified members: {len(eligible_members)}"
            )

        return eligible_members

    def _is_member_eligible_now(self, member_data: Dict, current_utc: datetime) -> Tuple[bool, str]:
        """Check if a member is eligible for a call right now"""
        member_id = member_data.get("member_id")
        logger.debug(
            f"🔍 [MemberQualificationService] Checking eligibility for member: {member_id}"
        )

        try:
            # Check timezone
            iana_timezone = member_data.get("timezone")
            if not iana_timezone:
                return False, "No timezone specified"

            try:
                member_tz = pytz.timezone(iana_timezone)
                member_local_time = current_utc.replace(tzinfo=pytz.UTC).astimezone(member_tz)
            except Exception as tz_error:
                return False, f"Invalid timezone: {iana_timezone} - {str(tz_error)}"

            # Check call days
            call_days_of_week = member_data.get("call_days_of_week", "")
            current_day_name = member_local_time.strftime("%A")
            if current_day_name not in call_days_of_week:
                return (
                    False,
                    f"Today ({current_day_name}) not in call_days_of_week ({call_days_of_week})",
                )

            # Check failed attempts
            # failed_attempts = member_data.get('todays_failed_attempts', 0)
            # if failed_attempts > 5:
            #     return False, f"Too many failed attempts today ({failed_attempts} > 5)"
            # Commented out: No longer checking failed attempts limit - now checking for ANY attempt in SQL query

            # Check time window
            preferred_window = member_data.get("preferred_window")
            start_time, end_time = TimeWindowHelper.get_time_window_bounds(preferred_window)
            if not start_time or not end_time:
                return (
                    False,
                    f"No valid preferred window specified ({preferred_window})",
                )

            current_time = member_local_time.time()
            if not (start_time <= current_time <= end_time):
                return (
                    False,
                    f"Current time ({current_time.strftime('%H:%M:%S')}) outside window ({start_time.strftime('%H:%M:%S')}-{end_time.strftime('%H:%M:%S')})",
                )

            return (
                True,
                f"Eligible - Day: {current_day_name}, Time: {current_time.strftime('%H:%M:%S')} in window {start_time.strftime('%H:%M:%S')}-{end_time.strftime('%H:%M:%S')}",
            )

        except Exception as e:
            return False, f"Error checking eligibility: {str(e)}"
