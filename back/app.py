
# todo: telegram, sleeping leaders delay not working, opti portoflio en fonction de la perf, close ALL from bot, REORGANIZE qpi paths, implement schedule for maintenance, get user, socket pour le front
# todo: inclure le type dans le mix que si il a engagé un minimum de son capital
# todo: V3 ==> PANDAS / NUMPY
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.hash import bcrypt
from starlette.middleware.cors import CORSMiddleware
from datetime import timedelta
from services import Binance, Auth, Scrap, Bot, Log, Database #, Telegram
from lib import *
import uvicorn
import asyncio
import schedule
import pandas as pd
# import logging
# import sys

# logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(sys.stdout)])
# Load env variables
load_dotenv()
# Intialize App
app = FastAPI()
# CORS middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://localhost:5173"],
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
app.log = Log(app)
app.database = Database(app)


@app.post('/scrap/{portfolioId}/{dataType}')
async def scrap_data(portfolioId: str, dataType:str, params: Params = Body(default={})):
    response = app.scrap.fetch_data(portfolioId, dataType, params.model_dump())

    return response.json()


# @app.get('/api/{leaderId}/create', response_model=LeaderTickResponse)
@app.get('/api/{leaderId}/create')
async def create_leader(leaderId: str):
    leader_response = await app.scrap.create_leader(leaderId)

    # return leader_response

@app.get('/api/tick_positions')
async def tick_positions():
    await app.bot.tick(API=True)



@app.get('/user/toogle_bot')
async def toogle_bot():
    bot = await app.db.bot.find_one()
    active = not bot["active"]

    await app.db.bot.update_one({}, {"$set": {"active": not bot["active"]}})

    if active:
        asyncio.create_task(app.bot.tick())

    print(f'[{utils.current_readable_time()}]: Bot is now Active: {not bot["active"]}')


@app.get('/user/close_all_positions')
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


@app.get('/scrapLeaders')
async def scrap_data():
    bot = await app.db.bot.find_one()
    response = await app.scrap.fetch_pages(bot, 'leaders', results_limit=0)

    print(pd.DataFrame(response["data"]).head().to())

    # return response.json()


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

@app.post('/auth/login')
async def login(credentials: LoginCredentials):
    user = await app.db.users.find_one({"username": credentials.username})
    if user and bcrypt.verify(credentials.password, user["auth"]["data"]["password_hash"]):
        # Here you should handle login logic, session, or token generation
        user_obj = User(
            id=str(user["_id"]),
            username=user["auth"]["data"]["username"],
            password_hash=user["auth"]["data"]["password_hash"],
        )
        return {"login": True, "message": "Login successful", "data": user_obj.dict()}
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/auth/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await app.auth.authenticate_user(
        # app.db, 
        form_data.username, 
        form_data.password
        )
    # print(user)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=app.auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = app.auth.create_access_token(
        data={"sub": user["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/auth/user", response_model=User)
async def read_user(current_user: User = Depends(app.auth.get_current_user)):
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    current_user.pop("auth")
    current_user.pop("mix")
    return current_user

@app.get("/auth/logout")
async def logout():
    # Here you should handle logout logic, session termination, or token invalidation
    return {"logout": True}


@app.get("/")
async def read_root():
    return {"message": "Hello World"}

@app.get("/api/ping")
async def home():
    return {"ping": "pong!"}

@app.get('/leaders/all', response_model=AllLeaders)
async def all_leaders():
    leaders_cursor = app.db.leaders.find()
    # leaders = await leaders_cursor.to_list(length=None)
    leaders = []
    async for leader in leaders_cursor:
        leader.pop("positions")
        leader.pop("grouped_positions")
        leader.pop("mix")
        leaders.append(app.database.unpack(leader))

    return {"success": True, "message": "All Leaders List", "data": leaders}

@app.get('/leaders/follow/{binanceId}')
async def follow(binanceId: str):
    bot = await app.db.bot.find_one()
    user = await app.db.users.find_one()
    leader, _ = await app.scrap.get_leader(bot, user, binance_id=binanceId)

    if leader:
        followed_leaders = pd.DataFrame(user["leaders"]["data"])

        if str(binanceId) not in followed_leaders.index.values:
            followed_leaders.loc[binanceId] = 1

            update = {
                "leaders": followed_leaders.to_dict()
            }
            await app.database.update(user, update, 'users')

@app.get('/leaders/unfollow/{binanceId}')
async def unfollow(binanceId: str):
    bot = await app.db.bot.find_one()
    user = await app.db.users.find_one()
    leader = await app.db.leaders.find_one({"binanceId": binanceId})
    print(leader["_id"])
    # if str(leader["_id"]) not in user["leaders"]["data"].keys():
    #     update = {
    #         "leaders": user["leaders"]["data"].pop(leader["_id"])
    #     }
    #     await app.database.update(user, update, 'users')

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




@app.on_event("startup")
async def startup():
    # await db_startup(app.db)
    # bot = await app.db.bot.find_one()
    # app.binance.exchange_information(bot, ['BIGTIMEUSDT'])
    # symbol = '1000SHIBUSDT'
    # await app.binance.get_asset_precision(bot, symbol)
    # print(symbol)
    # user = await app.db.users.find_one()
    # await app.log.bot.send_message(chat_id=user["chatId"], text='HEYB')
    # leaders = {
    #     "3810983022188954113": 2, #"type":"trumpet"
    #     '3876446298872838657': 2, #"type":"trumpet"
    #     '3907342150781504256': 1, #"type": "flat"
    #     '3842534998056366337': 1, #"type": "flat"
    #     '3716273180201331968': 1, #"type": "agro"
    #     '3695768829010696193': 1, #"type": "agro"
    #     '3843810303408715009': 1 #"type": "agro"
    # }
    # followed_leaders = {}
    # for leaderId, ratio in leaders.items():   
    #     print(leaderId, ratio)
    #     await app.scrap.create_leader(leaderId)
    #     leader = await app.db.leaders.find_one({"binanceId": leaderId})
    #     if leader["_id"] not in user["followedLeaders"].keys():
    #         followed_leaders[str(leader["_id"])] = ratio
    # print(followed_leaders)
    # await app.db.users.update_one(
    #     {}, 
    #     {
    #         "$set": {
    #             "updatedAt": int(time.time() * 1000),
    #             "followedLeaders": followed_leaders
    #         }
    #     }
    # )

    asyncio.create_task(app.bot.tick())

    # await app.telegram.bot.send_message(chat_id=user["chatId"], text='Hello, this is a notification!')
    pass

@app.on_event("shutdown")
async def shutdown_db_client():
    # app.scrap.cleanup()
    app.mongodb_client.close()


if __name__ == '__main__':
    # app.telegram = Telegram(app)

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

