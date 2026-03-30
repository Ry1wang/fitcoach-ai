.PHONY: up down test test-unit test-integration test-coverage e2e seed logs db-shell redis-cli stats

up:
	docker compose up -d --build

down:
	docker compose down

test:
	docker compose --profile test up -d postgres-test
	docker compose exec backend pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

test-unit:
	docker compose exec backend pytest tests/unit/ -v --tb=short

test-integration:
	docker compose --profile test up -d postgres-test
	docker compose exec backend pytest tests/integration/ -v --tb=short

test-coverage:
	docker compose --profile test up -d postgres-test
	docker compose exec backend pytest tests/ --cov=app --cov-report=term-missing --cov-report=html:htmlcov --tb=short

e2e:
	python3 scripts/e2e_test.py --base-url http://localhost:8000/api/v1

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
