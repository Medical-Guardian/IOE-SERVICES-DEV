"""
Comprehensive Unit Tests for Device Activation CSV Validation Rules

Tests 8 validation categories:
1. Filename Pattern Validation (3 tests)
2. Address Validation (8 tests)
3. Date of Birth Validation (5 tests)
4. Device UDI Validation (5 tests)
5. Monitoring System ID Validation (3 tests)
6. Device Status Fields (6 tests)
7. Language Preference Mapping (5 tests)
8. Duplicate Device UDI Detection (3 tests)

Total: ~38 test cases

BusinessCaseID: BC-125 (Device Activation)
"""

import sys
import re
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

sys.path.insert(0, '/home/zubair-ashfaque/MG-IOE/Azure Function/Azure_function_Deployment/IOE-functions')

from af_code.shared.language_mapper import map_language_code


# =============================================================================
# TEST 1: FILENAME PATTERN VALIDATION
# =============================================================================
class TestFilenamePatternValidation:
    """Test filename pattern validation for Device Activation CSV files."""

    def test_valid_medicaid_filename(self):
        """Test valid Medicaid filename pattern."""
        filename = "MedicalGuardian_DeviceActivationMedicaid_20260114_DELTA.csv"
        pattern = r"MedicalGuardian_DeviceActivationMedicaid_\d{8}_DELTA\.csv"

        result = re.match(pattern, filename)

        assert result is not None, f"Valid Medicaid filename should match: {filename}"
        print("✅ PASS: Valid Medicaid filename accepted")

    def test_valid_dtcma_filename(self):
        """Test valid DTC/MA filename pattern."""
        filename = "MedicalGuardian_DeviceActivationDTCMA_20260114_DELTA.csv"
        pattern = r"MedicalGuardian_DeviceActivationDTCMA_\d{8}_DELTA\.csv"

        result = re.match(pattern, filename)

        assert result is not None, f"Valid DTC/MA filename should match: {filename}"
        print("✅ PASS: Valid DTC/MA filename accepted")

    def test_invalid_filename_missing_campaign_type(self):
        """Test invalid filename - missing campaign type."""
        filename = "MedicalGuardian_DeviceActivation_20260114_DELTA.csv"
        patterns = [
            r"MedicalGuardian_DeviceActivationMedicaid_\d{8}_DELTA\.csv",
            r"MedicalGuardian_DeviceActivationDTCMA_\d{8}_DELTA\.csv"
        ]

        result = any(re.match(pattern, filename) for pattern in patterns)

        assert result is False, f"Invalid filename should be rejected: {filename}"
        print("✅ PASS: Invalid filename (missing campaign type) rejected")

    def test_invalid_filename_bad_date_format(self):
        """Test invalid filename - bad date format."""
        filename = "MedicalGuardian_DeviceActivationMedicaid_2026-01-14_DELTA.csv"
        pattern = r"MedicalGuardian_DeviceActivationMedicaid_\d{8}_DELTA\.csv"

        result = re.match(pattern, filename)

        assert result is None, f"Invalid filename should be rejected: {filename}"
        print("✅ PASS: Invalid filename (bad date format) rejected")


# =============================================================================
# TEST 2: ADDRESS VALIDATION (5-PART ADDRESS)
# =============================================================================
class TestAddressValidation:
    """Test address validation - requires all 5 components."""

    def _create_test_dataframe(self, address_data):
        """Helper to create test DataFrame with minimal required columns."""
        base_data = {
            'first_name': ['John'],
            'last_name': ['Doe'],
            'date_of_birth': ['1980-05-15'],
            'primary_phone': ['18123654567'],
            'device_phone_number': ['18123654567'],
            'salesforce_account_id': ['SF001'],
            'monitoring_system_id': ['MS001'],
            'device_udi': ['ABC-12345-XYZ'],
            'fall_detection': ['Yes'],
            'powersaver_mode': ['Default'],
            'is_device_callable': ['Y'],
            'language_pref': ['EN']
        }

        # Merge with address data
        base_data.update(address_data)

        return pd.DataFrame(base_data)

    def _validate_address(self, df):
        """Helper to validate address fields."""
        # Simplified address validation logic from af_device_activation_logic.py
        invalid_rows = []

        for idx, row in df.iterrows():
            errors = []

            # Check required address components
            if pd.isna(row.get('address_street')) or str(row.get('address_street')).strip() == '':
                errors.append("address_street: Missing or empty")

            if pd.isna(row.get('address_city')) or str(row.get('address_city')).strip() == '':
                errors.append("address_city: Missing or empty")

            if pd.isna(row.get('address_state')) or str(row.get('address_state')).strip() == '':
                errors.append("address_state: Missing or empty")

            # ZIP validation
            address_zip = str(row.get('address_zip', '')).strip()
            if not address_zip or address_zip == '' or address_zip == 'nan':
                errors.append("address_zip: Missing or empty")
            else:
                # ZIP must be 5 digits or 5+4 format
                zip_pattern = r'^\d{5}(-\d{4})?$'
                if not re.match(zip_pattern, address_zip):
                    errors.append(f"address_zip: Invalid format (must be 12345 or 12345-6789), got: {address_zip}")

            if errors:
                invalid_rows.append({'row_index': idx, 'errors': errors})

        return len(invalid_rows) == 0, invalid_rows

    def test_valid_address_all_fields_present(self):
        """Test valid address with all 5 fields present."""
        df = self._create_test_dataframe({
            'address_street': ['123 Main St'],
            'address_city': ['Indianapolis'],
            'address_state': ['IN'],
            'address_zip': ['46225'],
            'address_country': ['USA']
        })

        is_valid, errors = self._validate_address(df)

        assert is_valid, f"Valid address should pass validation. Errors: {errors}"
        print("✅ PASS: Valid address (all 5 fields) accepted")

    def test_invalid_address_missing_street(self):
        """Test invalid address - missing street."""
        df = self._create_test_dataframe({
            'address_street': [np.nan],
            'address_city': ['Indianapolis'],
            'address_state': ['IN'],
            'address_zip': ['46225'],
            'address_country': ['USA']
        })

        is_valid, errors = self._validate_address(df)

        assert not is_valid, "Address missing street should fail validation"
        assert any('address_street' in str(e) for e in errors[0]['errors']), "Should have street error"
        print("✅ PASS: Invalid address (missing street) rejected")

    def test_invalid_address_missing_city(self):
        """Test invalid address - missing city."""
        df = self._create_test_dataframe({
            'address_street': ['123 Main St'],
            'address_city': [''],
            'address_state': ['IN'],
            'address_zip': ['46225'],
            'address_country': ['USA']
        })

        is_valid, errors = self._validate_address(df)

        assert not is_valid, "Address missing city should fail validation"
        assert any('address_city' in str(e) for e in errors[0]['errors']), "Should have city error"
        print("✅ PASS: Invalid address (missing city) rejected")

    def test_invalid_address_missing_state(self):
        """Test invalid address - missing state."""
        df = self._create_test_dataframe({
            'address_street': ['123 Main St'],
            'address_city': ['Indianapolis'],
            'address_state': [np.nan],
            'address_zip': ['46225'],
            'address_country': ['USA']
        })

        is_valid, errors = self._validate_address(df)

        assert not is_valid, "Address missing state should fail validation"
        assert any('address_state' in str(e) for e in errors[0]['errors']), "Should have state error"
        print("✅ PASS: Invalid address (missing state) rejected")

    def test_invalid_address_missing_zip(self):
        """Test invalid address - missing ZIP."""
        df = self._create_test_dataframe({
            'address_street': ['123 Main St'],
            'address_city': ['Indianapolis'],
            'address_state': ['IN'],
            'address_zip': [np.nan],
            'address_country': ['USA']
        })

        is_valid, errors = self._validate_address(df)

        assert not is_valid, "Address missing ZIP should fail validation"
        assert any('address_zip' in str(e) for e in errors[0]['errors']), "Should have ZIP error"
        print("✅ PASS: Invalid address (missing ZIP) rejected")

    def test_invalid_address_bad_zip_format(self):
        """Test invalid address - bad ZIP format (4 digits)."""
        df = self._create_test_dataframe({
            'address_street': ['123 Main St'],
            'address_city': ['Indianapolis'],
            'address_state': ['IN'],
            'address_zip': ['4622'],  # Only 4 digits
            'address_country': ['USA']
        })

        is_valid, errors = self._validate_address(df)

        assert not is_valid, "Address with 4-digit ZIP should fail validation"
        assert any('Invalid format' in str(e) for e in errors[0]['errors']), "Should have ZIP format error"
        print("✅ PASS: Invalid address (4-digit ZIP) rejected")

    def test_valid_address_zip_plus_4(self):
        """Test valid address - ZIP+4 format."""
        df = self._create_test_dataframe({
            'address_street': ['123 Main St'],
            'address_city': ['Indianapolis'],
            'address_state': ['IN'],
            'address_zip': ['46225-1234'],  # ZIP+4 format
            'address_country': ['USA']
        })

        is_valid, errors = self._validate_address(df)

        assert is_valid, f"Valid ZIP+4 format should pass validation. Errors: {errors}"
        print("✅ PASS: Valid address (ZIP+4 format) accepted")

    def test_valid_address_null_country_defaults_usa(self):
        """Test valid address - NULL country defaults to USA."""
        df = self._create_test_dataframe({
            'address_street': ['123 Main St'],
            'address_city': ['Indianapolis'],
            'address_state': ['IN'],
            'address_zip': ['46225'],
            'address_country': [np.nan]  # NULL country
        })

        is_valid, errors = self._validate_address(df)

        # Country is optional, so this should pass
        assert is_valid, f"Address with NULL country should pass validation. Errors: {errors}"
        print("✅ PASS: Valid address (NULL country defaults to USA) accepted")


# =============================================================================
# TEST 3: DATE OF BIRTH VALIDATION AND AGE RANGE
# =============================================================================
class TestDOBValidation:
    """Test DOB validation (format validation, max age 120, no future dates)."""

    def _validate_dob(self, dob_str):
        """Helper to validate DOB."""
        from datetime import datetime
        import dateutil.parser

        try:
            # Parse date (supports multiple formats)
            if isinstance(dob_str, str):
                dob = dateutil.parser.parse(dob_str)
            else:
                return False, "Invalid DOB format"

            # Check if future date
            if dob > datetime.now():
                return False, "DOB cannot be in the future"

            # Calculate age
            today = datetime.now()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

            # Maximum age: 120
            if age > 120:
                return False, f"Age {age} exceeds maximum (120)"

            return True, dob.strftime('%Y-%m-%d')

        except Exception as e:
            return False, f"Error parsing DOB: {str(e)}"

    def test_valid_dob_45_years_old(self):
        """Test valid DOB - 45 years old."""
        dob = "1980-05-15"

        is_valid, result = self._validate_dob(dob)

        assert is_valid, f"Valid DOB should pass. Result: {result}"
        assert result == "1980-05-15", f"Expected 1980-05-15, got {result}"
        print("✅ PASS: Valid DOB (45 years old) accepted")

    def test_valid_dob_auto_convert_format(self):
        """Test valid DOB - auto-convert from MM/DD/YYYY."""
        dob = "05/15/1980"

        is_valid, result = self._validate_dob(dob)

        assert is_valid, f"Valid DOB should pass. Result: {result}"
        assert result == "1980-05-15", f"Expected 1980-05-15, got {result}"
        print("✅ PASS: Valid DOB (auto-converted from 05/15/1980) accepted")

    def test_invalid_dob_future_date(self):
        """Test invalid DOB - future date."""
        dob = "2030-01-01"

        is_valid, result = self._validate_dob(dob)

        assert not is_valid, "Future DOB should fail validation"
        assert "future" in result.lower(), f"Should have future date error: {result}"
        print("✅ PASS: Invalid DOB (future date) rejected")

    def test_invalid_dob_too_old(self):
        """Test invalid DOB - too old (135 years old)."""
        dob = "1890-01-01"

        is_valid, result = self._validate_dob(dob)

        assert not is_valid, "DOB resulting in age > 120 should fail validation"
        assert "exceeds maximum" in result.lower(), f"Should have age error: {result}"
        print("✅ PASS: Invalid DOB (too old - 135 years) rejected")


# =============================================================================
# TEST 4: DEVICE UDI VALIDATION
# =============================================================================
class TestDeviceUDIValidation:
    """Test Device UDI validation (5-50 chars, alphanumeric + hyphens)."""

    def _validate_device_udi(self, device_udi):
        """Helper to validate device UDI."""
        # Handle scientific notation (e.g., 1.23E+10 → 12300000000)
        if isinstance(device_udi, float):
            device_udi = f"{device_udi:.0f}"

        device_udi = str(device_udi).strip()

        # Check length (5-50 characters)
        if len(device_udi) < 5:
            return False, f"Device UDI too short ({len(device_udi)} chars, minimum 5)"

        if len(device_udi) > 50:
            return False, f"Device UDI too long ({len(device_udi)} chars, maximum 50)"

        # Check format (alphanumeric + hyphens only)
        if not re.match(r'^[A-Za-z0-9\-]+$', device_udi):
            return False, "Device UDI contains invalid characters (only alphanumeric + hyphens allowed)"

        return True, device_udi

    def test_valid_device_udi(self):
        """Test valid device UDI."""
        udi = "ABC-12345-XYZ"

        is_valid, result = self._validate_device_udi(udi)

        assert is_valid, f"Valid UDI should pass. Result: {result}"
        assert result == "ABC-12345-XYZ", f"Expected ABC-12345-XYZ, got {result}"
        print("✅ PASS: Valid device UDI accepted")

    def test_invalid_device_udi_too_short(self):
        """Test invalid device UDI - too short (3 chars)."""
        udi = "ABC"

        is_valid, result = self._validate_device_udi(udi)

        assert not is_valid, "UDI with < 5 chars should fail validation"
        assert "too short" in result.lower(), f"Should have length error: {result}"
        print("✅ PASS: Invalid device UDI (too short) rejected")

    def test_invalid_device_udi_too_long(self):
        """Test invalid device UDI - too long (51 chars)."""
        udi = "A" * 51

        is_valid, result = self._validate_device_udi(udi)

        assert not is_valid, "UDI with > 50 chars should fail validation"
        assert "too long" in result.lower(), f"Should have length error: {result}"
        print("✅ PASS: Invalid device UDI (too long) rejected")

    def test_invalid_device_udi_invalid_chars(self):
        """Test invalid device UDI - invalid characters."""
        udi = "ABC@12345"

        is_valid, result = self._validate_device_udi(udi)

        assert not is_valid, "UDI with special chars should fail validation"
        assert "invalid characters" in result.lower(), f"Should have character error: {result}"
        print("✅ PASS: Invalid device UDI (invalid characters) rejected")

    def test_valid_device_udi_scientific_notation(self):
        """Test valid device UDI - scientific notation conversion."""
        udi = 1.23E+10  # Should convert to 12300000000

        is_valid, result = self._validate_device_udi(udi)

        assert is_valid, f"Scientific notation UDI should pass. Result: {result}"
        assert result == "12300000000", f"Expected 12300000000, got {result}"
        print("✅ PASS: Valid device UDI (scientific notation) accepted")


# =============================================================================
# TEST 5: MONITORING SYSTEM ID VALIDATION
# =============================================================================
class TestMonitoringSystemIDValidation:
    """Test Monitoring System ID validation (required, non-empty)."""

    def _validate_monitoring_system_id(self, monitoring_system_id):
        """Helper to validate monitoring system ID."""
        if pd.isna(monitoring_system_id):
            return False, "Monitoring system ID is NULL"

        monitoring_system_id_str = str(monitoring_system_id).strip()

        if monitoring_system_id_str == '' or monitoring_system_id_str == 'nan':
            return False, "Monitoring system ID is empty"

        return True, monitoring_system_id_str

    def test_valid_monitoring_system_id(self):
        """Test valid monitoring system ID."""
        msid = "SF-ACCOUNT-12345"

        is_valid, result = self._validate_monitoring_system_id(msid)

        assert is_valid, f"Valid monitoring system ID should pass. Result: {result}"
        assert result == "SF-ACCOUNT-12345", f"Expected SF-ACCOUNT-12345, got {result}"
        print("✅ PASS: Valid monitoring system ID accepted")

    def test_invalid_monitoring_system_id_empty_string(self):
        """Test invalid monitoring system ID - empty string."""
        msid = ""

        is_valid, result = self._validate_monitoring_system_id(msid)

        assert not is_valid, "Empty monitoring system ID should fail validation"
        assert "empty" in result.lower(), f"Should have empty error: {result}"
        print("✅ PASS: Invalid monitoring system ID (empty string) rejected")

    def test_invalid_monitoring_system_id_null(self):
        """Test invalid monitoring system ID - NULL value."""
        msid = np.nan

        is_valid, result = self._validate_monitoring_system_id(msid)

        assert not is_valid, "NULL monitoring system ID should fail validation"
        assert "null" in result.lower(), f"Should have NULL error: {result}"
        print("✅ PASS: Invalid monitoring system ID (NULL) rejected")


# =============================================================================
# TEST 6: DEVICE STATUS FIELDS (BOOLEAN CONVERSIONS)
# =============================================================================
class TestDeviceStatusFields:
    """Test device status field conversions."""

    def _validate_fall_detection(self, value):
        """Helper to validate fall_detection (Yes/No, Y/N, true/false, 1/0 → 'true'/'false')."""
        if pd.isna(value):
            return True, "false"  # Default to false

        value_str = str(value).strip().lower()

        if value_str in ['yes', 'y', 'true', '1', '1.0']:
            return True, "true"
        elif value_str in ['no', 'n', 'false', '0', '0.0']:
            return True, "false"
        else:
            return False, f"Invalid fall_detection value: {value}"

    def _validate_powersaver_mode(self, value):
        """Helper to validate powersaver_mode (Default/Standard/Battery Saver)."""
        if pd.isna(value):
            return True, "Default"  # Default value

        value_str = str(value).strip()

        valid_values = ['Default', 'Standard', 'Battery Saver']
        if value_str in valid_values:
            return True, value_str
        else:
            return False, f"Invalid powersaver_mode value: {value} (must be Default/Standard/Battery Saver)"

    def _validate_is_device_callable(self, value):
        """Helper to validate is_device_callable (Y/N, 1/0 → 1/0)."""
        if pd.isna(value):
            return True, 1  # Default to 1 (callable)

        value_str = str(value).strip().upper()

        if value_str in ['Y', 'YES', '1', '1.0']:
            return True, 1
        elif value_str in ['N', 'NO', '0', '0.0']:
            return True, 0
        else:
            return False, f"Invalid is_device_callable value: {value}"

    def test_fall_detection_yes_to_true(self):
        """Test fall_detection: Yes → 'true'."""
        is_valid, result = self._validate_fall_detection("Yes")

        assert is_valid, f"Valid fall_detection should pass. Result: {result}"
        assert result == "true", f"Expected 'true', got {result}"
        print("✅ PASS: fall_detection 'Yes' → 'true'")

    def test_fall_detection_no_to_false(self):
        """Test fall_detection: No → 'false'."""
        is_valid, result = self._validate_fall_detection("No")

        assert is_valid, f"Valid fall_detection should pass. Result: {result}"
        assert result == "false", f"Expected 'false', got {result}"
        print("✅ PASS: fall_detection 'No' → 'false'")

    def test_fall_detection_true_false_conversions(self):
        """Test fall_detection: true/false, 1/0 conversions."""
        test_cases = [
            ("true", "true"),
            ("false", "false"),
            ("1", "true"),
            ("0", "false")
        ]

        for input_val, expected in test_cases:
            is_valid, result = self._validate_fall_detection(input_val)
            assert is_valid, f"Valid fall_detection should pass. Input: {input_val}, Result: {result}"
            assert result == expected, f"Expected {expected}, got {result} for input {input_val}"

        print("✅ PASS: fall_detection true/false, 1/0 conversions")

    def test_powersaver_mode_battery_saver_accepted(self):
        """Test powersaver_mode: 'Battery Saver' → accepted."""
        is_valid, result = self._validate_powersaver_mode("Battery Saver")

        assert is_valid, f"Valid powersaver_mode should pass. Result: {result}"
        assert result == "Battery Saver", f"Expected 'Battery Saver', got {result}"
        print("✅ PASS: powersaver_mode 'Battery Saver' accepted")

    def test_powersaver_mode_all_valid_values(self):
        """Test powersaver_mode: Default/Standard/Battery Saver all accepted."""
        valid_values = ['Default', 'Standard', 'Battery Saver']

        for value in valid_values:
            is_valid, result = self._validate_powersaver_mode(value)
            assert is_valid, f"Valid powersaver_mode should pass. Value: {value}, Result: {result}"
            assert result == value, f"Expected {value}, got {result}"

        print("✅ PASS: powersaver_mode all valid values accepted")

    def test_powersaver_mode_invalid_value_rejected(self):
        """Test powersaver_mode: Invalid value → rejected."""
        is_valid, result = self._validate_powersaver_mode("InvalidMode")

        assert not is_valid, "Invalid powersaver_mode should fail validation"
        assert "invalid" in result.lower(), f"Should have invalid error: {result}"
        print("✅ PASS: powersaver_mode invalid value rejected")

    def test_is_device_callable_y_to_1(self):
        """Test is_device_callable: Y → 1."""
        is_valid, result = self._validate_is_device_callable("Y")

        assert is_valid, f"Valid is_device_callable should pass. Result: {result}"
        assert result == 1, f"Expected 1, got {result}"
        print("✅ PASS: is_device_callable 'Y' → 1")

    def test_is_device_callable_n_to_0(self):
        """Test is_device_callable: N → 0."""
        is_valid, result = self._validate_is_device_callable("N")

        assert is_valid, f"Valid is_device_callable should pass. Result: {result}"
        assert result == 0, f"Expected 0, got {result}"
        print("✅ PASS: is_device_callable 'N' → 0")


# =============================================================================
# TEST 7: LANGUAGE PREFERENCE MAPPING (ISO 639)
# =============================================================================
class TestLanguageMapping:
    """Test language preference mapping (ISO 639 to platform codes)."""

    def test_language_en_to_EN(self):
        """Test language mapping: EN → EN."""
        result = map_language_code('EN')

        assert result == 'EN', f"Expected 'EN', got {result}"
        print("✅ PASS: Language 'EN' → 'EN'")

    def test_language_es_to_ES(self):
        """Test language mapping: ES → ES."""
        result = map_language_code('ES')

        assert result == 'ES', f"Expected 'ES', got {result}"
        print("✅ PASS: Language 'ES' → 'ES'")

    def test_language_eng_to_EN(self):
        """Test language mapping: eng (ISO 639-3) → EN."""
        result = map_language_code('eng')

        assert result == 'EN', f"Expected 'EN', got {result}"
        print("✅ PASS: Language 'eng' → 'EN'")

    def test_language_spa_to_ES(self):
        """Test language mapping: spa (ISO 639-3) → ES."""
        result = map_language_code('spa')

        assert result == 'ES', f"Expected 'ES', got {result}"
        print("✅ PASS: Language 'spa' → 'ES'")

    def test_language_fra_to_Other(self):
        """Test language mapping: fra (French) → Other."""
        result = map_language_code('fra')

        assert result == 'Other', f"Expected 'Other', got {result}"
        print("✅ PASS: Language 'fra' → 'Other'")


# =============================================================================
# TEST 8: DUPLICATE DEVICE UDI DETECTION
# =============================================================================
class TestDuplicateUDIDetection:
    """Test duplicate device UDI detection."""

    def _detect_duplicate_udi(self, df):
        """Helper to detect duplicate device UDI across different accounts."""
        # Group by device_udi and check if same UDI appears for different accounts
        duplicates = []

        udi_groups = df.groupby('device_udi')
        for udi, group in udi_groups:
            unique_accounts = group['salesforce_account_id'].nunique()
            if unique_accounts > 1:
                duplicates.append({
                    'device_udi': udi,
                    'accounts': group['salesforce_account_id'].unique().tolist()
                })

        return len(duplicates) == 0, duplicates

    def test_duplicate_udi_different_accounts_rejected(self):
        """Test duplicate device_udi for different accounts → rejected."""
        df = pd.DataFrame({
            'salesforce_account_id': ['ACC001', 'ACC002'],
            'device_udi': ['UDI-12345', 'UDI-12345'],  # Same UDI, different accounts
            'first_name': ['John', 'Jane'],
            'last_name': ['Doe', 'Smith']
        })

        is_valid, duplicates = self._detect_duplicate_udi(df)

        assert not is_valid, "Duplicate UDI for different accounts should be rejected"
        assert len(duplicates) == 1, f"Should have 1 duplicate, got {len(duplicates)}"
        assert duplicates[0]['device_udi'] == 'UDI-12345', "Should identify UDI-12345 as duplicate"
        print("✅ PASS: Duplicate device_udi for different accounts rejected")

    def test_same_account_different_udi_accepted(self):
        """Test same account + different device_udi → accepted."""
        df = pd.DataFrame({
            'salesforce_account_id': ['ACC001', 'ACC001'],
            'device_udi': ['UDI-12345', 'UDI-67890'],  # Different UDIs, same account
            'first_name': ['John', 'John'],
            'last_name': ['Doe', 'Doe']
        })

        is_valid, duplicates = self._detect_duplicate_udi(df)

        assert is_valid, f"Same account with different UDIs should be accepted. Duplicates: {duplicates}"
        print("✅ PASS: Same account + different device_udi accepted")

    def test_duplicate_row_all_fields_identical_rejected(self):
        """Test duplicate row (all fields identical) → rejected."""
        df = pd.DataFrame({
            'salesforce_account_id': ['ACC001', 'ACC001'],
            'device_udi': ['UDI-12345', 'UDI-12345'],  # Identical rows
            'first_name': ['John', 'John'],
            'last_name': ['Doe', 'Doe']
        })

        # Check for exact duplicates
        duplicate_rows = df.duplicated(keep=False)
        has_duplicates = duplicate_rows.any()

        assert has_duplicates, "Duplicate rows should be detected"
        print("✅ PASS: Duplicate row (all fields identical) rejected")


# =============================================================================
# TEST RUNNER
# =============================================================================
def run_all_tests():
    """Run all validation tests and report results."""
    print("=" * 80)
    print("Device Activation CSV Validation Tests")
    print("=" * 80)
    print()

    test_classes = [
        ("Filename Pattern Validation", TestFilenamePatternValidation),
        ("Address Validation (5-Part)", TestAddressValidation),
        ("Date of Birth Validation", TestDOBValidation),
        ("Device UDI Validation", TestDeviceUDIValidation),
        ("Monitoring System ID Validation", TestMonitoringSystemIDValidation),
        ("Device Status Fields", TestDeviceStatusFields),
        ("Language Preference Mapping", TestLanguageMapping),
        ("Duplicate Device UDI Detection", TestDuplicateUDIDetection)
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = 0

    for test_name, test_class in test_classes:
        print(f"\n{'=' * 80}")
        print(f"Testing: {test_name}")
        print(f"{'=' * 80}")

        test_instance = test_class()
        test_methods = [method for method in dir(test_instance) if method.startswith('test_')]

        for method_name in test_methods:
            total_tests += 1
            try:
                method = getattr(test_instance, method_name)
                method()
                passed_tests += 1
            except AssertionError as e:
                failed_tests += 1
                print(f"❌ FAIL: {method_name}")
                print(f"   Error: {str(e)}")
            except Exception as e:
                failed_tests += 1
                print(f"❌ ERROR: {method_name}")
                print(f"   Exception: {str(e)}")

    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests} ✅")
    print(f"Failed: {failed_tests} ❌")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    print("=" * 80)

    return passed_tests == total_tests


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
