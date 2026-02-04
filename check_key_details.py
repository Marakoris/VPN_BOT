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
    
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Servers).filter(Servers.name == 'Нидерланды Vless')
        result = await db.execute(stmt)
        server = result.scalars().first()
        
        manager = ServerManager(server)
        await manager.login()
        
        clients = await manager.get_all_user()
        
        for client in clients:
            email = client.get('email', '')
            if str(tgid) in email:
                print(f'Email: {email}')
                print(f'ID: {client.get("id")}')
                print(f'UUID: {client.get("id", "N/A")}')
                print(f'Enable: {client.get("enable")}')
                # Print full client data
                import json
                print(f'\nFull data:')
                print(json.dumps(client, indent=2, default=str))
                break

asyncio.run(main())
