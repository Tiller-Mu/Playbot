import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "server"))

from sqlalchemy import text
from app.models.database import async_session

async def check():
    async with async_session() as db:
        # 查询keyboard页面的数据
        result = await db.execute(text(
            "SELECT id, name, component_name, description FROM test_pages WHERE name = 'keyboard'"
        ))
        row = result.fetchone()
        
        if row:
            page_id, name, component_name, description = row
            print(f"\n页面: {name}")
            print(f"ID: {page_id}")
            print(f"\ncomponent_name字段:")
            print(component_name)
            print(f"\ndescription字段:")
            print(description[:100] if description else "None")
            print("...")
        else:
            print("未找到keyboard页面")

asyncio.run(check())
