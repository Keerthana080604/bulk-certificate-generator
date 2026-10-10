"""Database engine, session factory and declarative Base."""
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def create_db_engine(database_url: str) -> Engine:
    # check_same_thread=False: FastAPI handles requests and background tasks on
    # different threads. Each thread uses its OWN session, so this is safe.
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")  # SQLite ignores FKs unless enabled
        cursor.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
        cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    import app.models  # noqa: F401  (registers tables on Base.metadata)

    Base.metadata.create_all(bind=engine)
