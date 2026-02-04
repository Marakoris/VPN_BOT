import asyncio
import os
import sys

os.chdir('/app')
sys.path.insert(0, '/app')

async def main():
    from bot.database.main import engine
    from bot.database.models.main import Persons, Servers
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from bot.misc.VPN.ServerManager import ServerManager
    
    tgid_to_check = 817462050
    
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Servers).filter(Servers.type_vpn == 0)
        result = await db.execute(stmt)
        servers = result.scalars().all()
        
        print(f'Checking {len(servers)} Outline servers for user {tgid_to_check}...')
        
        for server in servers:
            try:
                manager = ServerManager(server)
                await manager.login()
                keys = await manager.client.client_outline.get_keys()
                for key in keys:
                    if str(key.name) == str(tgid_to_check):
                        # Get traffic
                        metrics = await manager.client.client_outline.get_transferred_data()
                        traffic = 0
                        if metrics and 'bytesTransferredByUserId' in metrics:
                            traffic = metrics['bytesTransferredByUserId'].get(str(key.key_id), 0)
                        print(f'{server.name}: Found key! ID={key.key_id}, traffic={traffic} bytes')
                        break
                else:
                    print(f'{server.name}: No key found')
            except Exception as e:
                print(f'{server.name}: Error - {str(e)[:80]}')

asyncio.run(main())
