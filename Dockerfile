# Use a lightweight base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY models/ /app/models/
COPY config.yml /app/
COPY domain.yml /app/
COPY data/ /app/data/
COPY endpoints.yml /app/

# Optimize memory usage
ENV PYTHONUNBUFFERED=1
ENV MALLOC_ARENA_MAX=1
ENV MAX_HISTORY=2
ENV DIET_EMBEDDING_DIMENSION=16

# Expose port for Rasa server
EXPOSE 5005

# Run Rasa server
CMD ["rasa", "run", "--enable-api", "--cors", "*", "--port", "5005", "--model", "models/latest.tar.gz"]
