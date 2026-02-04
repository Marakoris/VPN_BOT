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
    
    tgid_to_check = 817462050
    
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        # Get ALL servers
        stmt = select(Servers)
        result = await db.execute(stmt)
        servers = result.scalars().all()
        
        print(f'Checking {len(servers)} servers for user {tgid_to_check}...')
        print()
        
        for server in servers:
            server_type = 'Outline' if server.type_vpn == 0 else 'VLESS/SS'
            try:
                manager = ServerManager(server)
                await manager.login()
                
                if server.type_vpn == 0:  # Outline
                    keys = await manager.client.client_outline.get_keys()
                    metrics = await manager.client.client_outline.get_transferred_data()
                    bytes_by_id = metrics.get('bytesTransferredByUserId', {}) if metrics else {}
                    
                    for key in keys:
                        if str(key.name) == str(tgid_to_check):
                            traffic = bytes_by_id.get(str(key.key_id), 0)
                            print(f'{server.name} ({server_type}): key_id={key.key_id}, traffic={traffic/(1024*1024):.1f}MB')
                            break
                else:  # VLESS/Shadowsocks
                    # Get all clients from xray panel
                    clients = await manager.get_all_user()
                    if clients:
                        for client in clients:
                            email = client.get('email', '')
                            # Check if email contains user tgid
                            if str(tgid_to_check) in email:
                                up = client.get('up', 0) or 0
                                down = client.get('down', 0) or 0
                                total = (up + down) / (1024*1024)
                                print(f'{server.name} ({server_type}): email={email}, traffic={total:.1f}MB')
                                
            except Exception as e:
                pass  # Skip servers with errors

asyncio.run(main())
