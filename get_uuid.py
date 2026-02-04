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
    
    tgid = 817462050
    email = f'{tgid}_vless'
    
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Servers).filter(Servers.name == 'Нидерланды Vless')
        result = await db.execute(stmt)
        server = result.scalars().first()
        
        manager = ServerManager(server)
        await manager.login()
        
        # Get link directly from xray client
        link = await manager.client.get_client_link(email, server.inbound_id)
        if link:
            print(f'VLESS Link:')
            print(link[:100] + '...')
            # Extract UUID
            if 'vless://' in link:
                uuid = link.split('vless://')[1].split('@')[0]
                print(f'\nUUID: {uuid}')

asyncio.run(main())
