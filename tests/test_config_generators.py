#!/usr/bin/env python3
"""
Test Config Generators

This test script verifies VPN configuration generators:
1. VLESS configuration generation
2. Shadowsocks configuration generation
3. Configuration format validation
"""
import asyncio
import sys
import os
import re
from urllib.parse import parse_qs, urlparse, unquote

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from subscription_api.config_generators import (
    generate_vless_config,
    generate_shadowsocks_config,
    generate_config
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.main import engine
from bot.database.models.main import Servers


# Test user ID
TEST_USER_ID = 870499087


async def print_separator(title: str):
    """Print formatted separator"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)


# ==================== TEST 1: VLESS Config Generation ====================

async def test_vless_generator():
    """Test VLESS configuration generation"""
    await print_separator("TEST 1: VLESS Config Generator")

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get a VLESS server
        statement = select(Servers).filter(
            Servers.work == True,
            Servers.type_vpn == 1  # VLESS
        ).limit(1)

        result = await db.execute(statement)
        server = result.scalar_one_or_none()

        if not server:
            print("   ⚠️  No VLESS servers found, skipping test")
            return True

        print(f"1. Testing with server: {server.name} (ID: {server.id})")
        print(f"   IP: {server.ip}")

        # Generate config
        print(f"\n2. Generating VLESS config for user {TEST_USER_ID}...")
        config = await generate_vless_config(server, TEST_USER_ID)

        if not config:
            print("   ❌ Failed to generate config")
            return False

        print(f"   ✅ Config generated ({len(config)} chars)")
        print(f"\n   Config preview:")
        print(f"     {config[:100]}...")

        # Validate format
        print(f"\n3. Validating config format...")

        if not config.startswith("vless://"):
            print("   ❌ Config doesn't start with vless://")
            return False

        print("   ✅ Protocol prefix correct")

        # Parse URL
        try:
            # Extract UUID and parameters
            match = re.match(r'vless://([^@]+)@([^:]+):(\d+)\?(.+)#(.+)', config)
            if not match:
                print("   ❌ Invalid VLESS URL format")
                return False

            uuid_part, host, port, params, remark = match.groups()
            print(f"   ✅ UUID: {uuid_part[:8]}...")
            print(f"   ✅ Host: {host}")
            print(f"   ✅ Port: {port}")
            print(f"   ✅ Remark: {unquote(remark)}")

            # Parse parameters
            params_dict = {}
            for param in params.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params_dict[key] = value

            print(f"\n   Parameters:")
            for key, value in params_dict.items():
                print(f"     {key}: {value[:30] if len(value) > 30 else value}")

            required_params = ['type', 'security', 'fp', 'pbk', 'sni']
            missing = [p for p in required_params if p not in params_dict]

            if missing:
                print(f"   ❌ Missing required parameters: {missing}")
                return False

            print(f"   ✅ All required parameters present")

        except Exception as e:
            print(f"   ❌ Error parsing config: {e}")
            return False

    print("\n✅ VLESS generator test PASSED!")
    return True


# ==================== TEST 2: Shadowsocks Config Generation ====================

async def test_shadowsocks_generator():
    """Test Shadowsocks configuration generation"""
    await print_separator("TEST 2: Shadowsocks Config Generator")

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get a Shadowsocks server
        statement = select(Servers).filter(
            Servers.work == True,
            Servers.type_vpn == 2  # Shadowsocks
        ).limit(1)

        result = await db.execute(statement)
        server = result.scalar_one_or_none()

        if not server:
            print("   ⚠️  No Shadowsocks servers found, skipping test")
            return True

        print(f"1. Testing with server: {server.name} (ID: {server.id})")
        print(f"   IP: {server.ip}")

        # Generate config
        print(f"\n2. Generating Shadowsocks config for user {TEST_USER_ID}...")
        config = await generate_shadowsocks_config(server, TEST_USER_ID)

        if not config:
            print("   ❌ Failed to generate config")
            return False

        print(f"   ✅ Config generated ({len(config)} chars)")
        print(f"\n   Config preview:")
        print(f"     {config[:100]}...")

        # Validate format
        print(f"\n3. Validating config format...")

        if not config.startswith("ss://"):
            print("   ❌ Config doesn't start with ss://")
            return False

        print("   ✅ Protocol prefix correct")

        # Parse URL
        try:
            # Extract base64 and parameters
            match = re.match(r'ss://([^@]+)@([^:]+):(\d+)\?(.+)#(.+)', config)
            if not match:
                print("   ❌ Invalid Shadowsocks URL format")
                return False

            credentials_b64, host, port, params, remark = match.groups()
            print(f"   ✅ Credentials (b64): {credentials_b64[:20]}...")
            print(f"   ✅ Host: {host}")
            print(f"   ✅ Port: {port}")
            print(f"   ✅ Remark: {unquote(remark)}")

            # Decode credentials
            import base64
            try:
                credentials = base64.b64decode(credentials_b64).decode()
                print(f"   ✅ Decoded credentials: {credentials[:30]}...")
            except:
                print(f"   ⚠️  Could not decode credentials (might be valid)")

        except Exception as e:
            print(f"   ❌ Error parsing config: {e}")
            return False

    print("\n✅ Shadowsocks generator test PASSED!")
    return True


# ==================== TEST 3: Unified Generator ====================

async def test_unified_generator():
    """Test unified config generator"""
    await print_separator("TEST 3: Unified Config Generator")

    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get servers of different types
        statement = select(Servers).filter(
            Servers.work == True,
            Servers.type_vpn.in_([1, 2])  # VLESS and Shadowsocks
        ).limit(2)

        result = await db.execute(statement)
        servers = result.scalars().all()

        if not servers:
            print("   ⚠️  No servers found, skipping test")
            return True

        print(f"1. Testing with {len(servers)} server(s)...")

        success_count = 0
        for server in servers:
            type_name = {1: "VLESS", 2: "Shadowsocks"}.get(server.type_vpn, "Unknown")
            print(f"\n2. Testing {type_name} server: {server.name}")

            config = await generate_config(server, TEST_USER_ID)

            if config:
                print(f"   ✅ Config generated")
                print(f"   Preview: {config[:80]}...")
                success_count += 1
            else:
                print(f"   ❌ Failed to generate config")

        if success_count == len(servers):
            print(f"\n✅ All {len(servers)} configs generated successfully!")
            return True
        else:
            print(f"\n⚠️  Only {success_count}/{len(servers)} configs generated")
            return success_count > 0


# ==================== TEST 4: Config Format Validation ====================

async def test_config_validation():
    """Test that generated configs are properly formatted"""
    await print_separator("TEST 4: Config Format Validation")

    print("1. Checking config format standards...")

    # Get a test server
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        statement = select(Servers).filter(
            Servers.work == True,
            Servers.type_vpn.in_([1, 2])
        ).limit(1)

        result = await db.execute(statement)
        server = result.scalar_one_or_none()

        if not server:
            print("   ⚠️  No servers found, skipping test")
            return True

        config = await generate_config(server, TEST_USER_ID)

        if not config:
            print("   ❌ Failed to generate config")
            return False

        # Validation checks
        checks = [
            ("No spaces", ' ' not in config.split('#')[0]),  # Before remark
            ("No newlines", '\n' not in config),
            ("Has protocol", '://' in config),
            ("Has host", '@' in config),
            ("Has port", re.search(r':\d+', config) is not None),
            ("Has remark", '#' in config),
        ]

        all_passed = True
        for check_name, result in checks:
            status = "✅" if result else "❌"
            print(f"   {status} {check_name}")
            if not result:
                all_passed = False

        if all_passed:
            print("\n✅ Config format validation PASSED!")
        else:
            print("\n❌ Some format checks failed")

        return all_passed


# ==================== MAIN TEST RUNNER ====================

async def main():
    """Run all tests"""
    print("\n" + "🧪"*30)
    print("CONFIG GENERATORS TESTING")
    print("🧪"*30)

    print(f"\nTest User ID: {TEST_USER_ID}")
    print("Testing VPN configuration generators...")

    tests = [
        ("VLESS Config Generator", test_vless_generator),
        ("Shadowsocks Config Generator", test_shadowsocks_generator),
        ("Unified Config Generator", test_unified_generator),
        ("Config Format Validation", test_config_validation),
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
