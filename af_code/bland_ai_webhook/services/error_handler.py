import logging
import smtplib
import json
from email.mime.text import MIMEText
from typing import Dict, Any, Optional, List

# Local application imports
from ..models.error_enums import ErrorSeverity, ErrorCategory
from .config_manager import ConfigManager
from .database_service import DatabaseService
from ..utils.config import ERROR_LOG_TABLE

logger = logging.getLogger(__name__)


class ErrorHandler:
    """
    Manages structured error logging by delegating to the DatabaseService.
    This service centralizes error handling and ensures consistent reporting.
    """

    def __init__(self, config_manager: ConfigManager, db_service: DatabaseService):
        """
        Initializes the ErrorHandler with required service dependencies.
        It no longer manages its own DB connection.

        Args:
            config_manager: The application's configuration manager.
            db_service: The centralized service for all database operations.
        """
        self.config_manager = config_manager
        self.db_service = db_service  # Dependency injection for the database service
        self.error_log_table = ERROR_LOG_TABLE

        # Email notification settings remain the same
        self.smtp_server = self.config_manager.get_config("SMTP_SERVER")
        self.smtp_port = int(self.config_manager.get_config("SMTP_PORT", "587"))
        self.smtp_user = self.config_manager.get_config("SMTP_USER")
        self.smtp_password = self.config_manager.get_config("SMTP_PASSWORD")
        self.notify_email = self.config_manager.get_config("NOTIFY_EMAIL")

        logger.info("🚨 [ERROR-HANDLER] Initialized. Standardized on DatabaseService (pyodbc).")

    def log_validation_error(
        self, request_id: str, webhook_data: Optional[Dict[str, Any]], errors: list
    ) -> None:
        """Logs data validation errors."""
        error_message = "; ".join(errors)
        logger.error(f"❌ [VALIDATION-ERROR] Request {request_id}: {error_message}")
        self._log_to_database(
            request_id=request_id,
            error_message=error_message,
            error_category=ErrorCategory.VALIDATION,
            error_severity=ErrorSeverity.MEDIUM,
            context=webhook_data,
        )

    def log_database_error(
        self,
        request_id: str,
        operation: str,
        error_message: str,
        tables_updated: List[str],
    ) -> None:
        """Logs errors that occur during database operations."""
        logger.error(
            f"💥 [DATABASE-ERROR] Request {request_id} during '{operation}': {error_message}"
        )
        self._log_to_database(
            request_id=request_id,
            error_message=f"Operation '{operation}' failed: {error_message}",
            error_category=ErrorCategory.DATABASE,
            error_severity=ErrorSeverity.HIGH,
            context={"tables_updated": tables_updated},
        )

    def log_critical_error(
        self,
        request_id: str,
        webhook_data: Optional[Dict[str, Any]],
        error_message: str,
        stack_trace: str,
    ) -> None:
        """Logs unexpected critical errors and triggers an email alert."""
        logger.critical(
            f"🚨 [CRITICAL-ERROR] Request {request_id}: {error_message}\nStack Trace: {stack_trace}"
        )
        self._log_to_database(
            request_id=request_id,
            error_message=f"{error_message}\nStack Trace: {stack_trace}",
            error_category=ErrorCategory.UNEXPECTED,
            error_severity=ErrorSeverity.CRITICAL,
            context=webhook_data,
        )
        self._send_email_notification(request_id, error_message, stack_trace)

    def _log_to_database(
        self,
        request_id: str,
        error_message: str,
        error_category: ErrorCategory,
        error_severity: ErrorSeverity,
        context: Optional[Dict[str, Any]],
    ) -> None:
        """
        Writes error details to the database using the centralized DatabaseService.
        """
        try:
            query = f"""
                INSERT INTO {self.error_log_table} 
                (request_id, error_message, error_category, error_severity, context, error_timestamp)
                VALUES (?, ?, ?, ?, ?, GETUTCDATE())
            """
            context_json = json.dumps(context, default=str) if context else None
            params = (
                request_id,
                error_message[:4000],  # Truncate message
                error_category.value,
                error_severity.value,
                context_json,
            )

            # Delegate execution to the centralized DatabaseService.
            self.db_service.execute_query(query, params, fetch_results=False)
            logger.info(
                f"✅ [ERROR-HANDLER] Successfully logged error for request_id: {request_id} to database."
            )

        except Exception as e:
            logger.error(
                f"💥 CRITICAL: FAILED TO LOG ERROR TO DATABASE for request_id {request_id}. Error: {str(e)}"
            )

    def _send_email_notification(
        self, request_id: str, error_message: str, stack_trace: str
    ) -> None:
        """Sends an email notification for critical errors if SMTP is configured."""
        if not all([self.smtp_server, self.smtp_user, self.smtp_password, self.notify_email]):
            logger.warning("⚠️ [ERROR-HANDLER] Email notification skipped: SMTP not configured.")
            return

        try:
            msg_body = (
                f"A critical error occurred in the Bland AI Webhook processing.\n\n"
                f"Request ID: {request_id}\n"
                f"Error: {error_message}\n\n"
                f"Stack Trace:\n{stack_trace}"
            )

            msg = MIMEText(msg_body)
            msg["Subject"] = f"CRITICAL Alert: Bland AI Webhook Failure - Request {request_id}"
            msg["From"] = self.smtp_user
            msg["To"] = self.notify_email

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            logger.info(
                f"📧 [ERROR-HANDLER] Email notification sent successfully for request_id: {request_id}"
            )
        except Exception as e:
            logger.error(
                f"💥 [ERROR-HANDLER] Failed to send email notification for request_id {request_id}: {str(e)}"
            )
