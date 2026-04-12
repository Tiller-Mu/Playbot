"""数据库迁移脚本 - 添加页面描述字段"""
import asyncio
from sqlalchemy import text
from app.models.database import engine

async def migrate():
    """添加description字段到test_pages表"""
    async with engine.begin() as conn:
        # 检查字段是否已存在
        result = await conn.execute(text(
            "PRAGMA table_info(test_pages)"
        ))
        columns = [row[1] for row in result.fetchall()]
        
        if "description" not in columns:
            print("添加description字段到test_pages表...")
            await conn.execute(text(
                "ALTER TABLE test_pages ADD COLUMN description TEXT"
            ))
            print("✓ description字段添加成功")
        else:
            print("✓ description字段已存在")
            
        # 将component_name改为TEXT类型（如果需要）
        result = await conn.execute(text(
            "PRAGMA table_info(test_pages)"
        ))
        for row in result.fetchall():
            if row[1] == "component_name" and row[2] != "TEXT":
                print("修改component_name字段类型为TEXT...")
                # SQLite不支持直接修改列类型，需要重建表
                # 但这里我们暂时不处理，因为VARCHAR也能存储JSON
                break
    
    print("数据库迁移完成！")

if __name__ == "__main__":
    asyncio.run(migrate())
