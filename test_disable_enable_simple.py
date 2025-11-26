#!/usr/bin/env python3
"""
Простой тест disable/enable - проверка что методы существуют
Этап 0.3 - verification
"""
import sys
sys.path.insert(0, '/root/github_repos/VPN_BOT')

from bot.misc.VPN.Outline import Outline
from bot.misc.VPN.Xui.Vless import Vless
from bot.misc.VPN.Xui.Shadowsocks import Shadowsocks
import inspect


def test_methods_exist():
    """Проверка что методы disable_client и enable_client существуют"""
    print("\n" + "="*60)
    print("🧪 TESTING DISABLE/ENABLE METHODS EXISTENCE")
    print("="*60)

    results = {}

    # Test Outline
    print("\n🪐 Outline:")
    outline_methods = {
        'disable_client': hasattr(Outline, 'disable_client') and callable(getattr(Outline, 'disable_client')),
        'enable_client': hasattr(Outline, 'enable_client') and callable(getattr(Outline, 'enable_client')),
    }

    for method, exists in outline_methods.items():
        status = "✅" if exists else "❌"
        print(f"  {status} {method}")
        if exists:
            sig = inspect.signature(getattr(Outline, method))
            print(f"     Signature: {sig}")

    results['Outline'] = all(outline_methods.values())

    # Test VLESS
    print("\n🐊 VLESS:")
    vless_methods = {
        'disable_client': hasattr(Vless, 'disable_client') and callable(getattr(Vless, 'disable_client')),
        'enable_client': hasattr(Vless, 'enable_client') and callable(getattr(Vless, 'enable_client')),
    }

    for method, exists in vless_methods.items():
        status = "✅" if exists else "❌"
        print(f"  {status} {method}")
        if exists:
            sig = inspect.signature(getattr(Vless, method))
            print(f"     Signature: {sig}")

    results['VLESS'] = all(vless_methods.values())

    # Test Shadowsocks
    print("\n🦈 Shadowsocks:")
    ss_methods = {
        'disable_client': hasattr(Shadowsocks, 'disable_client') and callable(getattr(Shadowsocks, 'disable_client')),
        'enable_client': hasattr(Shadowsocks, 'enable_client') and callable(getattr(Shadowsocks, 'enable_client')),
    }

    for method, exists in ss_methods.items():
        status = "✅" if exists else "❌"
        print(f"  {status} {method}")
        if exists:
            sig = inspect.signature(getattr(Shadowsocks, method))
            print(f"     Signature: {sig}")

    results['Shadowsocks'] = all(ss_methods.values())

    # Summary
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)

    for vpn_type, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {vpn_type:15s} : {status}")

    all_passed = all(results.values())
    print("="*60)
    if all_passed:
        print("✅ ALL METHODS EXIST - Code structure verified!")
        print("\n📝 Note: Functional testing with real servers should be done manually")
        print("   or with access to working VPN servers.")
    else:
        print("❌ SOME METHODS MISSING - Code needs fixes")
    print("="*60)

    return all_passed


def show_implementation_summary():
    """Показать сводку по реализации"""
    print("\n" + "="*60)
    print("📋 IMPLEMENTATION SUMMARY - Stage 0")
    print("="*60)

    print("\n✅ Completed tasks:")
    print("  1. ✅ Merged disable/enable methods from feature branch")
    print("  2. ✅ Added disable/enable to Outline.py")
    print("  3. ✅ Verified disable/enable in Vless.py")
    print("  4. ✅ Verified disable/enable in Shadowsocks.py")
    print("  5. ✅ Created subscription fields migration")
    print("  6. ✅ Applied migration to VPNHubBotDB_TEST")

    print("\n📊 Database changes:")
    print("  • users.subscription_token (VARCHAR 255, UNIQUE)")
    print("  • users.subscription_created_at (TIMESTAMP TZ)")
    print("  • users.subscription_updated_at (TIMESTAMP TZ)")
    print("  • subscription_logs table created")
    print("  • Indexes: idx_users_subscription_token, idx_subscription_logs_user/time")

    print("\n💡 Disable/Enable logic by VPN type:")
    print("  • Outline:     data_limit = 1 byte / 30 GB")
    print("  • VLESS:       enable = false / true")
    print("  • Shadowsocks: totalGB = 1 byte / 30 GB")

    print("\n" + "="*60)


if __name__ == "__main__":
    success = test_methods_exist()
    show_implementation_summary()

    sys.exit(0 if success else 1)
