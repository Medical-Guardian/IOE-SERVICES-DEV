"""
Device Activation Eligibility Service
BusinessCaseID: BC-TBD (Device Activation System)
Created: 2025-12-07

This service determines which members are eligible for Device Activation calls based on:
1. Campaign enrollment status
2. Call sequence timing (Call 1-4+)
3. Business hours validation (dual-timezone)
4. Callback queue exclusion
5. 90-day campaign limit

Call Sequence Logic:
- Call 1: activation_start_date (delivery_date + 2 business days)
- Call 2: Call 1 + 2 business days (if no success)
- Call 3: Call 2 + 2 business days (if no success)
- Call 4: Call 3 + 5 business days (if no success)
- Call 5+: Weekly (7 calendar days) until 90-day limit
"""

import logging
from typing import List, Dict
from datetime import datetime
import pytz

from af_code.bland_ai_webhook.services.database_service import DatabaseService
from af_code.shared.business_hours_utils import can_make_call

logger = logging.getLogger(__name__)


class EligibilityService:
    """Service to determine member eligibility for Device Activation calls"""

    # SQL query to find eligible members
    ELIGIBLE_MEMBERS_QUERY = """
    SELECT
        e.enrollment_id,
        e.member_id,
        e.campaign_id,
        m.first_name,
        m.last_name,
        m.primary_phone,
        m.email,
        m.timezone,
        m.language_pref,
        -- Address and demographics (added 2025-12-19 for Bland AI request_data/metadata)
        m.address_street,
        m.address_city,
        m.address_state,
        m.address_zip,
        m.dob,
        m.member_brand,
        md.device_id,
        md.device_udi,
        md.device_name,
        md.brand AS device_brand,
        md.device_phone_number,
        md.is_device_callable,
        md.delivery_date,
        md.fall_detection_status,
        md.battery_status,
        e.activation_start_date,
        e.campaign_end_date,
        e.customer_type,
        c.campaign_name,
        c.operating_tz,
        c.operating_start_time,
        c.operating_end_time,
        c.timezone_flag,

        -- Calculate which call attempt this is
        ISNULL((
            SELECT COUNT(*)
            FROM engage360.outreach_attempts oa
            WHERE oa.enrollment_id = e.enrollment_id
        ), 0) + 1 AS call_attempt_number,

        -- Get last attempt date
        (
            SELECT MAX(oa.call_start_ts)
            FROM engage360.outreach_attempts oa
            WHERE oa.enrollment_id = e.enrollment_id
        ) AS last_attempt_date,

        -- Get last disposition
        (
            SELECT TOP 1 oa.disposition
            FROM engage360.outreach_attempts oa
            WHERE oa.enrollment_id = e.enrollment_id
            ORDER BY oa.call_start_ts DESC
        ) AS last_disposition

    FROM engage360.member_campaign_enrollments_enhanced e
    JOIN engage360.members m ON e.member_id = m.member_id
    JOIN engage360.member_devices md ON m.member_id = md.member_id
    JOIN engage360.campaigns_enhanced c ON e.campaign_id = c.campaign_id

    WHERE
        -- Campaign criteria (support both Device Activation and Operations campaigns)
        (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
        AND c.status = 'Active'

        -- Enrollment status
        AND e.current_status = 'ENROLLED'
        AND e.device_activated = 0  -- Device not yet activated

        -- Time criteria
        AND SYSDATETIMEOFFSET() >= e.activation_start_date  -- Past Day 2
        AND SYSDATETIMEOFFSET() <= e.campaign_end_date      -- Within 90-day window

        -- Not in callback queue (priority to callbacks)
        AND NOT EXISTS (
            SELECT 1 FROM engage360.outreach_callback_queue cq
            WHERE cq.enrollment_id = e.enrollment_id
            AND cq.status = 'PENDING'
        )

        -- Call frequency logic
        AND (
            -- No previous attempts (Call 1)
            NOT EXISTS (
                SELECT 1 FROM engage360.outreach_attempts oa
                WHERE oa.enrollment_id = e.enrollment_id
            )
            OR
            -- Call 2-3: 2 business days since last attempt
            (
                (SELECT COUNT(*) FROM engage360.outreach_attempts oa WHERE oa.enrollment_id = e.enrollment_id) BETWEEN 1 AND 2
                AND DATEDIFF(day, (SELECT MAX(call_start_ts) FROM engage360.outreach_attempts oa WHERE oa.enrollment_id = e.enrollment_id), SYSDATETIMEOFFSET()) >= 2
            )
            OR
            -- Call 4: 5 business days since Call 3
            (
                (SELECT COUNT(*) FROM engage360.outreach_attempts oa WHERE oa.enrollment_id = e.enrollment_id) = 3
                AND DATEDIFF(day, (SELECT MAX(call_start_ts) FROM engage360.outreach_attempts oa WHERE oa.enrollment_id = e.enrollment_id), SYSDATETIMEOFFSET()) >= 5
            )
            OR
            -- Call 5+: 7 calendar days since last attempt
            (
                (SELECT COUNT(*) FROM engage360.outreach_attempts oa WHERE oa.enrollment_id = e.enrollment_id) >= 4
                AND DATEDIFF(day, (SELECT MAX(call_start_ts) FROM engage360.outreach_attempts oa WHERE oa.enrollment_id = e.enrollment_id), SYSDATETIMEOFFSET()) >= 7
            )
        )

    ORDER BY e.activation_start_date, call_attempt_number
    """

    def __init__(self, db_service: DatabaseService):
        """
        Initialize EligibilityService

        Args:
            db_service: DatabaseService instance for database queries
        """
        self.db_service = db_service
        logger.info("🔍 [ELIGIBILITY-SERVICE] Initializing Device Activation eligibility service")

    def get_eligible_members(self) -> List[Dict]:
        """
        Get members eligible for Device Activation calls

        This method:
        1. Queries database for potentially eligible members
        2. Validates business hours for each member (dual-timezone)
        3. Returns list of eligible members ready for batch creation

        Returns:
            List of dictionaries containing member and campaign details

        BusinessCaseID: BC-TBD (Device Activation System)
        """
        logger.info("🔍 [ELIGIBILITY-SERVICE] ============================================")
        logger.info("🔍 [ELIGIBILITY-SERVICE] MEMBER QUALIFICATION - DATABASE QUERY")
        logger.info("🔍 [ELIGIBILITY-SERVICE] ============================================")
        logger.info("🔍 [ELIGIBILITY-SERVICE] Executing SQL eligibility query...")
        logger.info("🔍 [ELIGIBILITY-SERVICE] Query joins:")
        logger.info("   ✓ member_campaign_enrollments_enhanced (active enrollments)")
        logger.info("   ✓ members (member demographics, member_brand)")
        logger.info("   ✓ member_devices (device info, device brand)")
        logger.info("   ✓ campaigns_enhanced (campaign configuration)")

        try:
            # Execute eligibility query
            potential_members = self.db_service.execute_query(
                self.ELIGIBLE_MEMBERS_QUERY, fetch_results=True
            )

            if not potential_members:
                logger.info("")
                logger.info("⚠️ [ELIGIBILITY-SERVICE] ============================================")
                logger.info("⚠️ [ELIGIBILITY-SERVICE] NO POTENTIAL MEMBERS FOUND IN DATABASE")
                logger.info("⚠️ [ELIGIBILITY-SERVICE] ============================================")
                logger.info("⚠️ [ELIGIBILITY-SERVICE] Diagnostic checklist:")
                logger.info("   □ No members enrolled in Device Activation campaign")
                logger.info("   □ All members have recent attempts within frequency window")
                logger.info("   □ All members are in callback queue (higher priority)")
                logger.info("   □ All members outside 90-day campaign window (activation_start_date to campaign_end_date)")
                logger.info("   □ Campaign status is not 'Active'")
                logger.info("   □ No member_devices records linked to enrolled members")
                return []

            logger.info("")
            logger.info(f"✅ [ELIGIBILITY-SERVICE] Found {len(potential_members)} potential members from database")
            logger.info("")

            # Log detailed statistics for potential members
            call_attempt_summary = {}
            timezone_summary = {}
            customer_type_summary = {}
            last_disposition_summary = {}

            for member in potential_members:
                # Call attempt distribution
                attempt_num = member.get("call_attempt_number", 1)
                call_attempt_summary[attempt_num] = call_attempt_summary.get(attempt_num, 0) + 1

                # Timezone distribution
                tz = member.get("timezone", "Unknown")
                timezone_summary[tz] = timezone_summary.get(tz, 0) + 1

                # Customer type distribution
                cust_type = member.get("customer_type", "Unknown")
                customer_type_summary[cust_type] = customer_type_summary.get(cust_type, 0) + 1

                # Last disposition distribution
                last_disp = member.get("last_disposition", "No previous attempts")
                if last_disp:
                    last_disposition_summary[last_disp] = last_disposition_summary.get(last_disp, 0) + 1

            logger.info("📊 [ELIGIBILITY-SERVICE] POTENTIAL MEMBER STATISTICS (Before Business Hours Filter)")
            logger.info("📊 [ELIGIBILITY-SERVICE] ============================================")

            logger.info("📊 [ELIGIBILITY-SERVICE] Call Attempt Distribution:")
            for attempt_num in sorted(call_attempt_summary.keys()):
                logger.info(f"   📞 Call #{attempt_num}: {call_attempt_summary[attempt_num]} members")

            logger.info("")
            logger.info("📊 [ELIGIBILITY-SERVICE] Timezone Distribution:")
            for tz in sorted(timezone_summary.keys()):
                logger.info(f"   🕒 {tz}: {timezone_summary[tz]} members")

            logger.info("")
            logger.info("📊 [ELIGIBILITY-SERVICE] Customer Type Distribution:")
            for cust_type in sorted(customer_type_summary.keys()):
                logger.info(f"   👥 {cust_type}: {customer_type_summary[cust_type]} members")

            logger.info("")
            logger.info("📊 [ELIGIBILITY-SERVICE] Last Disposition Distribution:")
            for disp in sorted(last_disposition_summary.keys()):
                count = last_disposition_summary[disp]
                logger.info(f"   📋 {disp}: {count} members")

            logger.info("📊 [ELIGIBILITY-SERVICE] ============================================")

            # Filter by business hours
            logger.info("")
            logger.info("🕐 [ELIGIBILITY-SERVICE] ============================================")
            logger.info("🕐 [ELIGIBILITY-SERVICE] BUSINESS HOURS VALIDATION")
            logger.info("🕐 [ELIGIBILITY-SERVICE] ============================================")
            logger.info("🕐 [ELIGIBILITY-SERVICE] Filtering members by business hours...")
            logger.info("🕐 [ELIGIBILITY-SERVICE] Campaign operating hours: Check campaign.operating_start_time to campaign.operating_end_time")
            logger.info("🕐 [ELIGIBILITY-SERVICE] Member timezone: Using member.timezone for time calculations")

            eligible_members = self._filter_by_business_hours(potential_members)

            filtered_out_count = len(potential_members) - len(eligible_members)
            logger.info("")
            logger.info(f"✅ [ELIGIBILITY-SERVICE] Business hours validation complete")
            logger.info(f"   ✓ Eligible members: {len(eligible_members)}")
            logger.info(f"   ✗ Filtered out (outside business hours): {filtered_out_count}")

            # Final summary
            if len(eligible_members) > 0:
                logger.info("")
                logger.info("📊 [ELIGIBILITY-SERVICE] ============================================")
                logger.info("📊 [ELIGIBILITY-SERVICE] FINAL ELIGIBILITY SUMMARY")
                logger.info("📊 [ELIGIBILITY-SERVICE] ============================================")
                logger.info(f"📊 [ELIGIBILITY-SERVICE] ✅ Total Eligible Members: {len(eligible_members)}")
                logger.info(f"📊 [ELIGIBILITY-SERVICE] 📋 Total Potential Members: {len(potential_members)}")
                logger.info(f"📊 [ELIGIBILITY-SERVICE] 🕐 Filtered by Business Hours: {filtered_out_count}")
                logger.info(f"📊 [ELIGIBILITY-SERVICE] 📈 Qualification Rate: {(len(eligible_members)/len(potential_members)*100):.1f}%")
                logger.info("")
                logger.info("📊 [ELIGIBILITY-SERVICE] Qualification Funnel:")
                logger.info(f"   1. Database Query → {len(potential_members)} potential members")
                logger.info(f"   2. Business Hours Filter → {len(eligible_members)} eligible members")
                logger.info(f"   3. Ready for Bland AI Submission → {len(eligible_members)} calls")
                logger.info("📊 [ELIGIBILITY-SERVICE] ============================================")
            else:
                logger.info("")
                logger.info("⚠️ [ELIGIBILITY-SERVICE] ============================================")
                logger.info("⚠️ [ELIGIBILITY-SERVICE] NO ELIGIBLE MEMBERS AFTER FILTERING")
                logger.info("⚠️ [ELIGIBILITY-SERVICE] ============================================")
                logger.info("⚠️ [ELIGIBILITY-SERVICE] All potential members were outside business hours")
                logger.info(f"⚠️ [ELIGIBILITY-SERVICE] Potential members found: {len(potential_members)}")
                logger.info(f"⚠️ [ELIGIBILITY-SERVICE] Filtered out: {filtered_out_count}")
                logger.info("⚠️ [ELIGIBILITY-SERVICE] Next scheduler run may find eligible members during operating hours")
                logger.info("⚠️ [ELIGIBILITY-SERVICE] ============================================")

            return eligible_members

        except Exception as e:
            logger.error(
                f"💥 [ELIGIBILITY-SERVICE] Error getting eligible members: {str(e)}", exc_info=True
            )
            raise

    def _filter_by_business_hours(self, potential_members: List[Dict]) -> List[Dict]:
        """
        Filter members by business hours validation (dual-timezone)

        Validates BOTH:
        1. Medical Guardian operating hours (operating_tz = America/New_York, 9 AM - 5 PM)
        2. Member's local timezone (member.timezone, 9 AM - 5 PM)

        Args:
            potential_members: List of members from database query

        Returns:
            List of members eligible for calling based on business hours

        BusinessCaseID: BC-TBD (Device Activation System)
        """
        logger.info(
            f"⏰ [ELIGIBILITY-SERVICE] Validating business hours for {len(potential_members)} members..."
        )

        eligible_members = []
        now_utc = datetime.now(pytz.UTC)

        for member in potential_members:
            member_id = member.get("member_id")
            member_timezone = member.get("timezone")
            operating_tz = member.get("operating_tz", "America/New_York")
            timezone_flag = member.get("timezone_flag", "member_tz")

            logger.debug(
                f"⏰ [ELIGIBILITY-SERVICE] Checking member {member_id} "
                f"(timezone: {member_timezone}, mode: {timezone_flag})"
            )

            try:
                # Validate member timezone
                member_tz = pytz.timezone(member_timezone)

                # Use dual-timezone validation from business_hours_utils
                can_call, reason = can_make_call(now_utc, member_tz)

                if can_call:
                    eligible_members.append(member)
                    logger.info(f"✅ [ELIGIBILITY-SERVICE] Member {member_id} eligible: {reason}")
                else:
                    logger.info(
                        f"⏰ [ELIGIBILITY-SERVICE] Member {member_id} not eligible: {reason}"
                    )

            except Exception as e:
                logger.warning(
                    f"⚠️ [ELIGIBILITY-SERVICE] Error validating business hours for member {member_id}: {str(e)}"
                )
                # Skip this member if timezone validation fails
                continue

        logger.info(
            f"✅ [ELIGIBILITY-SERVICE] {len(eligible_members)}/{len(potential_members)} members passed business hours validation"
        )

        return eligible_members
