# todo: log - error boundaries, telegram, get user, socket pour le front
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.hash import bcrypt
from starlette.middleware.cors import CORSMiddleware
from datetime import timedelta
from services import Binance, Auth, Scrap, Bot
from lib import *
import uvicorn
import time
import asyncio

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
app.binance = Binance(app)
app.auth = Auth(app)
app.scrap = Scrap(app)
app.bot = Bot(app)


@app.post('/scrap/{portfolioId}/{dataType}')
async def scrap_data(portfolioId: str, dataType:str, params: Params = Body(default={})):
    response = app.scrap.fetch_data(portfolioId, dataType, params.model_dump())

    return response.json()


# @app.get('/api/{leaderId}/create', response_model=LeaderTickResponse)
@app.get('/api/{leaderId}/create')
async def create_leader(leaderId: str):
    leader_response = await app.scrap.tick_leader(leaderId)

    # return leader_response

@app.get('/api/tick_positions')
async def tick_positions():
    await app.bot.tick_positions(API=True)

@app.get('/api/{binanceId}/add_to_roster')
async def add_to_roster(binanceId: str):
    user = await app.db.users.find_one()
    leader = await app.db.leaders.find_one({"binanceId": binanceId})

    if leader["_id"] not in user["followedLeaders"].keys():
        user["followedLeaders"][str(leader["_id"])] = 1

        await app.db.users.update_one(
            {"username": "root"}, 
            {
                "$set": {
                    "updateTime": int(time.time() * 1000),
                    "followedLeaders": user["followedLeaders"],
                }
            }
        )

@app.get('/api/close_all_positions')
async def close_all_positions():
    user = await app.db.users.find_one()
    await app.binance.close_all_positions(user)

@app.get('/api/precision/{symbol}')
async def get_precision(symbol: str):
    response = app.binance.get_asset_precision(symbol)
    # print(response)
    return response

@app.get('/api/start/{userId}')
async def scrap_data(userId: str):
    response = app.bot.start(userId)

    return response.json()


@app.get('/scrap/{portfolioId}')
async def scrap_data(portfolioId: str, dataType:str, params: Params = Body(default={})):
    response = app.scrap.fetch_data(portfolioId, dataType, params.model_dump())

    return response.json()
    # return leaderboard
# @app.get('/api/create', response_model=List[Lead])
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
    user = await app.auth.authenticate_user(
        # app.db, 
        form_data.username, 
        form_data.password
        )
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
async def startup():
    # await db_startup(app.db)
    # leader_response = await app.scrap.tick_leader('3778840387155890433')
    # user = await app.db.users.find_one()
    # leader = await app.db.leaders.find_one({"binanceId": '3778840387155890433'})

    # if leader["_id"] not in user["followedLeaders"].keys():
    #     user["followedLeaders"][str(leader["_id"])] = 1

    #     await app.db.users.update_one(
    #         {"username": "root"}, 
    #         {
    #             "$set": {
    #                 "updateTime": int(time.time() * 1000),
    #                 "followedLeaders": user["followedLeaders"],
    #             }
    #         }
    #     )
    # asyncio.create_task(app.bot.tick_positions())
    
    pass

@app.on_event("shutdown")
async def shutdown_db_client():
    # app.scrap.cleanup()
    app.mongodb_client.close()


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

