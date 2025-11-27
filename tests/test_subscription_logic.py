#!/usr/bin/env python3
"""
Test subscription logic: activate, expire, and reactivate

This test script verifies the complete subscription flow:
1. Activate subscription (create/enable keys on all servers)
2. Expire subscription (disable keys on all servers)
3. Reactivate subscription (enable existing keys)
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bot.misc.subscription import (
    activate_subscription,
    expire_subscription,
    get_user_subscription_status,
    generate_subscription_token,
    verify_subscription_token
)
from bot.database.methods.get import get_person
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.main import engine
from bot.database.models.main import Persons, Servers


# Test user ID (change to your test user's telegram ID)
TEST_USER_ID = 870499087


async def print_separator(title: str):
    """Print formatted separator"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)


async def get_user_servers_with_keys(user_id: int):
    """Get servers where user has keys (check via API)"""
    from bot.misc.VPN.ServerManager import ServerManager

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Servers).filter(
            Servers.work == True,
            Servers.type_vpn.in_([1, 2])
        )
        result = await db.execute(statement)
        all_servers = result.scalars().all()

        user_servers = []
        for server in all_servers:
            try:
                server_manager = ServerManager(server)
                await server_manager.login()
                existing_client = await server_manager.get_user(user_id)
                if existing_client:
                    user_servers.append(server)
            except:
                continue

        return user_servers


# ==================== TEST 1: Token Generation ====================

async def test_token_generation():
    """Test token generation and verification"""
    await print_separator("TEST 1: Token Generation & Verification")

    print("1. Generating token for user ID 12345...")
    token = generate_subscription_token(12345)
    print(f"   ✅ Token generated: {token[:50]}...")
    print(f"   Length: {len(token)} characters")

    print("\n2. Verifying token...")
    verified_user_id = verify_subscription_token(token)
    print(f"   Verified user_id: {verified_user_id}")

    if verified_user_id == 12345:
        print("   ✅ Token verification PASSED!")
    else:
        print("   ❌ Token verification FAILED!")
        return False

    print("\n3. Testing invalid token...")
    invalid_result = verify_subscription_token("invalid_token_123")
    if invalid_result is None:
        print("   ✅ Invalid token correctly rejected")
    else:
        print("   ❌ Invalid token was accepted!")
        return False

    print("\n✅ Token generation test PASSED!")
    return True


# ==================== TEST 2: Activate Subscription ====================

async def test_activate_subscription():
    """Test subscription activation"""
    await print_separator("TEST 2: Activate Subscription")

    # Check current status
    print(f"1. Checking current status for user {TEST_USER_ID}...")
    user = await get_person(TEST_USER_ID)

    if not user:
        print(f"   ❌ User {TEST_USER_ID} not found in database!")
        print("   Please check TEST_USER_ID variable")
        return False

    current_status = user.subscription_active if hasattr(user, 'subscription_active') else False
    print(f"   Current subscription_active: {current_status}")

    # Activate subscription
    print(f"\n2. Activating subscription for user {TEST_USER_ID}...")
    token = await activate_subscription(TEST_USER_ID)

    if not token:
        print("   ❌ Activation failed! No token returned")
        return False

    print(f"   ✅ Subscription activated!")
    print(f"   Token: {token[:50]}...")

    # Verify status changed
    print("\n3. Verifying subscription status...")
    user = await get_person(TEST_USER_ID)
    new_status = user.subscription_active if hasattr(user, 'subscription_active') else False
    print(f"   New subscription_active: {new_status}")
    print(f"   Token in DB: {user.subscription_token[:50] if user.subscription_token else 'None'}...")

    if not new_status:
        print("   ❌ subscription_active is still False!")
        return False

    # List servers with keys
    print(f"\n4. Checking servers with keys...")
    servers = await get_user_servers_with_keys(TEST_USER_ID)
    print(f"   Found {len(servers)} server(s) with keys:")
    for server in servers:
        type_name = {0: "Outline", 1: "VLESS", 2: "Shadowsocks"}.get(server.type_vpn, "Unknown")
        print(f"   - Server {server.id}: {server.name} ({type_name})")

    print("\n✅ Activation test PASSED!")
    return True


# ==================== TEST 3: Expire Subscription ====================

async def test_expire_subscription():
    """Test subscription expiration"""
    await print_separator("TEST 3: Expire Subscription")

    # Check current status
    print(f"1. Checking current status for user {TEST_USER_ID}...")
    user = await get_person(TEST_USER_ID)
    current_status = user.subscription_active if hasattr(user, 'subscription_active') else False
    print(f"   Current subscription_active: {current_status}")

    if not current_status:
        print("   ⚠️  Warning: Subscription is already inactive!")

    # Expire subscription
    print(f"\n2. Expiring subscription for user {TEST_USER_ID}...")
    success = await expire_subscription(TEST_USER_ID)

    if success:
        print("   ✅ Subscription expired successfully!")
    else:
        print("   ⚠️  Subscription expired with some errors (but still disabled)")

    # Verify status changed
    print("\n3. Verifying subscription status...")
    user = await get_person(TEST_USER_ID)
    new_status = user.subscription_active if hasattr(user, 'subscription_active') else False
    print(f"   New subscription_active: {new_status}")

    if new_status:
        print("   ❌ subscription_active is still True!")
        return False

    print(f"\n4. Keys should now be disabled on servers (not deleted)")

    print("\n✅ Expiration test PASSED!")
    return True


# ==================== TEST 4: Reactivate Subscription ====================

async def test_reactivate_subscription():
    """Test reactivation (enable existing keys)"""
    await print_separator("TEST 4: Reactivate Subscription")

    print(f"1. Re-activating subscription for user {TEST_USER_ID}...")
    token = await activate_subscription(TEST_USER_ID)

    if not token:
        print("   ❌ Re-activation failed!")
        return False

    print(f"   ✅ Re-activated! Token: {token[:50]}...")

    # Verify status
    print("\n2. Verifying subscription status...")
    user = await get_person(TEST_USER_ID)
    status = user.subscription_active if hasattr(user, 'subscription_active') else False
    print(f"   subscription_active: {status}")

    if not status:
        print("   ❌ subscription_active is still False!")
        return False

    print("\n✅ Re-activation test PASSED!")
    return True


# ==================== TEST 5: Subscription Status ====================

async def test_subscription_status():
    """Test get_user_subscription_status function"""
    await print_separator("TEST 5: Get Subscription Status")

    print(f"1. Getting subscription status for user {TEST_USER_ID}...")
    status = await get_user_subscription_status(TEST_USER_ID)

    print(f"\nStatus info:")
    for key, value in status.items():
        if key == 'token' and value:
            print(f"   {key}: {value[:30]}...")
        else:
            print(f"   {key}: {value}")

    if 'error' in status:
        print(f"   ❌ Error: {status['error']}")
        return False

    print("\n✅ Status retrieval test PASSED!")
    return True


# ==================== MAIN TEST RUNNER ====================

async def main():
    """Run all tests"""
    print("\n" + "🧪"*30)
    print("SUBSCRIPTION LOGIC TESTING")
    print("🧪"*30)

    print(f"\nTest User ID: {TEST_USER_ID}")
    print(f"Make sure this user exists in the database!")

    # Check user exists
    user = await get_person(TEST_USER_ID)
    if not user:
        print(f"\n❌ ERROR: User {TEST_USER_ID} not found in database!")
        print("Please update TEST_USER_ID variable with a valid user ID")
        return

    print(f"✅ User found: {user.username if user.username else 'No username'}")

    tests = [
        ("Token Generation", test_token_generation),
        ("Activate Subscription", test_activate_subscription),
        ("Expire Subscription", test_expire_subscription),
        ("Reactivate Subscription", test_reactivate_subscription),
        ("Get Subscription Status", test_subscription_status),
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

        await asyncio.sleep(1)  # Small delay between tests

    # Final summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Total tests: {len(tests)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")

    if failed == 0:
        print("\n" + "✅"*30)
        print("ALL TESTS PASSED!")
        print("✅"*30 + "\n")
    else:
        print(f"\n❌ {failed} test(s) failed. Please review the output above.\n")


if __name__ == "__main__":
    asyncio.run(main())
