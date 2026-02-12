"""
Phone Selector Utility for DTC Campaigns

This module determines which phone number to call based on campaign contact preference
and member data (phone vs device routing).

Ported from Partner campaign batch_orchestrator.py to enable device routing in DTC campaigns.
"""

import logging
from typing import Optional, Dict
from af_code.shared.phone_utils import standardize_phone

logger = logging.getLogger(__name__)


def get_target_phone(member_data: Dict, contact_pref: str) -> Optional[str]:
    """
    Determine which phone to call based on contact_pref and member data.

    This function implements the same logic as Partner campaigns for device vs phone routing.

    Args:
        member_data: Dict with keys:
            - primary_phone: Member's primary phone number
            - device_phone_number: Device phone number (if device exists)
            - Channel: Member's routing preference (phone/device/None)
            - is_device_callable: Boolean indicating if device can receive calls
        contact_pref: Campaign's contact preference setting
            - "phone": Always use primary_phone
            - "device": Always use device_phone_number (if callable)
            - "member_preference": Use member's Channel preference with fallback
            - "auto": Treated same as "member_preference"

    Returns:
        Validated E.164 phone number string, or None if no valid phone available

    Examples:
        >>> # Phone-only mode
        >>> get_target_phone({"primary_phone": "+15551234567", "Channel": "device"}, "phone")
        "+15551234567"

        >>> # Device-only mode with callable device
        >>> get_target_phone({
        ...     "device_phone_number": "+15559876543",
        ...     "is_device_callable": True
        ... }, "device")
        "+15559876543"

        >>> # Member preference mode - respects enrollment-level channel setting
        >>> get_target_phone({
        ...     "primary_phone": "+15551234567",
        ...     "device_phone_number": "+15559876543",
        ...     "channel": "device",
        ...     "is_device_callable": True
        ... }, "member_preference")
        "+15559876543"
    """
    primary_phone = member_data.get("primary_phone")
    device_phone = member_data.get("device_phone_number")
    member_channel = member_data.get("channel")  # Enrollment-level channel
    is_callable = member_data.get("is_device_callable")
    member_id = member_data.get("member_id", "unknown")

    logger.info(f"📞 [PHONE-SELECTOR] Member {member_id}: contact_pref={contact_pref}")
    logger.info(f"   Primary phone: {primary_phone}")
    logger.info(f"   Device phone: {device_phone}")
    logger.info(f"   Enrollment channel: {member_channel}")
    logger.info(f"   Device callable: {is_callable}")

    # Handle auto -> member_preference conversion
    if contact_pref == "auto":
        contact_pref = "member_preference"
        logger.info("   Converted 'auto' to 'member_preference'")

    # OPTION 1: Phone Only (campaign forces phone)
    if contact_pref == "phone":
        if primary_phone:
            validated = standardize_phone(primary_phone)
            if validated:
                logger.info(f"✅ [PHONE-SELECTOR] Using primary phone: {validated}")
                return validated
        logger.warning(f"⚠️ [PHONE-SELECTOR] Member {member_id}: No valid primary phone available")
        return None

    # OPTION 2: Device Only (campaign forces device)
    elif contact_pref == "device":
        if device_phone and is_callable:
            validated = standardize_phone(device_phone)
            if validated:
                logger.info(f"✅ [PHONE-SELECTOR] Using device phone: {validated}")
                return validated
        logger.warning(
            f"⚠️ [PHONE-SELECTOR] Member {member_id}: No valid device phone available (or not callable)"
        )
        return None

    # OPTION 3: Member Preference (respect member's Channel setting)
    elif contact_pref == "member_preference":
        # Try member's preferred channel first
        if member_channel == "phone" and primary_phone:
            validated = standardize_phone(primary_phone)
            if validated:
                logger.info(f"✅ [PHONE-SELECTOR] Using member's preferred phone: {validated}")
                return validated

        elif member_channel == "device" and device_phone and is_callable:
            validated = standardize_phone(device_phone)
            if validated:
                logger.info(f"✅ [PHONE-SELECTOR] Using member's preferred device: {validated}")
                return validated

        # No fallback - return None with clear warning
        logger.warning(
            f"⚠️ [PHONE-SELECTOR] Member {member_id} INELIGIBLE: "
            f"Enrollment channel='{member_channel}' but channel unavailable. "
            f"primary_phone={bool(primary_phone)}, "
            f"device_phone={bool(device_phone)}, "
            f"device_callable={bool(is_callable)}. "
            f"No fallback - respecting member preference."
        )
        return None

    # Invalid contact_pref value
    else:
        logger.error(f"❌ [PHONE-SELECTOR] Invalid contact_pref: {contact_pref}")
        return None
