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
        stmt = select(Servers).filter(Servers.name == 'Нидерланды Vless')
        result = await db.execute(stmt)
        server = result.scalars().first()
        
        print(f'Server: {server.name}')
        print(f'IP: {server.ip}')
        print(f'Inbound ID: {server.inbound_id}')
        print()
        
        manager = ServerManager(server)
        await manager.login()
        
        # Get inbound info
        inbounds = await manager.client.get_inbounds()
        for inbound in inbounds.get('obj', []):
            if inbound.get('id') == server.inbound_id:
                print(f'Inbound:')
                print(f'  Port: {inbound.get("port")}')
                print(f'  Protocol: {inbound.get("protocol")}')
                print(f'  Enable: {inbound.get("enable")}')
                print(f'  Up: {inbound.get("up", 0) / (1024*1024*1024):.2f} GB')
                print(f'  Down: {inbound.get("down", 0) / (1024*1024*1024):.2f} GB')
                break

asyncio.run(main())
