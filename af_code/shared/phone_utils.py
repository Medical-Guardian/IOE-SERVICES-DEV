"""
Phone Number Utilities for IOE Services

Shared utilities for phone number validation and standardization across all campaigns.

BusinessCaseID: BC-109 (Partner), BC-101 (DTC)
"""

from typing import Optional
import logging

logger = logging.getLogger(__name__)


def standardize_phone(phone: str) -> Optional[str]:
    """
    Standardize phone number to E.164 format.

    E.164 is the international telephone numbering plan that ensures phone numbers
    are globally unique. Format: +[country code][subscriber number]

    Examples:
        - US 10-digit: 5551234567 → +15551234567
        - US 11-digit: 15551234567 → +15551234567
        - Already formatted: +15551234567 → +15551234567
        - International: 442012345678 → +442012345678

    Args:
        phone: Raw phone number string (may contain spaces, dashes, parentheses)

    Returns:
        Standardized phone number in E.164 format (+[digits]) or None if invalid

    Validation Rules:
        - E.164 format requires + prefix followed by 11-15 digits
        - US numbers: 10 digits (add +1) or 11 digits starting with 1 (add +)
        - International: 11-15 digits without + prefix
        - Rejects: Empty strings, non-numeric input, invalid lengths
    """
    if not phone or (hasattr(phone, "__iter__") and not isinstance(phone, str)):
        return None

    # Convert to string and strip whitespace
    phone_str = str(phone).strip()

    if not phone_str:
        return None

    # If already in E.164 format (starts with +), validate and return
    if phone_str.startswith("+"):
        # Remove + and any non-numeric characters after it
        digits_only = "".join(c for c in phone_str[1:] if c.isdigit())
        # E.164 format allows 11-15 digits after the +
        if 11 <= len(digits_only) <= 15:
            standardized = f"+{digits_only}"
            logger.debug(f"📞 [PHONE-UTILS] Valid E.164 format: {standardized}")
            return standardized
        else:
            logger.warning(
                f"⚠️ [PHONE-UTILS] Invalid E.164 length ({len(digits_only)} digits): {phone_str}"
            )
            return None

    # Remove all non-numeric characters
    digits_only = "".join(c for c in phone_str if c.isdigit())

    # Handle different phone number formats
    if len(digits_only) == 10 and digits_only[0] in "23456789":
        # Standard 10-digit US number (area code cannot start with 0 or 1)
        standardized = f"+1{digits_only}"
        logger.debug(f"📞 [PHONE-UTILS] Standardized 10-digit US number: {standardized}")
        return standardized
    elif len(digits_only) == 11 and digits_only[0] == "1" and digits_only[1] in "23456789":
        # 11-digit number starting with 1 (US country code)
        standardized = f"+{digits_only}"
        logger.debug(f"📞 [PHONE-UTILS] Standardized 11-digit US number: {standardized}")
        return standardized
    elif 11 <= len(digits_only) <= 15:
        # International number without + prefix
        # For numbers that don't fit US patterns but are valid international lengths
        standardized = f"+{digits_only}"
        logger.debug(f"📞 [PHONE-UTILS] Standardized international number: {standardized}")
        return standardized

    logger.warning(
        f"⚠️ [PHONE-UTILS] Invalid phone format (length: {len(digits_only)}): {phone_str}"
    )
    return None
