from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.orm import Session

from . import crud, models, security
from .config import settings
from .database import get_db

# The tokenUrl should point to the API login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")


def authenticate_user(db: Session, email: str, password: str) -> models.User | None:
    """
    Authenticates a user by email and password.

    In FastAPI, the `OAuth2PasswordRequestForm` uses the field name `username`,
    but we are using it to hold the user's email address.

    Returns the user object if authentication is successful, otherwise None.
    """
    user = crud.get_user_by_email(db, email)
    if not user or not security.verify_password(password, user.hashed_password):
        return None
    return user


def get_token_from_cookie_or_header(request: Request) -> str | None:
    """Extract token from either Authorization header or access_token cookie"""
    # First try authorization header
    authorization = request.headers.get("Authorization")
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]  # Remove "Bearer " prefix
    
    # Then try cookie
    cookie_token = request.cookies.get("access_token")
    if cookie_token and cookie_token.startswith("Bearer "):
        return cookie_token[7:]  # Remove "Bearer " prefix
    
    return None

def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Get token from cookie or header
    token = get_token_from_cookie_or_header(request)
    if not token:
        raise credentials_exception
    
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    user = crud.get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception
    return user

# Keep the old function for API-only endpoints that need OAuth2PasswordBearer
def get_current_user_api(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    user = crud.get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception
    return user
