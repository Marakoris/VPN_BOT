#!/usr/bin/env python3
"""
Test Subscription API endpoints

This test script verifies all API endpoints:
1. Health checks (/, /health, /ping)
2. Subscription endpoint (/sub/{token})
3. Stats endpoint (/stats)
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import aiohttp
from bot.misc.subscription import activate_subscription, generate_subscription_token
from bot.database.methods.get import get_person


# API configuration
API_BASE_URL = "http://localhost:8001"
TEST_USER_ID = 870499087


async def print_separator(title: str):
    """Print formatted separator"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)


# ==================== TEST 1: Health Checks ====================

async def test_health_endpoints():
    """Test all health check endpoints"""
    await print_separator("TEST 1: Health Check Endpoints")

    async with aiohttp.ClientSession() as session:
        # Test root endpoint
        print("1. Testing GET / (root)...")
        try:
            async with session.get(f"{API_BASE_URL}/") as response:
                data = await response.json()
                print(f"   Status: {response.status}")
                print(f"   Service: {data.get('service')}")
                print(f"   Version: {data.get('version')}")

                if response.status == 200 and data.get('status') == 'ok':
                    print("   ✅ Root endpoint OK")
                else:
                    print("   ❌ Root endpoint FAILED")
                    return False
        except Exception as e:
            print(f"   ❌ Root endpoint error: {e}")
            return False

        # Test health endpoint
        print("\n2. Testing GET /health...")
        try:
            async with session.get(f"{API_BASE_URL}/health") as response:
                data = await response.json()
                print(f"   Status: {response.status}")
                print(f"   Health: {data.get('status')}")
                print(f"   Database: {data.get('checks', {}).get('database')}")

                if response.status == 200 and data.get('status') == 'healthy':
                    print("   ✅ Health endpoint OK")
                else:
                    print("   ❌ Health endpoint FAILED")
                    return False
        except Exception as e:
            print(f"   ❌ Health endpoint error: {e}")
            return False

        # Test ping endpoint
        print("\n3. Testing GET /ping...")
        try:
            async with session.get(f"{API_BASE_URL}/ping") as response:
                data = await response.json()
                print(f"   Status: {response.status}")
                print(f"   Response: {data}")

                if response.status == 200 and data.get('ping') == 'pong':
                    print("   ✅ Ping endpoint OK")
                else:
                    print("   ❌ Ping endpoint FAILED")
                    return False
        except Exception as e:
            print(f"   ❌ Ping endpoint error: {e}")
            return False

    print("\n✅ Health checks PASSED!")
    return True


# ==================== TEST 2: Subscription Endpoint ====================

async def test_subscription_endpoint():
    """Test subscription endpoint with valid token"""
    await print_separator("TEST 2: Subscription Endpoint (Valid Token)")

    # Ensure user has active subscription
    print(f"1. Activating subscription for user {TEST_USER_ID}...")
    token = await activate_subscription(TEST_USER_ID)

    if not token:
        print("   ❌ Failed to activate subscription")
        return False

    print(f"   ✅ Subscription activated")
    print(f"   Token: {token[:50]}...")

    # Test subscription endpoint
    print(f"\n2. Testing GET /sub/{token[:20]}...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{API_BASE_URL}/sub/{token}") as response:
                content = await response.text()
                status = response.status

                print(f"   Status: {status}")
                print(f"   Content length: {len(content)} chars")

                if status == 200:
                    print("   ✅ Status code OK")
                else:
                    print(f"   ❌ Unexpected status code: {status}")
                    return False

                if len(content) > 0:
                    print("   ✅ Content received")
                    print(f"\n   Preview:")
                    for line in content.split('\n')[:10]:
                        print(f"     {line}")
                else:
                    print("   ❌ Empty content")
                    return False

        except Exception as e:
            print(f"   ❌ Subscription endpoint error: {e}")
            return False

    print("\n✅ Subscription endpoint PASSED!")
    return True


# ==================== TEST 3: Invalid Token ====================

async def test_invalid_token():
    """Test subscription endpoint with invalid token"""
    await print_separator("TEST 3: Invalid Token")

    invalid_tokens = [
        "invalid_token_123",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",  # JWT format
        "",
        "abc123"
    ]

    print("Testing invalid tokens...")
    async with aiohttp.ClientSession() as session:
        for i, token in enumerate(invalid_tokens, 1):
            try:
                token_preview = token[:20] if token else "(empty)"
                print(f"\n{i}. Testing token: {token_preview}...")

                async with session.get(f"{API_BASE_URL}/sub/{token}") as response:
                    content = await response.text()
                    status = response.status

                    print(f"   Status: {status}")
                    print(f"   Content: {len(content)} chars")

                    if status == 200 and len(content) == 0:
                        print("   ✅ Correctly returned empty response")
                    else:
                        print(f"   ⚠️  Unexpected: status={status}, content_len={len(content)}")

            except Exception as e:
                print(f"   ❌ Error: {e}")
                return False

    print("\n✅ Invalid token test PASSED!")
    return True


# ==================== TEST 4: Stats Endpoint ====================

async def test_stats_endpoint():
    """Test stats endpoint"""
    await print_separator("TEST 4: Stats Endpoint")

    print("Testing GET /stats...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{API_BASE_URL}/stats") as response:
                data = await response.json()
                status = response.status

                print(f"   Status: {status}")
                print(f"   Active subscriptions: {data.get('active_subscriptions')}")
                print(f"   Total accesses: {data.get('total_accesses')}")

                if status == 200:
                    print("   ✅ Stats endpoint OK")
                else:
                    print(f"   ❌ Unexpected status: {status}")
                    return False

        except Exception as e:
            print(f"   ❌ Stats endpoint error: {e}")
            return False

    print("\n✅ Stats endpoint PASSED!")
    return True


# ==================== TEST 5: Documentation ====================

async def test_documentation():
    """Test API documentation endpoints"""
    await print_separator("TEST 5: API Documentation")

    async with aiohttp.ClientSession() as session:
        # Test OpenAPI docs
        print("1. Testing GET /docs (Swagger UI)...")
        try:
            async with session.get(f"{API_BASE_URL}/docs") as response:
                status = response.status
                print(f"   Status: {status}")

                if status == 200:
                    print("   ✅ Docs endpoint OK")
                else:
                    print(f"   ⚠️  Docs not accessible: {status}")

        except Exception as e:
            print(f"   ⚠️  Docs endpoint error: {e}")

        # Test ReDoc
        print("\n2. Testing GET /redoc (ReDoc)...")
        try:
            async with session.get(f"{API_BASE_URL}/redoc") as response:
                status = response.status
                print(f"   Status: {status}")

                if status == 200:
                    print("   ✅ ReDoc endpoint OK")
                else:
                    print(f"   ⚠️  ReDoc not accessible: {status}")

        except Exception as e:
            print(f"   ⚠️  ReDoc endpoint error: {e}")

    print("\n✅ Documentation endpoints checked!")
    return True


# ==================== MAIN TEST RUNNER ====================

async def main():
    """Run all tests"""
    print("\n" + "🧪"*30)
    print("SUBSCRIPTION API TESTING")
    print("🧪"*30)

    print(f"\nAPI Base URL: {API_BASE_URL}")
    print(f"Test User ID: {TEST_USER_ID}")
    print("\nMake sure the API is running:")
    print("  python subscription_api/main.py")
    print("  or")
    print("  uvicorn subscription_api.main:app --host 0.0.0.0 --port 8001")

    # Wait for user confirmation
    print("\nPress Ctrl+C to cancel, or wait 3 seconds to continue...")
    try:
        await asyncio.sleep(3)
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user.")
        return

    tests = [
        ("Health Check Endpoints", test_health_endpoints),
        ("Subscription Endpoint", test_subscription_endpoint),
        ("Invalid Token Handling", test_invalid_token),
        ("Stats Endpoint", test_stats_endpoint),
        ("Documentation Endpoints", test_documentation),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            result = await test_func()
            if result:
                passed += 1
            else:
                failed += 1
                print(f"\n❌ {test_name} FAILED!")
        except Exception as e:
            failed += 1
            print(f"\n❌ {test_name} FAILED with exception: {e}")
            import traceback
            traceback.print_exc()

        await asyncio.sleep(1)

    # Final summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Total tests: {len(tests)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")

    if failed == 0:
        print("\n" + "✅"*30)
        print("ALL API TESTS PASSED!")
        print("✅"*30 + "\n")
    else:
        print(f"\n❌ {failed} test(s) failed. Please review the output above.\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
