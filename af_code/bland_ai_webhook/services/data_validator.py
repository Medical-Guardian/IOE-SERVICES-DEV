import logging
import re
from typing import Dict, Any
from ..models.validation_result import ValidationResult
from ..services.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class DataValidator:
    """
    Validates incoming webhook payloads to ensure they meet structural and data quality requirements.
    """

    def __init__(self, config_manager: ConfigManager = None):
        """
        Initialize the DataValidator with validation rules and optional configuration.

        Args:
            config_manager: Configuration manager for dynamic rules
        """
        # self.required_fields = {'call_id', 'status', 'metadata'}
        self.required_fields = {"call_id", "status", "metadata", "to"}
        # self.metadata_required_fields = {'attempt_id', 'phone_number'}
        self.metadata_required_fields = {"attempt_id"}
        self.config_manager = config_manager or ConfigManager()
        self.phone_regex = re.compile(r"^\+?[\d\s-]{7,15}$")  # Basic phone number format
        self.max_status_length = int(self.config_manager.get_config("MAX_STATUS_LENGTH", "50"))
        logger.info(
            f"🔍 [DATA-VALIDATOR] Data validator initialized with max status length: {self.max_status_length}"
        )

    def validate_webhook_payload(self, webhook_data: Dict[str, Any]) -> ValidationResult:
        """
        Validate the webhook payload for required fields and data types.

        Args:
            webhook_data: The webhook payload to validate

        Returns:
            ValidationResult: Result object containing validation status and any errors/warnings
        """
        errors = []
        warnings = []

        logger.info("🔍 [DATA-VALIDATOR] Starting webhook payload validation")

        # Check for required top-level fields
        missing_fields = self.required_fields - set(webhook_data.keys())
        if missing_fields:
            errors.append(f"Missing required fields: {', '.join(missing_fields)}")

        # Check for required top-level fields
        to_phone_number = webhook_data.get("to", "")
        if (
            not to_phone_number
            or not isinstance(to_phone_number, str)
            or not self.phone_regex.match(to_phone_number)
        ):
            errors.append("Invalid or missing top-level 'to' phone number (e.g., +1234567890)")

        # Validate metadata structure
        metadata = webhook_data.get("metadata", {})
        if not isinstance(metadata, dict):
            errors.append("Metadata must be a dictionary")
        else:
            missing_metadata_fields = self.metadata_required_fields - set(metadata.keys())
            if missing_metadata_fields:
                errors.append(
                    f"Missing required metadata fields: {', '.join(missing_metadata_fields)}"
                )

        # Validate status
        status_raw = webhook_data.get("status")
        if status_raw is None:
            logger.warning("⚠️ [DATA-VALIDATOR] Status field is None, treating as empty string")
        status = status_raw.lower() if status_raw is not None else ""
        valid_statuses = {"completed", "failed", "in-progress", "cancelled"}
        if status not in valid_statuses:
            warnings.append(
                f"Unknown status '{status}', expected one of {', '.join(valid_statuses)}"
            )
        if len(status) > self.max_status_length:
            errors.append(f"Status exceeds maximum length of {self.max_status_length} characters")

        # Validate call_id
        call_id = webhook_data.get("call_id", "")
        if not call_id or not isinstance(call_id, str) or len(call_id) > 100:
            errors.append("Invalid or missing call_id (max 100 characters)")

        is_valid = len(errors) == 0
        logger.info(
            f"{'✅' if is_valid else '❌'} [DATA-VALIDATOR] Validation {'succeeded' if is_valid else 'failed'}"
        )
        if errors:
            logger.error(f"❌ [DATA-VALIDATOR] Validation errors: {errors}")
        if warnings:
            logger.warning(f"⚠️ [DATA-VALIDATOR] Validation warnings: {warnings}")

        return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)
