# AI Development Team Agent

You describe a Python program, and a team of AI agents plans it, writes it and reviews it. You can watch progress live, read the files, request revisions and download the result as a `.zip`.

## What it is for

- Generating small Python programs (up to 10 files, under 30,000 characters each)
- Revising an earlier result while keeping every version
- Learning how a supervisor-based multi-agent system works

It does **not** run or test the generated code. Review is by reading only.

## Why it is built this way

| Choice | Reason |
|---|---|
| Planner, developer and reviewer | Separating the roles gives a plan with acceptance criteria and an independent check |
| Supervisor | One agent decides who works next and when to stop (approval, or 3 developer passes) |
| Files held in memory per run | Agents cannot touch the server's disk |
| PostgreSQL, one row per run | Each version is an immutable snapshot linked to its parent |
| Server-sent events | A run can take minutes, so the UI shows each step as it happens |
| Context7 (MCP) and Tavily | Current library documentation for the agents |
| Langfuse | Traces every agent, model and tool call |

## High-level design (HLD)

```mermaid
flowchart LR
    U[Browser] --> N[Next.js :3000<br/>/api/team/*]
    N -- SSE --> F[FastAPI :8000<br/>/api/team/*]
    F --> S[Supervisor]
    S --> P[planner]
    S --> D[developer]
    S --> R[reviewer]
    P & D & R & S --> L[LLM: Groq]
    P & D -.-> C7[Context7 MCP]
    P -.-> T[Tavily search]
    F --> DB[(PostgreSQL)]
    F -.-> LF[Langfuse]
```

Agent loop:

```mermaid
flowchart LR
    A[Request] --> P[Plan] --> D[Develop] --> R{Review}
    R -- changes requested --> D
    R -- approved or 3 passes --> Done[Summary, saved as a run]
```

## Low-level design (LLD)

### Backend (`backend/`)

| File | Responsibility |
|---|---|
| `main.py` | App setup, API key middleware and router |
| `middlewares/authenticate.py` | Compares the `X-API-KEY` header with `AUTHENTICATED_KEY`. `/`, `/docs` and `/openapi.json` are public |
| `modules/ai_team/router.py` | HTTP and streaming endpoints |
| `modules/ai_team/schema.py` | Request model |
| `modules/ai_team/service.py` | Prepare the run, stream progress, summarize, save, zip |
| `modules/ai_team/graph.py` | Model settings, agent prompts, supervisor |
| `modules/ai_team/tools.py` | `list_files`, `read_file`, `write_file`, `web_search` |
| `core/mcp.py` | Loads Context7 tools through `npx` |
| `core/database/postgres.py` | `Run` table and engine; creates the table on first use |

### Agent tools

| Agent | Tools |
|---|---|
| planner | `list_files`, `read_file`, Context7, `web_search` (only if `TAVILY_API_KEY` is set) |
| developer | `list_files`, `read_file`, `write_file`, Context7 |
| reviewer | `list_files`, `read_file` |

`write_file` rejects absolute paths and `..`, and enforces the file count and size limits. If Context7 fails to load, the team runs without it.

### API

| Method and path | Purpose |
|---|---|
| `POST /api/team/chat` | Run the team and return the saved run |
| `POST /api/team/chat/stream` | The same, as server-sent events |
| `GET /api/team/runs/{id}` | Load a run |
| `GET /api/team/runs/{id}/download` | Download its files as a zip |

Request body for both `POST` routes: `{ "message": "...", "parent_id": "<uuid, optional>" }`

Stream events:

| `type` | Fields |
|---|---|
| `agent` | `name`, `status` (`start` or `done`), `approved` (reviewer only) |
| `tool` | `agent`, `name`, `path` |
| `done` | `run` |
| `error` | `error` |

Run response:

```json
{ "id": "", "parent_id": null, "message": "", "created_at": "",
  "result": { "answer": "", "plan": "", "files": {}, "review": "", "approved": true, "attempts": 1 } }
```

### Data model (`runs` table)

`id`, `parent_id` (self reference), `message`, `answer`, `plan`, `review`, `approved`, `attempts`, `files` (JSONB), `created_at`

A run counts as approved only if the reviewer replied `APPROVED` after the developer's last change.

### Frontend (`frontend/src/`)

| Path | Responsibility |
|---|---|
| `app/api/team/` | Proxy routes: chat (streaming), run, download |
| `lib/backend.ts` | Forwards to FastAPI (10 minute timeout), hides backend error details |
| `lib/api.ts`, `lib/contracts.ts` | Reads the event stream, validates runs, groups versions into projects |
| `lib/storage.ts` | Sidebar shortcuts in `localStorage` |
| `hooks/use-runs.ts` | App state |
| `components/` | UI |

## Setup

### Requirements

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Node.js 22.17+ (also needed by the backend, to run Context7 with `npx`)
- A PostgreSQL database
- A [Groq](https://console.groq.com) API key
- Optional: [Tavily](https://tavily.com) and [Langfuse](https://langfuse.com) keys

### 1. Backend

```bash
cd ai-development-team-agent/backend
uv sync
```

Create `backend/.env`:

```bash
# Required. The +psycopg part is needed.
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
GROQ_API_KEY=
# Any long random string (openssl rand -hex 32). If unset, every API call is rejected.
AUTHENTICATED_KEY=

# Optional
GROQ_MODEL=openai/gpt-oss-120b
TAVILY_API_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=
```

```bash
uv run --env-file .env fastapi dev main.py      # http://localhost:8000, API docs at /docs
```

Keep `--env-file .env`: the model settings are read at import time, before `main.py` loads `.env`.

### 2. Frontend

In a second terminal:

```bash
cd ai-development-team-agent/frontend
npm install
cp .env.example .env.local      # set BACKEND_API_KEY to the AUTHENTICATED_KEY value
npm run dev                     # http://localhost:3000
```

Xander Bot uses the same default ports. To run both, start one backend with `--port 8001`, point its `BACKEND_URL` there, and start one frontend with `npm run dev -- -p 3001`.

### Checks

```bash
# frontend/
npm run lint && npm run typecheck && npm run build && npm test
```

## Known limitations

- **One shared API key, no user accounts.** Anyone who can reach the frontend can use the API.
- There is no endpoint to list runs. The browser remembers its own, and you can open any run by ID.
- Free model tiers can hit rate limits; the client retries up to 6 times.