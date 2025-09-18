from typing import List
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """
    Container for validation results that provides clear feedback about data quality.

    This class acts as a quality control report, indicating whether the incoming
    data meets standards and detailing any errors or warnings.
    """
    is_valid: bool
    errors: List[str]
    warnings: List[str]