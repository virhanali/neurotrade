.PHONY: all build run dev test clean docker-up docker-down docker-build migrate help

# Default target
all: help

# ===========================================
# Development Commands
# ===========================================

## Run Go application locally
run-go:
	@echo "Starting Go application..."
	cd .. && go run ./cmd/app/main.go

## Run Python engine locally
run-python:
	@echo "Starting Python engine..."
	cd ../python-engine && uvicorn main:app --reload --host 0.0.0.0 --port 8000

## Run both services locally (requires tmux or separate terminals)
dev:
	@echo "Use 'make run-go' and 'make run-python' in separate terminals"

# ===========================================
# Build Commands
# ===========================================

## Build Go binary
build-go:
	@echo "Building Go application..."
	cd .. && go build -o bin/neurotrade ./cmd/app

## Build all Docker images
docker-build:
	@echo "Building Docker images..."
	cd .. && docker-compose build

# ===========================================
# Docker Commands
# ===========================================

## Start all services with Docker Compose
docker-up:
	@echo "Starting all services..."
	cd .. && docker-compose up -d

## Start services with logs
docker-up-logs:
	@echo "Starting all services with logs..."
	cd .. && docker-compose up

## Stop all services
docker-down:
	@echo "Stopping all services..."
	cd .. && docker-compose down

## Stop and remove volumes
docker-clean:
	@echo "Stopping services and removing volumes..."
	cd .. && docker-compose down -v

## View logs
docker-logs:
	cd .. && docker-compose logs -f

## View specific service logs
docker-logs-go:
	cd .. && docker-compose logs -f go-app

docker-logs-python:
	cd .. && docker-compose logs -f python-engine

docker-logs-postgres:
	cd .. && docker-compose logs -f postgres

# ===========================================
# Database Commands
# ===========================================

## Run migrations
migrate:
	@echo "Running migrations..."
	cd .. && docker-compose exec postgres psql -U $${POSTGRES_USER:-neurotrade} -d $${POSTGRES_DB:-neurotrade_db} -f /docker-entrypoint-initdb.d/001_init_schema.sql

## Connect to PostgreSQL
psql:
	cd .. && docker-compose exec postgres psql -U $${POSTGRES_USER:-neurotrade} -d $${POSTGRES_DB:-neurotrade_db}

## Connect to Redis CLI
redis-cli:
	cd .. && docker-compose exec redis redis-cli

# ===========================================
# Test Commands
# ===========================================

## Run Go tests
test-go:
	@echo "Running Go tests..."
	cd .. && go test -v ./...

## Run Python tests
test-python:
	@echo "Running Python tests..."
	cd ../python-engine && pytest -v

## Run all tests
test: test-go test-python

# ===========================================
# Utility Commands
# ===========================================

## Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	cd .. && rm -rf bin/
	cd ../python-engine && rm -rf __pycache__ .pytest_cache

## Setup environment file
setup-env:
	@if [ ! -f ../.env ]; then \
		cp ../.env.example ../.env; \
		echo "Created .env file from .env.example"; \
		echo "Please edit .env with your actual values"; \
	else \
		echo ".env file already exists"; \
	fi

## Show help
help:
	@echo "NeuroTrade AI - Available Commands"
	@echo "=================================="
	@echo ""
	@echo "Development:"
	@echo "  make run-go         - Run Go application locally"
	@echo "  make run-python     - Run Python engine locally"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up      - Start all services"
	@echo "  make docker-down    - Stop all services"
	@echo "  make docker-build   - Build Docker images"
	@echo "  make docker-logs    - View all logs"
	@echo "  make docker-clean   - Stop and remove volumes"
	@echo ""
	@echo "Database:"
	@echo "  make psql           - Connect to PostgreSQL"
	@echo "  make redis-cli      - Connect to Redis"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run all tests"
	@echo "  make test-go        - Run Go tests"
	@echo "  make test-python    - Run Python tests"
	@echo ""
	@echo "Utility:"
	@echo "  make setup-env      - Create .env from example"
	@echo "  make clean          - Clean build artifacts"
