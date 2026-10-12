"""Configuración del backend (variables de entorno o archivo .env)."""
import datetime
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


def periodo_para(hoy: datetime.date | None = None) -> str:
    """Periodo escolar según la fecha: ENE-JUN (enero a julio) o AGO-DIC."""
    hoy = hoy or datetime.date.today()
    return f"{'ENE-JUN' if hoy.month <= 7 else 'AGO-DIC'} {hoy.year}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Base de datos (MySQL 8.0.19+ / MariaDB 10.2+; se necesitan CHECK y triggers)
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str
    db_password: str
    db_name: str = "ambar_escolar"

    # Sesión
    jwt_secret: str = Field(min_length=32)      # openssl rand -hex 32
    jwt_horas: int = 8
    login_max_intentos: int = 3
    login_segundos_bloqueo: int = 300

    # Expedientes digitales: los PDF viven en el servidor, la BD guarda solo la ruta
    storage_dir: Path = Path("expedientes")
    requiere_todos_los_documentos: bool = True

    # Reglas escolares
    plantel: int = 1
    dominio_institucional: str = "acapulco.tecnm.mx"
    periodo_escolar: str = ""                   # vacío = se calcula con la fecha

    @field_validator("storage_dir")
    @classmethod
    def _absoluta(cls, valor: Path) -> Path:
        return Path(valor).expanduser().resolve()

    @property
    def database_url(self) -> URL:
        return URL.create(
            "mysql+pymysql",
            username=self.db_user,
            password=self.db_password,      # URL.create escapa caracteres especiales
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"charset": "utf8mb4"},
        )

    @property
    def periodo(self) -> str:
        return self.periodo_escolar or periodo_para()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
