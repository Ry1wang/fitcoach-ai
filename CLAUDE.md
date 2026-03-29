# Project Context: FitCoach AI

## Objective
Build a fitness knowledge assistant powered by RAG + multi-agent architecture. Users upload fitness PDF books (e.g., Convict Conditioning), and the system parses, chunks, embeds, and indexes the content. Users chat with three specialist agents (Training, Rehab, Nutrition) and receive grounded answers with source citations.

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, Pydantic v2, SQLModel, LangChain, LangGraph
- **Frontend**: React 18, Vite 5, TailwindCSS, Zustand
- **Database**: PostgreSQL 16 + pgvector (HNSW index)
- **Cache**: Redis 7 (query cache + fixed-window rate limiting)
- **LLM**: OpenAI-compatible SDK (DeepSeek/OpenAI native; Claude requires LiteLLM proxy)
- **Auth**: JWT (python-jose + passlib bcrypt)
- **PDF**: PyMuPDF + pdfplumber
- **Testing**: Pytest + pytest-asyncio + httpx
- **Infra**: Docker Compose, Mac Mini 8GB

## Coding Standards
- Backend: Python with async/await throughout
- Frontend: TypeScript (may fall back to JavaScript for velocity)
- All config via environment variables (pydantic-settings); no hardcoded secrets
- SQL via SQLAlchemy parameterized queries; no string concatenation
- All data-access queries must include `user_id` filtering (resource isolation)
- Standardized API error format: `{ "error": "CODE", "message": "...", "detail": ... }`
- LLM API calls must use retry + exponential backoff (tenacity)
- Embedding and Chat LLM configs are independent; can point to different providers
- UI is Chinese-only (v1)

## Key Files to Watch
- `docs/dev-doc-v1.3.md` — Development doc (architecture, data model, API, agent design, deployment)
- `docker-compose.yml` — Service orchestration
- `.env` / `.env.example` — Environment configuration
- `backend/app/config.py` — pydantic-settings configuration class
- `backend/app/deps.py` — FastAPI dependency injection (DB session, LLM client, current user)
- `backend/app/agents/graph.py` — LangGraph state machine orchestration
- `backend/app/rag/retriever.py` — pgvector retrieval (user_id-scoped)
- `scripts/init.sql` — Database initialization (CREATE EXTENSION vector; CREATE TABLES)

## Current Focus
Phase 2 Day 7: Chat API + Redis caching
- `POST /chat` endpoint invokes agent graph and returns response. 
- SSE streaming works (routing → sources → tokens → done). 
- Redis query caching: second identical query returns from cache. 
- Rate limiting: 21st request within 1 minute returns 429. 
- Integration tests for chat endpoint (3+ cases). 
- Cache service tests (3+ cases).
