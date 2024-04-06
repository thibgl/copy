import time 
from passlib.hash import bcrypt

async def db_startup(db):
        # Ensure collections exist
    collections = await db.list_collection_names()
    
    if "users" in collections:
        await db.users.drop()

    await db.create_collection("users")
    await db.users.create_index([("username", 1)], unique=True)
    
    # Check if root user exists
    root_user = await db.users.find_one({"username": "root"})
    
    if not root_user:
        # Root user doesn't exist, so let's create one
        root_user_data = {
            "username": "root",
            "email": "root@example.com",
            "password_hash": bcrypt.hash("root"),  # Replace with a secure password
            "followedLeaders": {},
            "active": False,
            "liveRatio": 0,
            "leverage": 5,
            "valueBTC": 0,
            "valueUSDT": 0,
            "mix": {},
            "amounts": {},
            "notionalValues": {},
            "values": {},
            "shares": {},
            "liveAmounts": {},
            "chatId": 1031182213,
            "notionalValue": 0,
            "positionsValue": 0,
            "collateralMarginLevel": 0,
            "collateralValueUSDT": 0
        }

        await db.users.insert_one(root_user_data)
        print("Root user created.")
    else:
        print("Root user already exists.")


    if "leaders" in collections:
        await db.leaders.drop()

    await db.create_collection("leaders")
    await db.leaders.create_index([("binanceId", 1)], unique=True)
    # await db.leaders.create_index([("id", 1)], unique=True)

    # if "performances" not in collections:
    #     await db.create_collection("performances")
    #     await db.leads_performances.create_index([("portfolioId", 1)], unique=True)

    if "positions" in collections:
        await db.positions.drop()
    
    await db.create_collection("positions")
    await db.positions.create_index([("leaderId", 1), ("id", -1)], unique=True)
    # await db.positions.create_index([("leaderId", 1), ("symbol", -1)])

    if "position_history" in collections:
        await db.position_history.drop()
    
    await db.create_collection("position_history")
    await db.position_history.create_index([("leaderId", 1), ("id", -1)], unique=True)
    # await db.positions.create_index([("leaderId", 1)])
    
    # if "details" not in collections:
    #     await db.create_collection("details")
    #     await db.leads_performances.create_index([("portfolioId", 1)], unique=True)

    if "transfer_history" in collections:
        await db.transfer_history.drop()
    
    await db.create_collection("transfer_history")
    await db.transfer_history.create_index([("leaderId", 1), ("time", -1)], unique=True)

    if "history" in collections:
        await db.history.drop()
    
    await db.create_collection("history")
    await db.history.create_index([("userId", 1), ("symbol", -1)])

    if "live" in collections:
        await db.live.drop()
    
    await db.create_collection("live")
    await db.live.create_index([("userId", 1), ("symbol", -1)], unique=True)

    if "log" in collections:
        await db.log.drop()

    await db.create_collection("log")
    await db.log.create_index([("userId", 1)])

    if "bot" in collections:
        await db.bot.drop()

    await db.create_collection("bot")

    bot_data = {
        "active": True,
        "updateTime": int(time.time() * 1000),
        "tickInterval": 30,
        "shutdownTime": 0,
        "ticks": 0,
        "orders": 0,
        "precisions": {},
        "totalWeight": 0,
        "chatId": 1031182213,
        "logLevel": "INFO"
    }

    await db.bot.insert_one(bot_data)
    await db.bot.create_index([("logId", 1)], unique=True)