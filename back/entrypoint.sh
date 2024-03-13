#!/bin/bash

# Initialize MongoDB collections and indexes
echo "Initializing MongoDB..."
python /app/init_mongo.py

# Start the main process (e.g., Flask application)
exec "$@"
