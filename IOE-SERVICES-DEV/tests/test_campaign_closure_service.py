"""
Unit Tests for Device Activation Campaign Closure Service

Tests the automatic unenrollment logic when campaign_end_date is reached.

BusinessCaseID: BC-DA-007
Created: 2026-01-20
"""

import unittest
from unittest.mock import Mock
from datetime import date
import uuid

# Import the service to test
from af_code.device_activation_scheduler.services.campaign_closure_service import (
    CampaignClosureService,
)


class TestCampaignClosureService(unittest.TestCase):
    """
    Test suite for CampaignClosureService

    Tests:
    - Query logic for expired enrollments
    - Status update logic (ENROLLED -> UNENROLLED)
    - Audit trail logging
    - Distributed locking mechanism
    - Edge cases (no expired enrollments, NULL campaign_end_date, etc.)
    """

    def setUp(self):
        """Set up test fixtures before each test"""
        self.mock_db_service = Mock()
        self.mock_config_manager = Mock()
        self.service = CampaignClosureService(self.mock_db_service, self.mock_config_manager)

    def tearDown(self):
        """Clean up after each test"""
        self.mock_db_service.reset_mock()
        self.mock_config_manager.reset_mock()

    # ========================================================================
    # Test: Query Expired Enrollments
    # ========================================================================

    def test_query_expired_enrollments_success(self):
        """Test querying expired enrollments returns correct data"""
        # Arrange
        mock_enrollments = [
            {
                "enrollment_id": str(uuid.uuid4()),
                "member_id": str(uuid.uuid4()),
                "campaign_id": str(uuid.uuid4()),
                "campaign_end_date": date(2026, 1, 15),
                "current_status": "ENROLLED",
                "campaign_name": "Medicaid DeviceActivation",
                "campaign_type": "Operations",
            },
            {
                "enrollment_id": str(uuid.uuid4()),
                "member_id": str(uuid.uuid4()),
                "campaign_id": str(uuid.uuid4()),
                "campaign_end_date": date(2026, 1, 10),
                "current_status": "ENROLLED",
                "campaign_name": "DTCMA DeviceActivation",
                "campaign_type": "Operations",
            },
        ]

        self.mock_db_service.execute_query.return_value = mock_enrollments

        # Act
        result = self.service._query_expired_enrollments()

        # Assert
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["campaign_name"], "Medicaid DeviceActivation")
        self.assertEqual(result[1]["campaign_name"], "DTCMA DeviceActivation")
        self.mock_db_service.execute_query.assert_called_once()

    def test_query_expired_enrollments_empty_result(self):
        """Test querying when no expired enrollments exist"""
        # Arrange
        self.mock_db_service.execute_query.return_value = []

        # Act
        result = self.service._query_expired_enrollments()

        # Assert
        self.assertEqual(len(result), 0)
        self.mock_db_service.execute_query.assert_called_once()

    def test_query_expired_enrollments_filters_operations_only(self):
        """Test query filters by campaign_type = 'Operations'"""
        # Arrange
        self.mock_db_service.execute_query.return_value = []

        # Act
        self.service._query_expired_enrollments()

        # Assert
        query_arg = self.mock_db_service.execute_query.call_args[0][0]
        self.assertIn("campaign_type = 'Operations'", query_arg)

    def test_query_expired_enrollments_filters_enrolled_only(self):
        """Test query filters by current_status = 'ENROLLED'"""
        # Arrange
        self.mock_db_service.execute_query.return_value = []

        # Act
        self.service._query_expired_enrollments()

        # Assert
        query_arg = self.mock_db_service.execute_query.call_args[0][0]
        self.assertIn("current_status = 'ENROLLED'", query_arg)

    def test_query_expired_enrollments_excludes_null_campaign_end_date(self):
        """Test query excludes enrollments with NULL campaign_end_date"""
        # Arrange
        self.mock_db_service.execute_query.return_value = []

        # Act
        self.service._query_expired_enrollments()

        # Assert
        query_arg = self.mock_db_service.execute_query.call_args[0][0]
        self.assertIn("campaign_end_date IS NOT NULL", query_arg)

    # ========================================================================
    # Test: Update Enrollment Status
    # ========================================================================

    def test_update_enrollment_status_success(self):
        """Test successful enrollment status update to UNENROLLED"""
        # Arrange
        enrollment_id = str(uuid.uuid4())
        member_id = str(uuid.uuid4())
        campaign_id = str(uuid.uuid4())
        campaign_name = "Medicaid DeviceActivation"
        campaign_end_date = date(2026, 1, 15)

        self.mock_db_service.execute_transaction.return_value = None

        # Act
        result = self.service._update_enrollment_status(
            enrollment_id, member_id, campaign_id, campaign_name, campaign_end_date
        )

        # Assert
        self.assertTrue(result)
        self.mock_db_service.execute_transaction.assert_called_once()

        # Verify transaction contains 2 queries (update + audit)
        transaction_queries = self.mock_db_service.execute_transaction.call_args[0][0]
        self.assertEqual(len(transaction_queries), 2)

    def test_update_enrollment_status_sets_unenrollment_reason(self):
        """Test that unenrollment_reason is set correctly"""
        # Arrange
        enrollment_id = str(uuid.uuid4())
        member_id = str(uuid.uuid4())
        campaign_id = str(uuid.uuid4())
        campaign_name = "DTCMA DeviceActivation"
        campaign_end_date = date(2026, 1, 15)

        self.mock_db_service.execute_transaction.return_value = None

        # Act
        self.service._update_enrollment_status(
            enrollment_id, member_id, campaign_id, campaign_name, campaign_end_date
        )

        # Assert
        transaction_queries = self.mock_db_service.execute_transaction.call_args[0][0]
        update_query = transaction_queries[0][0]
        self.assertIn("Campaign 90-day window completed", update_query)

    def test_update_enrollment_status_creates_audit_trail(self):
        """Test that audit trail is created in member_enrollment_status_history"""
        # Arrange
        enrollment_id = str(uuid.uuid4())
        member_id = str(uuid.uuid4())
        campaign_id = str(uuid.uuid4())
        campaign_name = "Medicaid DeviceActivation"
        campaign_end_date = date(2026, 1, 15)

        self.mock_db_service.execute_transaction.return_value = None

        # Act
        self.service._update_enrollment_status(
            enrollment_id, member_id, campaign_id, campaign_name, campaign_end_date
        )

        # Assert
        transaction_queries = self.mock_db_service.execute_transaction.call_args[0][0]
        audit_query = transaction_queries[1][0]

        self.assertIn("member_enrollment_status_history", audit_query)
        self.assertIn("AUTOMATED_CLOSURE", audit_query)
        self.assertIn("ENROLLED", audit_query)
        self.assertIn("UNENROLLED", audit_query)

    def test_update_enrollment_status_handles_exception(self):
        """Test that update handles database exceptions gracefully"""
        # Arrange
        enrollment_id = str(uuid.uuid4())
        member_id = str(uuid.uuid4())
        campaign_id = str(uuid.uuid4())
        campaign_name = "Medicaid DeviceActivation"
        campaign_end_date = date(2026, 1, 15)

        self.mock_db_service.execute_transaction.side_effect = Exception("Database error")

        # Act
        result = self.service._update_enrollment_status(
            enrollment_id, member_id, campaign_id, campaign_name, campaign_end_date
        )

        # Assert
        self.assertFalse(result)

    # ========================================================================
    # Test: Distributed Locking
    # ========================================================================

    def test_acquire_lock_success(self):
        """Test successful lock acquisition"""
        # Arrange
        self.mock_db_service.execute_query.return_value = [{"acquired": 1}]

        # Act
        result = self.service._acquire_lock("test_lock", 50, "test_instance")

        # Assert
        self.assertTrue(result)
        self.mock_db_service.execute_query.assert_called_once()

    def test_acquire_lock_already_held(self):
        """Test lock acquisition when lock is already held"""
        # Arrange
        self.mock_db_service.execute_query.return_value = [{"acquired": 0}]

        # Act
        result = self.service._acquire_lock("test_lock", 50, "test_instance")

        # Assert
        self.assertFalse(result)

    def test_acquire_lock_handles_exception(self):
        """Test lock acquisition handles database exceptions"""
        # Arrange
        self.mock_db_service.execute_query.side_effect = Exception("Database error")

        # Act
        result = self.service._acquire_lock("test_lock", 50, "test_instance")

        # Assert
        self.assertFalse(result)

    def test_release_lock_success(self):
        """Test successful lock release"""
        # Arrange
        self.mock_db_service.execute_query.return_value = 1  # rows affected

        # Act
        self.service._release_lock("test_lock")

        # Assert
        self.mock_db_service.execute_query.assert_called_once()

    def test_release_lock_not_found(self):
        """Test lock release when lock doesn't exist (expired)"""
        # Arrange
        self.mock_db_service.execute_query.return_value = 0  # no rows affected

        # Act
        self.service._release_lock("test_lock")

        # Assert - should not raise exception
        self.mock_db_service.execute_query.assert_called_once()

    # ========================================================================
    # Test: Process Expired Enrollments
    # ========================================================================

    def test_process_expired_enrollments_success(self):
        """Test processing multiple expired enrollments"""
        # Arrange
        campaign_id_1 = str(uuid.uuid4())
        campaign_id_2 = str(uuid.uuid4())

        mock_enrollments = [
            {
                "enrollment_id": str(uuid.uuid4()),
                "member_id": str(uuid.uuid4()),
                "campaign_id": campaign_id_1,
                "campaign_end_date": date(2026, 1, 15),
                "current_status": "ENROLLED",
                "campaign_name": "Medicaid DeviceActivation",
            },
            {
                "enrollment_id": str(uuid.uuid4()),
                "member_id": str(uuid.uuid4()),
                "campaign_id": campaign_id_2,
                "campaign_end_date": date(2026, 1, 10),
                "current_status": "ENROLLED",
                "campaign_name": "DTCMA DeviceActivation",
            },
        ]

        self.mock_db_service.execute_query.return_value = mock_enrollments
        self.mock_db_service.execute_transaction.return_value = None

        # Act
        result = self.service._process_expired_enrollments()

        # Assert
        self.assertEqual(result["enrollments_closed"], 2)
        self.assertEqual(result["members_unenrolled"], 2)
        self.assertEqual(len(result["campaigns_affected"]), 2)
        self.assertIn("Medicaid DeviceActivation", result["campaigns_affected"])
        self.assertIn("DTCMA DeviceActivation", result["campaigns_affected"])

    def test_process_expired_enrollments_no_results(self):
        """Test processing when no expired enrollments exist"""
        # Arrange
        self.mock_db_service.execute_query.return_value = []

        # Act
        result = self.service._process_expired_enrollments()

        # Assert
        self.assertEqual(result["enrollments_closed"], 0)
        self.assertEqual(result["members_unenrolled"], 0)
        self.assertEqual(len(result["campaigns_affected"]), 0)

    def test_process_expired_enrollments_handles_partial_failure(self):
        """Test processing continues after individual enrollment failure"""
        # Arrange
        mock_enrollments = [
            {
                "enrollment_id": str(uuid.uuid4()),
                "member_id": str(uuid.uuid4()),
                "campaign_id": str(uuid.uuid4()),
                "campaign_end_date": date(2026, 1, 15),
                "current_status": "ENROLLED",
                "campaign_name": "Medicaid DeviceActivation",
            },
            {
                "enrollment_id": str(uuid.uuid4()),
                "member_id": str(uuid.uuid4()),
                "campaign_id": str(uuid.uuid4()),
                "campaign_end_date": date(2026, 1, 10),
                "current_status": "ENROLLED",
                "campaign_name": "DTCMA DeviceActivation",
            },
        ]

        self.mock_db_service.execute_query.return_value = mock_enrollments

        # First enrollment fails, second succeeds
        self.mock_db_service.execute_transaction.side_effect = [
            Exception("Database error"),
            None,
        ]

        # Act
        result = self.service._process_expired_enrollments()

        # Assert
        self.assertEqual(result["enrollments_closed"], 1)  # Only second succeeded
        self.assertEqual(
            result["members_unenrolled"], 1
        )  # Only second member counted (first failed)

    # ========================================================================
    # Test: Close Expired Campaigns (Full Flow)
    # ========================================================================

    def test_close_expired_campaigns_with_lock_acquired(self):
        """Test full flow when lock is successfully acquired"""
        # Arrange
        mock_enrollments = [
            {
                "enrollment_id": str(uuid.uuid4()),
                "member_id": str(uuid.uuid4()),
                "campaign_id": str(uuid.uuid4()),
                "campaign_end_date": date(2026, 1, 15),
                "current_status": "ENROLLED",
                "campaign_name": "Medicaid DeviceActivation",
            }
        ]

        # Mock lock acquisition success
        self.mock_db_service.execute_query.side_effect = [
            [{"acquired": 1}],  # Lock acquired
            mock_enrollments,  # Query results
            1,  # Release lock
        ]
        self.mock_db_service.execute_transaction.return_value = None

        # Act
        result = self.service.close_expired_campaigns()

        # Assert
        self.assertEqual(result["enrollments_closed"], 1)
        self.assertGreater(result["execution_duration_seconds"], 0)

    def test_close_expired_campaigns_lock_already_held(self):
        """Test full flow when lock is already held by another instance"""
        # Arrange
        self.mock_db_service.execute_query.return_value = [{"acquired": 0}]

        # Act
        result = self.service.close_expired_campaigns()

        # Assert
        self.assertEqual(result["enrollments_closed"], 0)
        self.assertIn("skipped_reason", result)
        self.assertEqual(result["skipped_reason"], "Lock held by another instance")

    def test_close_expired_campaigns_releases_lock_on_exception(self):
        """Test that lock is released even if processing fails"""
        # Arrange
        self.mock_db_service.execute_query.side_effect = [
            [{"acquired": 1}],  # Lock acquired
            Exception("Processing error"),  # Query fails
        ]

        # Act & Assert
        with self.assertRaises(Exception):
            self.service.close_expired_campaigns()

        # Verify release_lock was called (final execute_query call)
        # Lock acquisition (1 call) + failed query (1 call) + release (1 call)
        self.assertEqual(self.mock_db_service.execute_query.call_count, 3)


if __name__ == "__main__":
    unittest.main()
