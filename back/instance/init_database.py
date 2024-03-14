from pymongo import MongoClient
from werkzeug.security import generate_password_hash

# Connect to MongoDB
client = MongoClient("mongodb://mongo:27017/mydatabase")
db = client.mydatabase

# Initialize collections if they don't exist
if "users" not in db.list_collection_names():
    db.create_collection("users")
    # Create indexes here if needed
    db.users.create_index([("username", 1)], unique=True)

if "traders" not in db.list_collection_names():
    db.create_collection("traders")

# Check if root user exists
root_user = db.users.find_one({"username": "root"})

if not root_user:
    # Root user doesn't exist, so let's create one
    root_user_data = {
        "username": "root",
        "email": "root@example.com",
        "password_hash": generate_password_hash("your_secure_password")  # Replace with a secure password
    }
    db.users.insert_one(root_user_data)
    print("Root user created.")
else:
    print("Root user already exists.")
