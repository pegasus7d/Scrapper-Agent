"""Shared FastAPI dependencies (DESIGN.md §4) — split out so every router
module (routes.py, routes_companies.py) can depend on the request-scoped
session without importing each other.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session


def _session(request: Request) -> Iterator[Session]:
    engine: Engine = request.app.state.engine
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(_session)]
