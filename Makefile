.PHONY: up down build logs ports lint test migrate format backend-shell frontend-shell

# Start all services
up:
	powershell -NoProfile -ExecutionPolicy Bypass -File .\docker-up.ps1

# Stop all services
down:
	docker compose down

# Build all containers
build:
	docker compose build

# View logs
logs:
	docker compose logs -f

# Show published ports
ports:
	docker compose ps

# Backend shell
backend-shell:
	docker compose exec backend bash

# Frontend shell
frontend-shell:
	docker compose exec frontend sh

# Lint backend
lint:
	cd backend && ruff check .

# Format backend
format:
	cd backend && ruff format .

# Run backend tests
test:
	cd backend && pytest -v

# Run alembic migrations
migrate:
	docker compose exec backend alembic upgrade head

# Create new migration
migration:
	docker compose exec backend alembic revision --autogenerate -m "$(msg)"
