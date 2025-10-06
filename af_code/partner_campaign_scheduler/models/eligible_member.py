from dataclasses import dataclass
from typing import Optional
from datetime import datetime, time

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
    contact_pref: Optional[str]  # Use existing members.contact_pref
    is_device_callable: Optional[bool]  # From member_devices
    timezone: str
    preferred_window: Optional[str]
    enrollment_status: str
    last_attempt_ts: Optional[datetime]
    total_attempts: int
    member_current_time: Optional[time]
    member_current_day: Optional[str]