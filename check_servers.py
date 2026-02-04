import asyncio
import os
import sys

os.chdir('/app')
sys.path.insert(0, '/app')

async def main():
    from bot.database.main import engine
    from bot.database.models.main import Servers
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from bot.misc.VPN.ServerManager import ServerManager
    
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Servers).order_by(Servers.name)
        result = await db.execute(stmt)
        servers = result.scalars().all()
        
        print(f'Checking {len(servers)} servers...\n')
        
        for server in servers:
            server_type = 'Outline' if server.type_vpn == 0 else 'VLESS/SS'
            try:
                manager = ServerManager(server)
                await asyncio.wait_for(manager.login(), timeout=10)
                
                if server.type_vpn == 0:  # Outline
                    keys = await asyncio.wait_for(
                        manager.client.client_outline.get_keys(), 
                        timeout=10
                    )
                    print(f'✅ {server.name} ({server_type}) - OK, {len(keys)} keys')
                else:  # VLESS/SS
                    clients = await asyncio.wait_for(
                        manager.get_all_user(),
                        timeout=10
                    )
                    count = len(clients) if clients else 0
                    print(f'✅ {server.name} ({server_type}) - OK, {count} clients')
                    
            except asyncio.TimeoutError:
                print(f'❌ {server.name} ({server_type}) - TIMEOUT')
            except Exception as e:
                print(f'❌ {server.name} ({server_type}) - ERROR: {str(e)[:60]}')

asyncio.run(main())
