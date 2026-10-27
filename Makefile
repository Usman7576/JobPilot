# Convenience targets. On Windows without make, run the commands in README.md directly.

.PHONY: env up down logs migrate migration test lint gen-api shell-api

env:            ## create .env with fresh secrets
	python scripts/init_env.py

up:             ## build and start the whole stack
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api worker web

migrate:
	docker compose exec api alembic upgrade head

migration:      ## make migration m="message"
	docker compose exec api alembic revision --autogenerate -m "$(m)"

test:           ## backend tests inside the api container
	docker compose exec -e TEST_DATABASE_URL=postgresql+psycopg://jobpilot:jobpilot@postgres:5432/jobpilot_test -e REDIS_URL=redis://redis:6379/0 api pytest

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app
	cd frontend && npm run lint && npm run typecheck

gen-api:        ## regenerate the typed frontend client from the backend schema
	cd backend && uv run python scripts/export_openapi.py
	cd frontend && npm run gen:api

shell-api:
	docker compose exec api bash
