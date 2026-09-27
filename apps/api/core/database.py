from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from core.config import settings


class Base(DeclarativeBase):
    pass


# Production-hardened engine with connection pooling
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_size=settings.POSTGRES_POOL_SIZE,
    max_overflow=settings.POSTGRES_MAX_OVERFLOW,
    # Detects and recycles stale connections (essential for long-running containers)
    pool_pre_ping=settings.POSTGRES_POOL_PRE_PING,
    # Return connections to pool after 1 hour if not used
    pool_recycle=3600,
    # Echo SQL only in non-production environments
    echo=not settings.is_production,
    connect_args={"ssl_context": __import__("ssl").create_default_context()} if settings.is_production else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
