import asyncio
from sqlalchemy import select
from app.models.database import TestPage, async_session

async def main():
    async with async_session() as session:
        res = await session.execute(select(TestPage))
        pages = res.scalars().all()
        for p in pages:
            print(f"Name: {p.name}, Path: {p.path}, Full Path: {p.full_path}, File: {p.file_path}")

asyncio.run(main())
