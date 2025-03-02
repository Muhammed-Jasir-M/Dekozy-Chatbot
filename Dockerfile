# File: Dockerfile (for the main Rasa server)
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends build-essential wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your Rasa project files
COPY . .

# Expose the port Rasa runs on (Render will set the PORT env variable)
EXPOSE ${PORT}

# Run the Rasa server (using shell form to allow variable substitution)
CMD ["sh", "-c", "rasa run --enable-api --cors '*' --port ${PORT} --model models/"]
