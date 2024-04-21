import time 
from passlib.hash import bcrypt
from lib import utils

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
        current_time = utils.current_time()

        root_user_data = {
            "updated": current_time,
            "updated_date": utils.current_readable_time(),
            "auth": {
                "updated": current_time,
                "data": {
                    "username": "root",
                    "email": "root@example.com",
                    "password_hash": '',
                    "binance_api_key": '',
                    "binance_secret_hash": ''
                    }
            },
            "detail": {
                "updated": current_time,
                "data": {
                    "TARGET_RATIO": 0.6,
                    "active": True,
                    "chat_id": 1031182213
                    }
            },
            "account": {           
                "updated": current_time,
                "data": {
                    "leverage": 5,
                    "value_USDT": 0,
                    "value_BTC": 0,
                    "levered_ratio": 0,
                    "unlevered_ratio": 0,
                    "collateral_margin_level": 0,
                    "collateral_value_USDT": 0
                }
            },
            "leaders": {
                "updated": current_time,
                "data": {
                    "WEIGHT": {} #"3846188874749232129": 1, "3907342150781504256": 1
                }
            },
            "positions":{
                "updated": current_time,
                "data": []
            },
            "mix": {
                "updated": current_time,
                "data": {'symbol': {}, 'BAG': {}}
            }
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

    # if "positions" in collections:
    #     await db.positions.drop()
    
    # await db.create_collection("positions")
    # await db.positions.create_index([("leaderId", 1), ("id", -1)], unique=True)
    # await db.positions.create_index([("leaderId", 1), ("symbol", -1)])

    # if "position_history" in collections:
    #     await db.position_history.drop()
    
    # await db.create_collection("position_history")
    # await db.position_history.create_index([("leaderId", 1), ("id", -1)], unique=True)
    # await db.positions.create_index([("leaderId", 1)])
    
    # if "details" not in collections:
    #     await db.create_collection("details")
    #     await db.leads_performances.create_index([("portfolioId", 1)], unique=True)

    # if "transfer_history" in collections:
    #     await db.transfer_history.drop()
    
    # await db.create_collection("transfer_history")
    # await db.transfer_history.create_index([("leaderId", 1), ("time", -1)], unique=True)

    # if "history" in collections:
    #     await db.history.drop()
    
    # await db.create_collection("history")
    # await db.history.create_index([("userId", 1), ("symbol", -1)])

    # if "live" in collections:
    #     await db.live.drop()
    
    # await db.create_collection("live")
    # await db.live.create_index([("userId", 1), ("symbol", -1)], unique=True)

    # if "log" in collections:
    #     await db.log.drop()

    # await db.create_collection("log")
    # await db.log.create_index([("userId", 1)])

    if "bot" in collections:
        await db.bot.drop()

    await db.create_collection("bot")

    bot_data = {
        "_id": 'BOT',
        "updated": current_time,
        "updated_date": utils.current_readable_time(),
        "updatedAt": int(time.time() * 1000),
        "account": {
            "updated": current_time,
            "data": {
                "LEADER_INVESTED_CAP": 0.3,
                "active": True,
                "tick_interval": 30,
                "tick_boost": 10,
                "total_weight": 0,
                "shutdown_time": 0,
                "ticks": 0,
                "orders": 0,
            }
        },
        "precisions": {
            "updated": current_time,
            "data": {
                'stepSize': {},
                'minQty': {},
                'minNotional': {},
                'thousand': {}
            }
        },
        "detail": {
            "updated": current_time,
            "data": {
                "chat_id": 1031182213,
                "log_level": "INFO",
            }
        }
    }

    await db.bot.insert_one(bot_data)
    # await db.bot.create_index([("logId", 1)], unique=True)