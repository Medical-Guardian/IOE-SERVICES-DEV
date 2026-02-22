"""
Extensible Bland AI Parameters Validator

This module provides validation for Bland AI configuration parameters from the
bland_parameters_global JSON column in campaign_call_configs_enhanced table.

Design Goals:
1. Support 18+ known parameters without hardcoding validation for each
2. Allow future parameter additions without code changes
3. Classify REQUIRED vs OPTIONAL parameters
4. Normalize deprecated field names with warnings
5. Provide clear, actionable error messages

BusinessCaseID: BC-109

Author: AI-POD Team - Data Science
Created: 2025-12-03
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """
    Result of Bland AI parameters validation

    Attributes:
        is_valid: True if all required parameters present and valid
        normalized_params: Parameters with deprecated field names normalized
        errors: List of validation errors (missing required params, etc.)
        warnings: List of warnings (deprecated field names, etc.)
        info_messages: List of informational messages (unknown params, etc.)
        missing_required: List of required parameter names that are missing
        deprecated_fields: List of deprecated field names found
        unknown_fields: List of unknown parameter names (potential future additions)
    """

    is_valid: bool
    normalized_params: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info_messages: List[str] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)
    deprecated_fields: List[str] = field(default_factory=list)
    unknown_fields: List[str] = field(default_factory=list)


class BlandParametersValidator:
    """
    Extensible validator for Bland AI parameters from bland_parameters_global JSON

    This validator supports current and future Bland AI parameters with minimal code changes.
    It validates required parameters, normalizes deprecated field names, and provides
    clear error messages for configuration issues.

    Example Usage:
        validator = BlandParametersValidator()
        result = validator.validate(
            bland_params={'pathway_id': 'abc', 'voice_id': 'maya', 'webhook_url': 'https://...'},
            campaign_name='Fall Prevention 2024',
            strict=True
        )

        if not result.is_valid:
            raise ValueError(f"Invalid configuration: {result.errors}")

        # Use normalized parameters
        pathway_id = result.normalized_params['pathway_id']
    """

    # Required parameters - must include at least one of these
    # Per Bland AI API specification: task OR pathway_id required
    REQUIRED_PARAMS_ONE_OF: Set[str] = {"task", "pathway_id"}

    # Forbidden parameters - cannot be in global config
    # These must be in call_objects, not global
    FORBIDDEN_PARAMS: Set[str] = {"phone_number"}

    # Known optional parameters (complete list from Bland AI API)
    # All parameters are optional except task OR pathway_id (one required)
    KNOWN_OPTIONAL_PARAMS: Set[str] = {
        # Voice & Model Configuration
        "voice",  # Voice ID (e.g., "maya")
        "voice_id",  # Alternative field name for voice (backward compatibility)
        "model",  # "base" or "turbo"
        "language",  # Language code (en, es, fr, etc.)
        "temperature",  # Model creativity (default 0.7)
        # Call Behavior
        "wait_for_greeting",  # Wait for recipient to speak first
        "record",  # Record the call
        "answered_by_enabled",  # Detect answering machine
        "voicemail_action",  # Action on voicemail
        "voicemail_message",  # Voicemail text
        # Audio Settings
        "noise_cancellation",  # Enable noise cancellation
        "interruption_threshold",  # Interruption sensitivity (ms)
        "block_interruptions",  # Block all interruptions
        "background_track",  # Background audio
        # Call Limits & Timing
        "max_duration",  # Max call length (minutes)
        "start_time",  # Scheduled start time
        "timezone",  # Timezone for the call
        # Phone & Communication
        "from",  # Caller ID number (E.164 format)
        "local_dialing",  # Use local numbers
        # Webhooks & Events
        "webhook",  # Post-call webhook URL
        "webhook_url",  # Alternative field name for webhook (backward compatibility)
        "webhook_events",  # Events to stream
        # Data & Metadata
        "metadata",  # Custom metadata object
        "request_data",  # Custom key-value data
        "dynamic_data",  # External API data integration
        # Advanced Features
        "tools",  # Array of tool IDs
        "pronunciation_guide",  # Pronunciation instructions
        "citation_schema_ids",  # Citation schemas
        "persona_id",  # Persona configuration
        "analysis_schema",  # Analysis schema configuration
        # Legacy/Internal (not commonly used)
        "pathway_version",  # Version of the pathway
        "endpoint",  # Custom endpoint URL
        "keywords",  # Keywords for the call
    }

    # Deprecated field name mappings (old_name -> new_name)
    # Used for backward compatibility with legacy configurations
    DEPRECATED_FIELD_MAPPINGS: Dict[str, str] = {
        "webhook": "webhook_url",  # Old webhook field → new webhook_url field
        "voice": "voice_id",  # Old voice field → new voice_id field
    }

    def validate(
        self,
        bland_params: Optional[Dict[str, Any]],
        campaign_name: str,
        strict: bool = True,
    ) -> ValidationResult:
        """
        Validate Bland AI parameters from bland_parameters_global JSON

        Args:
            bland_params: Dictionary of Bland AI parameters from database
            campaign_name: Campaign name for error messages
            strict: If True, fail on missing required parameters. If False, log warnings only.

        Returns:
            ValidationResult with validation status, normalized params, and messages

        Example:
            result = validator.validate(
                {'pathway_id': 'abc', 'voice': 'maya'},  # Note: deprecated 'voice' field
                'Fall Prevention 2024'
            )
            # result.is_valid = True (has required params)
            # result.normalized_params = {'pathway_id': 'abc', 'voice_id': 'maya'}
            # result.deprecated_fields = ['voice']
            # result.warnings = ['Deprecated field "voice" → use "voice_id"']
        """
        logger.info(
            f"🔍 [BLAND-PARAMS-VALIDATOR] Validating parameters for campaign: {campaign_name}"
        )

        # Handle NULL or empty configuration
        if not bland_params:
            error_msg = (
                f"bland_parameters_global is NULL or empty for campaign '{campaign_name}'. "
                "Database configuration is required. Update campaign_call_configs_enhanced table."
            )
            logger.error(f"🚨 [BLAND-PARAMS-VALIDATOR] {error_msg}")
            return ValidationResult(
                is_valid=False,
                normalized_params={},
                errors=[error_msg],
                missing_required=list(self.REQUIRED_PARAMS_ONE_OF),
            )

        # Step 1: Normalize deprecated field names
        normalized_params, deprecated_fields = self.normalize_field_names(bland_params)

        # Step 2: Check forbidden parameters
        forbidden_found = self.check_forbidden_parameters(normalized_params)

        # Step 3: Check required parameters (task OR pathway_id)
        missing_required = self.check_required_parameters(normalized_params)

        # Step 4: Identify unknown parameters (potential future additions)
        unknown_fields = self.identify_unknown_parameters(normalized_params)

        # Step 5: Build validation result
        errors = []
        warnings = []
        info_messages = []

        # Add errors for forbidden parameters
        if forbidden_found:
            for param in forbidden_found:
                errors.append(
                    f"Forbidden parameter '{param}' found in bland_parameters_global - "
                    f"this parameter must be in call_objects, not global config"
                )

        # Add errors for missing required parameters (task OR pathway_id)
        if missing_required:
            if strict:
                errors.append(
                    f"Must include at least one of: {', '.join(self.REQUIRED_PARAMS_ONE_OF)}. "
                    f"Bland AI requires either 'task' or 'pathway_id' in global configuration."
                )
            else:
                warnings.append(
                    "Missing required parameter (task OR pathway_id) but continuing in non-strict mode"
                )

        # Add warnings for deprecated field names
        if deprecated_fields:
            warnings.append(f"Deprecated field names detected in campaign '{campaign_name}'")
            for old_field in deprecated_fields:
                new_field = self.DEPRECATED_FIELD_MAPPINGS.get(old_field)
                warnings.append(f"Field '{old_field}' is deprecated → use '{new_field}' instead")
            warnings.append(
                "Update bland_parameters_global in campaign_call_configs_enhanced to use new field names"
            )

        # Add info messages for unknown parameters (future additions)
        if unknown_fields:
            for unknown_field in unknown_fields:
                info_messages.append(
                    f"Unknown parameter '{unknown_field}' found in bland_parameters_global - "
                    "will be passed to Bland AI (may be future feature)"
                )

        # Determine if validation passed
        is_valid = len(errors) == 0

        # Log validation summary
        if is_valid:
            logger.info(
                f"✅ [BLAND-PARAMS-VALIDATOR] Validation passed for campaign: {campaign_name}"
            )
            logger.info(
                f"   📊 Parameters: {len(normalized_params)} total, "
                f"has required (task OR pathway_id), "
                f"{len(deprecated_fields)} deprecated, "
                f"{len(unknown_fields)} unknown"
            )
        else:
            logger.error(
                f"❌ [BLAND-PARAMS-VALIDATOR] Validation failed for campaign: {campaign_name}"
            )
            logger.error(f"   ❌ Errors: {len(errors)}")
            for error in errors:
                logger.error(f"      - {error}")

        # Log warnings
        for warning in warnings:
            logger.warning(f"⚠️ [BLAND-PARAMS-VALIDATOR] {warning}")

        # Log info messages
        for info in info_messages:
            logger.info(f"ℹ️ [BLAND-PARAMS-VALIDATOR] {info}")

        return ValidationResult(
            is_valid=is_valid,
            normalized_params=normalized_params,
            errors=errors,
            warnings=warnings,
            info_messages=info_messages,
            missing_required=missing_required,
            deprecated_fields=deprecated_fields,
            unknown_fields=unknown_fields,
        )

    def normalize_field_names(
        self, bland_params: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Normalize deprecated field names to current standard names

        Converts old field names to new names while preserving all other fields.
        This maintains backward compatibility with legacy configurations.

        Args:
            bland_params: Original parameters dictionary

        Returns:
            Tuple of (normalized_params, deprecated_fields_found)

        Example:
            params = {'pathway_id': 'abc', 'webhook': 'https://...', 'voice': 'maya'}
            normalized, deprecated = validator.normalize_field_names(params)
            # normalized = {'pathway_id': 'abc', 'webhook_url': 'https://...', 'voice_id': 'maya'}
            # deprecated = ['webhook', 'voice']
        """
        normalized = bland_params.copy()
        deprecated_found = []

        for old_field, new_field in self.DEPRECATED_FIELD_MAPPINGS.items():
            if old_field in normalized:
                # Only normalize if new field doesn't already exist
                if new_field not in normalized:
                    normalized[new_field] = normalized[old_field]
                    deprecated_found.append(old_field)
                    logger.debug(
                        f"🔄 [BLAND-PARAMS-VALIDATOR] Normalized '{old_field}' → '{new_field}'"
                    )
                # Remove old field after normalization
                del normalized[old_field]

        return normalized, deprecated_found

    def check_forbidden_parameters(self, bland_params: Dict[str, Any]) -> List[str]:
        """
        Check if any forbidden parameters are present in global config

        Per Bland AI specification, certain parameters (e.g., phone_number)
        MUST be in call_objects, not global configuration.

        Args:
            bland_params: Parameters dictionary (should be normalized first)

        Returns:
            List of forbidden parameter names found (empty if none)

        Example:
            params = {'pathway_id': 'abc', 'phone_number': '+15551234567'}
            forbidden = validator.check_forbidden_parameters(params)
            # forbidden = ['phone_number']
        """
        forbidden_found = []
        for forbidden_param in self.FORBIDDEN_PARAMS:
            if forbidden_param in bland_params:
                forbidden_found.append(forbidden_param)

        return forbidden_found

    def check_required_parameters(self, bland_params: Dict[str, Any]) -> bool:
        """
        Check if required parameters are present (task OR pathway_id)

        Per Bland AI specification: Must include at least ONE of: task OR pathway_id

        Args:
            bland_params: Parameters dictionary (should be normalized first)

        Returns:
            True if missing required parameters, False if at least one present

        Example:
            params = {'voice_id': 'maya', 'webhook_url': 'https://...'}  # Missing both task and pathway_id
            missing = validator.check_required_parameters(params)
            # missing = True

            params = {'pathway_id': 'abc', 'voice_id': 'maya'}  # Has pathway_id
            missing = validator.check_required_parameters(params)
            # missing = False
        """
        # Check if at least ONE of the required parameters is present
        has_at_least_one = any(
            param in bland_params and bland_params[param] for param in self.REQUIRED_PARAMS_ONE_OF
        )

        return not has_at_least_one  # True if missing (none present), False if at least one present

    def identify_unknown_parameters(self, bland_params: Dict[str, Any]) -> List[str]:
        """
        Identify parameters that are not in known required or optional sets

        These could be future parameters added to Bland AI API. The validator
        will pass them through but log them for visibility.

        Args:
            bland_params: Parameters dictionary

        Returns:
            List of unknown parameter names

        Example:
            params = {'pathway_id': 'abc', 'voice_id': 'maya', 'new_feature_2025': True}
            unknown = validator.identify_unknown_parameters(params)
            # unknown = ['new_feature_2025']
        """
        all_known_params = self.REQUIRED_PARAMS_ONE_OF.union(self.KNOWN_OPTIONAL_PARAMS)
        unknown = []

        for param_name in bland_params.keys():
            if param_name not in all_known_params:
                unknown.append(param_name)

        return unknown

    def get_parameter_metadata(self) -> Dict[str, Any]:
        """
        Get metadata about all known Bland AI parameters

        Useful for documentation, debugging, and potential UI display.

        Returns:
            Dictionary with parameter classifications and mappings

        Example:
            metadata = validator.get_parameter_metadata()
            # {
            #     'required_one_of': ['task', 'pathway_id'],
            #     'forbidden': ['phone_number'],
            #     'optional': ['voice', 'model', 'language', ...],
            #     'deprecated_mappings': {'webhook': 'webhook_url', 'voice': 'voice_id'},
            #     'total_known': 40+
            # }
        """
        return {
            "required_one_of": sorted(list(self.REQUIRED_PARAMS_ONE_OF)),
            "forbidden": sorted(list(self.FORBIDDEN_PARAMS)),
            "optional": sorted(list(self.KNOWN_OPTIONAL_PARAMS)),
            "deprecated_mappings": self.DEPRECATED_FIELD_MAPPINGS,
            "total_known": len(self.REQUIRED_PARAMS_ONE_OF) + len(self.KNOWN_OPTIONAL_PARAMS),
        }

    @staticmethod
    def get_example_configuration() -> Dict[str, Any]:
        """
        Get an example valid bland_parameters_global configuration

        Useful for documentation and as a template for new campaigns.

        Returns:
            Dictionary with example configuration including all common parameters

        Example:
            example = BlandParametersValidator.get_example_configuration()
            # Returns complete example with pathway_id, voice_id, webhook_url, etc.
        """
        return {
            "pathway_id": "partner-wellness-pathway-abc123",
            "pathway_version": "1.0.2",
            "voice_id": "maya",
            "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
            "max_duration": "300",
            "wait_for_greeting": True,
            "record": True,
            "answered_by_enabled": True,
            "noise_cancellation": True,
            "interruption_threshold": 100,
            "block_interruptions": False,
            "model": "enhanced",
            "temperature": 0.7,
            "language": "en",
            "background_track": "office",
            "from": "+15551234567",
            "timezone": "America/New_York",
        }
