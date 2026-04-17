import asyncio
from sqlalchemy import select
from app.models.database import TestPage, get_async_session

async def main():
    session_maker = get_async_session()
    async with session_maker() as session:
        res = await session.execute(select(TestPage).where(TestPage.path == '/settings'))
        page = res.scalars().first()
        if page:
            print(f"Name: {page.name}")
            print(f"Path: {page.path}")
            print(f"File Path: {repr(page.file_path)}")
        else:
            print("Page not found")

asyncio.run(main())
