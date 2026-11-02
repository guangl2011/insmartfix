"""FastAPI dependencies: `get_principal` (401 on none/invalid/expired/revoked, D10 M-5)."""

from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.auth.service import Principal, resolve_principal
from app.auth.store import SqlUserRepo
from app.contract.security import bearer_scheme
from app.db.session import get_db
from app.settings import Settings, get_settings


def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    token = credentials.credentials if credentials else None
    return resolve_principal(SqlUserRepo(db), token, settings.jwt_secret.get_secret_value())


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
