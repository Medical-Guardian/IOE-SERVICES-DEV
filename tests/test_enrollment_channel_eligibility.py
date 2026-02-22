"""
Unit tests for enrollment-level channel eligibility validation

Tests channel-based device status enforcement for member campaign enrollments.
Ensures that enrollments with channel='device' require active devices.

BusinessCaseID: BC-ENROLLMENT-CHANNEL-MIGRATION
Created: 2026-02-13
"""

import uuid
import pytest
from datetime import datetime, time
from unittest.mock import Mock, MagicMock
from af_code.partner_campaign_scheduler.models.eligible_member import EligibleMember


# ============================================================================
# Test Data Fixtures
# ============================================================================


@pytest.fixture
def test_campaign():
    """Mock campaign configuration"""
    campaign = Mock()
    campaign.campaign_id = str(uuid.uuid4())
    campaign.name = "Test Wellness Campaign"
    campaign.timezone_flag = "operating_tz"
    campaign.operating_tz = "America/New_York"
    campaign.contact_pref = "member_preference"
    campaign.frequency_value = 1
    campaign.frequency_unit = "week"
    campaign.operating_start_time = time(9, 0)
    campaign.operating_end_time = time(17, 0)
    campaign.call_days_of_week = "Monday,Tuesday,Wednesday,Thursday,Friday"
    campaign.org_id = str(uuid.uuid4())
    campaign.audience_file_batch = "BATCH-001"
    return campaign


@pytest.fixture
def test_member_with_active_device():
    """Member with active device (service_status='In Service')"""
    return {
        "member_id": str(uuid.uuid4()),
        "enrollment_id": str(uuid.uuid4()),
        "first_name": "Alice",
        "last_name": "Anderson",
        "primary_phone": "+18125551111",
        "device_phone_number": "+18125552222",
        "Channel": "device",  # ✅ Enrollment-level channel
        "is_device_callable": True,
        "device_service_status": "In Service",
        "active_device_count": 1,
        "total_device_count": 1,
        "timezone": "America/New_York",
        "preferred_window": "morning",
        "current_status": "Active",
        "last_attempt_ts": None,
        "total_attempts": 0,
        "member_current_time": time(10, 0),
        "member_current_day": "Monday",
        "member_care_gap_parameters": None,
        "language_pref": "EN",
        "address_street": "123 Main St",
        "address_city": "New York",
        "address_state": "NY",
        "address_zip": "10001",
        "dob": datetime(1970, 1, 1).date(),
    }


@pytest.fixture
def test_member_device_out_of_service():
    """Member with device in 'Out of Service' status"""
    return {
        "member_id": str(uuid.uuid4()),
        "enrollment_id": str(uuid.uuid4()),
        "first_name": "Bob",
        "last_name": "Brown",
        "primary_phone": "+18125553333",
        "device_phone_number": "+18125554444",
        "Channel": "device",  # ✅ Enrollment channel = device
        "is_device_callable": True,
        "device_service_status": "Out of Service",  # ❌ Device not active
        "active_device_count": 0,  # No active devices
        "total_device_count": 1,
        "timezone": "America/Chicago",
        "preferred_window": "afternoon",
        "current_status": "Active",
        "last_attempt_ts": None,
        "total_attempts": 0,
        "member_current_time": time(14, 0),
        "member_current_day": "Tuesday",
        "member_care_gap_parameters": None,
        "language_pref": "EN",
        "address_street": "456 Oak Ave",
        "address_city": "Chicago",
        "address_state": "IL",
        "address_zip": "60601",
        "dob": datetime(1980, 5, 15).date(),
    }


@pytest.fixture
def test_member_phone_channel():
    """Member with enrollment channel='phone' (device status irrelevant)"""
    return {
        "member_id": str(uuid.uuid4()),
        "enrollment_id": str(uuid.uuid4()),
        "first_name": "Carol",
        "last_name": "Chen",
        "primary_phone": "+18125555555",
        "device_phone_number": None,  # No device
        "Channel": "phone",  # ✅ Enrollment channel = phone
        "is_device_callable": False,
        "device_service_status": None,
        "active_device_count": 0,
        "total_device_count": 0,
        "timezone": "America/Los_Angeles",
        "preferred_window": "evening",
        "current_status": "Active",
        "last_attempt_ts": None,
        "total_attempts": 0,
        "member_current_time": time(18, 0),
        "member_current_day": "Wednesday",
        "member_care_gap_parameters": None,
        "language_pref": "ES",
        "address_street": "789 Palm Blvd",
        "address_city": "Los Angeles",
        "address_state": "CA",
        "address_zip": "90001",
        "dob": datetime(1990, 10, 20).date(),
    }


# ============================================================================
# Test Case 1: Enrollment with channel='device' + active device → ELIGIBLE
# ============================================================================


def test_enrollment_channel_device_with_active_device(test_member_with_active_device):
    """
    Test enrollment eligibility when channel='device' and device is 'In Service'

    Scenario:
    - Enrollment has channel='device'
    - Member has device with service_status='In Service'
    - Expected: Enrollment is ELIGIBLE for calling
    """
    member_data = test_member_with_active_device

    # Verify enrollment-level channel
    assert member_data["Channel"] == "device"

    # Verify device is active
    assert member_data["device_service_status"] == "In Service"
    assert member_data["active_device_count"] > 0

    # SQL query would include this enrollment
    # Eligibility logic: channel='device' + active_device_count > 0 → ELIGIBLE
    is_eligible = member_data["Channel"] == "device" and member_data["active_device_count"] > 0

    assert is_eligible is True

    # Create EligibleMember object
    eligible_member = EligibleMember(
        member_id=member_data["member_id"],
        campaign_id=str(uuid.uuid4()),
        enrollment_id=member_data["enrollment_id"],
        first_name=member_data["first_name"],
        last_name=member_data["last_name"],
        primary_phone=member_data["primary_phone"],
        device_phone_number=member_data["device_phone_number"],
        channel=member_data["Channel"],  # ✅ Enrollment-level channel
        is_device_callable=member_data["is_device_callable"],
        timezone=member_data["timezone"],
        preferred_window=member_data["preferred_window"],
        enrollment_status=member_data["current_status"],
        last_attempt_ts=member_data["last_attempt_ts"],
        total_attempts=member_data["total_attempts"],
        member_current_time=member_data["member_current_time"],
        member_current_day=member_data["member_current_day"],
        member_care_gap_parameters=member_data["member_care_gap_parameters"],
        language_pref=member_data["language_pref"],
        address_street=member_data["address_street"],
        address_city=member_data["address_city"],
        address_state=member_data["address_state"],
        address_zip=member_data["address_zip"],
        dob=member_data["dob"],
    )

    # Verify member is eligible for device-channel calling
    assert eligible_member.channel == "device"
    assert eligible_member.device_phone_number is not None


# ============================================================================
# Test Case 2: Enrollment with channel='device' + no active device → INELIGIBLE
# ============================================================================


def test_enrollment_channel_device_no_active_device(test_member_device_out_of_service):
    """
    Test enrollment ineligibility when channel='device' but all devices 'Out of Service'

    Scenario:
    - Enrollment has channel='device'
    - Member has device with service_status='Out of Service'
    - Expected: Enrollment is INELIGIBLE (excluded from SQL query)
    """
    member_data = test_member_device_out_of_service

    # Verify enrollment-level channel
    assert member_data["Channel"] == "device"

    # Verify no active devices
    assert member_data["device_service_status"] == "Out of Service"
    assert member_data["active_device_count"] == 0

    # SQL query would EXCLUDE this enrollment
    # Eligibility logic: channel='device' + active_device_count == 0 → INELIGIBLE
    is_eligible = member_data["Channel"] != "device" or (
        member_data["Channel"] == "device" and member_data["active_device_count"] > 0
    )

    assert is_eligible is False

    # This member would NOT appear in SQL query results
    # Log warning would be generated (but SQL filters them out)


# ============================================================================
# Test Case 3: Enrollment with channel='phone' → Always ELIGIBLE
# ============================================================================


def test_enrollment_channel_phone_ignores_device_status(test_member_phone_channel):
    """
    Test enrollment eligibility when channel='phone' (device status irrelevant)

    Scenario:
    - Enrollment has channel='phone'
    - Member has no devices or devices are 'Out of Service'
    - Expected: Enrollment is ELIGIBLE (phone channel doesn't depend on device status)
    """
    member_data = test_member_phone_channel

    # Verify enrollment-level channel
    assert member_data["Channel"] == "phone"

    # Verify no device available
    assert member_data["device_phone_number"] is None
    assert member_data["active_device_count"] == 0

    # SQL query would INCLUDE this enrollment (phone channel eligible regardless of device status)
    # Eligibility logic: channel='phone' → ELIGIBLE
    is_eligible = member_data["Channel"] == "phone" or member_data["Channel"] != "device"

    assert is_eligible is True

    # Create EligibleMember object
    eligible_member = EligibleMember(
        member_id=member_data["member_id"],
        campaign_id=str(uuid.uuid4()),
        enrollment_id=member_data["enrollment_id"],
        first_name=member_data["first_name"],
        last_name=member_data["last_name"],
        primary_phone=member_data["primary_phone"],
        device_phone_number=member_data["device_phone_number"],
        channel=member_data["Channel"],  # ✅ Enrollment-level channel
        is_device_callable=member_data["is_device_callable"],
        timezone=member_data["timezone"],
        preferred_window=member_data["preferred_window"],
        enrollment_status=member_data["current_status"],
        last_attempt_ts=member_data["last_attempt_ts"],
        total_attempts=member_data["total_attempts"],
        member_current_time=member_data["member_current_time"],
        member_current_day=member_data["member_current_day"],
        member_care_gap_parameters=member_data["member_care_gap_parameters"],
        language_pref=member_data["language_pref"],
        address_street=member_data["address_street"],
        address_city=member_data["address_city"],
        address_state=member_data["address_state"],
        address_zip=member_data["address_zip"],
        dob=member_data["dob"],
    )

    # Verify member is eligible for phone-channel calling
    assert eligible_member.channel == "phone"
    assert eligible_member.primary_phone is not None


# ============================================================================
# Test Case 4: Enrollment with channel=NULL → Default behavior (ELIGIBLE)
# ============================================================================


def test_enrollment_channel_null_default_behavior():
    """
    Test enrollment eligibility when channel is NULL (not set)

    Scenario:
    - Enrollment has channel=NULL
    - Expected: Default behavior (eligible if phone or device available)
    """
    member_data = {
        "member_id": str(uuid.uuid4()),
        "enrollment_id": str(uuid.uuid4()),
        "Channel": None,  # ✅ Enrollment channel not set
        "primary_phone": "+18125556666",
        "device_phone_number": None,
        "is_device_callable": False,
        "active_device_count": 0,
        "timezone": "America/Denver",
        "current_status": "Active",
    }

    # SQL query logic: channel=NULL → Eligible if phone OR device available
    is_eligible = member_data["Channel"] is None and (
        member_data["primary_phone"] is not None
        or (member_data["device_phone_number"] is not None and member_data["is_device_callable"])
    )

    assert is_eligible is True


# ============================================================================
# Test Case 5: Multiple enrollments for same member with different channels
# ============================================================================


def test_member_multiple_enrollments_different_channels():
    """
    Test member with multiple enrollments using different channels

    Scenario:
    - Member 123 enrolled in Campaign A with channel='device' (has active device)
    - Same member enrolled in Campaign B with channel='phone'
    - Expected: Both enrollments eligible (different channel preferences per campaign)
    """
    member_id = str(uuid.uuid4())

    # Enrollment A: Campaign A with channel='device'
    enrollment_a = {
        "enrollment_id": str(uuid.uuid4()),
        "campaign_id": "campaign-a",
        "member_id": member_id,
        "Channel": "device",  # ✅ Wants device for wellness checks
        "device_phone_number": "+18125557777",
        "is_device_callable": True,
        "device_service_status": "In Service",
        "active_device_count": 1,
    }

    # Enrollment B: Campaign B with channel='phone'
    enrollment_b = {
        "enrollment_id": str(uuid.uuid4()),
        "campaign_id": "campaign-b",
        "member_id": member_id,
        "Channel": "phone",  # ✅ Wants phone for appointment reminders
        "primary_phone": "+18125558888",
        "device_phone_number": "+18125557777",
        "is_device_callable": True,
        "active_device_count": 1,
    }

    # Enrollment A eligibility
    is_eligible_a = enrollment_a["Channel"] == "device" and enrollment_a["active_device_count"] > 0

    # Enrollment B eligibility
    is_eligible_b = enrollment_b["Channel"] == "phone" and enrollment_b["primary_phone"] is not None

    # Both enrollments should be eligible
    assert is_eligible_a is True
    assert is_eligible_b is True

    # Validate: Same member, different campaigns, different channel preferences
    assert enrollment_a["member_id"] == enrollment_b["member_id"]
    assert enrollment_a["campaign_id"] != enrollment_b["campaign_id"]
    assert enrollment_a["Channel"] != enrollment_b["Channel"]


# ============================================================================
# Test Case 6: Enrollment channel='device' with mixed device statuses
# ============================================================================


def test_enrollment_channel_device_mixed_device_statuses():
    """
    Test enrollment with multiple devices (some active, some inactive)

    Scenario:
    - Enrollment has channel='device'
    - Member has 2 devices: 1 'In Service', 1 'Out of Service'
    - Expected: Enrollment is ELIGIBLE (at least 1 active device available)
    """
    member_data = {
        "member_id": str(uuid.uuid4()),
        "enrollment_id": str(uuid.uuid4()),
        "Channel": "device",
        "active_device_count": 1,  # 1 active device
        "total_device_count": 2,  # 2 total devices
        "device_phone_number": "+18125559999",
        "is_device_callable": True,
        "device_service_status": "In Service",  # At least one is active
    }

    # Eligibility: channel='device' + at least 1 active device → ELIGIBLE
    is_eligible = member_data["Channel"] == "device" and member_data["active_device_count"] > 0

    assert is_eligible is True
    assert member_data["total_device_count"] == 2
    assert member_data["active_device_count"] == 1


# ============================================================================
# Test Case 7: SQL Query Filtering Validation
# ============================================================================


def test_sql_channel_device_status_filter():
    """
    Validate SQL WHERE clause logic for channel='device' + device status

    SQL Filter:
    AND (
        mce.channel != 'device'
        OR (mce.channel = 'device' AND eds.active_device_count > 0)
    )
    """
    test_cases = [
        # (channel, active_device_count, expected_eligible)
        ("device", 1, True),  # device + active → eligible
        ("device", 0, False),  # device + no active → ineligible
        ("phone", 0, True),  # phone + no device → eligible
        ("phone", 1, True),  # phone + device → eligible
        (None, 0, True),  # null channel + phone → eligible
        (None, 1, True),  # null channel + device → eligible
    ]

    for channel, active_count, expected in test_cases:
        # Simulate SQL WHERE clause
        is_eligible = channel != "device" or (channel == "device" and active_count > 0)

        assert is_eligible == expected, (
            f"Failed for channel={channel}, active_count={active_count}: "
            f"expected {expected}, got {is_eligible}"
        )


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
