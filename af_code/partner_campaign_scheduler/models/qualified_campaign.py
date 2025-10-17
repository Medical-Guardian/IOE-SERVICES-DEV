from dataclasses import dataclass
from typing import Optional

@dataclass
class QualifiedCampaign:
    """Model representing a Partner campaign that qualifies for current execution"""
    campaign_id: str
    org_id: str
    name: str
    description: str
    contact_pref: str
    call_days_of_week: str
    operating_start_time: str
    operating_end_time: str
    operating_tz: Optional[str]
    scheduling_mode: str
    frequency_value: int
    frequency_unit: str
    timezone_flag: str  # 'member_tz' or 'operating_tz'
    max_care_gaps: int
    config_id: Optional[str]
    call_type_id: Optional[str]
    org_type: str
    audience_file_batch: str
    partner_contact_name: Optional[str]  # Partner contact from orgs table
    org_name: Optional[str]  # Organization name from orgs table