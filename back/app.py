import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.hash import bcrypt
from starlette.middleware.cors import CORSMiddleware
from datetime import timedelta
from typing import List
from services import Binance, Auth, Scrap, Database
from lib.schema import *
import uvicorn

# Load env variables
load_dotenv()
# Intialize App
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
# Database connection
app.mongodb_client = AsyncIOMotorClient(os.environ.get("MONGO_URI", "mongodb://mongo:27017/db"))
app.db = app.mongodb_client.db
# Custom Services
app.binance = Binance()
app.auth = Auth(app)
app.scrap = Scrap(app)
app.database = Database(app)


# @app.get('/api/getleaderboard')
# async def get_leaders():
#     await app.scrap.get_leaders()

@app.post('/scrap/{portfolioId}/{dataType}')
async def scrap_data(portfolioId: str, dataType:str, params: Params = Body(default={})):
    response = app.scrap.request_data(portfolioId, dataType, params.model_dump())

    return response.json()

    # return leaderboard
# @app.get('/api/leads', response_model=List[Lead])
# async def get_leads():
#     leads = await app.database.get_all('traders')
#     print(leads)
#     return leads

@app.get("/api/binance/snapshot")
# @protected_route
async def binance_snapshot():
    account_snapshot = app.binance.account_snapshot()

    return account_snapshot
    
@app.post("/api/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await app.auth.authenticate_user(app.db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=app.auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = app.auth.create_access_token(
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
async def read_user(current_user: User = Depends(app.auth.get_current_user)):
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    return current_user


@app.on_event("startup")
async def startup_db_client():
    # Ensure collections exist
    collections = await app.db.list_collection_names()
    
    if "users" not in collections:
        await app.db.create_collection("users")
        # Create indexes here if needed
        await app.db.users.create_index([("username", 1)], unique=True)
    
    if "leaders" not in collections:
        await app.db.create_collection("leaders")
        await app.db.leads.create_index([("portfolioId", 1)], unique=True)

    if "performances" not in collections:
        await app.db.create_collection("performances")
        await app.db.leads_performances.create_index([("portfolioId", 1)], unique=True)

    if "positions" not in collections:
        await app.db.create_collection("positions")
        await app.db.leads_performances.create_index([("portfolioId", 1)], unique=True)
    
    if "details" not in collections:
        await app.db.create_collection("details")
        await app.db.leads_performances.create_index([("portfolioId", 1)], unique=True)

    if "transfers" not in collections:
        await app.db.create_collection("transfers")
        await app.db.leads_performances.create_index([("portfolioId", 1)], unique=True)

    if "pool" not in collections:
        await app.db.create_collection("pool")
        await app.db.leads_performances.create_index([("portfolioId", 1)], unique=True)

    if "live" not in collections:
        await app.db.create_collection("live")
        await app.db.leads_performances.create_index([("username", 1)], unique=True)

    if "history" not in collections:
        await app.db.create_collection("history")
        await app.db.leads_performances.create_index([("username", 1)], unique=True)
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
    app.scrap.cleanup()
    app.mongodb_client.close()


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

