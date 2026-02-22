#!/usr/bin/env python3
"""
Unit tests for safe_value() function in DTC logic.

Tests the NaN to None conversion utility that prevents SQL error 207.
"""

import pandas as pd
import numpy as np
from af_code.af_dtc_logic import safe_value


def test_safe_value():
    """Test safe_value() function handles all edge cases correctly."""
    print("Testing safe_value() function...")

    # Test 1: numpy NaN
    result = safe_value(np.nan)
    assert result is None, f"numpy.nan should return None, got {result}"
    print("✅ Test 1 passed: numpy.nan → None")

    # Test 2: pandas NA
    result = safe_value(pd.NA)
    assert result is None, f"pandas.NA should return None, got {result}"
    print("✅ Test 2 passed: pandas.NA → None")

    # Test 3: None value
    result = safe_value(None)
    assert result is None, f"None should return None, got {result}"
    print("✅ Test 3 passed: None → None")

    # Test 4: String value
    result = safe_value("test")
    assert result == "test", f"String should pass through, got {result}"
    print("✅ Test 4 passed: 'test' → 'test'")

    # Test 5: Integer value
    result = safe_value(123)
    assert result == 123, f"Integer should pass through, got {result}"
    print("✅ Test 5 passed: 123 → 123")

    # Test 6: Zero value
    result = safe_value(0)
    assert result == 0, f"Zero should pass through, got {result}"
    print("✅ Test 6 passed: 0 → 0")

    # Test 7: Empty string
    result = safe_value("")
    assert result == "", f"Empty string should pass through, got {result}"
    print("✅ Test 7 passed: '' → ''")

    # Test 8: Default parameter with None (pd.isna(None) is True, so returns None)
    result = safe_value(None, default="default")
    assert result is None, f"None should return None (pd.isna catches it first), got {result}"
    print("✅ Test 8 passed: None with default='default' → None (pd.isna catches None)")

    # Test 9: Default parameter with NaN
    result = safe_value(np.nan, default="default")
    assert result is None, f"NaN should return None (ignore default), got {result}"
    print("✅ Test 9 passed: np.nan with default='default' → None")

    # Test 10: Float value
    result = safe_value(3.14)
    assert result == 3.14, f"Float should pass through, got {result}"
    print("✅ Test 10 passed: 3.14 → 3.14")

    # Test 11: Boolean value
    result = safe_value(True)
    assert result is True, f"Boolean should pass through, got {result}"
    print("✅ Test 11 passed: True → True")

    # Test 12: False boolean
    result = safe_value(False)
    assert result is False, f"False should pass through, got {result}"
    print("✅ Test 12 passed: False → False")

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED! safe_value() is working correctly.")
    print("=" * 60)


def test_pandas_series_behavior():
    """
    Demonstrate the pandas Series.get() NaN issue that safe_value() fixes.
    """
    print("\n" + "=" * 60)
    print("Demonstrating pandas Series.get() NaN behavior:")
    print("=" * 60)

    # Create a Series with NaN
    row = pd.Series({"unenrollment_reason": np.nan, "name": "Maria"})

    # Show the problem: .get() returns NaN, not None
    value = row.get("unenrollment_reason", None)
    print(f"\nrow.get('unenrollment_reason', None) returns:")
    print(f"  Value: {value}")
    print(f"  Type: {type(value)}")
    print(f"  Is None: {value is None}")
    print(f"  Is NaN: {pd.isna(value)}")
    print(f"  ❌ PROBLEM: .get() returns NaN, NOT None!")

    # Show the solution: safe_value() converts NaN to None
    safe_val = safe_value(value)
    print(f"\nsafe_value(value) returns:")
    print(f"  Value: {safe_val}")
    print(f"  Type: {type(safe_val)}")
    print(f"  Is None: {safe_val is None}")
    print(f"  ✅ SOLUTION: safe_value() converts NaN → None")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    try:
        test_safe_value()
        test_pandas_series_behavior()
        print("\n🎉 All safe_value() tests completed successfully!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        exit(1)
