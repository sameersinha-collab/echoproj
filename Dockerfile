# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements-server.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-server.txt

# Copy application code
COPY server.py .
COPY agents.py .
COPY story_data.py .

# Copy data files (CSV)
COPY ["Questions - One Word.csv", "."]
COPY ["Questions - Greetings.csv", "."]

# Copy/Create audio cache directory
# This includes any pre-generated audio files in the image
COPY ["audio_cache/", "./audio_cache/"]

# Ensure the cache directory exists even if local one was empty
RUN mkdir -p audio_cache

# Expose port (Cloud Run will set PORT env var)
EXPOSE 8765

# Run the server
CMD ["python", "server.py"]
