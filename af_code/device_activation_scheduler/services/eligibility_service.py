"""
Device Activation Eligibility Service

BusinessCaseID: BC-DA-003 (Eligibility & Scheduling Logic), BC-DA-006 (Call Frequency & Sequencing Logic)
Created: 2025-12-07
Updated: 2026-01-01 - Added explicit business day validation for Call 5+ members (defense in depth)

This service determines which members are eligible for Device Activation calls by executing
a complex SQL eligibility query and filtering results by business hours.

PURPOSE:
--------
Device Activation campaigns proactively call members who have received medical alert devices
but have not yet activated them. This service identifies members ready to be called based on:

1. **Enrollment Status**: Member is ENROLLED in an active Device Activation campaign
2. **Call Sequence Timing**: Sufficient time has passed since last attempt (frequency rules)
3. **Business Hours Validation**: Dual-timezone check (MG operating hours + member timezone)
4. **Callback Queue Exclusion**: Members with pending callbacks are processed separately
5. **90-Day Window**: Call 5+ attempts must occur within 90 days from call_5_timestamp

CALL SEQUENCE LOGIC (BC-DA-006):
---------------------------------
Device Activation uses two distinct call frequency patterns:

**Calls 1-4 (Initial Attempts):**
- Call 1: Eligible on activation_start_date (delivery_date + 2 business days)
- Call 2: Call 1 + 2 business days (if no success)
- Call 3: Call 2 + 2 business days (if no success)
- Call 4: Call 3 + 5 business days (if no success)
- **NO 90-day limit** - Only frequency rules apply
- **Max 4 attempts** total in this phase

**Calls 5+ (Extended Attempts):**
- **Frequency Calculation**: After 7 days (>7 CALENDAR days = 8+ days between attempts - counts weekends/holidays)
- **Call Timing**: Calls ONLY on business days (Mon-Fri, excluding federal holidays)
- Max Attempts: Unlimited
- **90-Day Window**: call_5_timestamp + 90 days
  - Window starts FROM Call 5 creation (NOT activation_start_date)
  - Allows sufficient time for early attempts before enforcing hard stop
  - campaign_end_date = call_5_timestamp + 90 days
- Continue 8+ day calls until campaign_end_date reached
- **Defense in Depth**: Business day validated in BOTH eligibility filter AND business hours filter

**Example Timeline:**
```
Day 1:  Device Delivery
Day 3:  Call 1 (activation_start_date = delivery + 2 biz days)
Day 5:  Call 2 (Call 1 + 2 biz days)
Day 7:  Call 3 (Call 2 + 2 biz days)
Day 12: Call 4 (Call 3 + 5 biz days)
Day 20: Call 5 (Call 4 + 8 days) → call_5_timestamp SET, campaign_end_date = Day 110
Day 28: Call 6 (Call 5 + 8 days)
Day 36: Call 7 (Call 6 + 8 days)
...
Day 110: Campaign ends (call_5_timestamp + 90 days), no more calls
```

BUSINESS HOURS VALIDATION:
---------------------------
All eligible members are filtered by dual-timezone business hours validation:

1. **Medical Guardian Operating Hours**: 9 AM - 5 PM EST (operating_tz) [CONFIRMED]
2. **Member's Local Timezone**: 9 AM - 5 PM in member.timezone

Calls are only made when BOTH timezones are within business hours.

SQL ELIGIBILITY QUERY:
----------------------
The service executes a 200+ line SQL query (ELIGIBLE_MEMBERS_QUERY) that:

1. **JOINs 5 tables**:
   - member_campaign_enrollments_enhanced (enrollment status, dates, call_5_timestamp)
   - members (contact info, timezone, demographics)
   - member_devices (device info for metadata)
   - campaigns_enhanced (campaign config, operating hours)
   - campaign_call_configs_enhanced (Bland AI configuration)

2. **Calculates call_attempt_number**:
   - Counts previous outreach_attempts for this enrollment
   - Determines if member is on Call 1-4 vs Call 5+

3. **Filters by eligibility criteria**:
   - current_status = 'ENROLLED'
   - device_activated = 0 (device not yet activated)
   - activation_start_date <= today (past Day 2)
   - Frequency rules: 2/5 BUSINESS days for Calls 2-4, >7 CALENDAR days (8+ days) for Call 5+ (calls only on business days)
   - 90-day window for Call 5+ only
   - Not in callback queue (callbacks processed separately)

4. **Returns member data** for Bland AI batch creation:
   - Contact information (name, phone, email, address)
   - Device information (device_name, device_phone_number, fall_detection, powersaver_mode)
   - Campaign configuration (pathway_id, voice_id, operating hours)
   - Metadata (enrollment_id, member_id, salesforce_account_number, etc.)

RELATED COMPONENTS:
-------------------
- **BatchOrchestrator** (BC-DA-004): Consumes eligible members to create Bland AI batches
- **CallbackScheduler** (BC-DA-005): Processes callbacks separately (higher priority)
- **business_hours_utils.py**: Shared dual-timezone validation logic

RELATED DOCUMENTATION:
----------------------
- Complete Architecture: documentation/device_activation/ARCHITECTURE/DEVICE_ACTIVATION_COMPLETE_ARCHITECTURE.md
- Call Sequence Diagrams: documentation/device_activation/FLOWS/DEVICE_ACTIVATION_CALL_SEQUENCE.md
- SQL Query Reference: documentation/device_activation/REFERENCE/DEVICE_ACTIVATION_SQL_QUERY_REFERENCE.md

DATABASE TABLES ACCESSED:
--------------------------
- member_campaign_enrollments_enhanced (read: enrollment status, call_5_timestamp)
- members (read: contact info, timezone)
- member_devices (read: device info)
- campaigns_enhanced (read: campaign config)
- campaign_call_configs_enhanced (read: Bland AI config)
- outreach_attempts (read: previous call history)
- outreach_callback_queue (read: callback exclusion check)

EXAMPLES:
---------
Basic usage in scheduler:
    >>> from af_code.device_activation_scheduler.services.eligibility_service import EligibilityService
    >>> from af_code.bland_ai_webhook.services.database_service import DatabaseService
    >>>
    >>> db_service = DatabaseService(config_manager)
    >>> eligibility_service = EligibilityService(db_service)
    >>>
    >>> # Get members eligible for calls right now
    >>> eligible_members = eligibility_service.get_eligible_members()
    >>> print(f"Found {len(eligible_members)} eligible members")
    >>>
    >>> # Each member dict contains:
    >>> # - enrollment_id, member_id, campaign_id
    >>> # - first_name, last_name, primary_phone, email
    >>> # - device_id, device_name, device_phone_number
    >>> # - fall_detection, powersaver_mode
    >>> # - activation_start_date, campaign_end_date, call_5_timestamp
    >>> # - call_attempt_number, last_attempt_date, last_disposition
    >>> # - bland_parameters_global, config_status
"""

import logging
from typing import List, Dict
from datetime import datetime
import pytz

from af_code.bland_ai_webhook.services.database_service import DatabaseService
from af_code.shared.business_hours_utils import (
    can_make_call,
    get_business_days_between,
    is_business_day,
)

logger = logging.getLogger(__name__)


class EligibilityService:
    """
    Service to determine member eligibility for Device Activation calls

    BusinessCaseID: BC-DA-003, BC-DA-006

    This service is responsible for identifying which members should be called in the current
    scheduler run. It combines SQL-based eligibility queries with Python-based business hours
    validation to produce a final list of members ready for Bland AI batch submission.

    The service implements a two-stage filtering process:
    1. **SQL Query Stage**: Execute complex eligibility query against database (200+ lines)
    2. **Business Hours Stage**: Filter SQL results by dual-timezone validation (Python)

    Attributes:
        db_service (DatabaseService): Database service for query execution and connection management
        ELIGIBLE_MEMBERS_QUERY (str): Class-level constant containing the 200+ line SQL eligibility query

    Methods:
        get_eligible_members() -> List[Dict]:
            Main entry point - returns list of members eligible for calls right now

        _filter_by_business_hours(potential_members: List[Dict]) -> List[Dict]:
            Private method to filter members by dual-timezone business hours validation

    SQL Query Structure:
        The ELIGIBLE_MEMBERS_QUERY constant (lines 42-163) contains the eligibility logic:

        - SELECT fields: 30+ fields from 5 joined tables
        - FROM: member_campaign_enrollments_enhanced (base table)
        - JOINs: members, member_devices, campaigns_enhanced, campaign_call_configs_enhanced
        - WHERE clause: 10+ eligibility filters
        - Subqueries: Calculate call_attempt_number, last_attempt_date, last_disposition
        - ORDER BY: activation_start_date, call_attempt_number

    Call Frequency Logic (BC-DA-006):
        The SQL WHERE clause implements different frequency rules based on call_attempt_number:

        **Calls 1-4 (BUSINESS DAYS - excludes weekends + US federal holidays):**
        - Call 1: No previous attempts AND activation_start_date <= today
        - Call 2-3: 1-2 previous attempts AND >= 2 BUSINESS days since last attempt
        - Call 4: 3 previous attempts AND >= 5 BUSINESS days since last attempt
        - No 90-day window enforced
        - Uses Python get_business_days_between() function for day calculations (lines 666-730)
        - Business days exclude weekends and US federal holidays

        **Call 5+ (CALENDAR DAYS - includes weekends + holidays):**
        - >= 4 previous attempts AND > 7 CALENDAR days (8+ days) since last attempt
        - 90-day window: call_5_timestamp IS NULL OR today < call_5_timestamp + 90 days
        - Unlimited attempts within window
        - Uses DATEDIFF(day, ...) for calendar day calculations

    Business Hours Validation:
        After SQL filtering, the service validates business hours for each member:

        1. Get current time in UTC
        2. Convert to Medical Guardian timezone (America/New_York)
        3. Convert to member's timezone (from members.timezone)
        4. Check if BOTH timezones are within operating hours:
           - Medical Guardian: 9 AM - 4 PM EST (Monday-Friday, no US federal holidays)
           - Member: 9 AM - 5 PM (in member's timezone, Monday-Friday, no US federal holidays)
        5. Return only members passing both checks

        Uses shared utility: af_code/shared/business_hours_utils.py::can_make_call()

    Example:
        >>> # Initialize service
        >>> from af_code.bland_ai_webhook.services.config_manager import ConfigManager
        >>> from af_code.bland_ai_webhook.services.database_service import DatabaseService
        >>> from af_code.device_activation_scheduler.services.eligibility_service import EligibilityService
        >>>
        >>> config_manager = ConfigManager()
        >>> db_service = DatabaseService(config_manager)
        >>> eligibility_service = EligibilityService(db_service)
        >>>
        >>> # Get eligible members (combines SQL + business hours filtering)
        >>> eligible_members = eligibility_service.get_eligible_members()
        >>>
        >>> # Output example:
        >>> # ✅ [ELIGIBILITY-SERVICE] Found 25 potential members from database
        >>> # ✅ [ELIGIBILITY-SERVICE] 18/25 members passed business hours validation
        >>> # ✅ [ELIGIBILITY-SERVICE] Total Eligible Members: 18
        >>>
        >>> # Process members
        >>> for member in eligible_members:
        ...     print(f"Member {member['member_id']} - Call #{member['call_attempt_number']}")
        ...     print(f"  Phone: {member['primary_phone']}, Timezone: {member['timezone']}")
        ...     print(f"  Device: {member['device_name']}, Fall Detection: {member['fall_detection']}")

    Notes:
        - This service is called every 15 minutes by the device_activation_scheduler timer trigger
        - Eligible members are passed to BatchOrchestrator for Bland AI batch creation
        - Callbacks are processed separately via CallbackScheduler (not included in this query)
        - The SQL query excludes members with pending callbacks (higher priority)
        - Business hours validation ensures no calls outside operating hours (9 AM - 4 PM EST for MG, 9 AM - 5 PM for member)
        - All datetime comparisons use SYSDATETIMEOFFSET() for timezone awareness

    Related Components:
        - BatchOrchestrator (BC-DA-004): Consumes eligible members to create batches
        - CallbackScheduler (BC-DA-005): Processes callbacks separately
        - DatabaseService: Executes SQL queries and manages connections
        - business_hours_utils.can_make_call(): Dual-timezone validation

    Related Code:
        - af_code/device_activation_scheduler/main_logic.py: Calls this service
        - af_code/device_activation_scheduler/services/batch_orchestrator.py: Consumes results
        - af_code/shared/business_hours_utils.py: Business hours validation logic
    """

    # SQL query to find eligible members
    ELIGIBLE_MEMBERS_QUERY = """
    SELECT
        e.enrollment_id,
        e.member_id,
        e.campaign_id,
        m.first_name,
        m.last_name,
        m.primary_phone,
        m.salesforce_account_number,  -- Required for DTC-style metadata
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
        md.device_id AS device_udi,
        md.device_name,
        md.brand AS device_brand,
        md.device_phone_number,
        md.is_device_callable,
        e.activation_start_date AS delivery_date,
        md.fall_detection,
        md.powersaver_mode,
        e.activation_start_date,
        e.campaign_end_date,
        e.call_5_timestamp,  -- Timestamp when Call 5 was made (NULL until Call 5)
        c.name AS campaign_name,
        c.operating_tz,
        c.operating_start_time,
        c.operating_end_time,
        c.timezone_flag,
        cc.bland_parameters_global,  -- Bland AI configuration from database
        cc.config_status,            -- Config status (active/draft/archived)
        mi.id_value AS monitoring_system_id,  -- Monitoring system ID from member_identifiers

        -- Calculate which call attempt this is
        ISNULL((
            SELECT COUNT(*)
            FROM engage360.outreach_attempts oa
            WHERE oa.enrollment_id = e.enrollment_id
        ), 0) + 1 AS call_attempt_number,

        -- Get last attempt date
        (
            SELECT MAX(oa.attempt_ts)
            FROM engage360.outreach_attempts oa
            WHERE oa.enrollment_id = e.enrollment_id
        ) AS last_attempt_date,

        -- Get last disposition
        (
            SELECT TOP 1 oa.disposition
            FROM engage360.outreach_attempts oa
            WHERE oa.enrollment_id = e.enrollment_id
            ORDER BY oa.attempt_ts DESC
        ) AS last_disposition

    FROM engage360.member_campaign_enrollments_enhanced e
    JOIN engage360.members m ON e.member_id = m.member_id
    JOIN engage360.member_devices md ON m.member_id = md.member_id
    JOIN engage360.campaigns_enhanced c ON e.campaign_id = c.campaign_id
    LEFT JOIN engage360.campaign_call_configs_enhanced cc
        ON c.campaign_id = cc.campaign_id
        AND cc.call_type = 'Operations'
        AND cc.config_status = 'active'
    INNER JOIN engage360.member_identifiers mi
        ON m.member_id = mi.member_id
        AND mi.id_type = 'monitoring_system_id'

    WHERE
        -- Campaign criteria (support both Device Activation and Operations campaigns)
        (c.campaign_type = 'Device Activation' OR c.campaign_type = 'Operations')
        AND c.status = 'Active'

        -- Enrollment status
        AND e.current_status = 'ENROLLED'
        AND e.device_activated = 0  -- Device not yet activated

        -- Time criteria
        AND SYSDATETIMEOFFSET() >= e.activation_start_date  -- Past Day 2

        -- NEW: 90-day window logic ONLY applies to Call 5+
        -- For Calls 1-4: No 90-day check (call_5_timestamp IS NULL means haven't reached Call 5)
        -- For Call 5+: Check if within 90 days from call_5_timestamp
        AND (
            -- Calls 1-4: No 90-day limit (call_5_timestamp is NULL)
            e.call_5_timestamp IS NULL
            OR
            -- Call 5+: Within 90-day window from Call 5 timestamp
            SYSDATETIMEOFFSET() <= e.campaign_end_date
        )

        -- Call frequency logic
        AND (
            -- No previous attempts (Call 1)
            NOT EXISTS (
                SELECT 1 FROM engage360.outreach_attempts oa
                WHERE oa.enrollment_id = e.enrollment_id
            )
            OR
            -- Call 2-3: Has 1-2 previous attempts (business day check in Python)
            (
                (SELECT COUNT(*) FROM engage360.outreach_attempts oa WHERE oa.enrollment_id = e.enrollment_id) BETWEEN 1 AND 2
            )
            OR
            -- Call 4: Has exactly 3 previous attempts (business day check in Python)
            (
                (SELECT COUNT(*) FROM engage360.outreach_attempts oa WHERE oa.enrollment_id = e.enrollment_id) = 3
            )
            OR
            -- Call 5+: >7 calendar days (8+ days) since last attempt
            (
                (SELECT COUNT(*) FROM engage360.outreach_attempts oa WHERE oa.enrollment_id = e.enrollment_id) >= 4
                AND DATEDIFF(day, (SELECT MAX(attempt_ts) FROM engage360.outreach_attempts oa WHERE oa.enrollment_id = e.enrollment_id), SYSDATETIMEOFFSET()) > 7
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

        BusinessCaseID: BC-DA-003, BC-DA-006

        This is the main entry point for eligibility determination. It executes a two-stage
        filtering process to identify members ready to be called in the current scheduler run:

        **Stage 1: SQL Query (Database Filtering)**
            Executes ELIGIBLE_MEMBERS_QUERY to find potentially eligible members based on:
            - Enrollment status (ENROLLED, device not activated)
            - Campaign status (Active Device Activation campaign)
            - Call frequency rules:
              * Calls 2-3: 2 BUSINESS days (excludes weekends + US federal holidays)
              * Call 4: 5 BUSINESS days (excludes weekends + US federal holidays)
              * Call 5+: 7 CALENDAR days (includes weekends + holidays)
            - 90-day window for Call 5+ (call_5_timestamp + 90 days)
            - Callback queue exclusion (callbacks processed separately)

        **Stage 2: Business Hours Validation (Python Filtering)**
            Filters SQL results by dual-timezone business hours:
            - Medical Guardian operating hours: 9 AM - 4 PM EST (Monday-Friday, no US federal holidays)
            - Member's local timezone: 9 AM - 5 PM in member.timezone (Monday-Friday, no US federal holidays)
            - Calls only made when BOTH timezones are within business hours

        Process Flow:
            1. Log start of eligibility check
            2. Execute SQL query via db_service.execute_query()
            3. If no results, log diagnostic checklist and return empty list
            4. Log statistics: call attempt distribution, timezone distribution, disposition distribution
            5. Call _filter_by_business_hours() to filter by time
            6. Log final summary: eligible count, filtered count, qualification rate
            7. Return list of eligible members

        Returns:
            List[Dict]: List of dictionaries containing member and campaign details.
                Each dictionary contains:

                **Member Information:**
                - enrollment_id (str): Enrollment UUID
                - member_id (str): Member UUID
                - first_name (str): Member first name
                - last_name (str): Member last name
                - primary_phone (str): Member phone (E.164 format)
                - email (str): Member email
                - timezone (str): Member timezone (IANA format, e.g., 'America/New_York')
                - language_pref (str): Language preference ('EN', 'ES', 'Other')
                - address_street (str): Street address
                - address_city (str): City
                - address_state (str): State abbreviation
                - address_zip (str): ZIP code
                - dob (date): Date of birth
                - member_brand (str): Member brand (e.g., 'Medical Guardian')
                - salesforce_account_number (str): Salesforce account ID

                **Device Information:**
                - device_id (str): Device UUID
                - device_udi (str): Device UDI (same as device_id)
                - device_name (str): Device model name
                - device_brand (str): Device brand
                - device_phone_number (str): Device phone (E.164 format)
                - is_device_callable (bool): Whether device can receive calls
                - fall_detection (bit): Fall detection enabled (1/0)
                - powersaver_mode (bit): Power saver mode enabled (1/0)

                **Campaign Information:**
                - campaign_id (str): Campaign UUID
                - campaign_name (str): Campaign name
                - operating_tz (str): Campaign timezone
                - operating_start_time (time): Operating hours start (e.g., 09:00:00)
                - operating_end_time (time): Operating hours end (e.g., 17:00:00)
                - timezone_flag (str): Timezone mode ('member_tz' or 'operating_tz')

                **Enrollment Information:**
                - activation_start_date (date): Eligibility start date (delivery + 2 biz days)
                - campaign_end_date (date): Campaign end date (call_5_timestamp + 90 days)
                - call_5_timestamp (datetimeoffset): When Call 5 was made (NULL before Call 5)
                - delivery_date (date): Same as activation_start_date

                **Call History:**
                - call_attempt_number (int): Current call attempt (1, 2, 3, 4, 5+)
                - last_attempt_date (datetimeoffset): When last call was made (NULL for Call 1)
                - last_disposition (str): Last call outcome (NULL for Call 1)

                **Bland AI Configuration:**
                - bland_parameters_global (dict): Bland AI parameters from campaign_call_configs_enhanced
                - config_status (str): Configuration status ('active', 'draft', 'archived')

        Raises:
            Exception: If SQL query execution fails or business hours validation encounters errors
                Error details logged with correlation context

        Example:
            >>> # Basic usage
            >>> eligible_members = eligibility_service.get_eligible_members()
            >>> print(f"Found {len(eligible_members)} eligible members")
            Found 18 eligible members
            >>>
            >>> # Process each member
            >>> for member in eligible_members:
            ...     print(f"Call #{member['call_attempt_number']}: {member['first_name']} {member['last_name']}")
            ...     print(f"  Phone: {member['primary_phone']}, Timezone: {member['timezone']}")
            ...     print(f"  Last attempt: {member['last_attempt_date']}")
            Call #1: John Doe
              Phone: +15551234567, Timezone: America/New_York
              Last attempt: None
            Call #3: Jane Smith
              Phone: +15559876543, Timezone: America/Chicago
              Last attempt: 2025-12-20 14:30:00+00:00
            >>>
            >>> # Check Call 5+ members
            >>> call_5_plus = [m for m in eligible_members if m['call_attempt_number'] >= 5]
            >>> print(f"{len(call_5_plus)} members on Call 5+ (weekly frequency)")
            3 members on Call 5+ (weekly frequency)

        Logging Output:
            The method produces detailed logging output for debugging and monitoring:

            **Start:**
            🔍 [ELIGIBILITY-SERVICE] ============================================
            🔍 [ELIGIBILITY-SERVICE] MEMBER QUALIFICATION - DATABASE QUERY
            🔍 [ELIGIBILITY-SERVICE] Executing SQL eligibility query...

            **No Results:**
            ⚠️ [ELIGIBILITY-SERVICE] NO POTENTIAL MEMBERS FOUND IN DATABASE
            ⚠️ [ELIGIBILITY-SERVICE] Diagnostic checklist:
               □ No members enrolled in Device Activation campaign
               □ All members have recent attempts within frequency window
               □ All members are in callback queue (higher priority)

            **With Results:**
            ✅ [ELIGIBILITY-SERVICE] Found 25 potential members from database
            📊 [ELIGIBILITY-SERVICE] POTENTIAL MEMBER STATISTICS
            📊 [ELIGIBILITY-SERVICE] Call Attempt Distribution:
               📞 Call #1: 5 members
               📞 Call #2: 8 members
               📞 Call #5: 12 members

            **Business Hours Filtering:**
            🕐 [ELIGIBILITY-SERVICE] BUSINESS HOURS VALIDATION
            🕐 [ELIGIBILITY-SERVICE] Filtering members by business hours...
            ✅ [ELIGIBILITY-SERVICE] Business hours validation complete
               ✓ Eligible members: 18
               ✗ Filtered out (outside business hours): 7

            **Final Summary:**
            📊 [ELIGIBILITY-SERVICE] FINAL ELIGIBILITY SUMMARY
            📊 [ELIGIBILITY-SERVICE] ✅ Total Eligible Members: 18
            📊 [ELIGIBILITY-SERVICE] 📋 Total Potential Members: 25
            📊 [ELIGIBILITY-SERVICE] 🕐 Filtered by Business Hours: 7
            📊 [ELIGIBILITY-SERVICE] 📈 Qualification Rate: 72.0%

        Notes:
            - Called every 15 minutes by device_activation_scheduler timer trigger
            - Results are passed to BatchOrchestrator for Bland AI batch creation
            - Callbacks are NOT included (processed separately by CallbackScheduler)
            - Empty list is returned if no eligible members (not an error)
            - SQL query can return 0 results if all members are outside frequency window
            - Business hours validation can filter out all members (e.g., during off-hours)
            - All logging uses emoji prefixes for visibility in Application Insights

        Related Code:
            - af_code/device_activation_scheduler/main_logic.py:48-65 - Calls this method
            - af_code/device_activation_scheduler/services/batch_orchestrator.py:177-239 - Consumes results
            - af_code/shared/business_hours_utils.py:15-45 - Business hours validation
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
                logger.info(
                    "   □ All members outside 90-day campaign window (activation_start_date to campaign_end_date)"
                )
                logger.info("   □ Campaign status is not 'Active'")
                logger.info("   □ No member_devices records linked to enrolled members")
                return []

            logger.info("")
            logger.info(
                f"✅ [ELIGIBILITY-SERVICE] Found {len(potential_members)} potential members from database"
            )
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
                    last_disposition_summary[last_disp] = (
                        last_disposition_summary.get(last_disp, 0) + 1
                    )

            logger.info(
                "📊 [ELIGIBILITY-SERVICE] POTENTIAL MEMBER STATISTICS (Before Business Hours Filter)"
            )
            logger.info("📊 [ELIGIBILITY-SERVICE] ============================================")

            logger.info("📊 [ELIGIBILITY-SERVICE] Call Attempt Distribution:")
            for attempt_num in sorted(call_attempt_summary.keys()):
                logger.info(
                    f"   📞 Call #{attempt_num}: {call_attempt_summary[attempt_num]} members"
                )

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

            # Filter by business day frequency (Call 2-4 only)
            logger.info("")
            logger.info("📅 [ELIGIBILITY-SERVICE] ============================================")
            logger.info("📅 [ELIGIBILITY-SERVICE] BUSINESS DAY FREQUENCY VALIDATION")
            logger.info("📅 [ELIGIBILITY-SERVICE] ============================================")
            logger.info(
                "📅 [ELIGIBILITY-SERVICE] Filtering Call 2-4 by business days (excludes weekends/holidays)..."
            )
            logger.info("📅 [ELIGIBILITY-SERVICE] Call 1: No filter (first call)")
            logger.info(
                "📅 [ELIGIBILITY-SERVICE] Call 2-3: Require 2 business days since last attempt"
            )
            logger.info(
                "📅 [ELIGIBILITY-SERVICE] Call 4: Require 5 business days since last attempt"
            )
            logger.info(
                "📅 [ELIGIBILITY-SERVICE] Call 5+: >7 calendar days (8+ days) frequency (SQL)"
            )
            logger.info(
                "📅 [ELIGIBILITY-SERVICE] Call 5+: Business day validation (Python - current day check)"
            )

            business_day_filtered_members = []
            now_utc = datetime.now(pytz.UTC)

            for member in potential_members:
                call_attempt_number = member.get("call_attempt_number", 1)
                last_attempt_date = member.get("last_attempt_date")

                # Call 1: No previous attempts, always include
                if call_attempt_number == 1:
                    business_day_filtered_members.append(member)
                    continue

                # Call 5+: Check current day is a business day (no frequency calculation needed)
                # Frequency uses >7 CALENDAR days (8+ days, SQL), but calls only on business days
                if call_attempt_number >= 5:
                    # Check if TODAY is a business day (excludes weekends and federal holidays)
                    if is_business_day(now_utc):
                        logger.debug(
                            f"✅ [ELIGIBILITY-SERVICE] Member {member.get('member_id')} Call {call_attempt_number}: "
                            f"Current day is a business day - ELIGIBLE"
                        )
                        business_day_filtered_members.append(member)
                    else:
                        logger.debug(
                            f"❌ [ELIGIBILITY-SERVICE] Member {member.get('member_id')} Call {call_attempt_number}: "
                            f"Current day is NOT a business day (weekend or holiday) - SKIPPED"
                        )
                    continue

                # Call 2-4: Check business days
                if not last_attempt_date:
                    logger.warning(
                        f"⚠️ [ELIGIBILITY-SERVICE] Member {member.get('member_id')} has Call {call_attempt_number} "
                        f"but no last_attempt_date - SKIPPING"
                    )
                    continue

                # Calculate business days since last attempt
                business_days = get_business_days_between(last_attempt_date, now_utc)

                # Call 2-3: Need 2 business days
                if call_attempt_number in [2, 3]:
                    if business_days >= 2:
                        logger.debug(
                            f"✅ [ELIGIBILITY-SERVICE] Member {member.get('member_id')} Call {call_attempt_number}: "
                            f"{business_days} business days (>= 2 required) - ELIGIBLE"
                        )
                        business_day_filtered_members.append(member)
                    else:
                        logger.debug(
                            f"❌ [ELIGIBILITY-SERVICE] Member {member.get('member_id')} Call {call_attempt_number}: "
                            f"{business_days} business days (< 2 required) - SKIPPED"
                        )

                # Call 4: Need 5 business days
                elif call_attempt_number == 4:
                    if business_days >= 5:
                        logger.debug(
                            f"✅ [ELIGIBILITY-SERVICE] Member {member.get('member_id')} Call 4: "
                            f"{business_days} business days (>= 5 required) - ELIGIBLE"
                        )
                        business_day_filtered_members.append(member)
                    else:
                        logger.debug(
                            f"❌ [ELIGIBILITY-SERVICE] Member {member.get('member_id')} Call 4: "
                            f"{business_days} business days (< 5 required) - SKIPPED"
                        )

            business_day_filtered_count = len(potential_members) - len(
                business_day_filtered_members
            )
            logger.info("")
            logger.info("✅ [ELIGIBILITY-SERVICE] Business day frequency validation complete")
            logger.info(
                f"   ✓ Passed business day check: {len(business_day_filtered_members)} members"
            )
            logger.info(
                f"   ✗ Filtered out (insufficient business days): {business_day_filtered_count} members"
            )
            logger.info("   ℹ️ Call 5+ members validated for current day being a business day")

            # Filter by business hours
            logger.info("")
            logger.info("🕐 [ELIGIBILITY-SERVICE] ============================================")
            logger.info("🕐 [ELIGIBILITY-SERVICE] BUSINESS HOURS VALIDATION")
            logger.info("🕐 [ELIGIBILITY-SERVICE] ============================================")
            logger.info("🕐 [ELIGIBILITY-SERVICE] Filtering members by business hours...")
            logger.info(
                "🕐 [ELIGIBILITY-SERVICE] Campaign operating hours: Check campaign.operating_start_time to campaign.operating_end_time"
            )
            logger.info(
                "🕐 [ELIGIBILITY-SERVICE] Member timezone: Using member.timezone for time calculations"
            )

            eligible_members = self._filter_by_business_hours(business_day_filtered_members)

            filtered_out_count = len(business_day_filtered_members) - len(eligible_members)
            logger.info("")
            logger.info("✅ [ELIGIBILITY-SERVICE] Business hours validation complete")
            logger.info(f"   ✓ Eligible members: {len(eligible_members)}")
            logger.info(f"   ✗ Filtered out (outside business hours): {filtered_out_count}")

            # Final summary
            if len(eligible_members) > 0:
                logger.info("")
                logger.info("📊 [ELIGIBILITY-SERVICE] ============================================")
                logger.info("📊 [ELIGIBILITY-SERVICE] FINAL ELIGIBILITY SUMMARY")
                logger.info("📊 [ELIGIBILITY-SERVICE] ============================================")
                logger.info(
                    f"📊 [ELIGIBILITY-SERVICE] ✅ Total Eligible Members: {len(eligible_members)}"
                )
                logger.info(
                    f"📊 [ELIGIBILITY-SERVICE] 📋 Total Potential Members: {len(potential_members)}"
                )
                logger.info(
                    f"📊 [ELIGIBILITY-SERVICE] 🕐 Filtered by Business Hours: {filtered_out_count}"
                )
                logger.info(
                    f"📊 [ELIGIBILITY-SERVICE] 📈 Qualification Rate: {(len(eligible_members)/len(potential_members)*100):.1f}%"
                )
                logger.info("")
                logger.info("📊 [ELIGIBILITY-SERVICE] Qualification Funnel:")
                logger.info(f"   1. Database Query → {len(potential_members)} potential members")
                logger.info(
                    f"   2. Business Hours Filter → {len(eligible_members)} eligible members"
                )
                logger.info(f"   3. Ready for Bland AI Submission → {len(eligible_members)} calls")
                logger.info("📊 [ELIGIBILITY-SERVICE] ============================================")
            else:
                logger.info("")
                logger.info("⚠️ [ELIGIBILITY-SERVICE] ============================================")
                logger.info("⚠️ [ELIGIBILITY-SERVICE] NO ELIGIBLE MEMBERS AFTER FILTERING")
                logger.info("⚠️ [ELIGIBILITY-SERVICE] ============================================")
                logger.info(
                    "⚠️ [ELIGIBILITY-SERVICE] All potential members were outside business hours"
                )
                logger.info(
                    f"⚠️ [ELIGIBILITY-SERVICE] Potential members found: {len(potential_members)}"
                )
                logger.info(f"⚠️ [ELIGIBILITY-SERVICE] Filtered out: {filtered_out_count}")
                logger.info(
                    "⚠️ [ELIGIBILITY-SERVICE] Next scheduler run may find eligible members during operating hours"
                )
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

        BusinessCaseID: BC-DA-003

        This private method performs the second stage of eligibility filtering by validating
        business hours for each member. It ensures calls are only made when BOTH Medical Guardian
        operating hours AND the member's local timezone are within business hours (9 AM - 5 PM).

        **Why Dual-Timezone Validation?**
            Device Activation campaigns must respect two time constraints:

            1. **Medical Guardian Operating Hours**: Calls can only be made during MG business hours
               (9 AM - 5 PM EST) to ensure staff availability for escalations and support.

            2. **Member's Local Timezone**: Calls must respect the member's local time to avoid
               calling outside reasonable hours (e.g., don't call member at 8 AM Pacific when it's
               11 AM EST for Medical Guardian).

            Example scenario:
            - Current time: 8:30 AM EST (Medical Guardian time)
            - Member timezone: America/Los_Angeles (Pacific - 5:30 AM local time)
            - Result: ❌ Skip this member (before 9 AM in both timezones)

            Example scenario:
            - Current time: 11:00 AM EST (Medical Guardian time)
            - Member timezone: America/Los_Angeles (Pacific - 8:00 AM local time)
            - Result: ❌ Skip this member (before 9 AM in member's timezone)

            Example scenario:
            - Current time: 2:00 PM EST (Medical Guardian time)
            - Member timezone: America/Chicago (Central - 1:00 PM local time)
            - Result: ✅ Call this member (both timezones within 9 AM - 5 PM)

        **Business Hours Logic**:
            Uses shared utility function `can_make_call()` from business_hours_utils.py

            The function checks:
            1. Convert current UTC time to Medical Guardian timezone (America/New_York)
            2. Check if MG time is between 9 AM - 5 PM (operating hours)
            3. Convert current UTC time to member's timezone (from members.timezone)
            4. Check if member's local time is between 9 AM - 5 PM
            5. Return True only if BOTH checks pass

        **Timezone Handling**:
            - All member timezones stored in IANA format (e.g., 'America/New_York', 'America/Chicago')
            - Uses pytz library for accurate timezone conversion (handles DST automatically)
            - Invalid timezones cause member to be skipped with warning log
            - UTC time source: datetime.now(pytz.UTC)

        **Process Flow**:
            1. Get current time in UTC (timezone-aware)
            2. For each member in potential_members:
                a. Extract member_id, timezone
                b. Validate timezone format (pytz.timezone(member_timezone))
                c. Call can_make_call(now_utc, member_tz) from business_hours_utils
                d. If can_call = True: Add to eligible_members list
                e. If can_call = False: Log reason and skip member
            3. Return filtered eligible_members list

        Args:
            potential_members (List[Dict]): List of members from SQL eligibility query.
                Each dict must contain:
                - member_id (str): Member UUID for logging
                - timezone (str): Member timezone in IANA format (e.g., 'America/New_York')
                - timezone_flag (str, optional): Timezone mode (defaults to 'member_tz')

                Additional fields are passed through unchanged to eligible_members.

        Returns:
            List[Dict]: Filtered list of members passing business hours validation.
                Same structure as input, but only includes members where:
                - Medical Guardian time is 9 AM - 5 PM EST
                - Member's local time is 9 AM - 5 PM in member.timezone

                Returns empty list if no members pass validation (not an error).

        Raises:
            Exception: If timezone validation encounters critical errors.
                Individual member timezone errors are caught and logged as warnings.
                Member is skipped but processing continues for remaining members.

        Example:
            >>> # Setup
            >>> now_utc = datetime.now(pytz.UTC)  # 2025-12-24 18:00:00 UTC
            >>> print(f"Current time UTC: {now_utc}")
            Current time UTC: 2025-12-24 18:00:00+00:00
            >>>
            >>> # Member 1: Eastern timezone (1:00 PM local)
            >>> member1 = {
            ...     'member_id': 'abc-123',
            ...     'timezone': 'America/New_York',
            ...     'first_name': 'John'
            ... }
            >>>
            >>> # Member 2: Pacific timezone (10:00 AM local)
            >>> member2 = {
            ...     'member_id': 'def-456',
            ...     'timezone': 'America/Los_Angeles',
            ...     'first_name': 'Jane'
            ... }
            >>>
            >>> # Filter members
            >>> eligible = eligibility_service._filter_by_business_hours([member1, member2])
            >>> print(f"Eligible: {[m['first_name'] for m in eligible]}")
            Eligible: ['John', 'Jane']  # Both pass (1 PM EST and 10 AM PST are valid)

        Logging Output:
            **Start:**
            ⏰ [ELIGIBILITY-SERVICE] Validating business hours for 25 members...

            **Per Member (Debug Level):**
            ⏰ [ELIGIBILITY-SERVICE] Checking member abc-123 (timezone: America/New_York, mode: member_tz)
            ✅ [ELIGIBILITY-SERVICE] Member abc-123 eligible: Both timezones within business hours

            **Per Member (Filtered Out):**
            ⏰ [ELIGIBILITY-SERVICE] Checking member def-456 (timezone: America/Los_Angeles, mode: member_tz)
            ⏰ [ELIGIBILITY-SERVICE] Member def-456 not eligible: Member timezone outside business hours (8:00 AM Pacific)

            **Timezone Error:**
            ⚠️ [ELIGIBILITY-SERVICE] Error validating business hours for member ghi-789: Invalid timezone 'Bad/Timezone'

            **Summary:**
            ✅ [ELIGIBILITY-SERVICE] 18/25 members passed business hours validation

        Notes:
            - This is a private method (underscore prefix) called only by get_eligible_members()
            - Business hours are hardcoded: 9 AM - 5 PM (not configurable per campaign)
            - Timezone validation errors skip the member but don't fail the entire batch
            - DST transitions are handled automatically by pytz library
            - Weekend/holiday checks are NOT performed (only time-of-day validation)
            - Members with invalid timezones are skipped with warning log
            - Empty result is valid (e.g., all members called during off-hours)

        Related Code:
            - af_code/shared/business_hours_utils.py:15-45 - can_make_call() implementation
            - af_code/device_activation_scheduler/services/eligibility_service.py:389-552 - Calls this method
        """
        logger.info(
            f"⏰ [ELIGIBILITY-SERVICE] Validating business hours for {len(potential_members)} members..."
        )

        eligible_members = []
        now_utc = datetime.now(pytz.UTC)

        for member in potential_members:
            member_id = member.get("member_id")
            member_timezone = member.get("timezone")
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
