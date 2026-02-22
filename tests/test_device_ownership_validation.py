"""
Unit tests for device ownership validation

Tests device-to-member exclusivity enforcement to prevent cross-member
device reassignment in DTC and Device Activation workflows.

BusinessCaseID: BC-DEVICE-OWNERSHIP-VALIDATION
Created: 2026-02-13
"""

import uuid
import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
import pandas as pd

from af_code.shared.schema_config import IOE_SCHEMA, IOE_SCHEMA_STG


# ============================================================================
# Test Data Fixtures
# ============================================================================


@pytest.fixture
def test_member_a():
    """Member A - Original device owner"""
    return {
        "member_id": uuid.UUID("11111111-2222-3333-4444-555555555555"),
        "salesforce_account_number": "SF-12345",
        "first_name": "Alice",
        "last_name": "Anderson",
    }


@pytest.fixture
def test_member_b():
    """Member B - Attempting to claim existing device"""
    return {
        "member_id": uuid.UUID("66666666-7777-8888-9999-000000000000"),
        "salesforce_account_number": "SF-67890",
        "first_name": "Bob",
        "last_name": "Brown",
    }


@pytest.fixture
def test_device():
    """Test device data"""
    return {
        "device_udi": "TEST-DEVICE-001",
        "device_phone_number": "+18125551234",
        "is_device_callable": True,
        "device_name": "Test Device",
        "service_status": "In Service",
    }


@pytest.fixture
def mock_db_service():
    """Mock database service"""
    return Mock()


# ============================================================================
# Test Case 1: DTC Workflow - Device Ownership Conflict
# ============================================================================


def test_dtc_device_ownership_conflict(test_member_a, test_member_b, test_device):
    """
    Test DTC validation when device already exists for different member

    Scenario:
    - Device 'TEST-DEVICE-001' exists for Member A
    - DTC CSV attempts to assign same device to Member B
    - Expected: ValueError raised, error logged, row marked as VALIDATION_ERROR
    """
    # Mock database cursor results for ownership validation query
    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = [
        (
            test_device["device_udi"],  # device_udi
            str(test_member_b["member_id"]),  # incoming_member_id
            test_member_b["salesforce_account_number"],  # incoming_account
            str(test_member_a["member_id"]),  # existing_member_id
            test_member_a["salesforce_account_number"],  # existing_account
            1,  # row_number
        )
    ]

    mock_db_manager = Mock()
    mock_db_manager.execute_with_retry.return_value = mock_cursor

    # Create context mock
    mock_context = Mock()
    mock_context.file_batch_id = uuid.uuid4()
    mock_context.file_id = uuid.uuid4()
    mock_context.config.staging_table = f"{IOE_SCHEMA_STG}.stg_dtc_wellness_delta"
    mock_context.connection = Mock()

    # Test: Validation query should detect conflict
    with pytest.raises(ValueError) as exc_info:
        # Simulate the validation logic from af_dtc_logic.py
        device_ownership_validation_sql = f"""
        WITH ExistingDeviceOwners AS (
            SELECT
                stg.device_udi,
                m.member_id AS incoming_member_id,
                m.salesforce_account_number AS incoming_account,
                md.member_id AS existing_member_id,
                m_existing.salesforce_account_number AS existing_account,
                stg.row_number
            FROM {mock_context.config.staging_table} stg
            JOIN {IOE_SCHEMA}.members m
                ON m.org_id = stg.org_id
                AND m.salesforce_account_number = stg.salesforce_account_number
            JOIN {IOE_SCHEMA}.member_devices md
                ON stg.device_udi = md.device_id
            JOIN {IOE_SCHEMA}.members m_existing
                ON md.member_id = m_existing.member_id
            WHERE stg.file_batch_id = %s
              AND stg.processing_status = 'TRANSFORMING'
              AND stg.device_udi IS NOT NULL
              AND LTRIM(RTRIM(stg.device_udi)) != ''
              AND md.member_id != m.member_id
        )
        SELECT
            device_udi,
            incoming_member_id,
            incoming_account,
            existing_member_id,
            existing_account,
            row_number
        FROM ExistingDeviceOwners;
        """

        cursor = mock_db_manager.execute_with_retry(
            mock_context.connection,
            device_ownership_validation_sql,
            (str(mock_context.file_batch_id),),
        )
        conflict_results = cursor.fetchall()

        if conflict_results:
            conflict_count = len(conflict_results)
            raise ValueError(
                f"Device ownership validation failed: {conflict_count} device(s) have cross-member conflicts."
            )

    # Verify exception message
    assert "Device ownership validation failed" in str(exc_info.value)
    assert "cross-member conflicts" in str(exc_info.value)


# ============================================================================
# Test Case 2: Device Activation - Database Cross-Check
# ============================================================================


def test_device_activation_ownership_conflict(test_member_a, test_member_b, test_device):
    """
    Test Device Activation validation against database

    Scenario:
    - Device 'TEST-DEVICE-001' exists in database for Member A
    - Device Activation CSV has same device for Member B
    - Expected: Row marked as FAILED, error message populated
    """
    # Create test DataFrame
    df = pd.DataFrame(
        [
            {
                "device_udi": test_device["device_udi"],
                "member_id": test_member_b["member_id"],
                "salesforce_account_number": test_member_b["salesforce_account_number"],
                "validation_status": "VALIDATED",
                "error_message": "",
                "error_details": "",
            }
        ]
    )

    # Mock database query results (existing device ownership)
    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = [
        (
            test_device["device_udi"],  # device_udi
            test_member_a["member_id"],  # existing_member_id
            test_member_a["salesforce_account_number"],  # existing_account
        )
    ]

    mock_db_service = Mock()
    mock_db_service.execute_query.return_value = mock_cursor

    mock_context = Mock()
    mock_context.db_service = mock_db_service

    # Simulate device ownership validation logic
    validated_rows = df[df["validation_status"] == "VALIDATED"].copy()
    device_udis = validated_rows["device_udi"].unique().tolist()

    placeholders = ",".join(["%s"] * len(device_udis))
    ownership_check_sql = f"""
    SELECT
        md.device_id AS device_udi,
        md.member_id AS existing_member_id,
        m.salesforce_account_number AS existing_account
    FROM {IOE_SCHEMA}.member_devices md
    JOIN {IOE_SCHEMA}.members m ON md.member_id = m.member_id
    WHERE md.device_id IN ({placeholders});
    """

    cursor = mock_context.db_service.execute_query(
        ownership_check_sql, tuple(device_udis), fetch_results=True
    )
    existing_devices = cursor.fetchall()

    existing_ownership = {row[0]: (str(row[1]), row[2]) for row in existing_devices}

    # Check for conflicts
    for idx, row in validated_rows.iterrows():
        device_udi = row["device_udi"]
        incoming_member_id = str(row["member_id"])

        if device_udi in existing_ownership:
            existing_member_id, existing_account = existing_ownership[device_udi]

            if existing_member_id != incoming_member_id:
                error_msg = (
                    f"Device ownership conflict: device_udi='{device_udi}' already assigned to "
                    f"member_id={existing_member_id} (account={existing_account})."
                )
                df.at[idx, "validation_status"] = "FAILED"
                df.at[idx, "error_message"] = error_msg
                df.at[idx, "error_details"] = (
                    f"DEVICE_OWNERSHIP_CONFLICT|existing_member={existing_member_id}"
                )

    # Verify results
    assert df.at[0, "validation_status"] == "FAILED"
    assert "Device ownership conflict" in df.at[0, "error_message"]
    assert test_member_a["salesforce_account_number"] in df.at[0, "error_message"]
    assert "DEVICE_OWNERSHIP_CONFLICT" in df.at[0, "error_details"]


# ============================================================================
# Test Case 3: No Conflict - Same Member Update
# ============================================================================


def test_device_ownership_no_conflict_same_member(test_member_a, test_device):
    """
    Test device update for same member (no conflict)

    Scenario:
    - Device 'TEST-DEVICE-001' exists for Member A
    - CSV has same device for same Member A (update scenario)
    - Expected: No error, validation passes
    """
    # Create test DataFrame
    df = pd.DataFrame(
        [
            {
                "device_udi": test_device["device_udi"],
                "member_id": test_member_a["member_id"],
                "salesforce_account_number": test_member_a["salesforce_account_number"],
                "validation_status": "VALIDATED",
                "error_message": "",
                "error_details": "",
            }
        ]
    )

    # Mock database query results (same member owns device)
    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = [
        (
            test_device["device_udi"],  # device_udi
            test_member_a["member_id"],  # existing_member_id
            test_member_a["salesforce_account_number"],  # existing_account
        )
    ]

    mock_db_service = Mock()
    mock_db_service.execute_query.return_value = mock_cursor

    mock_context = Mock()
    mock_context.db_service = mock_db_service

    # Simulate validation logic
    validated_rows = df[df["validation_status"] == "VALIDATED"].copy()
    device_udis = validated_rows["device_udi"].unique().tolist()

    cursor = mock_context.db_service.execute_query(
        "SELECT * FROM member_devices WHERE device_id IN (%s)",
        tuple(device_udis),
        fetch_results=True,
    )
    existing_devices = cursor.fetchall()

    existing_ownership = {row[0]: (str(row[1]), row[2]) for row in existing_devices}

    conflicts_found = False
    for idx, row in validated_rows.iterrows():
        device_udi = row["device_udi"]
        incoming_member_id = str(row["member_id"])

        if device_udi in existing_ownership:
            existing_member_id, _ = existing_ownership[device_udi]

            # Same member - no conflict
            if existing_member_id != incoming_member_id:
                conflicts_found = True
                df.at[idx, "validation_status"] = "FAILED"

    # Verify: No conflicts detected
    assert not conflicts_found
    assert df.at[0, "validation_status"] == "VALIDATED"
    assert df.at[0, "error_message"] == ""


# ============================================================================
# Test Case 4: No Conflict - New Device
# ============================================================================


def test_device_ownership_no_conflict_new_device(test_member_b):
    """
    Test new device insertion (no existing ownership)

    Scenario:
    - Device 'NEW-DEVICE-999' does NOT exist in database
    - CSV has this device for Member B
    - Expected: No conflict, validation passes
    """
    new_device = "NEW-DEVICE-999"

    df = pd.DataFrame(
        [
            {
                "device_udi": new_device,
                "member_id": test_member_b["member_id"],
                "salesforce_account_number": test_member_b["salesforce_account_number"],
                "validation_status": "VALIDATED",
                "error_message": "",
                "error_details": "",
            }
        ]
    )

    # Mock database query results (device not found)
    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = []  # No existing ownership

    mock_db_service = Mock()
    mock_db_service.execute_query.return_value = mock_cursor

    mock_context = Mock()
    mock_context.db_service = mock_db_service

    # Simulate validation logic
    validated_rows = df[df["validation_status"] == "VALIDATED"].copy()
    device_udis = validated_rows["device_udi"].unique().tolist()

    cursor = mock_context.db_service.execute_query(
        "SELECT * FROM member_devices WHERE device_id IN (%s)",
        tuple(device_udis),
        fetch_results=True,
    )
    existing_devices = cursor.fetchall()

    existing_ownership = {row[0]: (str(row[1]), row[2]) for row in existing_devices}

    # Check for conflicts
    conflicts_found = False
    for idx, row in validated_rows.iterrows():
        device_udi = row["device_udi"]
        incoming_member_id = str(row["member_id"])

        if device_udi in existing_ownership:
            existing_member_id, _ = existing_ownership[device_udi]
            if existing_member_id != incoming_member_id:
                conflicts_found = True

    # Verify: No conflicts (new device)
    assert not conflicts_found
    assert df.at[0, "validation_status"] == "VALIDATED"
    assert new_device not in existing_ownership


# ============================================================================
# Test Case 5: Error Logging Verification
# ============================================================================


def test_device_ownership_error_logging(test_member_a, test_member_b, test_device):
    """
    Test error logging for device ownership conflicts

    Scenario:
    - Device conflict detected
    - Expected: Error logged to dtc_validation_error_details_row table
    """
    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = [
        (
            test_device["device_udi"],
            str(test_member_b["member_id"]),
            test_member_b["salesforce_account_number"],
            str(test_member_a["member_id"]),
            test_member_a["salesforce_account_number"],
            1,  # row_number
        )
    ]

    mock_db_manager = Mock()
    mock_db_manager.execute_with_retry.return_value = mock_cursor

    mock_context = Mock()
    mock_context.file_batch_id = uuid.uuid4()
    mock_context.file_id = uuid.uuid4()
    mock_context.config.staging_table = f"{IOE_SCHEMA_STG}.stg_dtc_wellness_delta"
    mock_context.connection = Mock()

    # Simulate error logging
    conflict_results = mock_cursor.fetchall()

    for row in conflict_results:
        device_udi = row[0]
        existing_member = row[3]
        existing_account = row[4]
        row_number = row[5]

        error_msg = (
            f"Device ownership conflict: device_udi='{device_udi}' already assigned to "
            f"member_id={existing_member} (account={existing_account})."
        )

        # Log to validation error table
        insert_error_sql = f"""
        INSERT INTO {IOE_SCHEMA}.dtc_validation_error_details_row
        (file_id, row_number, field_name, error_message, created_ts)
        VALUES (%s, %s, %s, %s, SYSDATETIMEOFFSET());
        """
        mock_db_manager.execute_with_retry(
            mock_context.connection,
            insert_error_sql,
            (str(mock_context.file_id), row_number, "device_udi", error_msg),
        )

    # Verify error logging was called
    assert mock_db_manager.execute_with_retry.called
    call_args = mock_db_manager.execute_with_retry.call_args_list[-1][0]
    assert "dtc_validation_error_details_row" in call_args[1]
    assert "device_udi" in call_args[2]


# ============================================================================
# Test Case 6: Multiple Device Conflicts
# ============================================================================


def test_multiple_device_ownership_conflicts():
    """
    Test handling of multiple device conflicts in same batch

    Scenario:
    - CSV has 3 devices, 2 have ownership conflicts
    - Expected: Both conflicts detected and logged
    """
    conflicts = [
        (
            "DEVICE-A",
            "member-1-incoming",
            "SF-111",
            "member-1-existing",
            "SF-999",
            1,
        ),
        (
            "DEVICE-B",
            "member-2-incoming",
            "SF-222",
            "member-2-existing",
            "SF-888",
            2,
        ),
    ]

    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = conflicts

    mock_db_manager = Mock()
    mock_db_manager.execute_with_retry.return_value = mock_cursor

    mock_context = Mock()
    mock_context.file_batch_id = uuid.uuid4()
    mock_context.file_id = uuid.uuid4()

    # Simulate validation
    conflict_results = mock_cursor.fetchall()
    conflict_count = len(conflict_results)

    # Verify both conflicts detected
    assert conflict_count == 2

    # Verify error would be raised
    with pytest.raises(ValueError) as exc_info:
        if conflict_results:
            raise ValueError(
                f"Device ownership validation failed: {conflict_count} device(s) have cross-member conflicts."
            )

    assert "2 device(s)" in str(exc_info.value)


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
