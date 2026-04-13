"""
数据库迁移脚本：添加 page_comments 和 component_comments 字段
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "server"))

from sqlalchemy import text
from app.models.database import async_session

async def migrate():
    """执行数据库迁移"""
    async with async_session() as db:
        try:
            # 检查字段是否已存在
            result = await db.execute(text(
                "PRAGMA table_info(test_pages)"
            ))
            columns = [row[1] for row in result.fetchall()]
            
            if 'page_comments' not in columns:
                print("添加 page_comments 字段...")
                await db.execute(text(
                    "ALTER TABLE test_pages ADD COLUMN page_comments TEXT"
                ))
                await db.commit()
                print("✅ page_comments 字段添加成功")
            else:
                print("⚠️ page_comments 字段已存在")
            
            if 'component_comments' not in columns:
                print("添加 component_comments 字段...")
                await db.execute(text(
                    "ALTER TABLE test_pages ADD COLUMN component_comments TEXT"
                ))
                await db.commit()
                print("✅ component_comments 字段添加成功")
            else:
                print("⚠️ component_comments 字段已存在")
            
            print("\n🎉 数据库迁移完成！")
            
        except Exception as e:
            print(f"\n❌ 迁移失败: {e}")
            await db.rollback()
            raise

asyncio.run(migrate())
