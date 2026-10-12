"""Motor de SQLAlchemy. Las consultas usan SQL explícito contra ambar-db.sql."""
from sqlalchemy import create_engine

from .config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,     # descarta conexiones muertas (MySQL cierra las inactivas)
    pool_recycle=1800,
)
