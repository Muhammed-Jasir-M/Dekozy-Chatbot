# Dockerfile for the main Rasa server
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends build-essential wget && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . /app

# Expose the port defined in the PORT environment variable, defaulting to 5005
EXPOSE 5005

# Start Rasa server using the PORT env variable (defaults to 5005 if not set)
CMD ["rasa", "run", "--enable-api", "--cors", "*", "--port", "5005", "--model", "models/20250302-122759-brass-parallel.tar.gz"]
