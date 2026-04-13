import asyncio
import sys
from pathlib import Path

# 添加server目录到路径
sys.path.insert(0, str(Path(__file__).parent / "server"))

from app.models.database import async_session
from sqlalchemy import text

async def check():
    async with async_session() as db:
        result = await db.execute(text(
            'SELECT id, name, component_name FROM test_pages LIMIT 10'
        ))
        rows = result.fetchall()
        
        print(f"\n共查询到 {len(rows)} 条记录:\n")
        for i, row in enumerate(rows, 1):
            page_id, name, component_name = row
            print(f"{i}. 页面: {name}")
            print(f"   组件: {component_name}")
            print()

asyncio.run(check())
