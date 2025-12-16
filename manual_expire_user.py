#!/usr/bin/env python3
"""
Manual script to expire subscription for a specific user
This will disable all keys on all servers
"""
import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from bot.misc.subscription import expire_subscription


async def main():
    user_id = 870499087

    print(f"[Manual Expire] Starting subscription expiry for user {user_id}")
    print(f"[Manual Expire] This will disable all keys on all servers (VLESS, Shadowsocks, Outline)")

    try:
        success = await expire_subscription(user_id)

        if success:
            print(f"[Manual Expire] ✅ SUCCESS: Subscription expired and all keys disabled for user {user_id}")
        else:
            print(f"[Manual Expire] ⚠️ WARNING: Subscription expired but some keys may not be disabled")

    except Exception as e:
        print(f"[Manual Expire] ❌ ERROR: Failed to expire subscription: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
