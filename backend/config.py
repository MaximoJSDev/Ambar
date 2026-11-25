"""Configuración del backend (variables de entorno o archivo .env)."""
import datetime
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.engine import URL


def periodo_para(hoy: datetime.date | None = None) -> str:
    """Periodo escolar según la fecha: ENE-JUN (enero a julio) o AGO-DIC."""
    hoy = hoy or datetime.date.today()
    return f"{'ENE-JUN' if hoy.month <= 7 else 'AGO-DIC'} {hoy.year}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base de datos (MySQL 8.0.19+ / MariaDB 10.2+; se necesitan CHECK y triggers)
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str
    db_password: str
    db_name: str = "ambar_escolar"
    db_ssl_ca: Path | None = None
    db_tidb: bool = False

    # Expedientes remotos (si no se configura, se conserva el almacenamiento local)
    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: str | None = None
    cloudinary_api_secret: str | None = None
    cloudinary_required: bool = False

    # Sesión
    jwt_secret: str = Field(min_length=32)      # openssl rand -hex 32
    jwt_horas: int = 8
    login_max_intentos: int = 3
    login_segundos_bloqueo: int = 300

    # Expedientes digitales: los PDF viven en el servidor, la BD guarda solo la ruta
    storage_dir: Path = Path("expedientes")
    requiere_todos_los_documentos: bool = True

    # Reglas escolares
    numero_tecnologico: int = 32
    numero_carrera: int = 7
    dominio_institucional: str = "acapulco.tecnm.mx"
    periodo_escolar: str = ""                   # vacío = se calcula con la fecha

    @field_validator("storage_dir")
    @classmethod
    def _absoluta(cls, valor: Path) -> Path:
        return Path(valor).expanduser().resolve()

    @field_validator("db_ssl_ca")
    @classmethod
    def _ca_absoluta(cls, valor: Path | None) -> Path | None:
        return Path(valor).expanduser().resolve() if valor else None

    @model_validator(mode="after")
    def _credenciales_cloudinary_completas(self):
        credenciales = (
            self.cloudinary_cloud_name,
            self.cloudinary_api_key,
            self.cloudinary_api_secret,
        )
        if any(credenciales) and not all(credenciales):
            raise ValueError("Configura CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY y CLOUDINARY_API_SECRET juntos")
        if self.cloudinary_required and not all(credenciales):
            raise ValueError("Cloudinary es obligatorio para este despliegue")
        return self

    @property
    def cloudinary_configurado(self) -> bool:
        return bool(
            self.cloudinary_cloud_name
            and self.cloudinary_api_key
            and self.cloudinary_api_secret
        )

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

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args=(
        {
            "ssl_ca": str(settings.db_ssl_ca),
            "ssl_verify_cert": True,
            "ssl_verify_identity": True,
        }
        if settings.db_ssl_ca
        else {}
    ),
)
