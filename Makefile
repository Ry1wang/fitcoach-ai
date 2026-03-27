.PHONY: up down test test-unit test-integration seed logs db-shell redis-cli stats

up:
	docker compose up -d --build

down:
	docker compose down

test:
	docker compose --profile test up -d postgres-test
	docker compose exec backend pytest tests/ -v --tb=short

test-unit:
	docker compose exec backend pytest tests/unit/ -v

test-integration:
	docker compose --profile test up -d postgres-test
	docker compose exec backend pytest tests/integration/ -v

seed:
	docker compose exec backend python -m scripts.seed_data

logs:
	docker compose logs -f backend

db-shell:
	docker compose exec postgres psql -U fitcoach -d fitcoach

redis-cli:
	docker compose exec redis redis-cli

stats:
	docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
