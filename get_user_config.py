import asyncio
import os
import sys

os.chdir('/app')
sys.path.insert(0, '/app')

async def main():
    from bot.database.main import engine
    from bot.database.models.main import Servers, Persons
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from bot.misc.VPN.ServerManager import ServerManager
    import json
    
    tgid = 817462050
    
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Servers).filter(Servers.name == 'Нидерланды Vless')
        result = await db.execute(stmt)
        server = result.scalars().first()
        
        manager = ServerManager(server)
        await manager.login()
        
        # Get user link/config
        try:
            link = await manager.get_subscription_link(tgid)
            print(f'Subscription link exists: {bool(link)}')
            if link:
                # Extract UUID from vless:// link
                # Format: vless://UUID@host:port?...
                if link.startswith('vless://'):
                    uuid = link.split('//')[1].split('@')[0]
                    print(f'UUID from link: {uuid}')
        except Exception as e:
            print(f'Error getting link: {e}')
        
        # Also check client directly
        try:
            client = await manager.get_client_by_email(f'{tgid}_vless')
            if client:
                print(f'Client UUID: {client.get("id", "N/A")}')
        except Exception as e:
            print(f'Error getting client: {e}')

asyncio.run(main())
