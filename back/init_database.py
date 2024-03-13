from your_flask_app import create_app  # Adjust this import according to your Flask app structure
from flask_pymongo import PyMongo

app = create_app()  # Create a Flask app instance

with app.app_context():
    mongo = PyMongo(app)
    db = mongo.db

    # Initialize collections if they don't exist
    if "users" not in db.list_collection_names():
        db.create_collection("users")
        # Create indexes here if needed
        db.users.create_index([("username", 1)], unique=True)

    if "traders" not in db.list_collection_names():
        db.create_collection("traders")

    # Select the database and collection
    db = client['mydatabase']
    users_collection = db['users']

    # Check if root user exists
    root_user = users_collection.find_one({"username": "root"})

    if not root_user:
        # Root user doesn't exist, so let's create one
        root_user_data = {
            "username": "root",
            "email": "root@example.com",
            "password_hash": generate_password_hash("your_secure_password")  # Replace with a secure password
        }
        users_collection.insert_one(root_user_data)
        print("Root user created.")
    else:
        print("Root user already exists.")