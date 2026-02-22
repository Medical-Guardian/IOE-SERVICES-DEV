from dataclasses import dataclass
from typing import Optional
from datetime import datetime, time, date


@dataclass
class EligibleMember:
    """Model representing a member eligible for campaign outreach"""

    member_id: str
    campaign_id: str
    enrollment_id: str  # Added for FK to outreach_attempts
    first_name: str
    last_name: str
    primary_phone: Optional[str]
    device_phone_number: Optional[str]  # From member_devices table
    channel: Optional[
        str
    ]  # ✅ Enrollment-level channel (from member_campaign_enrollments_enhanced.channel)
    is_device_callable: Optional[bool]  # From member_devices
    timezone: str
    preferred_window: Optional[str]
    enrollment_status: str
    last_attempt_ts: Optional[datetime]
    total_attempts: int
    member_current_time: Optional[time]
    member_current_day: Optional[str]

    # Additional fields for Bland AI request_data (DTC-style)
    member_care_gap_parameters: Optional[str]  # JSON string with care gap flags
    language_pref: Optional[str]  # Language preference (en, es, etc.)
    address_street: Optional[str]  # Street address
    address_city: Optional[str]  # City
    address_state: Optional[str]  # State
    address_zip: Optional[str]  # ZIP code
    dob: Optional[date]  # Date of birth
