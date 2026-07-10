from pathlib import Path

from sqlalchemy import create_engine
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_session() -> Session:
    return SessionLocal()
