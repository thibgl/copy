from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.hash import bcrypt

app = FastAPI()

# MongoDB connection settings
MONGO_DETAILS = "mongodb://mongo:27017/db"

# Initialize MongoDB client
client = AsyncIOMotorClient(MONGO_DETAILS)
db = client.mydatabase

@app.on_event("startup")
async def startup_db_client():
    # Ensure collections exist
    collections = await db.list_collection_names()
    
    if "users" not in collections:
        await db.create_collection("users")
        # Create indexes here if needed
        await db.users.create_index([("username", 1)], unique=True)
    
    if "traders" not in collections:
        await db.create_collection("traders")
    
    # Check if root user exists
    root_user = await db.users.find_one({"username": "root"})
    
    if not root_user:
        # Root user doesn't exist, so let's create one
        root_user_data = {
            "username": "root",
            "email": "root@example.com",
            "password_hash": bcrypt.hash("root")  # Replace with a secure password
        }
        await db.users.insert_one(root_user_data)
        print("Root user created.")
    else:
        print("Root user already exists.")

@app.get("/")
async def read_root():
    return {"message": "Hello World"}
