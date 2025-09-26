from typing import List, Optional
from dataclasses import dataclass


@dataclass
class UpdateResult:
    """
    Container for database update operation results.

    This class serves as a comprehensive report for database operations, detailing
    success status, affected tables, and any errors encountered.
    """

    success: bool
    tables_updated: List[str]
    error_message: Optional[str]
    records_affected: int
    operation_duration_ms: int
