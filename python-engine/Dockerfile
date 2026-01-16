# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install pip dependencies with cache
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt --target=/app/site-packages

# Stage 2: Runtime (Slimmer, Faster)
FROM python:3.11-slim

WORKDIR /app

# Install runtime libs only (libpq for Postgre)
RUN apt-get update && apt-get install -y \
    libpq5 \
    libgomp1 \
    curl \
    fontconfig \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /app/site-packages /usr/local/lib/python3.11/site-packages

# Copy application code
COPY . .

# Environment setup
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PYTHON_PORT:-8000} --workers 1"]
