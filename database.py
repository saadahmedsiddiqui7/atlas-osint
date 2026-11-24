
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Database location
BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = f"sqlite:///{BASE_DIR / 'atlas.db'}"

# Database connection
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Database foundation
class Base(DeclarativeBase):
    pass


def create_database():
    Base.metadata.create_all(bind=engine)
    # create_all creates missing tables, but does not change existing ones.
    # These nullable case links preserve all records saved by older ATLAS versions.
    columns = {column["name"] for column in inspect(engine).get_columns("evidence")}
    with engine.begin() as connection:
        if "verification_note" not in columns:
            connection.execute(text("ALTER TABLE evidence ADD COLUMN verification_note TEXT"))
        if "reviewed_at" not in columns:
            connection.execute(text("ALTER TABLE evidence ADD COLUMN reviewed_at DATETIME"))
        if "search_query" not in columns:
            connection.execute(text("ALTER TABLE evidence ADD COLUMN search_query TEXT"))
        if "case_id" not in columns:
            connection.execute(text(
                "ALTER TABLE evidence ADD COLUMN case_id INTEGER REFERENCES research_cases(id)"
            ))

        alert_columns = {column["name"] for column in inspect(engine).get_columns("exposure_alerts")}
        if "case_id" not in alert_columns:
            connection.execute(text(
                "ALTER TABLE exposure_alerts ADD COLUMN case_id INTEGER REFERENCES research_cases(id)"
            ))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
