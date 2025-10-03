# syntax=docker/dockerfile:1

FROM python:3.13-slim as base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install backend dependencies from root requirements (Flask server)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application sources
COPY . /app/

EXPOSE 8000

# Run the Flask server
CMD ["python", "server.py"]
