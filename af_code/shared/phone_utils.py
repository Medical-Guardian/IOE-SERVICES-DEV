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
    # Handle pandas NA/NaN FIRST (before any other operations)
    try:
        import pandas as pd

        if pd.isna(phone):
            return None
    except (ImportError, TypeError, ValueError):
        pass

    # Handle None and empty string
    if phone is None or phone == "":
        return None

    # Convert to string and strip whitespace
    phone_str = str(phone).strip()

    if not phone_str or phone_str.lower() in ("none", "nan", "nat"):
        return None

    # If already in E.164 format (starts with +), validate and return
    if phone_str.startswith("+"):
        # Remove + and any non-numeric characters after it
        digits_only = "".join(c for c in phone_str[1:] if c.isdigit())

        # Special validation for US/Canada numbers (country code 1)
        if digits_only.startswith("1"):
            # US/Canada must be EXACTLY 11 digits (+1 + 10 digits)
            if len(digits_only) == 11:
                # Also validate area code (2nd digit must be 2-9)
                if digits_only[1] in "23456789":
                    standardized = f"+{digits_only}"
                    logger.debug(f"📞 [PHONE-UTILS] Valid US/Canada E.164: {standardized}")
                    return standardized
                else:
                    logger.warning(
                        f"⚠️ [PHONE-UTILS] Invalid US/Canada area code (must start with 2-9): {phone_str}"
                    )
                    return None
            else:
                logger.warning(
                    f"⚠️ [PHONE-UTILS] Invalid US/Canada length ({len(digits_only)} digits, expected 11): {phone_str}"
                )
                return None

        # For other international numbers, allow 11-15 digits
        if 11 <= len(digits_only) <= 15:
            standardized = f"+{digits_only}"
            logger.debug(f"📞 [PHONE-UTILS] Valid international E.164: {standardized}")
            return standardized
        else:
            logger.warning(
                f"⚠️ [PHONE-UTILS] Invalid E.164 length ({len(digits_only)} digits): {phone_str}"
            )
            return None

    # Remove all non-numeric characters
    digits_only = "".join(c for c in phone_str if c.isdigit())

    # Handle different phone number formats
    if len(digits_only) == 10:
        # Device Activation: REJECT 10-digit numbers (must be 11 digits)
        logger.warning(
            f"⚠️ [PHONE-UTILS] Phone number must be 11 digits (received {len(digits_only)}): {phone_str}"
        )
        return None
    elif len(digits_only) == 11 and digits_only[0] == "1" and digits_only[1] in "23456789":
        # 11-digit number starting with 1 (US country code)
        standardized = f"+{digits_only}"
        logger.debug(f"📞 [PHONE-UTILS] Standardized 11-digit US number: {standardized}")
        return standardized
    elif len(digits_only) == 11:
        # Device Activation: 11-digit numbers must start with 1 (US format only)
        # Reject 11-digit numbers that don't start with 1
        logger.warning(
            f"⚠️ [PHONE-UTILS] 11-digit US phone numbers must start with 1 (received: {phone_str})"
        )
        return None
    elif 12 <= len(digits_only) <= 15:
        # Check if it starts with "1" (would be invalid US format)
        if digits_only[0] == "1":
            # Numbers starting with 1 must be EXACTLY 11 digits for US
            # 12+ digits starting with 1 are INVALID
            logger.warning(
                f"⚠️ [PHONE-UTILS] Invalid US number without + (starts with 1, {len(digits_only)} digits, expected 11): {phone_str}"
            )
            return None
        # International number without + prefix (not starting with 1)
        standardized = f"+{digits_only}"
        logger.debug(f"📞 [PHONE-UTILS] Standardized international number: {standardized}")
        return standardized

    logger.warning(
        f"⚠️ [PHONE-UTILS] Invalid phone format (length: {len(digits_only)}): {phone_str}"
    )
    return None


def standardize_phone_device_activation(phone: str) -> Optional[str]:
    """
    Standardize phone number for Device Activation campaigns with specific rules.

    Device Activation specific validation rules:
        - < 10 digits → reject
        - 10 digits → add +1 prefix
        - 11 digits starting with 1 → add + prefix
        - 13 digits starting with 001 → accept as-is (no + added)
        - Already has + and 11 digits → accept as-is
        - All other existing logic preserved

    Examples:
        - 9 digits: 555123456 → None (rejected)
        - 10 digits: 5551234567 → +15551234567
        - 11 digits: 15551234567 → +15551234567
        - 13 digits: 0012345678901 → 0012345678901 (as-is)
        - Already E.164: +15551234567 → +15551234567

    Args:
        phone: Raw phone number string (may contain spaces, dashes, parentheses)

    Returns:
        Standardized phone number or None if invalid
    """
    # Handle pandas NA/NaN FIRST (before any other operations)
    try:
        import pandas as pd

        if pd.isna(phone):
            return None
    except (ImportError, TypeError, ValueError):
        pass

    # Handle None and empty string
    if phone is None or phone == "":
        return None

    # Convert to string and strip whitespace
    phone_str = str(phone).strip()

    if not phone_str or phone_str.lower() in ("none", "nan", "nat"):
        return None

    # If already in E.164 format (starts with +), validate and return
    if phone_str.startswith("+"):
        # Remove + and any non-numeric characters after it
        digits_only = "".join(c for c in phone_str[1:] if c.isdigit())

        # If 11 digits after +, accept as-is (requirement: accept + and 11 digits)
        if len(digits_only) == 11:
            standardized = f"+{digits_only}"
            logger.debug(f"📞 [PHONE-UTILS-DA] Valid E.164 with 11 digits: {standardized}")
            return standardized

        # Special validation for US/Canada numbers (country code 1)
        if digits_only.startswith("1"):
            # US/Canada must be EXACTLY 11 digits (+1 + 10 digits)
            if len(digits_only) == 11:
                # Also validate area code (2nd digit must be 2-9)
                if digits_only[1] in "23456789":
                    standardized = f"+{digits_only}"
                    logger.debug(f"📞 [PHONE-UTILS-DA] Valid US/Canada E.164: {standardized}")
                    return standardized
                else:
                    logger.warning(
                        f"⚠️ [PHONE-UTILS-DA] Invalid US/Canada area code (must start with 2-9): {phone_str}"
                    )
                    return None
            else:
                logger.warning(
                    f"⚠️ [PHONE-UTILS-DA] Invalid US/Canada length ({len(digits_only)} digits, expected 11): {phone_str}"
                )
                return None

        # For other international numbers, allow 11-15 digits
        if 11 <= len(digits_only) <= 15:
            standardized = f"+{digits_only}"
            logger.debug(f"📞 [PHONE-UTILS-DA] Valid international E.164: {standardized}")
            return standardized
        else:
            logger.warning(
                f"⚠️ [PHONE-UTILS-DA] Invalid E.164 length ({len(digits_only)} digits): {phone_str}"
            )
            return None

    # Remove all non-numeric characters
    digits_only = "".join(c for c in phone_str if c.isdigit())

    # Device Activation specific rules
    if len(digits_only) < 10:
        # Reject if less than 10 digits
        logger.warning(
            f"⚠️ [PHONE-UTILS-DA] Phone number must be at least 10 digits (received {len(digits_only)}): {phone_str}"
        )
        return None
    elif len(digits_only) == 10:
        # 10 digits → add +1 prefix
        standardized = f"+1{digits_only}"
        logger.debug(f"📞 [PHONE-UTILS-DA] Standardized 10-digit number: {standardized}")
        return standardized
    elif len(digits_only) == 11:
        # 11 digits → must start with 1, then add + prefix
        if digits_only[0] == "1":
            standardized = f"+{digits_only}"
            logger.debug(f"📞 [PHONE-UTILS-DA] Standardized 11-digit US number: {standardized}")
            return standardized
        else:
            logger.warning(
                f"⚠️ [PHONE-UTILS-DA] 11-digit numbers must start with 1 (received: {phone_str})"
            )
            return None
    elif len(digits_only) == 13:
        # 13 digits starting with 001 → accept as-is (no + added)
        if digits_only.startswith("001"):
            logger.debug(
                f"📞 [PHONE-UTILS-DA] Accepting 13-digit number starting with 001 as-is: {phone_str}"
            )
            return phone_str  # Return original string (no + added)
        else:
            # 13 digits not starting with 001 → follow international logic
            standardized = f"+{digits_only}"
            logger.debug(
                f"📞 [PHONE-UTILS-DA] Standardized 13-digit international number: {standardized}"
            )
            return standardized
    elif 12 <= len(digits_only) <= 15:
        # Check if it starts with "1" (would be invalid US format)
        if digits_only[0] == "1":
            # Numbers starting with 1 must be EXACTLY 11 digits for US
            # 12+ digits starting with 1 are INVALID
            logger.warning(
                f"⚠️ [PHONE-UTILS-DA] Invalid US number without + (starts with 1, {len(digits_only)} digits, expected 11): {phone_str}"
            )
            return None
        # International number without + prefix (not starting with 1)
        standardized = f"+{digits_only}"
        logger.debug(f"📞 [PHONE-UTILS-DA] Standardized international number: {standardized}")
        return standardized

    logger.warning(
        f"⚠️ [PHONE-UTILS-DA] Invalid phone format (length: {len(digits_only)}): {phone_str}"
    )
    return None
