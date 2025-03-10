# Dockerfile for the main Rasa server
FROM python:3.9-slim 

WORKDIR /app

# Install system dependencies
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends build-essential wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only what's needed to run
COPY models/ /app/models/
COPY endpoints.yml /app/

# Memory optimization settings
ENV PYTHONUNBUFFERED=1
ENV MALLOC_ARENA_MAX=2

# Expose the port
EXPOSE 5005

# Start Rasa server
CMD ["rasa", "run", "--enable-api", "--cors", "*", "--port", "5005", "--model", "models/latest.tar.gz"]
