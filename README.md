# LLM Central Gateway

An MVP model gateway that exposes an OpenAI-compatible Qwen endpoint through LiteLLM. Caddy is the only host-facing service; FastAPI manages business users and virtual keys, PostgreSQL stores state, and Redis is ready for shared rate-limit state.

## Local architecture

```text
Client -> Caddy :8080 -> /v1/*     -> LiteLLM -> DashScope/Qwen
                      -> /api/v1/* -> FastAPI

FastAPI -> llm_gateway_business (PostgreSQL)
LiteLLM -> llm_gateway_litellm (PostgreSQL)
LiteLLM -> Redis
```

The existing `local-postgres` Docker container remains separate from this Compose project. Redis data is stored in the `llm-central-gateway_redis_data` Docker volume.

## Setup

Requirements: Python 3.12, `uv`, Docker Desktop, and a PostgreSQL server available on `localhost:5432`.

1. Copy `config.example.ini` to `config.ini` if a local config does not exist, then add the DashScope API key and PostgreSQL credentials.
2. Install the project and initialize generated local secrets plus the two dedicated databases:

   ```bash
   uv sync --all-groups --no-editable
   uv run --no-sync python scripts/bootstrap.py
   ```

3. Start the stack. Always use the wrapper so secrets are passed from `config.ini` without creating a second environment file:

   ```bash
   uv run --no-sync gateway-compose up -d --build
   uv run --no-sync gateway-compose ps
   ```

4. Verify health, then optionally make one short paid Qwen request:

   ```bash
   uv run --no-sync python scripts/smoke_test.py
   uv run --no-sync python scripts/smoke_test.py --live
   ```

The local endpoints are:

- `http://127.0.0.1:8080/v1/chat/completions`
- `http://127.0.0.1:8080/v1/models`
- `http://127.0.0.1:8080/api/v1/docs`
- `http://127.0.0.1:8080/health`

LiteLLM management endpoints and internal container ports are not exposed by Caddy.

## Quick test commands

Run these commands from the repository root after starting the stack. Except for the explicitly marked live test, none calls a model or incurs provider cost.

### Check containers and logs

```bash
# All four project services should be Up; Redis should also be healthy.
uv run --no-sync gateway-compose ps

# Show recent startup and request logs from every service.
uv run --no-sync gateway-compose logs --tail=100

# Follow only the API and LiteLLM logs. Press Ctrl-C to stop following.
uv run --no-sync gateway-compose logs -f api litellm
```

### Check the public gateway and control API

```bash
# Caddy health: expect HTTP 200.
curl -i http://127.0.0.1:8080/health

# FastAPI health and dependency readiness: both should return HTTP 200.
curl -i http://127.0.0.1:8080/api/v1/health
curl -i http://127.0.0.1:8080/api/v1/ready

# API documentation and schema should be reachable through Caddy.
curl -I http://127.0.0.1:8080/api/v1/docs
curl -I http://127.0.0.1:8080/api/v1/openapi.json

# An unknown route should return HTTP 404.
curl -i http://127.0.0.1:8080/not-found

# The model endpoint without a key should return HTTP 401.
curl -i http://127.0.0.1:8080/v1/models
```

The bundled health smoke test performs the first three successful checks together:

```bash
uv run --no-sync python scripts/smoke_test.py
```

### Check Redis and PostgreSQL

```bash
# Redis should respond with PONG.
docker exec llm-central-gateway-redis-1 redis-cli PING

# Inspect the current number of Redis keys and keyspace statistics.
docker exec llm-central-gateway-redis-1 redis-cli DBSIZE
docker exec llm-central-gateway-redis-1 redis-cli INFO keyspace

# The existing PostgreSQL container should report that it accepts connections.
docker exec local-postgres pg_isready

# Confirm both isolated project databases exist without displaying credentials.
docker exec local-postgres psql -U postgres -d postgres -Atc \
  "SELECT datname FROM pg_database WHERE datname IN ('llm_gateway_business', 'llm_gateway_litellm') ORDER BY datname;"
```

An empty Redis database is currently expected: Redis is installed and reachable, but distributed rate-limit state has not yet been implemented.

### Run the complete live model test

```bash
uv run --no-sync python scripts/smoke_test.py --live
```

This command creates a temporary business user and LiteLLM virtual key, sends one short streaming request to `qwen-plus`, validates the SSE response, and therefore incurs a very small DashScope charge. It does not print any API key.

After testing, inspect the API log or stop the stack:

```bash
tail -n 20 logs/app.log
uv run --no-sync gateway-compose down
```

## Admin flow

Read `ADMIN_API_TOKEN` locally from `config.ini` and send it as a Bearer token to the control API. Create a user with `POST /api/v1/admin/users`, then create a virtual key with `POST /api/v1/admin/users/{user_id}/keys`. The returned key is shown only once. The control API also supports usage lookup and key disabling; see `/api/v1/docs` for schemas.

## Development checks

```bash
uv run --no-sync ruff format --check .
uv run --no-sync ruff check .
uv run --no-sync mypy src
uv run --no-sync pytest -q
uv run --no-sync gateway-compose config --quiet
```

View logs with `uv run --no-sync gateway-compose logs -f` and stop the stack with `uv run --no-sync gateway-compose down`. Do not add `-v` unless intentionally deleting Redis data. Never commit `config.ini`, provider keys, generated admin/master keys, or runtime logs.
