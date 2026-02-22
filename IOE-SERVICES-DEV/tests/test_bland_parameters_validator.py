"""
Unit tests for BlandParametersValidator

Tests comprehensive validation of Bland AI parameters including:
- Required parameter validation (task OR pathway_id)
- Forbidden parameter detection (phone_number)
- Deprecated field name normalization (webhook, voice)
- Unknown parameter handling (future additions)
- NULL/empty configuration handling
- All 40+ known parameters

BusinessCaseID: BC-109

Author: AI-POD Team - Data Science
Created: 2025-12-03
"""

import pytest
from af_code.shared.bland_parameters_validator import (
    BlandParametersValidator,
    ValidationResult,
)


class TestBlandParametersValidator:
    """Test suite for BlandParametersValidator"""

    def setup_method(self):
        """Setup validator instance for each test"""
        self.validator = BlandParametersValidator()

    # ========================================================================
    # Test 1: Valid Configuration with pathway_id
    # ========================================================================
    def test_valid_configuration_with_pathway_id(self):
        """Test validation passes with valid pathway_id configuration"""
        params = {
            "pathway_id": "partner-wellness-pathway-123",
            "voice": "maya",
            "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
            "max_duration": "300",
            "record": True,
        }

        result = self.validator.validate(params, "Test Campaign", strict=True)

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert "pathway_id" in result.normalized_params
        assert result.normalized_params["pathway_id"] == "partner-wellness-pathway-123"

    # ========================================================================
    # Test 2: Valid Configuration with task
    # ========================================================================
    def test_valid_configuration_with_task(self):
        """Test validation passes with valid task configuration"""
        params = {
            "task": "Call member to schedule wellness check appointment",
            "voice": "maya",
            "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
            "language": "en",
        }

        result = self.validator.validate(params, "Test Campaign", strict=True)

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert "task" in result.normalized_params

    # ========================================================================
    # Test 3: Missing Required Parameters (neither task nor pathway_id)
    # ========================================================================
    def test_missing_required_parameters(self):
        """Test validation fails when both task and pathway_id are missing"""
        params = {
            "voice": "maya",
            "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
            "record": True,
        }

        result = self.validator.validate(params, "Test Campaign", strict=True)

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("task" in error and "pathway_id" in error for error in result.errors)

    # ========================================================================
    # Test 4: Forbidden Parameter (phone_number in global)
    # ========================================================================
    def test_forbidden_parameter_phone_number(self):
        """Test validation fails when phone_number is in global config"""
        params = {
            "pathway_id": "partner-wellness-pathway-123",
            "phone_number": "+15551234567",  # FORBIDDEN in global
            "voice": "maya",
        }

        result = self.validator.validate(params, "Test Campaign", strict=True)

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("phone_number" in error and "Forbidden" in error for error in result.errors)

    # ========================================================================
    # Test 5: Deprecated Field Name - webhook
    # ========================================================================
    def test_deprecated_field_webhook(self):
        """Test deprecated 'webhook' field is normalized to 'webhook_url'"""
        params = {
            "pathway_id": "partner-wellness-pathway-123",
            "webhook": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",  # Old name
            "voice": "maya",
        }

        result = self.validator.validate(params, "Test Campaign", strict=True)

        assert result.is_valid is True
        assert "webhook_url" in result.normalized_params
        assert "webhook" not in result.normalized_params
        assert "webhook" in result.deprecated_fields
        assert len(result.warnings) > 0

    # ========================================================================
    # Test 6: Deprecated Field Name - voice
    # ========================================================================
    def test_deprecated_field_voice(self):
        """Test deprecated 'voice' field is normalized to 'voice_id'"""
        params = {
            "pathway_id": "partner-wellness-pathway-123",
            "voice": "maya",  # Old name
            "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
        }

        result = self.validator.validate(params, "Test Campaign", strict=True)

        assert result.is_valid is True
        assert "voice_id" in result.normalized_params
        assert result.normalized_params["voice_id"] == "maya"
        assert "voice" not in result.normalized_params
        assert "voice" in result.deprecated_fields

    # ========================================================================
    # Test 7: Multiple Deprecated Fields
    # ========================================================================
    def test_multiple_deprecated_fields(self):
        """Test multiple deprecated fields are normalized with warnings"""
        params = {
            "pathway_id": "partner-wellness-pathway-123",
            "webhook": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
            "voice": "maya",
        }

        result = self.validator.validate(params, "Test Campaign", strict=True)

        assert result.is_valid is True
        assert len(result.deprecated_fields) == 2
        assert "webhook" in result.deprecated_fields
        assert "voice" in result.deprecated_fields
        assert "webhook_url" in result.normalized_params
        assert "voice_id" in result.normalized_params

    # ========================================================================
    # Test 8: NULL Configuration
    # ========================================================================
    def test_null_configuration(self):
        """Test validation fails for NULL configuration"""
        result = self.validator.validate(None, "Test Campaign", strict=True)

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("NULL or empty" in error for error in result.errors)

    # ========================================================================
    # Test 9: Empty Configuration
    # ========================================================================
    def test_empty_configuration(self):
        """Test validation fails for empty dict configuration"""
        result = self.validator.validate({}, "Test Campaign", strict=True)

        assert result.is_valid is False
        assert len(result.errors) > 0

    # ========================================================================
    # Test 10: Unknown Parameter (Future Addition)
    # ========================================================================
    def test_unknown_parameter_future_feature(self):
        """Test unknown parameters pass through with info messages"""
        params = {
            "pathway_id": "partner-wellness-pathway-123",
            "voice": "maya",
            "new_ai_feature_2026": True,  # Unknown parameter
            "experimental_setting": "value",  # Another unknown
        }

        result = self.validator.validate(params, "Test Campaign", strict=True)

        assert result.is_valid is True  # Unknown params don't fail validation
        assert len(result.unknown_fields) == 2
        assert "new_ai_feature_2026" in result.unknown_fields
        assert "experimental_setting" in result.unknown_fields
        assert len(result.info_messages) > 0

    # ========================================================================
    # Test 11: All Known Optional Parameters
    # ========================================================================
    def test_all_known_optional_parameters(self):
        """Test validation with all 40+ known optional parameters"""
        params = {
            "pathway_id": "partner-wellness-pathway-123",
            # Voice & Model
            "voice": "maya",
            "model": "turbo",
            "language": "en",
            "temperature": 0.7,
            # Call Behavior
            "wait_for_greeting": True,
            "record": True,
            "answered_by_enabled": True,
            "voicemail_action": "hangup",
            "voicemail_message": "Please call back",
            # Audio Settings
            "noise_cancellation": True,
            "interruption_threshold": 100,
            "block_interruptions": False,
            "background_track": "office",
            # Call Limits & Timing
            "max_duration": "300",
            "start_time": "2025-12-03T10:00:00Z",
            "timezone": "America/New_York",
            # Phone & Communication
            "from": "+15551234567",
            "local_dialing": True,
            # Webhooks & Events
            "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
            "webhook_events": ["call_started", "call_ended"],
            # Data & Metadata
            "metadata": {"campaign_type": "Partner"},
            "request_data": {"member_name": "John Doe"},
            "dynamic_data": [{"key": "value"}],
            # Advanced Features
            "tools": ["tool-id-123"],
            "pronunciation_guide": [{"word": "IOE", "pronunciation": "I-O-E"}],
            "citation_schema_ids": ["schema-123"],
            "persona_id": "persona-456",
            "analysis_schema": {"sentiment": True},
            # Legacy/Internal
            "pathway_version": "1.0.2",
            "endpoint": "https://custom-endpoint.com",
            "keywords": ["wellness", "check"],
        }

        result = self.validator.validate(params, "Test Campaign", strict=True)

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.normalized_params) >= 30  # Should have many params

    # ========================================================================
    # Test 12: Non-Strict Mode with Missing Required
    # ========================================================================
    def test_non_strict_mode_missing_required(self):
        """Test non-strict mode logs warnings instead of errors for missing required"""
        params = {
            "voice": "maya",
            "record": True,
        }

        result = self.validator.validate(params, "Test Campaign", strict=False)

        assert result.is_valid is True  # Non-strict allows missing required
        assert len(result.warnings) > 0
        assert any("task" in warning or "pathway_id" in warning for warning in result.warnings)

    # ========================================================================
    # Test 13: Normalize Field Names Method
    # ========================================================================
    def test_normalize_field_names_method(self):
        """Test normalize_field_names method directly"""
        params = {
            "pathway_id": "abc",
            "webhook": "https://example.com",
            "voice": "maya",
            "record": True,
        }

        normalized, deprecated = self.validator.normalize_field_names(params)

        assert "webhook_url" in normalized
        assert "voice_id" in normalized
        assert "webhook" not in normalized
        assert "voice" not in normalized
        assert len(deprecated) == 2
        assert "webhook" in deprecated
        assert "voice" in deprecated

    # ========================================================================
    # Test 14: Check Forbidden Parameters Method
    # ========================================================================
    def test_check_forbidden_parameters_method(self):
        """Test check_forbidden_parameters method directly"""
        params = {
            "pathway_id": "abc",
            "phone_number": "+15551234567",
            "voice": "maya",
        }

        forbidden = self.validator.check_forbidden_parameters(params)

        assert len(forbidden) == 1
        assert "phone_number" in forbidden

    # ========================================================================
    # Test 15: Check Required Parameters Method
    # ========================================================================
    def test_check_required_parameters_method(self):
        """Test check_required_parameters method directly"""
        # Missing both task and pathway_id
        params_missing = {"voice": "maya", "record": True}
        missing = self.validator.check_required_parameters(params_missing)
        assert missing is True

        # Has pathway_id
        params_has_pathway = {"pathway_id": "abc", "voice": "maya"}
        missing = self.validator.check_required_parameters(params_has_pathway)
        assert missing is False

        # Has task
        params_has_task = {"task": "Call member", "voice": "maya"}
        missing = self.validator.check_required_parameters(params_has_task)
        assert missing is False

    # ========================================================================
    # Test 16: Identify Unknown Parameters Method
    # ========================================================================
    def test_identify_unknown_parameters_method(self):
        """Test identify_unknown_parameters method directly"""
        params = {
            "pathway_id": "abc",
            "voice": "maya",
            "unknown_param_1": "value1",
            "future_feature": True,
        }

        unknown = self.validator.identify_unknown_parameters(params)

        assert len(unknown) == 2
        assert "unknown_param_1" in unknown
        assert "future_feature" in unknown

    # ========================================================================
    # Test 17: Get Parameter Metadata Method
    # ========================================================================
    def test_get_parameter_metadata_method(self):
        """Test get_parameter_metadata method returns correct structure"""
        metadata = self.validator.get_parameter_metadata()

        assert "required_one_of" in metadata
        assert "forbidden" in metadata
        assert "optional" in metadata
        assert "deprecated_mappings" in metadata
        assert "total_known" in metadata

        assert "task" in metadata["required_one_of"]
        assert "pathway_id" in metadata["required_one_of"]
        assert "phone_number" in metadata["forbidden"]
        assert len(metadata["optional"]) >= 30  # 33 optional parameters currently

    # ========================================================================
    # Test 18: Get Example Configuration Method
    # ========================================================================
    def test_get_example_configuration_method(self):
        """Test get_example_configuration returns valid example"""
        example = BlandParametersValidator.get_example_configuration()

        assert isinstance(example, dict)
        assert "pathway_id" in example
        assert "voice_id" in example
        assert "webhook_url" in example
        assert len(example) >= 15

    # ========================================================================
    # Test 19: Both pathway_id and task Present
    # ========================================================================
    def test_both_pathway_id_and_task_present(self):
        """Test validation passes when BOTH task and pathway_id are present"""
        params = {
            "task": "Call member",
            "pathway_id": "backup-pathway-123",
            "voice": "maya",
        }

        result = self.validator.validate(params, "Test Campaign", strict=True)

        assert result.is_valid is True
        assert "task" in result.normalized_params
        assert "pathway_id" in result.normalized_params

    # ========================================================================
    # Test 20: Validation with Real-World Partner Campaign Config
    # ========================================================================
    def test_real_world_partner_campaign_config(self):
        """Test validation with realistic Partner campaign configuration"""
        params = {
            "pathway_id": "partner-wellness-pathway-abc123",
            "voice": "maya",
            "webhook": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
            "max_duration": "300",
            "wait_for_greeting": True,
            "record": True,
            "answered_by_enabled": True,
            "noise_cancellation": True,
            "interruption_threshold": 100,
            "block_interruptions": False,
            "model": "turbo",
            "temperature": 0.7,
            "language": "en",
            "background_track": "office",
            "from": "+15551234567",
            "timezone": "America/New_York",
        }

        result = self.validator.validate(params, "Partner Wellness Campaign", strict=True)

        assert result.is_valid is True
        assert len(result.deprecated_fields) == 2  # webhook and voice
        assert "webhook_url" in result.normalized_params
        assert "voice_id" in result.normalized_params
        assert len(result.warnings) > 0  # Deprecation warnings


# ========================================================================
# Integration Tests with Batch Orchestrator Pattern
# ========================================================================
class TestValidatorIntegration:
    """Integration tests simulating batch orchestrator usage"""

    def setup_method(self):
        """Setup validator instance"""
        self.validator = BlandParametersValidator()

    def test_orchestrator_pattern_valid_config(self):
        """Test validator with batch orchestrator pattern (valid config)"""
        campaign_bland_params = {
            "pathway_id": "partner-wellness-pathway-123",
            "voice_id": "maya",
            "webhook_url": "https://ioe-function.azurewebsites.net/api/bland_ai_webhook",
            "max_duration": "300",
            "record": True,
        }

        # Simulate orchestrator validation
        result = self.validator.validate(campaign_bland_params, "Fall Prevention 2024", strict=True)

        if not result.is_valid:
            error_msg = "Invalid Bland AI configuration:\n"
            for error in result.errors:
                error_msg += f"  - {error}\n"
            raise ValueError(error_msg)

        # Extract parameters like orchestrator does
        bland_params = result.normalized_params
        pathway_id = bland_params.get("pathway_id") or bland_params.get("task")
        voice_id = bland_params.get("voice_id") or bland_params.get("voice")

        assert pathway_id == "partner-wellness-pathway-123"
        assert voice_id == "maya"

    def test_orchestrator_pattern_null_fallback_to_env(self):
        """Test validator with NULL config that falls back to environment vars"""
        # Simulate NULL bland_parameters_global
        campaign_bland_params = None

        # Orchestrator would construct from env vars
        env_fallback = {
            "pathway_id": "env-fallback-pathway",
            "voice_id": "env-fallback-voice",
            "webhook_url": "https://env-webhook.com",
            "max_duration": "300",
        }

        # Validate env fallback config
        result = self.validator.validate(env_fallback, "Campaign with NULL config", strict=True)

        assert result.is_valid is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
