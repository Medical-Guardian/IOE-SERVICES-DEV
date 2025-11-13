"""
Language Code Mapping Utility

This module provides conversion between ISO 639-3 (3-letter) language codes
and the 2-letter codes used in the IOE platform for language preference handling.

BusinessCaseID: BC-109

Author: AI-POD Team
Created: 2025-11-13
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ISO 639-3 (3-letter) to 2-letter code mapping
# Only English and Spanish are explicitly mapped, all others become 'Other'
ISO_639_3_TO_2_LETTER = {
    # English variants
    "eng": "EN",
    "en": "EN",  # Support both 2-letter and 3-letter
    # Spanish variants
    "spa": "ES",
    "es": "ES",  # Support both 2-letter and 3-letter
}

# Valid output values (for backward compatibility)
VALID_LANGUAGE_CODES = ["EN", "ES", "Other"]


def map_language_code(language_input: Optional[str]) -> str:
    """
    Convert language input to standardized 2-letter code or 'Other'.

    This function handles multiple input formats:
    - ISO 639-3 codes (3-letter): 'eng', 'spa', 'som', 'swa', etc.
    - ISO 639-1 codes (2-letter): 'en', 'es', 'so', 'sw', etc.
    - Existing platform codes: 'EN', 'ES', 'Other'
    - None or empty strings

    Mapping Logic:
    - 'eng' or 'en' (any case) → 'EN'
    - 'spa' or 'es' (any case) → 'ES'
    - Any other valid string → 'Other'
    - None or empty → 'EN' (default)

    BusinessCaseID: BC-109

    Args:
        language_input: Language code from CSV or other source

    Returns:
        str: One of 'EN', 'ES', or 'Other'

    Examples:
        >>> map_language_code('eng')
        'EN'
        >>> map_language_code('spa')
        'ES'
        >>> map_language_code('som')
        'Other'
        >>> map_language_code('EN')
        'EN'
        >>> map_language_code(None)
        'EN'
        >>> map_language_code('')
        'EN'
    """
    # Handle None or empty string - default to English
    if not language_input or language_input.strip() == "":
        logger.debug("Empty language input, defaulting to 'EN'")
        return "EN"

    # Clean input: strip whitespace and convert to lowercase for comparison
    cleaned_input = language_input.strip().lower()

    # Check if already in valid format (EN, ES, Other) - case insensitive
    if cleaned_input in ["en", "es", "other"]:
        result = cleaned_input.upper() if cleaned_input in ["en", "es"] else "Other"
        logger.debug(f"Input '{language_input}' already in valid format, returning '{result}'")
        return result

    # Check ISO mapping
    if cleaned_input in ISO_639_3_TO_2_LETTER:
        result = ISO_639_3_TO_2_LETTER[cleaned_input]
        logger.debug(f"Mapped ISO code '{language_input}' to '{result}'")
        return result

    # Any other input becomes 'Other'
    logger.debug(f"Language '{language_input}' not explicitly mapped, returning 'Other'")
    return "Other"


def validate_language_code(language_code: str) -> bool:
    """
    Validate that a language code is one of the accepted output values.

    This is used for validation AFTER mapping has occurred.

    BusinessCaseID: BC-109

    Args:
        language_code: Language code to validate

    Returns:
        bool: True if valid, False otherwise

    Examples:
        >>> validate_language_code('EN')
        True
        >>> validate_language_code('ES')
        True
        >>> validate_language_code('Other')
        True
        >>> validate_language_code('FR')
        False
    """
    return language_code in VALID_LANGUAGE_CODES


def get_language_display_name(language_code: str) -> str:
    """
    Get human-readable display name for language code.

    BusinessCaseID: BC-109

    Args:
        language_code: 2-letter code ('EN', 'ES', 'Other')

    Returns:
        str: Display name for the language

    Examples:
        >>> get_language_display_name('EN')
        'English'
        >>> get_language_display_name('ES')
        'Spanish'
        >>> get_language_display_name('Other')
        'Other Language'
    """
    display_names = {"EN": "English", "ES": "Spanish", "Other": "Other Language"}
    return display_names.get(language_code, "Unknown")


# For backward compatibility and testing
def is_supported_language(language_code: str) -> bool:
    """
    Check if language is explicitly supported (EN or ES).

    BusinessCaseID: BC-109

    Args:
        language_code: Language code to check

    Returns:
        bool: True if EN or ES, False if Other

    Examples:
        >>> is_supported_language('EN')
        True
        >>> is_supported_language('ES')
        True
        >>> is_supported_language('Other')
        False
    """
    return language_code in ["EN", "ES"]
