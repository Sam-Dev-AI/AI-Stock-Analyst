# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Install system-level build tools needed for libraries like pandas/numpy/nsepy
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container
COPY . .

# Set the default port the app will run on
ENV PORT 8080

# This is the correct production command
# It runs as a shell to correctly read the $PORT variable
CMD gunicorn --bind "0.0.0.0:$PORT" --workers=1 --threads=80 API_Server:app