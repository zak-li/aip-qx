import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings

logger = logging.getLogger(__name__)

_masked_url = settings.database_url.split("@")[-1] if "@" in settings.database_url else "[masked]"
logger.info(f"Initializing async engine targeting {_masked_url}")

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
