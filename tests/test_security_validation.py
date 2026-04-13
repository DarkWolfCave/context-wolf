#!/usr/bin/env python3
"""
Security Validation Tests for Test Management System

Tests:
- Command sanitization (injection prevention)
- Input validation (length limits, whitelist)
- Timeout enforcement
- Output size limits
- Path traversal prevention
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.features.test_runner import TestSecurityValidator, TestRunner
from src.features.test_management import TestSanitizer
from src.core.database import Database


def test_command_sanitization():
    """Test dangerous command detection"""
    print("\n🔒 Test 1: Command Sanitization")

    validator = TestSecurityValidator()

    # Valid commands should pass
    try:
        validator.sanitize_command("python3 test.py")
        print("  ✅ Valid command accepted: python3 test.py")
    except ValueError as e:
        print(f"  ❌ False positive: {e}")
        return False

    # Dangerous commands should be rejected
    dangerous_commands = [
        "rm -rf /",
        "dd if=/dev/zero of=/dev/sda",
        ":(){ :|:& };:",  # Fork bomb
        "mkfs.ext4 /dev/sda1",
    ]

    for cmd in dangerous_commands:
        try:
            validator.sanitize_command(cmd)
            print(f"  ❌ Dangerous command NOT blocked: {cmd}")
            return False
        except ValueError:
            print(f"  ✅ Dangerous command blocked: {cmd[:30]}...")

    return True


def test_input_length_limits():
    """Test length limit enforcement"""
    print("\n🔒 Test 2: Input Length Limits")

    validator = TestSecurityValidator()

    # Command too long
    try:
        long_command = "a" * 3000
        validator.sanitize_command(long_command)
        print("  ❌ Long command NOT rejected")
        return False
    except ValueError as e:
        print(f"  ✅ Long command rejected: {e}")

    # Timeout too high
    try:
        validator.validate_timeout(5000)
        print("  ❌ High timeout NOT rejected")
        return False
    except ValueError as e:
        print(f"  ✅ High timeout rejected: {e}")

    # Valid timeout
    try:
        timeout = validator.validate_timeout(300)
        print(f"  ✅ Valid timeout accepted: {timeout}s")
    except ValueError as e:
        print(f"  ❌ False positive: {e}")
        return False

    return True


def test_output_truncation():
    """Test output size limit enforcement"""
    print("\n🔒 Test 3: Output Truncation")

    validator = TestSecurityValidator()

    # Small output should not be truncated
    small_output = "test" * 100
    result = validator.truncate_output(small_output)
    if len(result) == len(small_output):
        print(f"  ✅ Small output not truncated: {len(result)} bytes")
    else:
        print(f"  ❌ Small output incorrectly truncated")
        return False

    # Large output should be truncated
    large_output = "x" * (11 * 1024 * 1024)  # 11MB
    result = validator.truncate_output(large_output)
    if len(result) < len(large_output) and "[... Output truncated" in result:
        print(f"  ✅ Large output truncated: {len(large_output)} → {len(result)} bytes")
    else:
        print(f"  ❌ Large output NOT truncated")
        return False

    return True


def test_data_sanitization():
    """Test test data sanitization"""
    print("\n🔒 Test 4: Data Sanitization")

    sanitizer = TestSanitizer()

    # Test name with control characters
    data = {
        'name': "Test\x00Name\x01With\x02Control",
        'description': "A" * 20000,  # Too long
        'tags': ["tag1", "tag2", "tag3" * 100]  # Long tag
    }

    try:
        sanitized = sanitizer.sanitize_test_data(data)

        # Name should be cleaned
        if '\x00' in sanitized['name'] or '\x01' in sanitized['name']:
            print("  ❌ Control characters NOT removed from name")
            return False
        else:
            print(f"  ✅ Control characters removed: '{sanitized['name']}'")

        # Description should be truncated
        if len(sanitized['description']) > TestSanitizer.MAX_DESCRIPTION_LENGTH:
            print(f"  ❌ Description NOT truncated: {len(sanitized['description'])} bytes")
            return False
        else:
            print(f"  ✅ Description truncated: {len(sanitized['description'])} bytes")

        # Long tags should be truncated
        for tag in sanitized['tags']:
            if len(tag) > TestSanitizer.MAX_TAG_LENGTH:
                print(f"  ❌ Tag NOT truncated: {len(tag)} chars")
                return False
        print(f"  ✅ Tags truncated to max length")

    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return False

    return True


def test_priority_whitelist():
    """Test priority whitelist validation"""
    print("\n🔒 Test 5: Priority Whitelist")

    sanitizer = TestSanitizer()

    # Valid priority
    try:
        data = {'priority': 'high'}
        sanitized = sanitizer.sanitize_test_data(data)
        print(f"  ✅ Valid priority accepted: {sanitized['priority']}")
    except ValueError as e:
        print(f"  ❌ False positive: {e}")
        return False

    # Invalid priority
    try:
        data = {'priority': 'super_urgent_critical'}
        sanitized = sanitizer.sanitize_test_data(data)
        print(f"  ❌ Invalid priority NOT rejected: {sanitized['priority']}")
        return False
    except ValueError as e:
        print(f"  ✅ Invalid priority rejected: {e}")

    return True


def test_working_directory_validation():
    """Test working directory validation"""
    print("\n🔒 Test 6: Working Directory Validation")

    validator = TestSecurityValidator()

    # Non-existent directory should fail
    try:
        validator.validate_working_directory("/non/existent/path")
        print("  ❌ Non-existent directory NOT rejected")
        return False
    except ValueError as e:
        print(f"  ✅ Non-existent directory rejected: {e}")

    # Valid directory should pass (use /tmp which should exist)
    try:
        import tempfile
        temp_dir = tempfile.gettempdir()
        path = validator.validate_working_directory(temp_dir)
        print(f"  ✅ Valid directory accepted: {path}")
    except ValueError as e:
        print(f"  ❌ False positive: {e}")
        return False

    return True


def run_all_tests():
    """Run all security tests"""
    print("=" * 60)
    print("🔒 SECURITY VALIDATION TEST SUITE")
    print("=" * 60)

    tests = [
        test_command_sanitization,
        test_input_length_limits,
        test_output_truncation,
        test_data_sanitization,
        test_priority_whitelist,
        test_working_directory_validation,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n❌ Test crashed: {test.__name__}")
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: ✅ {passed} passed | ❌ {failed} failed")
    print("=" * 60)

    if failed == 0:
        print("\n🎉 All security tests passed!")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(run_all_tests())
