# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
# Ensure you have uvicorn and fastapi in your requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8000 available to the world outside this container
# FastAPI default port is 8000, but you can change it if needed
EXPOSE 8000

# Define environment variable
# FastAPI doesn't use FLASK_ENV. You can define custom env variables as needed
ENV FASTAPI_ENV=development

# To print() in DEV
ENV PYTHONUNBUFFERED=1

# Run app.py using uvicorn when the container launches
# Replace 'app:app' with 'your_fastapi_file_name:app_instance_name'
# CMD ["pydantic2ts", "--module", "app.py", "--output", "../front/apiTypes.ts"]
CMD ["uvicorn", "app:app", "--host=0.0.0.0", "--reload"]
