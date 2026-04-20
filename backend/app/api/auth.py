"""
/api/auth — autenticação JWT simplificada.
Em produção, integrar com SSO corporativo (Google Workspace / Azure AD).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ---------------------------------------------------------------------------
# DEMO: banco de usuários em memória. Substituir por tabela dim_user + bcrypt.
# ---------------------------------------------------------------------------
DEMO_USERS = {
    "joao@vitaforte.com": {
        "password": "changeme",
        "name": "João",
        "role": "admin",
    },
}


def create_access_token(subject: str, extra: dict | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire, **(extra or {})}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    user = DEMO_USERS.get(form.username)
    if not user or user["password"] != form.password:
        raise HTTPException(401, "Credenciais inválidas")
    token = create_access_token(form.username, {"role": user["role"], "name": user["name"]})
    return TokenResponse(access_token=token, expires_in=settings.JWT_EXPIRE_MINUTES * 60)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return {"email": payload["sub"], "role": payload.get("role"), "name": payload.get("name")}
    except JWTError:
        raise HTTPException(401, "Token inválido")


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user
