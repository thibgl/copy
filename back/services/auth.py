import os
from lib.schema import *
from jose import JWTError, jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
import functools
from fastapi.security import OAuth2PasswordBearer
from typing import Callable


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

class Auth:
    def __init__(self, app):
        self.SECRET_KEY = os.environ.get("SECRET_KEY", "secretkey")
        self.ALGORITHM = "HS256"
        self.ACCESS_TOKEN_EXPIRE_MINUTES = 30

        self.app = app

    async def get_db(self):
        yield self.app.db

    def verify_password(self, plain_password, hashed_password):
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password):
        return pwd_context.hash(password)

    def create_access_token(self, data: dict, expires_delta: timedelta = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.SECRET_KEY, algorithm=self.ALGORITHM)
        return encoded_jwt

    async def authenticate_user(self, username: str, password: str):
        user = await self.app.db.users.find_one({"username": username})
        if user and self.verify_password(password, user["auth"]["data"]["password_hash"]):
            return self.app.database.unpack(user)
        return False

    async def get_current_user(self, token: str = Depends(oauth2_scheme)):
        db=Depends(self.get_db)
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(token, self.SECRET_KEY, algorithms=[self.ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise credentials_exception
            token_data = TokenData(username=username)
        except JWTError:
            raise credentials_exception
        user = await self.app.db.users.find_one({"username": token_data.username})
        if user is None:
            raise credentials_exception
        return self.app.database.unpack(user)

    def protected_route():
        def decorator_route(self, func: Callable):
            user_dependency = Depends(self.get_current_user)

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                user = await user_dependency()
                if not user:
                    raise HTTPException(status_code=404, detail="User not found")
                return await func(*args, **kwargs)
            return wrapper
        return decorator_route