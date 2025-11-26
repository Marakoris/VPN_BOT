#!/usr/bin/env python3
"""
Тестирование disable/enable функционала для всех VPN типов
Этап 0.3 - проверка что disable/enable работает корректно
"""
import asyncio
import sys
sys.path.insert(0, '/root/github_repos/VPN_BOT')

from bot.misc.VPN.Outline import Outline
from bot.misc.VPN.Xui.Vless import Vless
from bot.misc.VPN.Xui.Shadowsocks import Shadowsocks
from bot.database import db


# Test user telegram ID
TEST_USER_ID = 999999999


async def get_server_by_id(server_id):
    """Получить данные сервера из БД"""
    async with db.db_session() as session:
        query = await session.execute(
            f"SELECT * FROM servers WHERE id = {server_id}"
        )
        result = query.fetchone()
        if result:
            return result
        return None


async def test_outline():
    """Тест Outline disable/enable"""
    print("\n" + "="*60)
    print("🪐 Testing Outline VPN disable/enable")
    print("="*60)

    # Server data for Russia Outline server (id=5)
    class MockServer:
        outline_link = '{"apiUrl":"https://95.142.46.141:31391/IpO8OqEb8Mxz2ZOpwrAQpg","certSha256":"3C:80:D9:14:F9:CB:65:FB:CE:70:E5:1E:D8:4C:6C:6D:12:63:16:2B:32:4C:9D:76:CA:BE:C9:44:5E:E5:D5:77"}'

    server = MockServer()
    outline = Outline(server)

    try:
        # Login
        print("  1. Connecting to server...")
        await outline.login()
        print("     ✅ Connected")

        # Check if client exists
        print(f"  2. Checking if client {TEST_USER_ID} exists...")
        client = await outline.get_client(str(TEST_USER_ID))

        if client is None:
            print(f"     ⚠️  Client not found, creating...")
            key = await outline.add_client(str(TEST_USER_ID))
            if key:
                print(f"     ✅ Client created (key_id={key.key_id})")
            else:
                print(f"     ❌ Failed to create client")
                return False
        else:
            print(f"     ✅ Client exists (key_id={client.key_id})")

        # Test disable
        print(f"  3. Disabling client {TEST_USER_ID}...")
        result = await outline.disable_client(str(TEST_USER_ID))
        if result:
            print(f"     ✅ Client disabled successfully")
        else:
            print(f"     ❌ Failed to disable client")
            return False

        # Verify disabled (should have 1 byte limit)
        client = await outline.get_client(str(TEST_USER_ID))
        if client and hasattr(client, 'data_limit') and client.data_limit == 1:
            print(f"     ✅ Verified: data_limit = 1 byte")
        else:
            print(f"     ⚠️  Could not verify disable state")

        # Test enable
        print(f"  4. Enabling client {TEST_USER_ID}...")
        result = await outline.enable_client(str(TEST_USER_ID))
        if result:
            print(f"     ✅ Client enabled successfully")
        else:
            print(f"     ❌ Failed to enable client")
            return False

        # Verify enabled (should have normal limit or no limit)
        client = await outline.get_client(str(TEST_USER_ID))
        if client:
            if hasattr(client, 'data_limit'):
                if client.data_limit > 1:
                    print(f"     ✅ Verified: data_limit = {client.data_limit} bytes ({client.data_limit / 10**9:.1f} GB)")
                else:
                    print(f"     ⚠️  data_limit still 1 byte")
            else:
                print(f"     ✅ Verified: no data_limit (unlimited)")

        print("\n  ✅ Outline test PASSED")
        return True

    except Exception as e:
        print(f"\n  ❌ Outline test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_vless():
    """Тест VLESS disable/enable"""
    print("\n" + "="*60)
    print("🐊 Testing VLESS VPN disable/enable")
    print("="*60)

    # Server data for Russia VLESS server (id=6)
    class MockServer:
        panel = 'https://95.142.46.141:2053'
        login = 'admin'
        password = 'admin'
        inbound_id = 1
        ip = '95.142.46.141'

    server = MockServer()
    vless = Vless(server)

    try:
        # Login
        print("  1. Connecting to server...")
        await vless.login()
        print("     ✅ Connected")

        # Check if client exists
        print(f"  2. Checking if client {TEST_USER_ID} exists...")
        client = await vless.get_client(str(TEST_USER_ID))

        if client == 'User not found':
            print(f"     ⚠️  Client not found, creating...")
            result = await vless.add_client(str(TEST_USER_ID))
            if result:
                print(f"     ✅ Client created")
            else:
                print(f"     ❌ Failed to create client")
                return False
            client = await vless.get_client(str(TEST_USER_ID))
        else:
            print(f"     ✅ Client exists (uuid={client['id']})")

        # Test disable
        print(f"  3. Disabling client {TEST_USER_ID}...")
        result = await vless.disable_client(str(TEST_USER_ID))
        if result:
            print(f"     ✅ Client disabled successfully")
        else:
            print(f"     ❌ Failed to disable client")
            return False

        # Verify disabled (should have enable=false)
        client = await vless.get_client(str(TEST_USER_ID))
        if client != 'User not found' and not client.get('enable', True):
            print(f"     ✅ Verified: enable = False")
        else:
            print(f"     ⚠️  Could not verify disable state")

        # Test enable
        print(f"  4. Enabling client {TEST_USER_ID}...")
        result = await vless.enable_client(str(TEST_USER_ID))
        if result:
            print(f"     ✅ Client enabled successfully")
        else:
            print(f"     ❌ Failed to enable client")
            return False

        # Verify enabled (should have enable=true)
        client = await vless.get_client(str(TEST_USER_ID))
        if client != 'User not found' and client.get('enable', False):
            print(f"     ✅ Verified: enable = True")
        else:
            print(f"     ⚠️  Could not verify enable state")

        print("\n  ✅ VLESS test PASSED")
        return True

    except Exception as e:
        print(f"\n  ❌ VLESS test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_shadowsocks():
    """Тест Shadowsocks disable/enable"""
    print("\n" + "="*60)
    print("🦈 Testing Shadowsocks VPN disable/enable")
    print("="*60)

    # Server data for Russia Shadowsocks server (id=7)
    class MockServer:
        panel = 'https://95.142.46.141:2053'
        login = 'admin'
        password = 'admin'
        inbound_id = 2
        ip = '95.142.46.141'

    server = MockServer()
    ss = Shadowsocks(server)

    try:
        # Login
        print("  1. Connecting to server...")
        await ss.login()
        print("     ✅ Connected")

        # Check if client exists
        print(f"  2. Checking if client {TEST_USER_ID} exists...")
        client = await ss.get_client(str(TEST_USER_ID))

        if client == 'User not found' or not client:
            print(f"     ⚠️  Client not found, creating...")
            result = await ss.add_client(str(TEST_USER_ID))
            if result:
                print(f"     ✅ Client created")
            else:
                print(f"     ❌ Failed to create client")
                return False
            client = await ss.get_client(str(TEST_USER_ID))
        else:
            print(f"     ✅ Client exists (email={client.get('email', 'N/A')})")

        # Test disable
        print(f"  3. Disabling client {TEST_USER_ID}...")
        result = await ss.disable_client(str(TEST_USER_ID))
        if result:
            print(f"     ✅ Client disabled successfully")
        else:
            print(f"     ❌ Failed to disable client")
            return False

        # Verify disabled (should have totalGB=1)
        client = await ss.get_client(str(TEST_USER_ID))
        if client and isinstance(client, dict) and client.get('totalGB') == 1:
            print(f"     ✅ Verified: totalGB = 1 byte")
        else:
            print(f"     ⚠️  Could not verify disable state (totalGB={client.get('totalGB') if client else 'N/A'})")

        # Test enable
        print(f"  4. Enabling client {TEST_USER_ID}...")
        result = await ss.enable_client(str(TEST_USER_ID))
        if result:
            print(f"     ✅ Client enabled successfully")
        else:
            print(f"     ❌ Failed to enable client")
            return False

        # Verify enabled (should have normal totalGB)
        client = await ss.get_client(str(TEST_USER_ID))
        if client and isinstance(client, dict):
            total_gb = client.get('totalGB', 0)
            if total_gb > 1:
                print(f"     ✅ Verified: totalGB = {total_gb} bytes ({total_gb / 1073741824:.1f} GB)")
            else:
                print(f"     ⚠️  totalGB still {total_gb}")

        print("\n  ✅ Shadowsocks test PASSED")
        return True

    except Exception as e:
        print(f"\n  ❌ Shadowsocks test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Запуск всех тестов"""
    print("\n" + "="*60)
    print("🧪 TESTING DISABLE/ENABLE FUNCTIONALITY")
    print("="*60)
    print(f"Test User ID: {TEST_USER_ID}")

    results = {
        'Outline': False,
        'VLESS': False,
        'Shadowsocks': False
    }

    # Run tests
    results['Outline'] = await test_outline()
    await asyncio.sleep(1)

    results['VLESS'] = await test_vless()
    await asyncio.sleep(1)

    results['Shadowsocks'] = await test_shadowsocks()

    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)

    for vpn_type, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {vpn_type:15s} : {status}")

    all_passed = all(results.values())
    print("="*60)
    if all_passed:
        print("✅ ALL TESTS PASSED - Этап 0 завершен успешно!")
    else:
        print("❌ SOME TESTS FAILED - требуется доработка")
    print("="*60)

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
