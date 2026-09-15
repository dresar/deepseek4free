FROM python:3.12-slim

WORKDIR /app

# Install basic build tools if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Environment variables
ENV PORT=8000
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Run lightweight FastAPI server
CMD ["python", "web_server.py"]
