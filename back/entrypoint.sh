#!/bin/bash

# Initialize MongoDB collections and indexes
echo "Initializing MongoDB..."
python ./instance/init_database.py

# Start the main process (e.g., Flask application)
exec "$@"
