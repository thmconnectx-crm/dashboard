from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import BASE_DIR, get_settings
from app.models import Base


settings = get_settings()

if settings.database_url.startswith("sqlite:///./"):
    db_path = BASE_DIR / settings.database_url.replace("sqlite:///./", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
elif settings.database_url.startswith("sqlite:////"):
    db_path = Path("/" + settings.database_url.removeprefix("sqlite:////"))
    db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_lightweight_columns()


def _ensure_lightweight_columns() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if "campaigns" in existing_tables:
        _add_missing_columns("campaigns", {"objective": "VARCHAR(128) DEFAULT ''"})
    if "campaign_metrics" in existing_tables:
        _add_missing_columns(
            "campaign_metrics",
            {
                "campaign_objective": "VARCHAR(128) DEFAULT ''",
                "reach": "INTEGER DEFAULT 0",
                "messages": "FLOAT DEFAULT 0",
                "cost_per_message": "FLOAT DEFAULT 0",
            },
        )


def _add_missing_columns(table_name: str, columns: dict[str, str]) -> None:
    inspector = inspect(engine)
    existing = {column["name"] for column in inspector.get_columns(table_name)}
    missing = {name: definition for name, definition in columns.items() if name not in existing}
    if not missing:
        return
    with engine.begin() as connection:
        for name, definition in missing.items():
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_session() -> Session:
    return SessionLocal()
