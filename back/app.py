import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status, Cookie, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.hash import bcrypt
from pydantic import BaseModel, Field, ConfigDict, PlainSerializer, AfterValidator, WithJsonSchema
from starlette.middleware.cors import CORSMiddleware
from bson.objectid import ObjectId
from passlib.context import CryptContext
from typing import Union, Annotated, Any
from jose import JWTError, jwt
from datetime import datetime, timedelta

load_dotenv()

SECRET_KEY = os.environ.get("SECRET_KEY", "secretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

app = FastAPI()

# CORS middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type", "X-CSRFToken"],
)

async def get_db():
    yield app.db

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Union[str, None] = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Serialize MongoDB ObjectId
def validate_object_id(v: Any) -> ObjectId:
    if isinstance(v, ObjectId):
        return v
    if ObjectId.is_valid(v):
        return ObjectId(v)
    raise ValueError("Invalid ObjectId")

ObjectIdType = Annotated[
    Union[str, ObjectId],
    PlainSerializer(lambda x: str(x), return_type=str, when_used="json"),
    AfterValidator(validate_object_id),
    WithJsonSchema({"type": "string"}, mode="serialization"),
]

class User(BaseModel):
    model_config = ConfigDict()

    id: ObjectIdType = Field(None, alias="_id")
    username: str
    password_hash: str

    class Config:
        arbitrary_types_allowed = True
        populate_by_alias=True
        populate_by_name=True
        validate_assignment=True

# Pydantic model for login credentials
class LoginCredentials(BaseModel):
    username: str
    password: str

# Pydantic model for user registration
class RegisterUser(BaseModel):
    username: str
    email: str  # Assuming you want to use this somewhere
    password: str


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def authenticate_user(db, username: str, password: str):
    user = await db["users"].find_one({"username": username})
    if user and verify_password(password, user["password_hash"]):
        return User(**user)
    return False

async def get_current_user(db=Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = await db["users"].find_one({"username": token_data.username})
    if user is None:
        raise credentials_exception
    return user


@app.on_event("startup")
async def startup_db_client():
    # Database connection
    app.mongodb_client = AsyncIOMotorClient(os.environ.get("MONGO_URI", "mongodb://mongo:27017/db"))
    app.db = app.mongodb_client.db

    # Ensure collections exist
    collections = await app.db.list_collection_names()
    
    if "users" not in collections:
        await app.db.create_collection("users")
        # Create indexes here if needed
        await app.db.users.create_index([("username", 1)], unique=True)
    
    if "traders" not in collections:
        await app.db.create_collection("traders")
    
    # Check if root user exists
    root_user = await app.db.users.find_one({"username": "root"})
    
    if not root_user:
        # Root user doesn't exist, so let's create one
        root_user_data = {
            "username": "root",
            "email": "root@example.com",
            "password_hash": bcrypt.hash("root")  # Replace with a secure password
        }
        await app.db.users.insert_one(root_user_data)
        print("Root user created.")
    else:
        print("Root user already exists.")

@app.on_event("shutdown")
async def shutdown_db_client():
    app.mongodb_client.close()

@app.post("/api/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await authenticate_user(app.db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/")
async def read_root():
    return {"message": "Hello World"}

@app.get("/api/ping")
async def home():
    return {"ping": "pong!"}

@app.post('/api/login')
async def login(credentials: LoginCredentials):
    user_data = await app.db.users.find_one({"username": credentials.username})
    if user_data and bcrypt.verify(credentials.password, user_data["password_hash"]):
        # Here you should handle login logic, session, or token generation
        user_obj = User(
            id=str(user_data["_id"]),
            username=user_data["username"],
            password_hash=user_data["password_hash"],
        )
        return {"login": True, "message": "Login successful", "data": user_obj.dict()}
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/api/logout")
async def logout():
    # Here you should handle logout logic, session termination, or token invalidation
    return {"logout": True}

@app.post('/api/data')
async def handle_data_post(data: dict):
    # Store data sent by the front end in MongoDB
    result = await app.db.users.insert_one(data)
    return {"message": "Data stored successfully", "id": str(result.inserted_id)}

@app.get('/api/data')
async def handle_data_get():
    # Retrieve and return data from MongoDB
    data = await app.db.users.find_one({}, {'_id': 0})
    return data

@app.post('/api/register')
async def register_user(user: RegisterUser):
    # Insert user data into MongoDB with hashed password
    hashed_password = bcrypt.hash(user.password)
    result = await app.db.users.insert_one({
        "username": user.username,
        "email": user.email,
        "password_hash": hashed_password
    })
    return {"message": "User registered successfully", "id": str(result.inserted_id)}

@app.get("/api/user", response_model=User)
async def read_user(current_user: User = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    return current_user


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
