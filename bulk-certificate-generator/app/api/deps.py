"""FastAPI dependencies. The session factory lives on app.state (set in create_app)."""
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from sqlalchemy.orm import Session


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_output_dir(request: Request) -> Path:
    return request.app.state.output_dir
