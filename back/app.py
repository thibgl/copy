import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.hash import bcrypt
from starlette.middleware.cors import CORSMiddleware
from datetime import timedelta
from typing import List
from services import Binance, Auth, Scrap, Database, Bot
from lib.schema import *
import uvicorn
import time

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
app.database = Database(app)
app.bot = Bot(app)


# @app.get('/api/getleaderboard')
# async def get_leaders():
#     await app.scrap.get_leaders()

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
    user = await app.db.users.find_one({"username": 'root'})
    bot = await app.db.bot.find_one()
    pool = {}
    latest_user_amounts = user["amounts"]
    current_user_amounts = {}

    # todo change for users followed leaders
    for leaderId in bot["activeLeaders"]:
        leader = await app.db.leaders.find_one({"_id": leaderId})
        await app.scrap.tick_positions(leader)
        pool[leader["_id"]] = leader
        leader_amounts = leader["amounts"]
        
        for symbol, amount in leader_amounts.items():
            if symbol not in current_user_amounts: 
                current_user_amounts[symbol] = 0

            current_user_amounts[symbol] += amount

    if current_user_amounts != latest_user_amounts:
        current_set, latest_set = set(current_user_amounts.items()), set(latest_user_amounts.items())
        current_difference, last_difference = current_set.difference(latest_set), latest_set.difference(current_set)

        for bag in last_difference:
            symbol, amount = bag

            if amount != 0:
                if symbol not in current_user_amounts:
                    print(f'{bag} CLOSED POSITION')
                    # app.binance.close_position()

        leader_ratio = 1 / len(bot["activeLeaders"])

        if len(current_difference) > 0:
            user_account = app.binance.account_snapshot(user)
            user_account_value = float(user_account["valueUSDT"])

        for bag in current_difference:
            symbol, amount = bag

            if amount != 0:
                user_share = 0
                index = 0

                for leaderId in bot["activeLeaders"]:
                    if "account" not in pool[leader["_id"]].keys():
                        pool[leader["_id"]]["account"] = await app.scrap.update_leader_stats(leader)

                    leader_live_ratio = pool[leader["_id"]]["account"]["liveRatio"]

                    if symbol in pool[leader["_id"]]["amounts"].keys():
                        leader_amount = pool[leader["_id"]]["amounts"][symbol]
                        leader_share = pool[leader["_id"]]["shares"][symbol]
                        symbol_value = pool[leader["_id"]]["values"][symbol]

                        user_share += leader_ratio * leader_live_ratio * leader_share

                        if index == 0:
                            symbol_price = abs(symbol_value / leader_amount)

                        index += 1

                print('user_share, symbol_price')
                print(user_share, symbol_price)
                if symbol in latest_user_amounts:
                    print(f'{bag} CHANGED POSITION')
                    laast_amount = latest_user_amounts[symbol]
                    amount = (user_account_value * user_share) / symbol_price / user["leverage"]


                else:
                    print(f'{bag} NEW POSITION')
                    amount = (user_account_value * user_share) / symbol_price / user["leverage"]
                    value = amount * symbol_price
                    print('amount, value')
                    print(amount, value)
                    # app.binance.open_position()

                    # for leaderId in bot["activeLeaders"]:
                    #     position_ratio = 
        

                    # await app.db.live.insert_one({"userId": 'root', "symbol": symbol})
    # if current_user_amounts != last_user_amounts:
    #     print(set(current_user_amounts.items()).symmetric_difference(set(last_user_amounts.items())))
        # print('user')
        # print(user)
                # await app.db.bot.update_one({
                #     "$set": {
                #         "updateTime": int(time.time() * 1000),
                #         "amounts": current_amounts
                #     }
                # })

@app.get('/api/{binanceId}/add_to_roster')
async def add_to_roster(binanceId: str):
    leader = await app.db.leaders.find_one({"binanceId": binanceId})
    bot = await app.db.bot.find_one()

    # async for bot in bots:
    #     bot = bot

    # ! DO THE SAME THING FOR THE USERID
    if leader["_id"] not in bot["activeLeaders"]:
        activeLeaders = bot["activeLeaders"] + [leader["_id"]]

        await app.db.bot.update_one(
            {"_id": bot["_id"]}, 
            {
                "$set": {
                    "updateTime": int(time.time() * 1000),
                    "activeLeaders": activeLeaders,
                }
            }
        )

    # print(leader)
    # response = app.scrap.tick_leader(portfolioId, False)
        
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


# @app.on_event("startup")
# async def startup_db_client():
#     # Ensure collections exist
#     collections = await app.db.list_collection_names()
    
#     if "users" in collections:
#         await app.db.users.drop()

#     await app.db.create_collection("users")
#     await app.db.users.create_index([("username", 1)], unique=True)
    
#     # Check if root user exists
#     root_user = await app.db.users.find_one({"username": "root"})
    
#     if not root_user:
#         # Root user doesn't exist, so let's create one
#         root_user_data = {
#             "username": "root",
#             "email": "root@example.com",
#             "password_hash": bcrypt.hash("root"),  # Replace with a secure password
#             "followedLeaders": {},
#             "active": False,
#             "liveRatio": 0.5,
#             "leverage": 5,
#             "amounts": {},
#             "values": {},
#             "shares": {},
#             "account": {
#                 "BNB": 0,
#                 "USDT": 0,
#                 "valueBTC": 0,
#                 "valueUSDT": 0
#             }
#         }

#         await app.db.users.insert_one(root_user_data)
#         print("Root user created.")
#     else:
#         print("Root user already exists.")


#     if "leaders" in collections:
#         await app.db.leaders.drop()

#     await app.db.create_collection("leaders")
#     await app.db.leaders.create_index([("binanceId", 1)], unique=True)
#     # await app.db.leaders.create_index([("id", 1)], unique=True)

#     # if "performances" not in collections:
#     #     await app.db.create_collection("performances")
#     #     await app.db.leads_performances.create_index([("portfolioId", 1)], unique=True)

#     if "positions" in collections:
#         await app.db.positions.drop()
    
#     await app.db.create_collection("positions")
#     await app.db.positions.create_index([("leaderId", 1), ("id", -1)], unique=True)
#     await app.db.positions.create_index([("leaderId", 1), ("symbol", -1)])

#     if "position_history" in collections:
#         await app.db.position_history.drop()
    
#     await app.db.create_collection("position_history")
#     await app.db.position_history.create_index([("leaderId", 1), ("id", -1)], unique=True)
#     # await app.db.positions.create_index([("leaderId", 1)])
    
#     # if "details" not in collections:
#     #     await app.db.create_collection("details")
#     #     await app.db.leads_performances.create_index([("portfolioId", 1)], unique=True)

#     if "transfer_history" in collections:
#         await app.db.transfer_history.drop()
    
#     await app.db.create_collection("transfer_history")
#     await app.db.transfer_history.create_index([("leaderId", 1), ("time", -1)], unique=True)

#     if "pool" in collections:
#         await app.db.pool.drop()
    
#     await app.db.create_collection("pool")
#     await app.db.pool.create_index([("leaderId", 1)], unique=True)

#     if "live" in collections:
#         await app.db.live.drop()
    
#     await app.db.create_collection("live")
#     await app.db.live.create_index([("userId", 1)], unique=True)

#     if "log" in collections:
#         await app.db.log.drop()

#     await app.db.create_collection("log")
#     await app.db.log.create_index([("userId", 1)], unique=True)

#     if "bot" in collections:
#         await app.db.bot.drop()

#     await app.db.create_collection("bot")

#     bot_data = {
#         "active": False,
#         "activeUsers": [],
#         "activeLeaders": [],
#         "updateTime": int(time.time() * 1000),
#         "tickInterval": 30,
#         "shutdownTime": 0,
#         "ticks": 0,
#         "orders": 0
#     }

#     await app.db.bot.insert_one(bot_data)
#     await app.db.bot.create_index([("logId", 1)], unique=True)

@app.on_event("shutdown")
async def shutdown_db_client():
    # app.scrap.cleanup()
    app.mongodb_client.close()


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

