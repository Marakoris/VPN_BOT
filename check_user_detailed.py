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
        stmt = select(Servers).filter(Servers.name == 'Нидерланды Outline')
        result = await db.execute(stmt)
        server = result.scalars().first()
        
        manager = ServerManager(server)
        await manager.login()
        
        keys = await manager.client.client_outline.get_keys()
        metrics = await manager.client.client_outline.get_transferred_data()
        
        print(f'Total keys: {len(keys)}')
        print(f'Metrics keys: {len(metrics["bytesTransferredByUserId"])}')
        
        # Find user key
        for key in keys:
            if str(key.name) == str(tgid_to_check):
                print(f'User key: id={key.key_id}, name={key.name}')
                print(f'Metrics has key_id {key.key_id}? {str(key.key_id) in metrics["bytesTransferredByUserId"]}')
                
                # Try different ID formats
                for k, v in metrics['bytesTransferredByUserId'].items():
                    if str(k) == str(key.key_id):
                        print(f'Found by key_id: {v} bytes')
                        break
                break
        
        # Show first 5 keys and their metrics
        print('\nFirst 5 keys:')
        for key in list(keys)[:5]:
            kid = str(key.key_id)
            traffic = metrics['bytesTransferredByUserId'].get(kid, 'NOT FOUND')
            print(f'  key_id={kid}, name={key.name}, traffic={traffic}')

asyncio.run(main())
