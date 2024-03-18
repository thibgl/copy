import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from bson.objectid import ObjectId  # Make sure to import ObjectId

load_dotenv()

app = Flask(__name__)

app.config.update(
    DEBUG=True,
    SECRET_KEY=os.environ.get('SECRET_KEY'),
    SESSION_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    WTF_CSRF_ENABLED=False # for dev only
)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.session_protection = "strong"


@login_manager.user_loader
def load_user(user_id):
    """
    Flask-Login user_loader callback.
    """
    return User.get(user_id)


csrf = CSRFProtect(app)

# @app.after_request
# def set_csrf_cookie(response):
#     response.set_cookie('csrf_token', generate_csrf())
#     return response


cors = CORS(
    app,
    resources={r"*": {"origins": "http://localhost:5173"}},
    expose_headers=["Content-Type", "X-CSRFToken"],
    supports_credentials=True,
)

# Configure the MongoDB URI
app.config["MONGO_URI"] = "mongodb://mongo:27017/db"
mongo = PyMongo(app)


class User(UserMixin):
    def __init__(self, user_data):
        """
        Initializes a User object with the data fetched from MongoDB.

        Args:
            user_data (dict): A dictionary containing user information fetched from MongoDB.
        """
        self.id = str(user_data['_id'])  # Convert ObjectId to string
        self.username = user_data['username']
        self.password_hash = user_data['password_hash']

    @staticmethod
    def get(user_id):
        """
        Static method to search the database and load a user by ID.

        Args:
            user_id (str): The ID of the user to load.

        Returns:
            User: The loaded user object if found, else None.
        """
        # Convert the string ID back to ObjectId for querying MongoDB
        user_data = mongo.db.users.find_one({"_id": ObjectId(user_id)})
        if user_data:
            return User(user_data)
        return None


@app.route("/api/ping", methods=["GET"])
def home():
    return jsonify({"ping": "pong!"})


@app.route("/api/get_csrf", methods=["GET"])
def get_csrf():
    token = generate_csrf()
    response = jsonify({"csrf_token": token})  # Include the token in the JSON response body
    return response


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()  # Use this to parse JSON data
    username = data.get('username')
    password = data.get('password')
    # Fetch the user from the database
    user_data = mongo.db.users.find_one({"username": username})

    if user_data and check_password_hash(user_data.get('password_hash'), password):
        print('LOGIN SUCCESS')
        # Login successful
        user_obj = User(user_data)  # Create a User object from the fetched data
        login_user(user_obj)  # Log the user in

        # Remove sensitive information before returning response
        user_data.pop('_id', None)
        user_data.pop('password_hash', None)

        return jsonify({"login": True, "message": "Login successful", "data": user_data}), 200
    else:
        print('LOGIN FAIL')
        # Login failed
        return jsonify({"login": False, "message": "Invalid credentials"}), 401

    

@app.route("/api/get_session", methods=["GET"])
def check_session():
    if current_user.is_authenticated:
        return jsonify({"login": True})

    return jsonify({"login": False})


@app.route("/api/logout", methods=["GET"])
@login_required
def logout():
    logout_user()
    return jsonify({"logout": True})


@app.route('/api/data', methods=['POST', 'GET'])
@login_required
def handle_data():
    if request.method == 'POST':
        # Store data sent by the Svelte front end in MongoDB
        data = request.json
        mongo.db.users.insert_one(data)
        return jsonify({"message": "Data stored successfully"}), 201
    
    elif request.method == 'GET':
        # Retrieve and return data from MongoDB
        data = mongo.db.users.find_one({}, {'_id': 0})  # Example: omitting the MongoDB ID
        return jsonify(data), 200


@app.route('/api/register', methods=['POST'])
def register_user():
    # Example user data
    user_data = {
        "username": request.json['username'],
        "email": request.json['email'],
        "password_hash": generate_password_hash(request.json['password'])
    }
    
    # Insert user data into MongoDB
    mongo.db.users.insert_one(user_data)
    
    return jsonify({"message": "User registered successfully"}), 201


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')