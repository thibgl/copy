from flask import Flask, request, jsonify
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash

app = Flask(__name__)

# Configure the MongoDB URI
app.config["MONGO_URI"] = "mongodb://mongo:27017/mydatabase"
mongo = PyMongo(app)


@app.route('/api/data', methods=['POST', 'GET'])
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


@app.route('/register', methods=['POST'])
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

