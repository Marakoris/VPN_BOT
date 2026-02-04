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
        stmt = select(Servers).filter(Servers.type_vpn == 0)
        result = await db.execute(stmt)
        servers = result.scalars().all()
        
        for server in servers:
            try:
                manager = ServerManager(server)
                await manager.login()
                metrics = await manager.client.client_outline.get_transferred_data()
                
                if not metrics or 'bytesTransferredByUserId' not in metrics:
                    print(f'{server.name}: No metrics!')
                    continue
                    
                traffic_data = metrics['bytesTransferredByUserId']
                total_keys = len(traffic_data)
                non_zero = sum(1 for v in traffic_data.values() if v > 0)
                max_traffic = max(traffic_data.values()) if traffic_data else 0
                
                print(f'{server.name}: {non_zero}/{total_keys} keys with traffic, max={max_traffic/(1024*1024):.1f}MB')
            except Exception as e:
                print(f'{server.name}: Error - {str(e)[:80]}')

asyncio.run(main())
