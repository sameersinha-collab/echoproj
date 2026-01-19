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

# Expose port (Cloud Run will set PORT env var)
EXPOSE 8080

# Run the server
CMD ["python", "server.py"]
