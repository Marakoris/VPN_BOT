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
    
    tgid = 5699870493
    
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Servers).filter(Servers.name == 'Нидерланды-2 Vless')
        result = await db.execute(stmt)
        server = result.scalars().first()
        
        print(f'Server: {server.name}')
        print(f'IP: {server.ip}')
        
        manager = ServerManager(server)
        await manager.login()
        
        clients = await manager.get_all_user()
        
        for client in clients:
            email = client.get('email', '')
            if str(tgid) in email:
                print(f'\nClient found:')
                print(f'  Email: {email}')
                print(f'  Enable: {client.get("enable")}')
                print(f'  Up: {(client.get("up") or 0) / (1024*1024):.1f} MB')
                print(f'  Down: {(client.get("down") or 0) / (1024*1024):.1f} MB')
                break
        else:
            print(f'\nClient {tgid} NOT FOUND!')

asyncio.run(main())
