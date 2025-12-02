"""
Tests for subscription API security features

Stage 6: Security testing
"""
import sys
import os
import time

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from subscription_api.security import (
    SecurityManager,
    SecurityConfig,
    check_rate_limit,
    record_failed_attempt,
    check_suspicious_activity,
    get_security_stats,
    unban_ip
)


def test_rate_limiting():
    """Test rate limiting functionality"""
    print("\n" + "="*70)
    print("TEST 1: Rate Limiting")
    print("="*70)

    # Create security manager with low limits for testing
    config = SecurityConfig()
    config.RATE_LIMIT_REQUESTS = 5
    config.RATE_LIMIT_WINDOW = 10  # 10 seconds

    manager = SecurityManager(config)
    test_ip = "192.168.1.100"

    # Make 5 requests (should all pass)
    print(f"\n1. Making {config.RATE_LIMIT_REQUESTS} requests (should all pass)...")
    for i in range(config.RATE_LIMIT_REQUESTS):
        allowed, error = manager.check_rate_limit(test_ip)
        print(f"   Request {i+1}: {'✅ Allowed' if allowed else '❌ Blocked'}")
        assert allowed, f"Request {i+1} should be allowed"

    # 6th request should be blocked
    print(f"\n2. Making 6th request (should be blocked)...")
    allowed, error = manager.check_rate_limit(test_ip)
    print(f"   Request 6: {'✅ Allowed' if allowed else '❌ Blocked'} - {error}")
    assert not allowed, "6th request should be blocked"
    assert "Rate limit exceeded" in error

    # Wait for window to expire
    print(f"\n3. Waiting {config.RATE_LIMIT_WINDOW + 1} seconds for rate limit to reset...")
    time.sleep(config.RATE_LIMIT_WINDOW + 1)

    # Should be allowed again
    print(f"4. Making request after window (should pass)...")
    allowed, error = manager.check_rate_limit(test_ip)
    print(f"   Request: {'✅ Allowed' if allowed else '❌ Blocked'}")
    assert allowed, "Request should be allowed after window expires"

    print("\n✅ Rate limiting test PASSED!")
    return True


def test_brute_force_protection():
    """Test brute-force protection"""
    print("\n" + "="*70)
    print("TEST 2: Brute-Force Protection")
    print("="*70)

    # Create security manager with low thresholds for testing
    config = SecurityConfig()
    config.BRUTE_FORCE_THRESHOLD = 3
    config.BRUTE_FORCE_WINDOW = 10  # 10 seconds
    config.BRUTE_FORCE_BAN_DURATION = 5  # 5 seconds for testing

    manager = SecurityManager(config)
    test_ip = "192.168.1.101"

    # First, allow some requests
    print(f"\n1. Making normal request...")
    allowed, error = manager.check_rate_limit(test_ip)
    print(f"   Initial request: {'✅ Allowed' if allowed else '❌ Blocked'}")
    assert allowed

    # Record failed attempts
    print(f"\n2. Recording {config.BRUTE_FORCE_THRESHOLD} failed login attempts...")
    for i in range(config.BRUTE_FORCE_THRESHOLD):
        manager.record_failed_attempt(test_ip, "invalid_token")
        print(f"   Failed attempt {i+1} recorded")

    # Should be banned now
    print(f"\n3. Trying to access after {config.BRUTE_FORCE_THRESHOLD} failed attempts...")
    allowed, error = manager.check_rate_limit(test_ip)
    print(f"   Request: {'✅ Allowed' if allowed else '❌ Blocked'} - {error}")
    assert not allowed, "IP should be banned"
    assert "banned" in error.lower()

    # Check stats
    stats = manager.get_stats(test_ip)
    print(f"\n4. IP Stats:")
    print(f"   - Total requests: {stats['total_requests']}")
    print(f"   - Total failed: {stats['total_failed']}")
    print(f"   - Is banned: {stats['is_banned']}")

    # Wait for ban to expire
    print(f"\n5. Waiting {config.BRUTE_FORCE_BAN_DURATION + 1} seconds for ban to expire...")
    time.sleep(config.BRUTE_FORCE_BAN_DURATION + 1)

    # Should be allowed again
    print(f"6. Making request after ban expires...")
    allowed, error = manager.check_rate_limit(test_ip)
    print(f"   Request: {'✅ Allowed' if allowed else '❌ Blocked'}")
    assert allowed, "IP should be unbanned after duration expires"

    print("\n✅ Brute-force protection test PASSED!")
    return True


def test_manual_unban():
    """Test manual IP unbanning"""
    print("\n" + "="*70)
    print("TEST 3: Manual IP Unbanning")
    print("="*70)

    config = SecurityConfig()
    config.BRUTE_FORCE_THRESHOLD = 2
    config.BRUTE_FORCE_BAN_DURATION = 300  # 5 minutes

    manager = SecurityManager(config)
    test_ip = "192.168.1.102"

    # Ban the IP
    print(f"\n1. Banning IP by triggering {config.BRUTE_FORCE_THRESHOLD} failed attempts...")
    for i in range(config.BRUTE_FORCE_THRESHOLD):
        manager.record_failed_attempt(test_ip)

    # Verify banned
    allowed, error = manager.check_rate_limit(test_ip)
    print(f"   IP status: {'✅ Allowed' if allowed else '❌ Banned'}")
    assert not allowed, "IP should be banned"

    # Manually unban
    print(f"\n2. Manually unbanning IP...")
    result = manager.unban_ip(test_ip)
    print(f"   Unban result: {'✅ Success' if result else '❌ Failed'}")
    assert result, "Unban should succeed"

    # Verify unbanned
    print(f"\n3. Checking if IP can access now...")
    allowed, error = manager.check_rate_limit(test_ip)
    print(f"   IP status: {'✅ Allowed' if allowed else '❌ Banned'}")
    assert allowed, "IP should be allowed after manual unban"

    print("\n✅ Manual unban test PASSED!")
    return True


def test_suspicious_activity():
    """Test suspicious activity detection"""
    print("\n" + "="*70)
    print("TEST 4: Suspicious Activity Detection")
    print("="*70)

    config = SecurityConfig()
    config.SUSPICIOUS_THRESHOLD = 5  # Low threshold for testing
    config.SUSPICIOUS_WINDOW = 10  # 10 seconds

    manager = SecurityManager(config)
    test_ip = "192.168.1.103"

    # Make many requests
    print(f"\n1. Making {config.SUSPICIOUS_THRESHOLD} requests rapidly...")
    for i in range(config.SUSPICIOUS_THRESHOLD):
        manager.check_rate_limit(test_ip)
        print(f"   Request {i+1} made")

    # Check for suspicious activity
    print(f"\n2. Checking for suspicious activity...")
    is_suspicious = manager.check_suspicious_activity(test_ip)
    print(f"   Activity suspicious: {'🚨 YES' if is_suspicious else '✅ NO'}")
    assert is_suspicious, "Should detect suspicious activity"

    print("\n✅ Suspicious activity test PASSED!")
    return True


def test_whitelist():
    """Test IP whitelisting"""
    print("\n" + "="*70)
    print("TEST 5: IP Whitelisting")
    print("="*70)

    config = SecurityConfig()
    config.RATE_LIMIT_REQUESTS = 2
    config.IP_WHITELIST = ["127.0.0.1", "192.168.1.200"]

    manager = SecurityManager(config)
    whitelisted_ip = "192.168.1.200"
    normal_ip = "192.168.1.201"

    # Whitelisted IP should never be rate limited
    print(f"\n1. Testing whitelisted IP: {whitelisted_ip}")
    print(f"   Making 10 requests (should all pass)...")
    for i in range(10):
        allowed, error = manager.check_rate_limit(whitelisted_ip)
        if i < 3 or i >= 7:  # Only print first 3 and last 3
            print(f"   Request {i+1}: {'✅ Allowed' if allowed else '❌ Blocked'}")
        elif i == 3:
            print(f"   ...")
        assert allowed, f"Whitelisted IP should always be allowed (request {i+1})"

    # Normal IP should be rate limited
    print(f"\n2. Testing normal IP: {normal_ip}")
    print(f"   Making 3 requests (3rd should be blocked)...")
    for i in range(3):
        allowed, error = manager.check_rate_limit(normal_ip)
        print(f"   Request {i+1}: {'✅ Allowed' if allowed else '❌ Blocked'}")

    # 3rd request should be blocked
    allowed, error = manager.check_rate_limit(normal_ip)
    assert not allowed, "Normal IP should be rate limited"

    print("\n✅ Whitelist test PASSED!")
    return True


def test_global_stats():
    """Test global statistics"""
    print("\n" + "="*70)
    print("TEST 6: Global Statistics")
    print("="*70)

    manager = SecurityManager()

    # Generate some activity
    print(f"\n1. Generating activity from 3 different IPs...")
    ips = ["192.168.1.104", "192.168.1.105", "192.168.1.106"]

    for ip in ips:
        # Make some requests
        for _ in range(5):
            manager.check_rate_limit(ip)
        # Some failed attempts
        manager.record_failed_attempt(ip)

    print(f"   Activity generated")

    # Get global stats
    print(f"\n2. Retrieving global statistics...")
    stats = manager.get_stats()

    print(f"\n   Global Statistics:")
    print(f"   - Total IPs: {stats['total_ips']}")
    print(f"   - Banned IPs: {stats['banned_ips']}")
    print(f"   - Total requests: {stats['total_requests']}")
    print(f"   - Total failed: {stats['total_failed']}")
    print(f"   - Rate limit config: {stats['config']['rate_limit']}")

    assert stats['total_ips'] == 3, "Should track 3 IPs"
    assert stats['total_requests'] == 15, "Should count all requests"
    assert stats['total_failed'] == 3, "Should count all failures"

    print("\n✅ Global stats test PASSED!")
    return True


def main():
    """Run all security tests"""
    print("\n" + "🔒"*35)
    print("SUBSCRIPTION API SECURITY TESTS")
    print("🔒"*35)

    tests = [
        ("Rate Limiting", test_rate_limiting),
        ("Brute-Force Protection", test_brute_force_protection),
        ("Manual Unban", test_manual_unban),
        ("Suspicious Activity", test_suspicious_activity),
        ("IP Whitelisting", test_whitelist),
        ("Global Statistics", test_global_stats),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except AssertionError as e:
            print(f"\n❌ {test_name} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"\n❌ {test_name} ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"✅ Passed: {passed}/{len(tests)}")
    print(f"❌ Failed: {failed}/{len(tests)}")

    if failed == 0:
        print("\n🎉 ALL SECURITY TESTS PASSED! 🎉")
        return True
    else:
        print(f"\n⚠️  {failed} test(s) failed")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
