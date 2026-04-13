import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "server"))

from sqlalchemy import text
from app.models.database import async_session

async def check():
    async with async_session() as db:
        result = await db.execute(text("PRAGMA table_info(test_pages)"))
        columns = result.fetchall()
        
        print("\n数据库 test_pages 表结构:")
        print("=" * 80)
        for col in columns:
            cid, name, col_type, notnull, default, pk = col
            print(f"  {cid:2d}. {name:30s} {col_type:20s} {'NOT NULL' if notnull else 'NULLABLE'}")
        print("=" * 80)
        
        # 检查缺失的字段
        col_names = [col[1] for col in columns]
        required = ['imported_components', 'page_comments', 'component_comments']
        
        missing = [f for f in required if f not in col_names]
        if missing:
            print(f"\n❌ 缺失字段: {missing}")
            print("\n正在添加缺失字段...")
            
            for field in missing:
                try:
                    await db.execute(text(f"ALTER TABLE test_pages ADD COLUMN {field} TEXT"))
                    await db.commit()
                    print(f"  ✅ {field} 添加成功")
                except Exception as e:
                    print(f"  ❌ {field} 添加失败: {e}")
                    await db.rollback()
        else:
            print("\n✅ 所有字段都存在")

asyncio.run(check())
