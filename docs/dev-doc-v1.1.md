# FitCoach AI — Project Development Document

> **Version:** 1.1  
> **Last Updated:** 2026-03-27  
> **Author:** Ry1wang  
> **Repository:** github.com/Ry1wang/fitcoach-ai

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Environment & Configuration](#4-environment--configuration)
5. [Data Structure](#5-data-structure)
6. [Data Flow](#6-data-flow)
7. [API Specification](#7-api-specification)
8. [Multi-Agent Design](#8-multi-agent-design)
9. [Key Functional Logic](#9-key-functional-logic)
10. [Error Handling Strategy](#10-error-handling-strategy)
11. [Security Design](#11-security-design)
12. [Caching Strategy](#12-caching-strategy)
13. [Logging & Observability](#13-logging--observability)
14. [Testing Strategy](#14-testing-strategy)
15. [Deployment Architecture](#15-deployment-architecture)
16. [Development Milestones](#16-development-milestones)
17. [Dependency & Risk Register](#17-dependency--risk-register)

---

## 1. Project Overview

### 1.1 What Is FitCoach AI

FitCoach AI is a production-grade fitness knowledge assistant that combines RAG (Retrieval-Augmented Generation) with a multi-agent architecture. Users upload fitness-related books (such as Convict Conditioning, sports rehabilitation references), and the system ingests, chunks, embeds, and indexes the content. Users then interact with specialized AI agents — Training, Rehab, and Nutrition — via a conversational interface. A Router Agent automatically classifies user intent and dispatches queries to the appropriate specialist agent, which retrieves relevant document passages and generates grounded, cited answers.

### 1.2 Core Capabilities

- **Document Ingestion Pipeline**: Upload PDF books → automatic parsing, chunking, embedding, and vector storage in PostgreSQL (pgvector).
- **Multi-Agent Orchestration**: A Router Agent classifies user intent and delegates to domain-specific agents (Training, Rehab, Nutrition), each with tailored retrieval strategies and system prompts.
- **Conversational Interface**: Multi-turn chat with streaming responses (SSE), conversation history persistence, and source citations.
- **Dual Access**: Web UI (React) and external API consumption (Feishu bot via OpenClaw).
- **Query Caching**: Redis-backed response caching to reduce latency and LLM API cost on repeated or similar queries.

### 1.3 Non-Goals (Out of Scope)

- User-generated content or social features.
- Model fine-tuning or training.
- Real-time exercise tracking or device integration.
- Multi-tenancy or team/organization management.
- Internationalization (UI in Chinese only for v1).

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
                         ┌─────────────────────────────────────────────────────────┐
                         │                    Docker Compose                        │
                         │                                                         │
  ┌────────────┐         │   ┌────────────┐        ┌──────────────────────────┐    │
  │   React    │ ◄──HTTP──┼─▶│  FastAPI    │───────▶│  PostgreSQL 16           │    │
  │  Frontend  │         │   │  Backend    │        │  + pgvector extension    │    │
  │  :3000     │         │   │  :8000      │        │  :5432                   │    │
  └────────────┘         │   └─────┬───────┘        │                          │    │
                         │         │                │  Tables:                 │    │
  ┌────────────┐         │         │                │  ├── users               │    │
  │  Feishu    │ ◄──HTTP──┼────────┤                │  ├── documents           │    │
  │  OpenClaw  │         │         │                │  ├── document_chunks     │    │
  └────────────┘         │         │                │  ├── conversations       │    │
                         │         ▼                │  └── messages            │    │
                         │   ┌────────────┐         └──────────────────────────┘    │
                         │   │ LangChain  │                                         │
                         │   │ + LangGraph│         ┌──────────────────────────┐    │
                         │   │            │◄───────▶│  Redis 7                  │    │
                         │   │ ┌────────┐ │         │  :6379                    │    │
                         │   │ │ Router │ │         │  ├── query response cache │    │
                         │   │ │ Agent  │ │         │  └── rate limiter         │    │
                         │   │ └───┬────┘ │         └──────────────────────────┘    │
                         │   │     │      │                                         │
                         │   │  ┌──┴───┬──────────┐                                │
                         │   │  ▼      ▼          ▼                                │
                         │   │┌──────┐┌─────┐┌─────────┐                           │
                         │   ││Train ││Rehab││Nutrition│                           │
                         │   ││Agent ││Agent││ Agent   │                           │
                         │   │└──────┘└─────┘└─────────┘                           │
                         │   └────────────┘                                         │
                         │         │                                                │
                         │         ▼ (External API calls)                           │
                         │   ┌──────────────────┐                                   │
                         │   │ LLM Provider API │                                   │
                         │   │ (Chat + Embedding)│                                   │
                         │   │ DeepSeek / OpenAI │                                   │
                         │   │  / Claude / etc.  │                                   │
                         │   └──────────────────┘                                   │
                         └─────────────────────────────────────────────────────────┘
```

### 2.2 Component Responsibilities

| Component | Responsibility | Stateful? |
|-----------|---------------|-----------|
| React Frontend | User interface, document management, chat rendering, SSE stream consumption | No (JWT in localStorage) |
| FastAPI Backend | API gateway, authentication, business logic orchestration, agent invocation | No (stateless; delegates to DB/Redis) |
| PostgreSQL + pgvector | Persistent storage for users, documents, chunks, conversations, messages; vector similarity search | Yes |
| Redis | Query response caching, API rate limiting | Yes (ephemeral) |
| LangChain / LangGraph | RAG pipeline, multi-agent orchestration, LLM interaction | No (state passed per invocation) |
| LLM Provider API | LLM inference (chat completion) and text embedding generation. Provider-agnostic via OpenAI-compatible SDK (supports DeepSeek, OpenAI, Claude, etc.) | External service |

### 2.3 Network Topology

All services communicate within a Docker Compose internal network. Only the frontend (:3000) and backend (:8000) expose ports to the host. PostgreSQL and Redis are accessible only within the Docker network. The LLM Provider API (DeepSeek, OpenAI, or Claude) is the sole external dependency, configurable via environment variables.

```
Host Machine (Mac Mini)
│
├── :3000 → frontend container
├── :8000 → backend container
│
Docker Internal Network (fitcoach-net)
│
├── postgres:5432  (internal only)
├── redis:6379     (internal only)
├── backend:8000   (bridged to host)
└── frontend:3000  (bridged to host)
```

---

## 3. Technology Stack

### 3.1 Stack Selection

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Frontend | React + Vite | React 18, Vite 5 | Component-based SPA with fast HMR; Vite eliminates Webpack complexity |
| Frontend Styling | TailwindCSS | 3.x | Utility-first CSS avoids context-switching to separate stylesheets |
| Frontend State | Zustand | 4.x | Minimal API surface (single-file store), sufficient for this scale |
| Backend Framework | FastAPI | 0.110+ | Async-native, auto-generated OpenAPI docs, Pydantic-integrated |
| Data Validation | Pydantic v2 | 2.x | Runtime type validation for request/response and configuration |
| ORM | SQLModel | 0.x | Unifies SQLAlchemy table definitions with Pydantic schemas, reducing boilerplate |
| Database | PostgreSQL | 16 | Mature relational DB with JSONB, CTEs, and native pgvector support |
| Vector Search | pgvector | 0.7+ | Co-locating vectors with relational data avoids cross-system joins and simplifies backup/restore |
| Cache / Rate Limit | Redis | 7 (Alpine) | In-memory key-value store; low latency for cache-aside and sliding-window rate limiting |
| RAG Framework | LangChain | 0.2+ | Document loaders, text splitters, retriever abstractions, broad LLM provider support |
| Agent Orchestration | LangGraph | 0.1+ | Explicit state machine graphs for multi-agent workflows; supports cycles, branching, checkpointing |
| LLM Provider | OpenAI-compatible API | — | Provider-agnostic design via OpenAI SDK; supports DeepSeek, OpenAI, Claude (via compatible endpoint). Chat and embedding providers can be configured independently — switch by changing `.env` only, no code changes |
| Auth | python-jose (JWT) | — | Stateless token authentication; no session storage needed |
| Testing | Pytest + pytest-asyncio + httpx | — | Async test support, parametrization, fixture-based architecture |
| Containerization | Docker + Docker Compose | — | Reproducible multi-service deployment; single-command startup |

### 3.2 Language & Runtime

- **Backend**: Python 3.11+
- **Frontend**: TypeScript (optional, can fall back to JavaScript if velocity is prioritized)
- **Database**: SQL (PostgreSQL dialect)
- **Infrastructure**: YAML (Docker Compose), Bash (Makefile scripts)

---

## 4. Environment & Configuration

### 4.1 Configuration Management

All configuration is managed via environment variables, loaded through `pydantic-settings`. No hardcoded secrets or connection strings in source code.

```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str
    CACHE_TTL_SECONDS: int = 3600       # 1 hour default

    # LLM Configuration (provider-agnostic)
    # All providers accessed via OpenAI-compatible SDK
    LLM_API_KEY: str
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_CHAT_MODEL: str = "deepseek-chat"
    LLM_TEMPERATURE: float = 0.3

    # Embedding Configuration (can use a different provider than LLM)
    # Falls back to LLM_* values if not explicitly set
    EMBEDDING_API_KEY: str | None = None
    EMBEDDING_BASE_URL: str | None = None
    EMBEDDING_MODEL: str = "deepseek-embedding"
    EMBEDDING_DIMENSION: int = 1024

    # Auth
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440      # 24 hours

    # Upload
    UPLOAD_DIR: str = "/app/uploads"
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list[str] = [".pdf"]

    # Agent
    AGENT_MAX_ITERATIONS: int = 5
    RETRIEVAL_TOP_K: int = 5

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 20

    @property
    def effective_embedding_api_key(self) -> str:
        return self.EMBEDDING_API_KEY or self.LLM_API_KEY

    @property
    def effective_embedding_base_url(self) -> str:
        return self.EMBEDDING_BASE_URL or self.LLM_BASE_URL

    model_config = {"env_file": ".env"}
```

> **Design Decision — Separated LLM and Embedding Configuration:**
> The LLM (chat) and Embedding providers are configured independently because not all LLM providers offer embedding endpoints. For example, Claude does not provide an embedding API, so a deployment using Claude for chat may use OpenAI or another provider for embeddings. The `EMBEDDING_*` fields fall back to `LLM_*` values when not set, so single-provider setups (e.g., DeepSeek for both) require no extra configuration.

> **Important Constraint — Embedding Dimension Consistency:**
> The `EMBEDDING_DIMENSION` value determines the pgvector column size in `document_chunks`. If you switch embedding providers (e.g., DeepSeek 1024-dim → OpenAI 1536-dim), existing vectors become incompatible and all documents must be re-ingested. The chat model, however, can be swapped freely at any time without side effects.

### 4.2 Environment Files

```bash
# .env.example (committed to repo)
DATABASE_URL=postgresql+asyncpg://fitcoach:fitcoach_dev@postgres:5432/fitcoach
REDIS_URL=redis://redis:6379/0
JWT_SECRET=your-secret-key-change-in-production

# LLM Provider (switch by changing these values — no code changes needed)
LLM_API_KEY=sk-xxxxxxxxxxxx
LLM_BASE_URL=https://api.deepseek.com
LLM_CHAT_MODEL=deepseek-chat

# Embedding Provider (optional — falls back to LLM_* if not set)
# EMBEDDING_API_KEY=sk-openai-xxx
# EMBEDDING_BASE_URL=https://api.openai.com/v1
# EMBEDDING_MODEL=text-embedding-3-small
# EMBEDDING_DIMENSION=1536
EMBEDDING_MODEL=deepseek-embedding
EMBEDDING_DIMENSION=1024

# .env (git-ignored, actual secrets)
# Copy from .env.example and fill in real values
```

**Provider Configuration Examples:**

```bash
# --- DeepSeek (default, single provider for both LLM and embedding) ---
LLM_API_KEY=sk-deepseek-xxx
LLM_BASE_URL=https://api.deepseek.com
LLM_CHAT_MODEL=deepseek-chat
EMBEDDING_MODEL=deepseek-embedding
EMBEDDING_DIMENSION=1024

# --- OpenAI (single provider for both) ---
LLM_API_KEY=sk-openai-xxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_CHAT_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536

# --- Claude for chat + OpenAI for embeddings (mixed providers) ---
LLM_API_KEY=sk-ant-xxx
LLM_BASE_URL=https://api.anthropic.com/v1
LLM_CHAT_MODEL=claude-sonnet-4-20250514
EMBEDDING_API_KEY=sk-openai-xxx
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536
```

### 4.3 Makefile Shortcuts

```makefile
.PHONY: up down test seed logs

up:
	docker compose up -d --build

down:
	docker compose down

test:
	docker compose exec backend pytest tests/ -v --tb=short

test-unit:
	docker compose exec backend pytest tests/unit/ -v

test-integration:
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
```

---

## 5. Data Structure

### 5.1 Entity-Relationship Diagram

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────────┐
│    users     │       │    documents      │       │  document_chunks │
├──────────────┤       ├──────────────────┤       ├──────────────────┤
│ id (PK, UUID)│◄──┐   │ id (PK, UUID)    │◄──┐   │ id (PK, UUID)   │
│ username     │   ├──▶│ user_id (FK)     │   ├──▶│ document_id (FK)│
│ email        │   │   │ filename         │   │   │ content (TEXT)   │
│ hashed_pwd   │   │   │ file_path        │   │   │ chunk_index     │
│ created_at   │   │   │ file_size        │   │   │ content_type    │
│ is_active    │   │   │ content_type     │   │   │ metadata (JSONB)│
└──────────────┘   │   │ chunk_count      │   │   │ embedding (vec) │
                   │   │ status           │   │   │ created_at      │
                   │   │ created_at       │   │   └──────────────────┘
                   │   │ updated_at       │   │
                   │   └──────────────────┘   │
                   │                          │
                   │   ┌──────────────────┐   │
                   │   │  conversations   │   │
                   │   ├──────────────────┤   │
                   └──▶│ id (PK, UUID)    │   │
                       │ user_id (FK)     │   │
                       │ title            │   │
                       │ created_at       │   │
                       │ updated_at       │   │
                       └────────┬─────────┘   │
                                │             │
                       ┌────────▼─────────┐   │
                       │    messages       │   │
                       ├──────────────────┤   │
                       │ id (PK, UUID)    │   │
                       │ conversation_id  │───┘
                       │ role             │
                       │ content (TEXT)   │
                       │ agent_used       │
                       │ sources (JSONB)  │
                       │ latency_ms       │
                       │ created_at       │
                       └──────────────────┘
```

### 5.2 Table Definitions

#### 5.2.1 users

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK, DEFAULT gen_random_uuid() | Primary key |
| username | VARCHAR(50) | UNIQUE, NOT NULL | Display name |
| email | VARCHAR(100) | UNIQUE, NOT NULL | Login identifier |
| hashed_password | VARCHAR(255) | NOT NULL | bcrypt hashed password |
| created_at | TIMESTAMP | DEFAULT NOW() | Registration time |
| is_active | BOOLEAN | DEFAULT TRUE | Soft delete flag |

#### 5.2.2 documents

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Primary key |
| user_id | UUID | FK → users.id | Document owner |
| filename | VARCHAR(255) | NOT NULL | Original filename |
| file_path | VARCHAR(500) | NOT NULL | Server-side storage path |
| file_size | INTEGER | — | File size in bytes |
| content_type | VARCHAR(50) | — | Domain classification: 'training', 'rehab', 'nutrition' |
| chunk_count | INTEGER | DEFAULT 0 | Number of chunks generated |
| status | VARCHAR(20) | DEFAULT 'pending' | Processing status: pending → processing → ready → failed |
| error_message | TEXT | — | Error detail when status = 'failed' |
| created_at | TIMESTAMP | DEFAULT NOW() | Upload time |
| updated_at | TIMESTAMP | DEFAULT NOW() | Last status change |

#### 5.2.3 document_chunks

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Primary key |
| document_id | UUID | FK → documents.id, ON DELETE CASCADE | Parent document |
| content | TEXT | NOT NULL | Chunk text content |
| chunk_index | INTEGER | NOT NULL | Position within document |
| content_type | VARCHAR(50) | — | Content classification: 'text', 'table', 'exercise', 'definition' |
| metadata | JSONB | — | Structured metadata (see 5.3) |
| embedding | vector(1024) | — | Embedding vector (dimension matches EMBEDDING_DIMENSION config; must re-ingest if changed) |
| created_at | TIMESTAMP | DEFAULT NOW() | Ingestion time |

**Indexes:**
```sql
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_chunks_document ON document_chunks (document_id);
CREATE INDEX idx_chunks_metadata ON document_chunks USING gin (metadata);
```

#### 5.2.4 conversations

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Primary key |
| user_id | UUID | FK → users.id | Conversation owner |
| title | VARCHAR(255) | — | Auto-generated from first message |
| created_at | TIMESTAMP | DEFAULT NOW() | Creation time |
| updated_at | TIMESTAMP | DEFAULT NOW() | Last message time |

#### 5.2.5 messages

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | Primary key |
| conversation_id | UUID | FK → conversations.id, ON DELETE CASCADE | Parent conversation |
| role | VARCHAR(20) | NOT NULL | 'user' or 'assistant' |
| content | TEXT | NOT NULL | Message text |
| agent_used | VARCHAR(50) | — | Which agent handled this: 'router', 'training', 'rehab', 'nutrition' |
| sources | JSONB | — | Retrieved chunk references (see 5.3) |
| latency_ms | INTEGER | — | End-to-end response time |
| created_at | TIMESTAMP | DEFAULT NOW() | Message time |

### 5.3 JSONB Schema Conventions

#### document_chunks.metadata

```json
{
    "source_book": "囚徒健身",
    "chapter": "第5章",
    "section": "引体向上的进阶训练",
    "page_start": 87,
    "page_end": 89,
    "content_domain": "training"
}
```

#### messages.sources

```json
[
    {
        "chunk_id": "uuid",
        "content_preview": "前50字的内容预览...",
        "source_book": "囚徒健身",
        "chapter": "第5章",
        "section": "引体向上的进阶训练",
        "relevance_score": 0.87
    }
]
```

### 5.4 Redis Key Schema

| Key Pattern | Value Type | TTL | Description |
|-------------|-----------|-----|-------------|
| `cache:query:{md5_hash}` | JSON string | 3600s | Cached agent response (hash of query + content_type) |
| `ratelimit:{user_id}:{minute}` | Integer (counter) | 60s | Request count in current minute window |

---

## 6. Data Flow

### 6.1 Document Ingestion Flow

```
User uploads PDF
        │
        ▼
┌─────────────────────┐
│ POST /api/v1/       │
│ documents/upload    │
│                     │
│ 1. Validate file    │─── Reject if not PDF or > 50MB
│    (extension, size)│
│ 2. Save to disk     │──▶ /app/uploads/{user_id}/{uuid}.pdf
│ 3. Create DB record │──▶ INSERT INTO documents (status='pending')
│ 4. Enqueue bg task  │
│ 5. Return 202       │──▶ { "id": "uuid", "status": "pending" }
└────────┬────────────┘
         │
         ▼  (BackgroundTask)
┌─────────────────────┐
│ Document Processing  │
│ Pipeline             │
│                      │
│ 1. UPDATE status =   │
│    'processing'      │
│                      │
│ 2. Parse PDF         │──▶ PyMuPDF: extract text by page
│    (extract text,    │──▶ pdfplumber: extract tables
│     tables, metadata)│
│                      │
│ 3. Chunk content     │──▶ Split by semantic boundaries
│    - text → RecursiveCharacterTextSplitter (800 tokens, 200 overlap)
│    - tables → preserve as single chunks
│    - exercises → one chunk per exercise description
│                      │
│ 4. Classify chunks   │──▶ Label each chunk: text / table / exercise / definition
│                      │
│ 5. Generate          │──▶ Embedding API (batch, max 25 per call)
│    embeddings        │
│                      │
│ 6. Store chunks      │──▶ BATCH INSERT INTO document_chunks
│                      │
│ 7. UPDATE status =   │
│    'ready',          │
│    chunk_count = N   │
└──────────────────────┘
         │
         ▼  (On failure at any step)
┌──────────────────────┐
│ UPDATE status =      │
│   'failed',          │
│   error_message = ?  │
└──────────────────────┘
```

### 6.2 Chat Query Flow

```
User sends message
        │
        ▼
┌─────────────────────────┐
│ POST /api/v1/chat        │
│                          │
│ 1. Authenticate (JWT)    │─── 401 if invalid
│ 2. Rate limit check      │──▶ Redis INCR ratelimit:{user_id}:{minute}
│                          │─── 429 if > 20 req/min
│ 3. Check query cache     │──▶ Redis GET cache:query:{hash}
│    ├── Cache HIT         │──▶ Return cached response immediately
│    └── Cache MISS        │──▶ Continue to step 4
│                          │
│ 4. Load/create           │──▶ SELECT or INSERT conversation
│    conversation          │
│                          │
│ 5. Save user message     │──▶ INSERT INTO messages (role='user')
│                          │
│ 6. Invoke Agent Graph    │──▶ See section 6.3
│    (LangGraph)           │
│                          │
│ 7. Stream response       │──▶ SSE: routing → sources → tokens → done
│    via SSE               │
│                          │
│ 8. Save assistant msg    │──▶ INSERT INTO messages (role='assistant',
│                          │        agent_used, sources, latency_ms)
│                          │
│ 9. Cache response        │──▶ Redis SET cache:query:{hash} TTL=3600
└──────────────────────────┘
```

### 6.3 Agent Orchestration Flow (LangGraph)

```
                  ┌─────────┐
                  │  START   │
                  └────┬────┘
                       │
                       ▼
              ┌────────────────┐
              │  Router Agent   │
              │                 │
              │  Input:         │
              │  - user query   │
              │  - chat history │
              │                 │
              │  Output:        │
              │  - agent_name   │
              │  - refined_query│
              └───────┬────────┘
                      │
           ┌──────────┼──────────┐
           ▼          ▼          ▼
     ┌──────────┐ ┌────────┐ ┌──────────┐
     │ Training │ │ Rehab  │ │Nutrition │
     │  Agent   │ │ Agent  │ │  Agent   │
     │          │ │        │ │          │
     │ 1.Retrieve│ │1.Retrieve│ │1.Retrieve│
     │   chunks │ │  chunks│ │  chunks  │
     │ 2.Build  │ │2.Build │ │2.Build   │
     │   prompt │ │  prompt│ │  prompt  │
     │ 3.LLM   │ │3.LLM  │ │3.LLM    │
     │   call   │ │  call  │ │  call    │
     └────┬─────┘ └───┬────┘ └────┬─────┘
          │           │           │
          └───────────┼───────────┘
                      │
                      ▼
              ┌───────────────┐
              │  Format       │
              │  Response     │
              │               │
              │  - answer     │
              │  - sources    │
              │  - agent_used │
              │  - disclaimer │
              │    (if rehab) │
              └───────┬───────┘
                      │
                      ▼
                  ┌────────┐
                  │  END    │
                  └────────┘
```

### 6.4 SSE Streaming Protocol

The chat endpoint uses Server-Sent Events to stream responses to the client. Event types:

| Event Type | Payload | When |
|-----------|---------|------|
| `routing` | `{ "agent": "training", "refined_query": "..." }` | After Router Agent classifies intent |
| `sources` | `{ "chunks": [ { "content_preview", "source_book", "chapter", "score" } ] }` | After retrieval, before LLM generation |
| `token` | `{ "content": "..." }` | Each token from LLM streaming response |
| `done` | `{ "agent_used": "training", "latency_ms": 2340, "conversation_id": "uuid" }` | Stream complete |
| `error` | `{ "message": "...", "code": "..." }` | On failure |

Client-side handling:

```
EventSource connection → /api/v1/chat/stream?token=xxx

on "routing"  → show "正在分析问题... → 训练 Agent"
on "sources"  → render source cards (collapsed)
on "token"    → append to message bubble
on "done"     → finalize UI, enable input
on "error"    → show error toast, re-enable input
```

---

## 7. API Specification

### 7.1 Endpoint Overview

```
Base URL: http://localhost:8000/api/v1

Auth
  POST   /auth/register               # Create account
  POST   /auth/login                  # Obtain JWT token

Documents
  POST   /documents/upload            # Upload PDF (multipart/form-data)
  GET    /documents                   # List user's documents
  GET    /documents/{document_id}     # Document detail + processing status
  DELETE /documents/{document_id}     # Remove document and all its chunks

Chat
  POST   /chat                        # Send message + stream response (SSE)
  GET    /conversations               # List user's conversations
  GET    /conversations/{id}          # Full conversation history
  DELETE /conversations/{id}          # Delete conversation

System
  GET    /health                      # Service health (DB, Redis, LLM Provider)
  GET    /stats                       # System statistics
```

### 7.2 Endpoint Details

#### POST /auth/register

```
Request:
{
    "username": "hush",
    "email": "hush@example.com",
    "password": "securepassword"
}

Response: 201 Created
{
    "id": "uuid",
    "username": "hush",
    "email": "hush@example.com",
    "created_at": "2026-03-27T10:00:00Z"
}

Errors:
  409 - Username or email already exists
  422 - Validation error (password too short, invalid email)
```

#### POST /auth/login

```
Request: (OAuth2 form)
  username=hush@example.com
  password=securepassword

Response: 200 OK
{
    "access_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 86400
}

Errors:
  401 - Invalid credentials
```

#### POST /documents/upload

```
Request: multipart/form-data
  file: (PDF binary)
  content_type: "training"    # optional: training | rehab | nutrition

Headers:
  Authorization: Bearer {token}

Response: 202 Accepted
{
    "id": "uuid",
    "filename": "convict_conditioning.pdf",
    "status": "pending",
    "created_at": "2026-03-27T10:05:00Z"
}

Errors:
  400 - Invalid file type or exceeds size limit
  401 - Unauthorized
```

#### GET /documents

```
Headers:
  Authorization: Bearer {token}

Response: 200 OK
{
    "documents": [
        {
            "id": "uuid",
            "filename": "convict_conditioning.pdf",
            "content_type": "training",
            "chunk_count": 342,
            "status": "ready",
            "file_size": 15234567,
            "created_at": "2026-03-27T10:05:00Z"
        }
    ],
    "total": 1
}
```

#### POST /chat

```
Request:
{
    "conversation_id": "uuid" | null,
    "message": "我想练引体向上，但一个都拉不起来，怎么开始训练？"
}

Headers:
  Authorization: Bearer {token}

Response: 200 OK (text/event-stream)
  data: {"type":"routing","agent":"training","refined_query":"引体向上零基础入门训练进阶计划"}

  data: {"type":"sources","chunks":[{"content_preview":"...","source_book":"囚徒健身","chapter":"第5章","relevance_score":0.91}]}

  data: {"type":"token","content":"根据"}
  data: {"type":"token","content":"《囚徒健身》"}
  data: {"type":"token","content":"的训练体系..."}

  data: {"type":"done","agent_used":"training","latency_ms":2340,"conversation_id":"uuid"}

Errors:
  401 - Unauthorized
  429 - Rate limit exceeded
  503 - LLM provider API unavailable
```

#### GET /health

```
Response: 200 OK
{
    "status": "healthy",
    "services": {
        "database": { "status": "up", "latency_ms": 2 },
        "redis": { "status": "up", "latency_ms": 1 },
        "llm_provider": { "status": "up", "latency_ms": 450 }
    },
    "timestamp": "2026-03-27T10:10:00Z"
}
```

#### GET /stats

```
Response: 200 OK
{
    "documents": { "total": 3, "ready": 2, "processing": 1 },
    "chunks": { "total": 856 },
    "conversations": { "total": 15 },
    "cache": { "hit_rate": 0.34, "total_queries": 128 },
    "uptime_seconds": 86400
}
```

---

## 8. Multi-Agent Design

### 8.1 Agent Architecture

The system uses a **Supervisor-Worker** pattern implemented as a LangGraph StateGraph. The Router Agent acts as supervisor, classifying user intent and dispatching to one of three specialist Worker Agents.

### 8.2 Shared State Schema

```python
from typing import TypedDict, Literal, Optional

class AgentState(TypedDict):
    # Input
    user_query: str
    chat_history: list[dict]           # previous messages in this conversation
    user_id: str

    # Router output
    routed_agent: Literal["training", "rehab", "nutrition"]
    refined_query: str

    # Retrieval output
    retrieved_chunks: list[dict]       # top-K chunks from pgvector

    # Generation output
    response: str                      # final LLM-generated answer
    sources: list[dict]                # source citations
    disclaimer: Optional[str]          # medical disclaimer (rehab agent only)

    # Metadata
    agent_used: str
    latency_ms: int
```

### 8.3 Router Agent

**Purpose:** Classify user intent into one of three domains and refine the query for optimal retrieval.

**Implementation approach:** Single LLM call with structured output (Pydantic model parsing).

```
System Prompt:
  You are a fitness query classifier. Given a user question, determine
  which specialist should handle it:
  - "training": exercise technique, workout plans, progressions, strength training
  - "rehab": injury, pain, recovery, mobility, rehabilitation, medical concerns
  - "nutrition": diet, calories, macros, supplements, meal planning

  Also refine the user's query into a clear, search-optimized form.

  Respond in JSON: { "agent": "...", "refined_query": "..." }

Few-shot examples:
  "我想练引体向上" → { "agent": "training", "refined_query": "引体向上训练方法和进阶计划" }
  "跑步后膝盖疼" → { "agent": "rehab", "refined_query": "跑步后膝盖疼痛原因和康复方法" }
  "增肌吃多少蛋白质" → { "agent": "nutrition", "refined_query": "增肌期每日蛋白质摄入量建议" }

Edge case rules:
  - If query involves both training AND injury → route to "rehab" (safety first)
  - If query is ambiguous or general greeting → default to "training"
  - If query is unrelated to fitness → still route to "training" with note
```

### 8.4 Specialist Agents

Each specialist agent follows the same three-step pattern but with different system prompts and retrieval filters.

#### Training Agent

```
Retrieval filter: metadata.content_domain IN ('training') OR no filter
System prompt emphasis:
  - Reference specific exercise progressions (levels 1-10 from Convict Conditioning)
  - Suggest form cues and common mistakes
  - Always cite source book and chapter

Tools: search_training_docs (pgvector retrieval with training filter)
```

#### Rehab Agent

```
Retrieval filter: metadata.content_domain IN ('rehab', 'training')
System prompt emphasis:
  - Prioritize safety; when in doubt, recommend consulting a professional
  - Distinguish between acute injury and chronic condition
  - Always append medical disclaimer

Mandatory disclaimer:
  "⚠️ 以上信息仅供参考，不构成医疗建议。如有持续疼痛或严重不适，请及时就医。"

Tools: search_rehab_docs (pgvector retrieval with rehab filter)
```

#### Nutrition Agent

```
Retrieval filter: metadata.content_domain IN ('nutrition')
System prompt emphasis:
  - Provide specific quantities where available (grams, calories)
  - Reference source data for nutritional claims
  - Note individual variation

Tools: search_nutrition_docs (pgvector retrieval with nutrition filter)
```

### 8.5 LangGraph Wiring

```python
# Pseudocode for graph construction

graph = StateGraph(AgentState)

# Nodes
graph.add_node("router", router_agent_node)
graph.add_node("training", training_agent_node)
graph.add_node("rehab", rehab_agent_node)
graph.add_node("nutrition", nutrition_agent_node)
graph.add_node("format_response", format_response_node)

# Edges
graph.add_edge(START, "router")
graph.add_conditional_edges(
    "router",
    route_by_agent,                     # reads state["routed_agent"]
    {
        "training": "training",
        "rehab": "rehab",
        "nutrition": "nutrition",
    }
)
graph.add_edge("training", "format_response")
graph.add_edge("rehab", "format_response")
graph.add_edge("nutrition", "format_response")
graph.add_edge("format_response", END)

app = graph.compile()
```

---

## 9. Key Functional Logic

### 9.1 Document Chunking Pipeline

```python
# Pseudocode: app/rag/chunker.py

function chunk_document(file_path: str, document_id: str) -> list[Chunk]:
    """Parse PDF and produce semantically meaningful chunks."""

    raw_pages = pymupdf.extract_pages(file_path)        # text by page
    tables = pdfplumber.extract_tables(file_path)        # structured tables

    chunks = []
    chunk_index = 0

    for page_num, page_text in raw_pages:
        # Check if page contains a table
        page_tables = find_tables_on_page(tables, page_num)

        if page_tables:
            for table in page_tables:
                # Tables are kept as single chunks to preserve structure
                chunks.append(Chunk(
                    document_id = document_id,
                    content = format_table_as_text(table),
                    chunk_index = chunk_index++,
                    content_type = "table",
                    metadata = {
                        "page_start": page_num,
                        "page_end": page_num,
                        "chapter": detect_chapter(page_text),
                    }
                ))
            # Remove table text from page to avoid duplication
            page_text = remove_table_text(page_text, page_tables)

        if page_text.strip():
            # Split remaining text by semantic boundaries
            text_splits = RecursiveCharacterTextSplitter(
                chunk_size = 800,
                chunk_overlap = 200,
                separators = ["\n\n", "\n", "。", "；", " "]
            ).split(page_text)

            for split in text_splits:
                content_type = classify_content(split)  # text | exercise | definition
                chunks.append(Chunk(
                    document_id = document_id,
                    content = split,
                    chunk_index = chunk_index++,
                    content_type = content_type,
                    metadata = {
                        "page_start": page_num,
                        "page_end": page_num,
                        "chapter": detect_chapter(split),
                        "section": detect_section(split),
                    }
                ))

    return chunks


function classify_content(text: str) -> str:
    """Rule-based content type classification."""
    if contains_exercise_pattern(text):     # regex: "第X式", "组数", "次数"
        return "exercise"
    if contains_definition_pattern(text):   # regex: "是指", "定义为", "又称"
        return "definition"
    return "text"
```

### 9.2 Embedding & Storage

```python
# Pseudocode: app/rag/embedder.py

async function embed_and_store(chunks: list[Chunk], session: AsyncSession):
    """Batch-embed chunks and store in pgvector."""

    BATCH_SIZE = 25     # Safe batch size for most embedding APIs

    embedding_client = get_embedding_client()   # from deps.py

    for batch in batched(chunks, BATCH_SIZE):
        texts = [chunk.content for chunk in batch]

        # Call Embedding API (provider-agnostic via OpenAI SDK)
        embeddings = await embedding_client.embeddings.create(
            model = settings.EMBEDDING_MODEL,
            input = texts
        )

        # Attach embeddings to chunk objects
        for chunk, emb_data in zip(batch, embeddings.data):
            chunk.embedding = emb_data.embedding

        # Batch insert into PostgreSQL
        session.add_all(batch)

    await session.commit()
```

### 9.3 Vector Retrieval with Metadata Filtering

```python
# Pseudocode: app/rag/retriever.py

async function retrieve(
    query: str,
    content_domain: str | None,
    top_k: int = 5,
    session: AsyncSession
) -> list[ChunkResult]:
    """Retrieve top-K relevant chunks using pgvector cosine similarity."""

    # 1. Embed the query
    query_embedding = await embed_text(query)

    # 2. Build SQL with optional metadata filter
    sql = """
        SELECT
            id,
            content,
            content_type,
            metadata,
            1 - (embedding <=> :query_vec) AS relevance_score
        FROM document_chunks
        WHERE 1=1
    """

    params = {"query_vec": query_embedding, "top_k": top_k}

    if content_domain:
        sql += " AND metadata->>'content_domain' = :domain"
        params["domain"] = content_domain

    sql += """
        ORDER BY embedding <=> :query_vec
        LIMIT :top_k
    """

    # 3. Execute and return
    results = await session.execute(text(sql), params)
    return [ChunkResult(**row) for row in results]
```

### 9.4 Agent Node Implementation

```python
# Pseudocode: app/agents/training.py

async function training_agent_node(state: AgentState) -> AgentState:
    """Training specialist agent: retrieve → prompt → generate."""

    # 1. Retrieve relevant chunks
    chunks = await retrieve(
        query = state["refined_query"],
        content_domain = "training",
        top_k = 5
    )
    state["retrieved_chunks"] = chunks

    # 2. Build prompt with retrieved context
    context = "\n\n---\n\n".join([
        f"[来源: {c.metadata['source_book']} {c.metadata.get('chapter', '')}]\n{c.content}"
        for c in chunks
    ])

    messages = [
        SystemMessage(content=TRAINING_SYSTEM_PROMPT),
        *format_chat_history(state["chat_history"]),
        HumanMessage(content=f"""
            参考资料:
            {context}

            用户问题: {state["refined_query"]}

            请根据以上参考资料回答用户问题。回答中请标注信息来源（书名和章节）。
            如果参考资料中没有相关内容，请如实说明。
        """)
    ]

    # 3. Stream LLM response
    response = await llm.ainvoke(messages)

    state["response"] = response.content
    state["sources"] = format_sources(chunks)
    state["agent_used"] = "training"

    return state
```

### 9.5 Query Caching Logic

```python
# Pseudocode: app/services/cache_service.py

import hashlib, json

class CacheService:
    def __init__(self, redis_client, ttl: int = 3600):
        self.redis = redis_client
        self.ttl = ttl

    def _make_key(self, query: str, content_domain: str | None) -> str:
        raw = f"{query.strip().lower()}:{content_domain or 'all'}"
        hash_val = hashlib.md5(raw.encode()).hexdigest()
        return f"cache:query:{hash_val}"

    async def get(self, query: str, content_domain: str | None) -> dict | None:
        key = self._make_key(query, content_domain)
        cached = await self.redis.get(key)
        if cached:
            return json.loads(cached)
        return None

    async def set(self, query: str, content_domain: str | None, response: dict):
        key = self._make_key(query, content_domain)
        await self.redis.set(key, json.dumps(response, ensure_ascii=False), ex=self.ttl)

    async def get_stats(self) -> dict:
        """Return cache hit rate for observability."""
        hits = int(await self.redis.get("cache:stats:hits") or 0)
        misses = int(await self.redis.get("cache:stats:misses") or 0)
        total = hits + misses
        return {
            "hit_rate": round(hits / total, 2) if total > 0 else 0,
            "total_queries": total
        }
```

### 9.6 Rate Limiting Logic

```python
# Pseudocode: app/services/rate_limiter.py

import time

class RateLimiter:
    def __init__(self, redis_client, max_requests: int = 20, window_seconds: int = 60):
        self.redis = redis_client
        self.max_requests = max_requests
        self.window = window_seconds

    async def check(self, user_id: str) -> bool:
        """Returns True if request is allowed, False if rate limited."""
        current_minute = int(time.time()) // self.window
        key = f"ratelimit:{user_id}:{current_minute}"

        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, self.window)

        return count <= self.max_requests

    async def get_remaining(self, user_id: str) -> int:
        current_minute = int(time.time()) // self.window
        key = f"ratelimit:{user_id}:{current_minute}"
        count = int(await self.redis.get(key) or 0)
        return max(0, self.max_requests - count)
```

### 9.7 JWT Authentication Flow

```python
# Pseudocode: app/services/auth_service.py

from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta

pwd_context = CryptContext(schemes=["bcrypt"])

function hash_password(password: str) -> str:
    return pwd_context.hash(password)

function verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

function create_access_token(user_id: str, secret: str, expires_minutes: int) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=expires_minutes),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, secret, algorithm="HS256")

function decode_token(token: str, secret: str) -> dict:
    """Raises JWTError if invalid or expired."""
    return jwt.decode(token, secret, algorithms=["HS256"])


# Pseudocode: app/deps.py — FastAPI dependency

from openai import AsyncOpenAI

def get_llm_client() -> AsyncOpenAI:
    """Factory for LLM chat client. Provider-agnostic via OpenAI-compatible SDK."""
    return AsyncOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
    )

def get_embedding_client() -> AsyncOpenAI:
    """Factory for embedding client. Falls back to LLM config if not explicitly set."""
    return AsyncOpenAI(
        api_key=settings.effective_embedding_api_key,
        base_url=settings.effective_embedding_base_url,
    )

async function get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session)
) -> User:
    try:
        payload = decode_token(token, settings.JWT_SECRET)
        user_id = payload["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user
```

### 9.8 SSE Streaming Implementation

```python
# Pseudocode: app/api/chat.py

from fastapi.responses import StreamingResponse

@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    cache: CacheService = Depends(get_cache),
    limiter: RateLimiter = Depends(get_limiter),
):
    # Rate limit check
    if not await limiter.check(str(current_user.id)):
        raise HTTPException(429, "Rate limit exceeded")

    # Cache check
    cached = await cache.get(request.message, content_domain=None)
    if cached:
        await cache.redis.incr("cache:stats:hits")
        return cached   # Return JSON directly for cached responses

    await cache.redis.incr("cache:stats:misses")

    # Stream response
    return StreamingResponse(
        generate_stream(request, current_user, session, cache),
        media_type="text/event-stream"
    )

async function generate_stream(request, user, session, cache):
    start_time = time.time()

    # Create or load conversation
    conversation = await get_or_create_conversation(request.conversation_id, user, session)

    # Save user message
    await save_message(conversation.id, "user", request.message, session)

    # Load chat history
    history = await get_recent_messages(conversation.id, limit=10, session=session)

    # Step 1: Route
    routing_result = await router_agent.classify(request.message, history)
    yield f"data: {json.dumps({'type': 'routing', 'agent': routing_result.agent, 'refined_query': routing_result.refined_query})}\n\n"

    # Step 2: Retrieve
    chunks = await retrieve(routing_result.refined_query, routing_result.agent)
    sources = format_sources(chunks)
    yield f"data: {json.dumps({'type': 'sources', 'chunks': sources})}\n\n"

    # Step 3: Generate (streaming)
    full_response = ""
    async for token in agent_stream(routing_result.agent, routing_result.refined_query, chunks, history):
        full_response += token
        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

    # Step 4: Finalize
    latency = int((time.time() - start_time) * 1000)
    yield f"data: {json.dumps({'type': 'done', 'agent_used': routing_result.agent, 'latency_ms': latency, 'conversation_id': str(conversation.id)})}\n\n"

    # Save assistant message
    await save_message(conversation.id, "assistant", full_response, session,
                       agent_used=routing_result.agent, sources=sources, latency_ms=latency)

    # Cache the response
    await cache.set(request.message, None, {
        "response": full_response,
        "sources": sources,
        "agent_used": routing_result.agent
    })
```

---

## 10. Error Handling Strategy

### 10.1 Error Categories

| Category | HTTP Code | Handling |
|----------|----------|----------|
| Validation errors | 422 | Pydantic auto-validation; return field-level error details |
| Authentication errors | 401 | Invalid/expired JWT; return generic "unauthorized" message |
| Authorization errors | 403 | User accessing another user's resources |
| Resource not found | 404 | Invalid document_id, conversation_id, etc. |
| Rate limited | 429 | Redis counter exceeded; return Retry-After header |
| File processing error | 500 | PDF parsing failure; set document status to 'failed' with error message |
| LLM provider API error | 502/503 | Upstream timeout or error; return user-friendly message, log details |
| Internal error | 500 | Unexpected exception; log stack trace, return generic error |

### 10.2 Standardized Error Response

```python
# All API errors follow this shape:
class ErrorResponse(BaseModel):
    error: str          # machine-readable error code
    message: str        # human-readable description
    detail: Any = None  # optional field-level details

# Example:
{
    "error": "DOCUMENT_NOT_FOUND",
    "message": "Document with the specified ID does not exist.",
    "detail": { "document_id": "uuid" }
}
```

### 10.3 Global Exception Handler

```python
# Pseudocode: app/main.py

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail if isinstance(exc.detail, str) else "HTTP_ERROR",
            message=str(exc.detail)
        ).model_dump()
    )

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="INTERNAL_ERROR",
            message="An unexpected error occurred. Please try again."
        ).model_dump()
    )
```

### 10.4 LLM API Resilience

```python
# Pseudocode: retry wrapper for LLM API calls (provider-agnostic)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=10),
    retry=retry_if_exception_type((APITimeoutError, APIConnectionError))
)
async function call_llm(messages, stream=False):
    llm_client = get_llm_client()       # from deps.py
    try:
        return await llm_client.chat.completions.create(
            model=settings.LLM_CHAT_MODEL,
            messages=messages,
            stream=stream
        )
    except RateLimitError:
        raise HTTPException(503, "LLM service is temporarily overloaded. Please retry.")
    except AuthenticationError:
        logger.critical("LLM API key invalid — check LLM_API_KEY in .env")
        raise HTTPException(503, "LLM service configuration error.")
```

---

## 11. Security Design

### 11.1 Authentication Flow

```
Register: password → bcrypt hash → store in DB
Login:    password → bcrypt verify → issue JWT (24h expiry)
Request:  JWT in Authorization header → decode → load user → inject as dependency
```

### 11.2 Security Measures

| Area | Measure |
|------|---------|
| Passwords | bcrypt hashing (12 rounds), never stored in plaintext |
| JWT | HS256 signed, 24h expiry, secret from environment variable |
| File Upload | Extension whitelist (.pdf only), size limit (50MB), saved with UUID filename (prevents path traversal) |
| SQL Injection | SQLAlchemy parameterized queries; no raw string concatenation |
| CORS | Allowed origins restricted to frontend URL in production |
| Rate Limiting | 20 requests/minute per user via Redis sliding window |
| Secrets | All secrets in .env file (git-ignored), never in source code |
| Input Sanitization | Pydantic v2 strict validation on all request bodies |

### 11.3 Resource Isolation

Every data-access query includes `user_id` filtering:

```python
# Users can only access their own documents
statement = select(Document).where(
    Document.id == document_id,
    Document.user_id == current_user.id    # always filter by owner
)
```

---

## 12. Caching Strategy

### 12.1 Cache Architecture

```
                  ┌──────────────────────────┐
                  │       User Query          │
                  └────────────┬─────────────┘
                               │
                               ▼
                     ┌───────────────────┐
                     │  Hash(query +     │
                     │  content_domain)  │
                     └────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │   Redis Lookup      │
                    │   GET cache:query:  │
                    │   {hash}            │
                    └────┬──────────┬─────┘
                         │          │
                    HIT  │          │ MISS
                         ▼          ▼
              ┌──────────────┐  ┌─────────────┐
              │ Return cached│  │ Run agent    │
              │ response     │  │ pipeline     │
              │ (< 5ms)      │  │ (2-5 sec)    │
              └──────────────┘  └──────┬──────┘
                                       │
                                       ▼
                                ┌─────────────┐
                                │ Cache result │
                                │ SET with TTL │
                                │ (3600s)      │
                                └─────────────┘
```

### 12.2 Cache Invalidation Rules

| Event | Action |
|-------|--------|
| New document uploaded and processed | Flush all query cache keys (new knowledge available) |
| Document deleted | Flush all query cache keys |
| TTL expires (1 hour) | Automatic Redis expiry |
| Manual flush | `make cache-clear` → `redis-cli FLUSHDB` |

### 12.3 Cache Key Design

```
cache:query:{md5(normalized_query + ":" + content_domain)}

Normalization:
  - strip whitespace
  - lowercase
  - content_domain defaults to "all"

Example:
  query = "如何练引体向上"
  domain = None
  key = cache:query:a1b2c3d4e5f6...
```

---

## 13. Logging & Observability

### 13.1 Structured Logging

```python
# All logs use structured JSON format via Python's logging + json formatter

import logging, json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
            "extra": getattr(record, "extra", {})
        }
        return json.dumps(log_data, ensure_ascii=False)
```

### 13.2 Key Log Events

| Event | Level | Fields |
|-------|-------|--------|
| User login | INFO | user_id, ip_address |
| Document upload | INFO | user_id, filename, file_size |
| Document processing start/end/fail | INFO/ERROR | document_id, chunk_count, duration_ms, error |
| Chat query | INFO | user_id, query (truncated), agent_used, latency_ms, cache_hit |
| LLM API call | DEBUG | model, token_count, latency_ms |
| LLM API error | ERROR | model, error_type, error_message |
| Rate limit triggered | WARN | user_id, current_count |

### 13.3 Health Monitoring

The `/health` endpoint probes all dependencies and reports status:

```python
async function health_check():
    checks = {}

    # Database
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = {"status": "up"}
    except Exception as e:
        checks["database"] = {"status": "down", "error": str(e)}

    # Redis
    try:
        await redis.ping()
        checks["redis"] = {"status": "up"}
    except Exception as e:
        checks["redis"] = {"status": "down", "error": str(e)}

    # LLM Provider
    try:
        llm_client = get_llm_client()
        await llm_client.models.list()
        checks["llm_provider"] = {"status": "up"}
    except Exception as e:
        checks["llm_provider"] = {"status": "down", "error": str(e)}

    overall = "healthy" if all(c["status"] == "up" for c in checks.values()) else "degraded"
    return {"status": overall, "services": checks}
```

---

## 14. Testing Strategy

### 14.1 Test Architecture

```
tests/
├── conftest.py                      # Global fixtures
│   ├── test_engine                  # Isolated test database (session scope)
│   ├── db_session                   # Per-test session with auto-rollback
│   ├── client                       # Async HTTP test client (httpx)
│   ├── auth_headers                 # Pre-authenticated JWT headers
│   ├── mock_llm                     # Mocked LLM API responses (provider-agnostic)
│   ├── sample_user                  # Pre-created test user
│   └── sample_document              # Pre-created document with chunks
│
├── unit/                            # Isolated function tests (no DB, no network)
│   ├── test_chunking.py             # PDF parsing, chunk splitting, classification
│   ├── test_retrieval.py            # Vector search query construction
│   ├── test_router_agent.py         # Intent classification accuracy
│   ├── test_cache_service.py        # Cache key generation, hit/miss logic
│   ├── test_rate_limiter.py         # Rate limit counter logic
│   └── test_auth_service.py         # JWT creation, validation, password hashing
│
├── integration/                     # Cross-component tests (real DB, mocked LLM)
│   ├── test_api_auth.py             # Register → login → access protected endpoint
│   ├── test_api_documents.py        # Upload → poll status → list → delete
│   ├── test_api_chat.py             # Chat request → agent invocation → response
│   └── test_database.py             # CRUD operations, pgvector search verification
│
├── evaluation/                      # RAG quality tests
│   └── test_rag_quality.py          # Retrieval precision, answer faithfulness
│
└── fixtures/
    ├── sample_chunks.json           # Pre-embedded test chunks
    ├── sample_pdf.pdf               # Small test PDF
    └── mock_llm_responses.json      # Deterministic LLM outputs
```

### 14.2 Test Configuration

```python
# tests/conftest.py — Core fixtures

import pytest
from httpx import AsyncClient, ASGITransport
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from unittest.mock import AsyncMock

# ---------- Database Isolation ----------

@pytest.fixture(scope="session")
async def test_engine():
    """Create a dedicated test database; tear down after all tests."""
    engine = create_async_engine(
        "postgresql+asyncpg://fitcoach:fitcoach_dev@localhost:5433/fitcoach_test",
        echo=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def db_session(test_engine):
    """Per-test session with automatic rollback for isolation."""
    async with AsyncSession(test_engine) as session:
        yield session
        await session.rollback()

# ---------- HTTP Client ----------

@pytest.fixture
async def client(db_session):
    """Async HTTP test client bound to test DB session."""
    from app.main import app
    from app.deps import get_session
    app.dependency_overrides[get_session] = lambda: db_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()

# ---------- Auth ----------

@pytest.fixture
async def sample_user(db_session):
    """Pre-created user for authenticated tests."""
    user = User(username="testuser", email="test@test.com",
                hashed_password=hash_password("testpass123"))
    db_session.add(user)
    await db_session.commit()
    return user

@pytest.fixture
def auth_headers(sample_user):
    """JWT headers for authenticated requests."""
    token = create_access_token(str(sample_user.id), settings.JWT_SECRET, 60)
    return {"Authorization": f"Bearer {token}"}

# ---------- LLM Mocking ----------

@pytest.fixture
def mock_llm(monkeypatch):
    """Replace LLM API calls with deterministic responses (provider-agnostic)."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = MockCompletion(
        content="这是一个模拟的训练建议回答。"
    )
    mock_client.embeddings.create.return_value = MockEmbedding(
        data=[MockEmbData(embedding=[0.1] * settings.EMBEDDING_DIMENSION)]
    )
    monkeypatch.setattr("app.deps.get_llm_client", lambda: mock_client)
    monkeypatch.setattr("app.deps.get_embedding_client", lambda: mock_client)
    return mock_client
```

### 14.3 Example Test Cases

```python
# tests/unit/test_router_agent.py

@pytest.mark.parametrize("query, expected_agent", [
    # Clear-cut cases
    ("如何练引体向上", "training"),
    ("我膝盖疼怎么办", "rehab"),
    ("增肌期每天吃多少蛋白质", "nutrition"),

    # Edge cases: mixed intent → safety-first routing
    ("深蹲后膝盖不舒服还能继续练吗", "rehab"),
    ("跑步时脚踝扭了，还能做上肢训练吗", "rehab"),

    # Edge cases: ambiguous
    ("减脂期的训练计划和饮食怎么搭配", "training"),
    ("你好", "training"),                # default fallback

    # Edge cases: adversarial
    ("", "training"),                    # empty input
    ("a" * 5000, "training"),            # very long input
    ("SELECT * FROM users", "training"), # injection attempt
])
async def test_router_classifies_intent(query, expected_agent, mock_llm):
    result = await router_agent.classify(query)
    assert result.agent == expected_agent


# tests/integration/test_api_auth.py

async def test_register_and_login(client):
    """Full auth flow: register → login → access protected endpoint."""
    # Register
    res = await client.post("/api/v1/auth/register", json={
        "username": "newuser",
        "email": "new@test.com",
        "password": "password123"
    })
    assert res.status_code == 201

    # Login
    res = await client.post("/api/v1/auth/login", data={
        "username": "new@test.com",
        "password": "password123"
    })
    assert res.status_code == 200
    token = res.json()["access_token"]

    # Access protected endpoint
    res = await client.get("/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

async def test_login_wrong_password(client, sample_user):
    res = await client.post("/api/v1/auth/login", data={
        "username": "test@test.com",
        "password": "wrongpassword"
    })
    assert res.status_code == 401


# tests/unit/test_cache_service.py

async def test_cache_miss_then_hit(redis_client):
    cache = CacheService(redis_client, ttl=60)

    # Miss
    result = await cache.get("test query", None)
    assert result is None

    # Set
    await cache.set("test query", None, {"response": "cached answer"})

    # Hit
    result = await cache.get("test query", None)
    assert result["response"] == "cached answer"

async def test_cache_key_normalization(redis_client):
    cache = CacheService(redis_client, ttl=60)

    await cache.set("  Hello World  ", None, {"data": 1})
    result = await cache.get("hello world", None)
    assert result is not None   # normalized keys match
```

---

## 15. Deployment Architecture

### 15.1 Docker Compose Configuration

```yaml
version: "3.9"

services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: fitcoach-db
    environment:
      POSTGRES_USER: fitcoach
      POSTGRES_PASSWORD: fitcoach_dev
      POSTGRES_DB: fitcoach
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./scripts/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U fitcoach"]
      interval: 5s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 512M

  redis:
    image: redis:7-alpine
    container_name: fitcoach-redis
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    command: redis-server --maxmemory 128mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 128M

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: fitcoach-backend
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://fitcoach:fitcoach_dev@postgres:5432/fitcoach
      REDIS_URL: redis://redis:6379/0
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - uploaded_docs:/app/uploads
    deploy:
      resources:
        limits:
          memory: 1G

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: fitcoach-frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend
    environment:
      VITE_API_URL: http://localhost:8000
    deploy:
      resources:
        limits:
          memory: 256M

volumes:
  pgdata:
  redisdata:
  uploaded_docs:
```

### 15.2 Backend Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies for PDF parsing
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 15.3 Frontend Dockerfile

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
```

### 15.4 Memory Budget (Mac Mini 8GB)

| Service | Memory Limit | Notes |
|---------|-------------|-------|
| macOS + system | ~2.5 GB | OS overhead |
| PostgreSQL | 512 MB | Sufficient for development scale |
| Redis | 128 MB | LRU eviction enabled |
| FastAPI Backend | 1 GB | Includes Python runtime + LangChain |
| Frontend (nginx) | 256 MB | Static file serving only |
| Docker overhead | ~500 MB | Docker Desktop for Mac |
| **Remaining buffer** | **~3.1 GB** | Available for spikes |

### 15.5 Startup Sequence

```
docker compose up -d
        │
        ├── 1. postgres starts → runs init.sql (CREATE EXTENSION vector; CREATE TABLES)
        │      waits for healthcheck (pg_isready)
        │
        ├── 2. redis starts
        │      waits for healthcheck (redis-cli ping)
        │
        ├── 3. backend starts (after postgres + redis healthy)
        │      uvicorn binds to :8000
        │      FastAPI lifespan: verify DB connection, verify Redis, log config
        │
        └── 4. frontend starts (after backend)
               nginx serves React SPA on :3000
               API requests proxied to backend:8000
```

---

## 16. Development Milestones

### Phase 1: Foundation (Days 1-3)

**Objective:** Deployable skeleton with database, auth, and project structure.

| Day | Deliverable | Acceptance Criteria |
|-----|-------------|---------------------|
| Day 1 | Project scaffolding + Docker Compose | `docker compose up` starts postgres (pgvector), redis, and an empty FastAPI app. `GET /health` returns `200`. Project directory structure matches Section 11 of the plan. Makefile shortcuts work (`make up`, `make down`, `make logs`). |
| Day 2 | Database schema + SQLModel models | All tables from Section 5.2 exist in PostgreSQL. `init.sql` runs automatically on first startup. SQLModel classes match table definitions. CRUD helper functions for User, Document exist and are manually verified via `make db-shell`. |
| Day 3 | JWT auth system + test foundation | `POST /auth/register` and `POST /auth/login` work correctly. Protected endpoints return 401 without valid token. `conftest.py` created with `test_engine`, `db_session`, `client`, `auth_headers` fixtures. `test_api_auth.py` has at least 5 test cases — all green. `make test` runs the suite successfully inside Docker. |

### Phase 2: Core Pipeline (Days 4-7)

**Objective:** Working RAG pipeline and multi-agent system with API endpoints.

| Day | Deliverable | Acceptance Criteria |
|-----|-------------|---------------------|
| Day 4 | Document upload + processing pipeline | `POST /documents/upload` accepts PDF, saves to disk, creates DB record. Background task: parses PDF → chunks → classifies content type. `GET /documents/{id}` shows status progression: pending → processing → ready. At least one real PDF processed end-to-end. Unit tests for chunking logic (3+ test cases). |
| Day 5 | Embedding + vector retrieval | Chunks are embedded via Embedding API and stored in pgvector. `retrieve()` function returns top-K results with cosine similarity scores. Metadata filtering by `content_domain` works. Unit tests for retrieval (3+ test cases) with pre-embedded fixtures. |
| Day 6 | Multi-agent system (LangGraph) | Router Agent classifies intent into training/rehab/nutrition. Three specialist agents: retrieve → prompt → generate. LangGraph StateGraph compiled and invocable. Parametrized router tests (8+ cases including edge cases) — all green. Manual test: send query via Python script, get cited response. |
| Day 7 | Chat API + Redis caching | `POST /chat` endpoint invokes agent graph and returns response. SSE streaming works (routing → sources → tokens → done). Redis query caching: second identical query returns from cache. Rate limiting: 21st request within 1 minute returns 429. Integration tests for chat endpoint (3+ cases). Cache service tests (3+ cases). |

### Phase 3: Frontend + Polish (Days 8-12)

**Objective:** Functional React UI and comprehensive test coverage.

| Day | Deliverable | Acceptance Criteria |
|-----|-------------|---------------------|
| Day 8 | React project setup + login page | Vite + React + TailwindCSS + Zustand initialized. Login and registration forms connect to backend API. JWT token stored and attached to subsequent requests. Protected routes redirect to login when unauthenticated. |
| Day 9 | Document management panel | Left panel shows list of user's documents with status indicators. Upload button triggers file picker → upload → polling for status. Delete button removes document. Status transitions visible: pending → processing → ready. |
| Day 10 | Chat interface with streaming | Right panel: message list, input box, send button. SSE streaming displays tokens in real time. Source citations rendered below assistant messages. Conversation list in sidebar; switching conversations loads history. Agent routing indicator shown ("训练Agent 回答中..."). |
| Day 11 | Test framework completion | All unit tests finalized and green. All integration tests finalized and green. `make test` produces full report. Test coverage measured (target: 70%+ on backend). |
| Day 12 | Docker optimization + full system test | Multi-stage Dockerfiles (builder pattern for frontend). `docker compose up` from clean state works without manual steps. Full end-to-end test: register → upload → wait for processing → chat → get cited response. Memory usage verified under 8GB total. |

### Phase 4: Deployment & Demo (Days 13-14)

**Objective:** Live deployment on Mac Mini, demo rehearsal.

| Day | Deliverable | Acceptance Criteria |
|-----|-------------|---------------------|
| Day 13 | Mac Mini deployment + Feishu integration | All services running on Mac Mini via Docker Compose. React frontend accessible from browser on same network. OpenClaw successfully calls `POST /chat` and relays response to Feishu. System stable for at least 1 hour of intermittent use. |
| Day 14 | Documentation + demo rehearsal | README.md: project description, architecture diagram, setup instructions, API overview. FastAPI auto-generated Swagger docs accessible at `/docs`. Demo script rehearsed: web walkthrough + Feishu demo + test suite + architecture explanation ≤ 5 minutes. |

### Milestone Exit Criteria (Go/No-Go)

| Checkpoint | Date | Must Have | Nice to Have |
|-----------|------|-----------|-------------|
| Phase 1 complete | Day 3 | Auth works, tests green, Docker running | — |
| Phase 2 complete | Day 7 | Chat returns cited answers, cache works | All 3 agents working (2 is minimum) |
| Phase 3 complete | Day 12 | Frontend functional, all tests green | SSE streaming (fallback: JSON response) |
| Phase 4 complete | Day 14 | Demo-ready on Mac Mini | Feishu integration working |

---

## 17. Dependency & Risk Register

### 17.1 External Dependencies

| Dependency | Type | Risk Level | Mitigation |
|-----------|------|-----------|------------|
| LLM Provider API (DeepSeek / OpenAI / Claude) | LLM + Embedding | **High** — single point of failure for all AI functionality | Provider-agnostic design allows hot-switching via `.env`; retry with exponential backoff; cache responses aggressively; seed demo responses in Redis for live demo fallback |
| pgvector Docker image | Database | **Low** — stable, widely used | Pin to specific version `pgvector/pgvector:pg16` |
| LangChain / LangGraph | Framework | **Medium** — API surface changes between versions | Pin exact versions in `requirements.txt` |
| Fitness book PDFs | Knowledge source | **Low** — static content | Acquire and pre-process before development begins |

### 17.2 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| 8GB RAM insufficient for all Docker services | Medium | High — system crashes or swaps | Memory limits per container (see 15.4); monitor with `docker stats`; reduce PostgreSQL `shared_buffers` if needed |
| SSE streaming complexity slows frontend development | Medium | Medium — delays Day 10 | Fallback: implement simple JSON response first, add SSE as enhancement |
| React learning curve exceeds estimate | Medium | Medium — delays Days 8-10 | Use shadcn/ui copy-paste components; keep to 6-7 components max |
| PDF parsing produces poor chunks for Chinese books | Low | High — RAG quality degrades | Test chunking early (Day 4) with actual target PDFs; adjust splitter parameters |
| LLM/Embedding API rate limits hit during embedding | Low | Medium — document processing stalls | Batch embeddings (25/call), add delay between batches, implement retry; can switch to alternative provider via `.env` |

### 17.3 Scope Reduction Waterfall

If schedule slips, reduce scope in this exact order:

| Priority | Item to Cut | Consequence |
|----------|------------|-------------|
| 1st cut | Nutrition Agent | System works with 2 agents (training + rehab); still demonstrates multi-agent pattern |
| 2nd cut | Rate limiting | Redis still used for query caching; one less Redis pattern demonstrated |
| 3rd cut | SSE streaming | Chat returns complete JSON response; less visually impressive but fully functional |
| 4th cut | Test coverage target | Reduce from 70% to core paths only; framework and key tests still present |
| **Never cut** | Pytest framework (conftest.py + core tests) | — |
| **Never cut** | Docker Compose deployment | — |
| **Never cut** | JWT auth + database schema | — |
| **Never cut** | At least 2 working agents with RAG | — |

---

## Appendix A: Project Directory Structure

```
fitcoach-ai/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
├── Makefile
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                  # FastAPI app factory + lifespan
│   │   ├── config.py                # pydantic-settings configuration
│   │   ├── deps.py                  # Dependency injection
│   │   │
│   │   ├── models/                  # SQLModel table definitions
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── document.py
│   │   │   ├── conversation.py
│   │   │   └── message.py
│   │   │
│   │   ├── schemas/                 # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── document.py
│   │   │   └── chat.py
│   │   │
│   │   ├── api/                     # Route handlers
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── documents.py
│   │   │   ├── chat.py
│   │   │   └── system.py
│   │   │
│   │   ├── services/                # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py
│   │   │   ├── document_service.py
│   │   │   ├── chat_service.py
│   │   │   ├── cache_service.py
│   │   │   └── rate_limiter.py
│   │   │
│   │   ├── rag/                     # RAG pipeline
│   │   │   ├── __init__.py
│   │   │   ├── chunker.py
│   │   │   ├── embedder.py
│   │   │   ├── retriever.py
│   │   │   └── pipeline.py
│   │   │
│   │   └── agents/                  # Multi-agent system
│   │       ├── __init__.py
│   │       ├── router.py
│   │       ├── training.py
│   │       ├── rehab.py
│   │       ├── nutrition.py
│   │       └── graph.py
│   │
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── unit/
│       │   ├── __init__.py
│       │   ├── test_chunking.py
│       │   ├── test_retrieval.py
│       │   ├── test_router_agent.py
│       │   ├── test_cache_service.py
│       │   ├── test_rate_limiter.py
│       │   └── test_auth_service.py
│       ├── integration/
│       │   ├── __init__.py
│       │   ├── test_api_auth.py
│       │   ├── test_api_documents.py
│       │   ├── test_api_chat.py
│       │   └── test_database.py
│       ├── evaluation/
│       │   ├── __init__.py
│       │   └── test_rag_quality.py
│       └── fixtures/
│           ├── sample_chunks.json
│           ├── sample_pdf.pdf
│           └── mock_llm_responses.json
│
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── api/
│       │   └── client.js            # Axios instance with JWT interceptor
│       ├── store/
│       │   └── useStore.js          # Zustand store
│       ├── hooks/
│       │   ├── useAuth.js
│       │   ├── useChat.js
│       │   └── useDocuments.js
│       └── components/
│           ├── Layout.jsx
│           ├── Login.jsx
│           ├── DocumentPanel.jsx
│           ├── ChatPanel.jsx
│           ├── MessageBubble.jsx
│           └── StreamingText.jsx
│
└── scripts/
    ├── init.sql                     # DB initialization
    └── seed_data.py                 # Sample data loader
```

---

## Appendix B: Key Library Versions (requirements.txt)

```
# Web framework
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
pydantic>=2.0
pydantic-settings>=2.0

# Database
sqlmodel>=0.0.14
asyncpg>=0.29.0
sqlalchemy[asyncio]>=2.0
pgvector>=0.3.0

# Redis
redis[hiredis]>=5.0

# Auth
python-jose[cryptography]>=3.3
passlib[bcrypt]>=1.7
python-multipart>=0.0.6

# RAG & Agents
langchain>=0.2.0
langchain-community>=0.2.0
langgraph>=0.1.0

# PDF processing
pymupdf>=1.24.0
pdfplumber>=0.11.0

# LLM Provider (OpenAI-compatible client — works with DeepSeek, OpenAI, Claude)
openai>=1.0

# Utilities
httpx>=0.27.0
tenacity>=8.0        # retry logic

# Testing
pytest>=8.0
pytest-asyncio>=0.23
httpx>=0.27.0        # async test client
pytest-cov>=4.0      # coverage reporting
```
