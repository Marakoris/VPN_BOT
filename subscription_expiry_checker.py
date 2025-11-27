#!/usr/bin/env python3
"""
Subscription Expiry Checker - Cronjob

This script runs periodically to check for expired subscriptions
and automatically disables VPN keys for users whose subscription has ended.

Usage:
    python subscription_expiry_checker.py

Schedule with cron or docker-compose to run every N minutes.
"""
import asyncio
import logging
import sys
import time
from datetime import datetime

# Add project root to path
import os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.main import engine
from bot.database.models.main import Persons
from bot.misc.subscription import expire_subscription

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/subscription_expiry.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

log = logging.getLogger(__name__)


async def check_expired_subscriptions():
    """
    Check all users with active subscriptions and expire those that have ended

    Process:
    1. Find all users with subscription_active = true
    2. Check if their subscription timestamp has expired (subscription < current_time)
    3. Call expire_subscription() for expired users
    4. Log results
    """
    log.info("=" * 60)
    log.info("Starting subscription expiry check")
    log.info("=" * 60)

    current_time = int(time.time())
    current_datetime = datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')

    log.info(f"Current time: {current_datetime} (timestamp: {current_time})")

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        try:
            # Get all users with active subscriptions
            statement = select(Persons).filter(
                Persons.subscription_active == True
            )

            result = await db.execute(statement)
            active_users = result.scalars().all()

            log.info(f"Found {len(active_users)} users with active subscriptions")

            if not active_users:
                log.info("No active subscriptions to check")
                return

            # Check each user
            expired_count = 0
            still_active_count = 0
            error_count = 0

            for user in active_users:
                user_sub_end = int(user.subscription)
                user_sub_datetime = datetime.fromtimestamp(user_sub_end).strftime('%Y-%m-%d %H:%M:%S')

                # Check if subscription has expired
                if user_sub_end < current_time:
                    # Subscription expired!
                    time_diff = current_time - user_sub_end
                    hours_expired = time_diff // 3600

                    log.info(
                        f"⚠️  User {user.tgid} subscription EXPIRED "
                        f"({hours_expired}h ago, ended: {user_sub_datetime})"
                    )

                    # Call expire_subscription to disable keys
                    try:
                        success = await expire_subscription(user.tgid)

                        if success:
                            expired_count += 1
                            log.info(f"✅ Successfully expired subscription for user {user.tgid}")
                        else:
                            error_count += 1
                            log.error(f"❌ Failed to expire subscription for user {user.tgid}")

                    except Exception as e:
                        error_count += 1
                        log.error(f"❌ Exception expiring subscription for user {user.tgid}: {e}")
                else:
                    # Subscription still active
                    time_left = user_sub_end - current_time
                    days_left = time_left // 86400
                    hours_left = (time_left % 86400) // 3600

                    still_active_count += 1
                    log.debug(
                        f"✅ User {user.tgid} subscription active "
                        f"({days_left}d {hours_left}h left, ends: {user_sub_datetime})"
                    )

            # Summary
            log.info("=" * 60)
            log.info("Expiry check completed")
            log.info("=" * 60)
            log.info(f"Total active subscriptions checked: {len(active_users)}")
            log.info(f"✅ Still active: {still_active_count}")
            log.info(f"⚠️  Expired and disabled: {expired_count}")
            log.info(f"❌ Errors: {error_count}")
            log.info("=" * 60)

        except Exception as e:
            log.error(f"Fatal error during expiry check: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """Main entry point"""
    log.info("Subscription Expiry Checker started")

    try:
        await check_expired_subscriptions()
        log.info("Subscription Expiry Checker finished successfully")

    except Exception as e:
        log.error(f"Subscription Expiry Checker failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
