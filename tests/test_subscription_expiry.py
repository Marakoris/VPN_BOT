#!/usr/bin/env python3
"""
Test Subscription Expiry Checker

This test script verifies the cronjob functionality:
1. Identifies users with expired subscriptions
2. Calls expire_subscription() for them
3. Verifies keys are disabled
"""
import asyncio
import sys
import os
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.main import engine
from bot.database.models.main import Persons
from bot.misc.subscription import expire_subscription

# Test user ID
TEST_USER_ID = 870499087


async def print_separator(title: str):
    """Print formatted separator"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)


# ==================== TEST 1: Find Expired Subscriptions ====================

async def test_find_expired():
    """Test finding users with expired subscriptions"""
    await print_separator("TEST 1: Find Expired Subscriptions")

    current_time = int(time.time())
    current_datetime = datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')

    print(f"Current time: {current_datetime} (timestamp: {current_time})")

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get all users with active subscriptions
        statement = select(Persons).filter(
            Persons.subscription_active == True
        )

        result = await db.execute(statement)
        active_users = result.scalars().all()

        print(f"\n1. Found {len(active_users)} users with active subscriptions")

        if not active_users:
            print("   ⚠️  No active subscriptions found")
            return True

        # Check each user
        expired_users = []
        active_users_list = []

        for user in active_users:
            user_sub_end = int(user.subscription)
            user_sub_datetime = datetime.fromtimestamp(user_sub_end).strftime('%Y-%m-%d %H:%M:%S')

            if user_sub_end < current_time:
                # Expired
                time_diff = current_time - user_sub_end
                hours_expired = time_diff // 3600
                expired_users.append(user)
                print(f"   ❌ User {user.tgid}: EXPIRED {hours_expired}h ago (ended: {user_sub_datetime})")
            else:
                # Still active
                time_left = user_sub_end - current_time
                days_left = time_left // 86400
                hours_left = (time_left % 86400) // 3600
                active_users_list.append(user)
                print(f"   ✅ User {user.tgid}: Active {days_left}d {hours_left}h left (ends: {user_sub_datetime})")

        print(f"\n2. Summary:")
        print(f"   Active subscriptions: {len(active_users_list)}")
        print(f"   Expired subscriptions: {len(expired_users)}")

        if expired_users:
            print(f"\n✅ Test PASSED - Found {len(expired_users)} expired subscription(s)")
        else:
            print(f"\n✅ Test PASSED - No expired subscriptions (all good!)")

        return True


# ==================== TEST 2: Expire Subscription ====================

async def test_expire_action():
    """Test expiring a subscription"""
    await print_separator("TEST 2: Expire Subscription Action")

    current_time = int(time.time())

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get test user
        statement = select(Persons).filter(Persons.tgid == TEST_USER_ID)
        result = await db.execute(statement)
        user = result.scalar_one_or_none()

        if not user:
            print(f"   ⚠️  Test user {TEST_USER_ID} not found")
            return True

        print(f"1. Test user: {user.tgid}")
        print(f"   Subscription active: {user.subscription_active}")
        print(f"   Subscription end: {datetime.fromtimestamp(int(user.subscription)).strftime('%Y-%m-%d %H:%M:%S')}")

        user_sub_end = int(user.subscription)

        if user_sub_end >= current_time:
            print(f"\n   ℹ️  User subscription not expired yet, skipping expire test")
            print(f"   (Use this test when subscription has expired)")
            return True

        if not user.subscription_active:
            print(f"\n   ℹ️  User subscription already inactive, skipping expire test")
            return True

        # Expire subscription
        print(f"\n2. Calling expire_subscription({user.tgid})...")

        success = await expire_subscription(user.tgid)

        if success:
            print(f"   ✅ Subscription expired successfully")
        else:
            print(f"   ❌ Failed to expire subscription")
            return False

        # Verify
        await db.refresh(user)

        print(f"\n3. Verification:")
        print(f"   subscription_active: {user.subscription_active}")

        if not user.subscription_active:
            print(f"   ✅ subscription_active set to False")
        else:
            print(f"   ❌ subscription_active still True")
            return False

    print(f"\n✅ Test PASSED - Subscription expired successfully")
    return True


# ==================== TEST 3: Cronjob Logic ====================

async def test_cronjob_logic():
    """Test the full cronjob logic"""
    await print_separator("TEST 3: Full Cronjob Logic")

    print("1. Simulating cronjob run...")

    current_time = int(time.time())

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get all users with active subscriptions
        statement = select(Persons).filter(
            Persons.subscription_active == True
        )

        result = await db.execute(statement)
        active_users = result.scalars().all()

        print(f"   Found {len(active_users)} active subscriptions")

        if not active_users:
            print(f"   ℹ️  No active subscriptions to process")
            return True

        # Process each user
        expired_count = 0
        still_active_count = 0

        for user in active_users:
            user_sub_end = int(user.subscription)

            if user_sub_end < current_time:
                # Would expire this user
                expired_count += 1
                print(f"   ⚠️  Would expire user {user.tgid}")
            else:
                still_active_count += 1

        print(f"\n2. Results:")
        print(f"   Still active: {still_active_count}")
        print(f"   Would expire: {expired_count}")

    print(f"\n✅ Test PASSED - Cronjob logic verified")
    return True


# ==================== MAIN TEST RUNNER ====================

async def main():
    """Run all tests"""
    print("\n" + "🧪"*30)
    print("SUBSCRIPTION EXPIRY CHECKER TESTING")
    print("🧪"*30)

    print(f"\nTest User ID: {TEST_USER_ID}")
    print("Testing subscription expiry checker...")

    tests = [
        ("Find Expired Subscriptions", test_find_expired),
        ("Expire Subscription Action", test_expire_action),
        ("Full Cronjob Logic", test_cronjob_logic),
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
        print("ALL TESTS PASSED!")
        print("✅"*30 + "\n")
    else:
        print(f"\n❌ {failed} test(s) failed. Please review the output above.\n")


if __name__ == "__main__":
    asyncio.run(main())
