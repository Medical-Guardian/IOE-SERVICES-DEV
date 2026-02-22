from enum import Enum


class ErrorSeverity(Enum):
    """
    Enumeration of error severity levels for categorizing different types of issues.

    This classification helps prioritize error handling and response strategies.
    """

    LOW = "low"  # Minor issues that don't affect core functionality
    MEDIUM = "medium"  # Issues that may impact some operations
    HIGH = "high"  # Significant issues affecting multiple operations
    CRITICAL = "critical"  # Severe issues that could halt system operations


class ErrorCategory(Enum):
    """
    Enumeration of error categories for organizing different types of failures.

    This categorization aids in identifying root causes and remediation strategies.
    """

    VALIDATION = "validation"  # Data validation failures
    DATABASE = "database"  # Database connectivity or query issues
    BUSINESS_LOGIC = "business_logic"  # Business rule processing errors
    EXTERNAL_API = "external_api"  # Issues with external service calls
    CONFIGURATION = "configuration"  # Configuration or environment issues
    UNEXPECTED = "unexpected"  # Unforeseen errors requiring investigation
