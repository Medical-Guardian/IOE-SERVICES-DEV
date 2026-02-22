"""
Filename validation utilities for Azure Function blob processors.

Provides strict pattern matching with calendar date validation for:
- Device Activation files (Medicaid and DTCMA campaigns only)
- DTC Wellness files (snake_case format with legacy support)

BusinessCaseID: BC-DA-002 (File Processing Utils)
"""

import re
from datetime import datetime
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


def validate_device_activation_filename(
    filename: str,
) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    Validate Device Activation filename (Medicaid or DTCMA campaigns only).

    Expected patterns:
    - MedicalGuardian_DeviceActivationMedicaid_YYYYMMDD_DELTA.csv
    - MedicalGuardian_DeviceActivationDTCMA_YYYYMMDD_DELTA.csv

    YYYYMMDD must be a valid calendar date where:
    - YYYY = 4-digit year (e.g., 2026)
    - MM = 2-digit month (01-12)
    - DD = 2-digit day (01-31, validated for the specific month/year)
    - Invalid dates like 20251340 (month 13), 20250230 (Feb 30), or 20250431 (Apr 31) are REJECTED

    Args:
        filename: Filename to validate (without path)

    Returns:
        Tuple of (is_valid, error_message, extracted_date_str, campaign_type)
        - is_valid: True if filename matches pattern and date is valid
        - error_message: Empty string if valid, descriptive error if invalid
        - extracted_date_str: YYYYMMDD string if valid, None if invalid
        - campaign_type: "Medicaid" or "DTCMA" if valid, None if invalid

    Examples:
        >>> validate_device_activation_filename("MedicalGuardian_DeviceActivationMedicaid_20260105_DELTA.csv")
        (True, "", "20260105", "Medicaid")

        >>> validate_device_activation_filename("MedicalGuardian_DeviceActivationDTCMA_20260105_DELTA.csv")
        (True, "", "20260105", "DTCMA")

        >>> validate_device_activation_filename("MedicalGuardian_DeviceActivationMedicaid_20250230_DELTA.csv")
        (False, "Invalid date in filename: 20250230 (day is out of range for month)", None, None)

        >>> validate_device_activation_filename("MedicalGuardian_DeviceActivationMedicaid_20251340_DELTA.csv")
        (False, "Invalid date in filename: 20251340 (month must be in 1..12)", None, None)

        >>> validate_device_activation_filename("MedicalGuardian_DeviceActivation_20260105_DELTA.csv")
        (False, "Filename must contain 'Medicaid' or 'DTCMA' suffix", None, None)

        >>> validate_device_activation_filename("MedicalGuardian_DeviceActivationOther_20260105_DELTA.csv")
        (False, "Filename must contain 'Medicaid' or 'DTCMA' suffix", None, None)
    """
    # Define ONLY allowed patterns (Medicaid and DTCMA)
    patterns = {
        "Medicaid": r"^MedicalGuardian_DeviceActivationMedicaid_(\d{8})_DELTA\.csv$",
        "DTCMA": r"^MedicalGuardian_DeviceActivationDTCMA_(\d{8})_DELTA\.csv$",
    }

    # Try each pattern
    for campaign_type, pattern in patterns.items():
        match = re.match(pattern, filename)
        if match:
            # Extract date string (YYYYMMDD)
            date_str = match.group(1)

            # Validate it's a real calendar date
            try:
                datetime.strptime(date_str, "%Y%m%d")
                logger.info(f"✅ [VALIDATOR] Date validation passed: {date_str} ({campaign_type})")
                return (True, "", date_str, campaign_type)
            except ValueError as e:
                logger.warning(f"❌ [VALIDATOR] Invalid date: {date_str} - {str(e)}")
                return (
                    False,
                    f"Invalid date in filename: {date_str} ({str(e)})",
                    None,
                    None,
                )

    # No pattern matched - invalid filename
    logger.warning(f"❌ [VALIDATOR] Filename does not match Medicaid or DTCMA patterns: {filename}")
    return (False, "Filename must contain 'Medicaid' or 'DTCMA' suffix", None, None)


def validate_dtc_wellness_filename(
    filename: str, allow_legacy: bool = True
) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    Validate DTC Wellness filename with calendar date validation.

    Expected patterns:
    - NEW (preferred): medical_guardian_dtc_wellness_YYYYMMDD.csv
    - LEGACY (Phase 1 only): MedicalGuardian_DTCWellness_YYYYMMDD_Delta.csv

    YYYYMMDD must be a valid calendar date where:
    - YYYY = 4-digit year (e.g., 2026)
    - MM = 2-digit month (01-12)
    - DD = 2-digit day (01-31, validated for the specific month/year)
    - Invalid dates like 20261340 (month 13), 20260230 (Feb 30), or 20260431 (Apr 31) are REJECTED

    Args:
        filename: Filename to validate (without path)
        allow_legacy: If True, accepts both NEW and LEGACY patterns. If False, only NEW pattern.

    Returns:
        Tuple of (is_valid, error_message, extracted_date_str, pattern_type)
        - is_valid: True if filename matches pattern and date is valid
        - error_message: Empty string if valid, descriptive error if invalid
        - extracted_date_str: YYYYMMDD string if valid, None if invalid
        - pattern_type: "NEW" or "LEGACY" if valid, None if invalid

    Examples:
        >>> validate_dtc_wellness_filename("medical_guardian_dtc_wellness_20260202.csv")
        (True, "", "20260202", "NEW")

        >>> validate_dtc_wellness_filename("MedicalGuardian_DTCWellness_20260202_Delta.csv")
        (True, "", "20260202", "LEGACY")

        >>> validate_dtc_wellness_filename("medical_guardian_dtc_wellness_20260230.csv")
        (False, "Invalid date in filename: 20260230 (day is out of range for month)", None, None)

        >>> validate_dtc_wellness_filename("medical_guardian_dtc_wellness_20260431.csv")
        (False, "Invalid date in filename: 20260431 (day is out of range for month)", None, None)

        >>> validate_dtc_wellness_filename("medical_guardian_dtc_wellness_20261340.csv")
        (False, "Invalid date in filename: 20261340 (month must be in 1..12)", None, None)

        >>> validate_dtc_wellness_filename("medical_guardian_dtc_wellness_20240229.csv")
        (True, "", "20240229", "NEW")  # 2024 is leap year

        >>> validate_dtc_wellness_filename("medical_guardian_dtc_wellness_20260229.csv")
        (False, "Invalid date in filename: 20260229 (day is out of range for month)", None, None)

        >>> validate_dtc_wellness_filename("Medical_Guardian_DTC_Wellness_20260202.csv")
        (False, "Expected pattern: medical_guardian_dtc_wellness_YYYYMMDD.csv (all lowercase)", None, None)

        >>> validate_dtc_wellness_filename("MedicalGuardian_DTCWellness_20260202_Delta.csv", allow_legacy=False)
        (False, "Legacy pattern no longer accepted. Use: medical_guardian_dtc_wellness_YYYYMMDD.csv", None, None)
    """
    # Define patterns
    new_pattern = r"^medical_guardian_dtc_wellness_(\d{8})\.csv$"
    legacy_pattern = r"^MedicalGuardian_DTCWellness_(\d{8})_Delta\.csv$"

    # Try NEW pattern first (preferred)
    match = re.match(new_pattern, filename)
    if match:
        date_str = match.group(1)

        # Validate calendar date
        try:
            datetime.strptime(date_str, "%Y%m%d")
            logger.info(f"✅ [VALIDATOR] DTC Wellness - NEW pattern validated: {date_str}")
            return (True, "", date_str, "NEW")
        except ValueError as e:
            logger.warning(f"❌ [VALIDATOR] DTC Wellness - Invalid date: {date_str} - {str(e)}")
            return (
                False,
                f"Invalid date in filename: {date_str} ({str(e)})",
                None,
                None,
            )

    # Try LEGACY pattern if allowed
    if allow_legacy:
        match = re.match(legacy_pattern, filename)
        if match:
            date_str = match.group(1)

            # Validate calendar date
            try:
                datetime.strptime(date_str, "%Y%m%d")
                logger.warning(f"⚠️ [VALIDATOR] DTC Wellness - LEGACY pattern detected: {date_str}")
                logger.warning(
                    "   This pattern will be deprecated soon. Use: medical_guardian_dtc_wellness_YYYYMMDD.csv"
                )
                return (True, "", date_str, "LEGACY")
            except ValueError as e:
                logger.warning(
                    f"❌ [VALIDATOR] DTC Wellness - Invalid date in legacy pattern: {date_str} - {str(e)}"
                )
                return (
                    False,
                    f"Invalid date in filename: {date_str} ({str(e)})",
                    None,
                    None,
                )
    else:
        # Check if it matches legacy pattern structure (but reject it)
        if re.match(legacy_pattern, filename):
            logger.warning(f"❌ [VALIDATOR] DTC Wellness - Legacy pattern rejected: {filename}")
            return (
                False,
                "Legacy pattern no longer accepted. Use: medical_guardian_dtc_wellness_YYYYMMDD.csv",
                None,
                None,
            )

    # No pattern matched
    logger.warning(f"❌ [VALIDATOR] DTC Wellness - Invalid filename: {filename}")
    return (
        False,
        "Expected pattern: medical_guardian_dtc_wellness_YYYYMMDD.csv (all lowercase)",
        None,
        None,
    )
