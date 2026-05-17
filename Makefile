# =============================================================================
# Crypto Funding Rate Dashboard — Makefile
# =============================================================================
# Quick start:  make up
# Stop:         make down
# See all:      make help
# =============================================================================

.DEFAULT_GOAL := help

# ── Service Management ───────────────────────────────────────────────────────

up:  ## Start all services
	docker compose up -d
	@echo "Backend  http://localhost:8000  |  Frontend  http://localhost:5173  |  Grafana  http://localhost:3001"

up-backend:  ## Start only backend + db + redis
	docker compose up -d db redis backend

down:  ## Stop all services
	docker compose down

restart-backend:  ## Restart backend only (picks up code changes)
	docker compose restart backend

logs:  ## Tail backend logs
	docker compose logs -f backend

logs-all:  ## Tail all services
	docker compose logs -f

ps:  ## Show service status
	docker compose ps

# ── Database ─────────────────────────────────────────────────────────────────

db-shell:  ## Open psql shell
	docker compose exec db psql -U postgres -d funding_rates

db-analyze:  ## Table stats (rows, size, growth rate)
	docker compose exec db psql -U postgres -d funding_rates -c " \
		SELECT '表總覽' as info, \
		       COUNT(*) as total_rows, \
		       pg_size_pretty(pg_total_relation_size('funding_rates')) as total_size, \
		       COUNT(DISTINCT exchange) as exchanges, \
		       COUNT(DISTINCT symbol) as symbols, \
		       ROUND(COUNT(*)::numeric / NULLIF(EXTRACT(EPOCH FROM (MAX(timestamp)-MIN(timestamp)))/86400,0), 0) as rows_per_day \
		FROM funding_rates;"

db-analyze-exchange:  ## Rows/exchange + dedup ratio
	docker compose exec db psql -U postgres -d funding_rates -c " \
		SELECT exchange, COUNT(*) as rows, \
		       pg_size_pretty(SUM(pg_column_size(funding_rates.*))::bigint) as size, \
		       MIN(timestamp)::date as since, MAX(timestamp)::date as until, \
		       EXTRACT(DAY FROM (MAX(timestamp)-MIN(timestamp)))::int as days \
		FROM funding_rates GROUP BY exchange ORDER BY rows DESC;"

db-dedup-ratio:  ## Dedup ratio for BTCUSDT per exchange
	docker compose exec db psql -U postgres -d funding_rates -c " \
		SELECT exchange, COUNT(*) as rows, COUNT(DISTINCT rate::text) as unique_rates, \
		       ROUND(100.0 - 100.0 * COUNT(DISTINCT rate::text) / NULLIF(COUNT(*),0), 2) as redundant_pct \
		FROM funding_rates WHERE symbol='BTCUSDT' \
		GROUP BY exchange ORDER BY exchange;"

db-migrate:  ## Run Alembic migrations
	docker compose exec backend python3 -c "from alembic.config import Config; from alembic.command import upgrade; upgrade(Config('backend/alembic.ini'), 'head')"

db-reset:  ## ⚠️ DROP all data + re-create schema + re-migrate
	@echo "⚠️  DROP all data in funding_rates?"
	@read -p "Type yes to confirm: " c; \
	if [ "$$c" = "yes" ]; then \
		docker compose exec db psql -U postgres -d funding_rates -c "DROP TABLE IF EXISTS funding_rates CASCADE; DROP TABLE IF EXISTS alembic_version;"; \
		make db-migrate; \
		echo "✅ Done"; \
	else \
		echo "Cancelled."; \
	fi

db-dedup-old-data:  ## 🧹 Deduplicate pre-fix rows to 1 per funding period
	@echo "Aggregating old rows into per-funding-period rows..."
	@read -p "Type yes to confirm: " c; \
	if [ "$$c" = "yes" ]; then \
		docker compose exec db psql -U postgres -d funding_rates -c " \
			WITH dedup AS ( \
				SELECT DISTINCT ON (exchange, symbol, \
				    CASE WHEN settlement_time IS NOT NULL AND funding_interval > 0 \
				         THEN settlement_time - (funding_interval || ' hours')::interval \
				         ELSE date_trunc('hour', timestamp) END) \
				    exchange, symbol, \
				    CASE WHEN settlement_time IS NOT NULL AND funding_interval > 0 \
				         THEN settlement_time - (funding_interval || ' hours')::interval \
				         ELSE date_trunc('hour', timestamp) END AS ts, \
				    rate, funding_interval, settlement_time \
				FROM funding_rates \
				ORDER BY 1, 2, 3 DESC, timestamp DESC) \
			DELETE FROM funding_rates f \
			WHERE (f.exchange, f.symbol, f.timestamp) NOT IN ( \
			    SELECT exchange, symbol, ts FROM dedup);" \
		&& echo "✅ Done. Run 'make db-analyze' to verify." \
		|| echo "❌ Failed."; \
	else \
		echo "Cancelled."; \
	fi

db-dedup-dry-run:  ## Preview dedup impact
	docker compose exec db psql -U postgres -d funding_rates -c " \
		WITH dedup AS ( \
			SELECT DISTINCT ON (exchange, symbol, \
			    CASE WHEN settlement_time IS NOT NULL AND funding_interval > 0 \
			         THEN settlement_time - (funding_interval || ' hours')::interval \
			         ELSE date_trunc('hour', timestamp) END) \
			    exchange, symbol \
			FROM funding_rates) \
		SELECT '去重後保留' as info, COUNT(*)::text as rows FROM dedup \
		UNION ALL SELECT '目前總行數', COUNT(*)::text FROM funding_rates \
		UNION ALL SELECT '預計刪除', (SELECT (COUNT(*) - (SELECT COUNT(*) FROM dedup))::text FROM funding_rates);"

db-backup:  ## Backup database to ./backups/
	@mkdir -p backups
	docker compose exec db pg_dump -U postgres -d funding_rates --no-owner --no-acl > backups/dump_$$(date +%Y%m%d_%H%M%S).sql
	gzip backups/dump_*.sql 2>/dev/null; echo "✅ Saved to backups/"

db-restore:  ## Restore: make db-restore FILE=backups/dump_20260517.sql.gz
	@if [ -z "$(FILE)" ]; then echo "Usage: make db-restore FILE=backups/dump_20260517.sql.gz"; exit 1; fi
	@read -p "Replace all data? Type yes: " c; \
	if [ "$$c" = "yes" ]; then \
		gunzip -c $(FILE) | docker compose exec -T db psql -U postgres -d funding_rates && echo "✅ Done" || echo "❌ Failed."; \
	else \
		echo "Cancelled."; \
	fi

# ── Testing ──────────────────────────────────────────────────────────────────

test:  ## Run all tests with coverage
	docker compose exec backend python3 -m pytest backend/tests/ -v --tb=short --cov=backend.app --cov-report=term-missing

test-quick:  ## Quick test (fail-fast, no coverage)
	docker compose exec backend python3 -m pytest backend/tests/ -x --tb=short -q

# ── Backfill ─────────────────────────────────────────────────────────────────

backfill:  ## Backfill all 6 supported exchanges, last 30 days
	docker compose exec backend python3 -m backend.app.backfill --all --days 30

backfill-dryrun:  ## Preview backfill (count rows, no writes)
	docker compose exec backend python3 -m backend.app.backfill --all --days 30 --dry-run

backfill-btc:  ## Backfill BTC only, all exchanges, 30 days
	docker compose exec backend python3 -m backend.app.backfill --exchanges binance,bybit,okx,gate,mexc,bingx --days 30 --symbols BTCUSDT,BTCUSDT,BTC-USDT-SWAP,BTC_USDT,BTC_USDT,BTC-USDT

backfill-top10:  ## Backfill top 10 symbols, 30 days
	docker compose exec backend python3 -m backend.app.backfill --all --days 30 --symbols BTCUSDT,ETHUSDT,SOLUSDT,DOGEUSDT,PEPEUSDT,XRPUSDT,ADAUSDT,AVAXUSDT,LINKUSDT,BNBUSDT

backfill-top10-90d:  ## Backfill top 10 symbols, 90 days
	docker compose exec backend python3 -m backend.app.backfill --all --days 90 --symbols BTCUSDT,ETHUSDT,SOLUSDT,DOGEUSDT,PEPEUSDT,XRPUSDT,ADAUSDT,AVAXUSDT,LINKUSDT,BNBUSDT

# ── Development Shell ────────────────────────────────────────────────────────

shell-backend:  ## Open bash in backend container
	docker compose exec backend bash

shell-db:  ## Open psql
	docker compose exec db psql -U postgres -d funding_rates

shell-redis:  ## Open redis-cli
	docker compose exec redis redis-cli

shell-python:  ## Open Python REPL
	docker compose exec backend python3

# ── Build & Rebuild ──────────────────────────────────────────────────────────

build:  ## Rebuild backend image (after requirements.txt changes)
	docker compose build backend

rebuild:  ## Full rebuild + restart
	docker compose build backend && docker compose up -d

restart:  ## Restart all services
	docker compose down && docker compose up -d

deploy:  ## Deploy to production (git pull → build → restart → verify)
	@echo "┌─────────────────────────────────────────────┐"
	@echo "│  Deploy to production                        │"
	@echo "└─────────────────────────────────────────────┘"
	@echo ""
	git pull origin main
	docker compose build backend
	docker compose up -d --force-recreate backend
	@sleep 5
	@echo ""
	@echo "─── Health check ───"
	curl -s http://localhost:8000/api/health/ready | python3 -m json.tool
	@echo ""
	@echo "✅ Deploy complete"

# ── Monitoring ───────────────────────────────────────────────────────────────

redis-flush:  ## ⚠️ Clear all Redis cache (safe — DB has full data)
	docker compose exec redis redis-cli FLUSHALL
	@echo "✅ Redis cleared"

redis-keys:  ## Count Redis keys
	docker compose exec redis redis-cli DBSIZE

metrics:  ## Show Prometheus metrics
	docker compose exec backend python3 -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/metrics').read().decode()[:2000])"

health:  ## Check backend health
	docker compose exec backend python3 -c "import urllib.request; r = urllib.request.urlopen('http://localhost:8000/api/health/ready'); print(r.status, r.read().decode())"

# ── Help ─────────────────────────────────────────────────────────────────────

help:  ## Show this help
	@echo "┌─────────────────────────────────────────────────────────────┐"
	@echo "│  Crypto Funding Rate Dashboard — Makefile                   │"
	@echo "│  Usage: make <target>                                       │"
	@echo "└─────────────────────────────────────────────────────────────┘"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Quick Start:"
	@echo "  make up          # Start everything"
	@echo "  make test        # Run tests"
	@echo "  make logs        # Watch backend"
	@echo "  make db-analyze  # Check DB size"
	@echo "  make health      # Health check"
	@echo "  make deploy      # Deploy to production"
