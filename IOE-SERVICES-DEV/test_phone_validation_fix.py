"""
Quick test to verify phone number validation fix
Tests the 3 rules:
1. 10 digits → REJECT
2. 11 digits starting with 1 → ACCEPT (add + prefix)
3. 12+ digits → REJECT
"""

import sys
sys.path.insert(0, '/home/zubair-ashfaque/MG-IOE/Azure Function/Azure_function_Deployment/IOE-functions')

from af_code.shared.phone_utils import standardize_phone

def test_phone_validation():
    print("Testing Phone Number Validation Fix")
    print("=" * 60)

    # Test Case 1: 10 digits (should REJECT)
    print("\n✅ Test Case 1: 10-digit number (should REJECT)")
    result = standardize_phone("8123654567")
    expected = None
    status = "✅ PASS" if result == expected else f"❌ FAIL (got {result})"
    print(f"   Input: 8123654567")
    print(f"   Expected: {expected}")
    print(f"   Got: {result}")
    print(f"   {status}")

    # Test Case 2: 11 digits starting with 1 (should ACCEPT)
    print("\n✅ Test Case 2: 11-digit number starting with 1 (should ACCEPT)")
    result = standardize_phone("18123654567")
    expected = "+18123654567"  # Add + prefix to 11 digits
    status = "✅ PASS" if result == expected else f"❌ FAIL (got {result})"
    print(f"   Input: 18123654567")
    print(f"   Expected: {expected}")
    print(f"   Got: {result}")
    print(f"   {status}")

    # Test Case 3: 12 digits (should REJECT)
    print("\n✅ Test Case 3: 12-digit number (should REJECT)")
    result = standardize_phone("181236514122")
    expected = None
    status = "✅ PASS" if result == expected else f"❌ FAIL (got {result})"
    print(f"   Input: 181236514122")
    print(f"   Expected: {expected}")
    print(f"   Got: {result}")
    print(f"   {status}")

    # Test Case 4: 11 digits NOT starting with 1 (should REJECT)
    print("\n✅ Test Case 4: 11-digit number NOT starting with 1 (should REJECT)")
    result = standardize_phone("28123654567")
    expected = None
    status = "✅ PASS" if result == expected else f"❌ FAIL (got {result})"
    print(f"   Input: 28123654567")
    print(f"   Expected: {expected}")
    print(f"   Got: {result}")
    print(f"   {status}")

    # Test Case 5: Already has + prefix (should pass through)
    print("\n✅ Test Case 5: Already has + prefix (should ACCEPT)")
    result = standardize_phone("+18123654567")  # Correct: 11 digits after +
    expected = "+18123654567"
    status = "✅ PASS" if result == expected else f"❌ FAIL (got {result})"
    print(f"   Input: +18123654567")
    print(f"   Expected: {expected}")
    print(f"   Got: {result}")
    print(f"   {status}")

    print("\n" + "=" * 60)
    print("All tests completed!")

if __name__ == "__main__":
    test_phone_validation()
