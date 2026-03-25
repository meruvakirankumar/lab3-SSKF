# Coding Agent Rules

> These rules tell your AI coding assistant how to behave in this project.
> Fill in the placeholder sections so the agent produces consistent,
> high-quality code that matches your team's conventions.

---

## 0. Project Scope (read this first)

This is a **workshop project**. It must stay within the boundaries of a
**simple, self-contained full stack web app**. The goal is to ship something
working, not something impressive on a whiteboard.

### What is in scope

| Layer | This project |
|-------|-------------|
| Frontend | React + Vite SPA with React Router (a few pages/routes) |
| Backend | A single FastAPI server with a handful of REST endpoints |
| Database | Couchbase — a small number of document collections (aim for 2–4) |
| Auth | **Out of scope for this workshop** — skip authentication entirely |
| Relationships | Model references between documents (e.g. store an id field); avoid deeply nested or highly relational data |
| Runtime | Containerized via Polytope; inspect running services with the Polytope MCP tools |

### What is out of scope

The agent must refuse to design or implement any of the following. If the
user's requirements imply one of these, the agent should flag it and propose a
simpler alternative instead.

- Authentication or user accounts of any kind (login, sessions, JWT, OAuth)
- Multiple backend services / microservices
- Real-time features (WebSockets, Server-Sent Events, live dashboards)
- File upload or cloud object storage (S3, GCS, etc.)
- Background job queues
- In-memory caching layers (Redis, Memcached)
- Full-text or faceted search beyond Couchbase's built-in N1QL queries
- Payment processing, email/SMS delivery, or other third-party service integrations
- AI / ML model inference or training
- Mobile apps or native desktop apps
- Multi-tenant or role-based permission systems

> **Rule of thumb:** if implementing the feature requires a third managed
> cloud service, a separate daemon process, or a protocol other than HTTP/REST,
> it is out of scope. Simplify the requirement until it fits.

---

## 1. Project Conventions

- **Frontend:** TypeScript · React · Vite · React Router
- **Backend:** Python · FastAPI
- **Database:** Couchbase (document store — use the Couchbase Python SDK)
- **Runtime:** Polytope (containerized); use the Polytope MCP tools to inspect
  running services, logs, and container state
- **Package managers:** `npm` (frontend) · `pip` / `uv` (backend). Add dependencies using MCP. 

## 2. File & Folder Structure

<!-- Describe the directory layout the agent should follow when creating or
     modifying files. -->

```
project/
├── …
├── …
└── …
```

## 3. Commit Practices

<!-- How should commits be structured? Conventional commits? Signed? -->

- Commit message format: …
- Branch naming: …

## 4. Code Style

<!-- Formatting, naming conventions, and patterns to follow or avoid. -->

- Formatting: …
- Naming: …
- Patterns to prefer: …
- Anti-patterns to avoid: …

## 5. Testing Strategy

<!-- What should be tested and how? Unit tests, integration tests, E2E? -->

- Test framework: …
- Coverage expectations: …
- What to test: …

## 6. AI Assistant Guardrails

<!-- Boundaries for the coding agent: what it should and shouldn't do
     autonomously. -->

- Always: check Section 0 before designing a new feature — if it falls outside
  workshop scope, stop and propose a simpler alternative before writing any code.
- Always: prefer the simplest data model and fewest endpoints that satisfy the
  requirement. Three lines of code beat a premature abstraction.
- Always: use the Polytope MCP tools to inspect the running stack (logs,
  container status, env vars) before assuming something is misconfigured.
- Never: implement any form of authentication, user accounts, or authorization —
  this is explicitly out of scope for the workshop.
- Never: introduce a dependency, service, or architectural pattern listed in
  Section 0's "out of scope" list.
- Never: add features, error handling, or configuration that was not explicitly
  requested — scope creep is the main risk in a workshop setting.
- Ask before: adding any new third-party library or service integration.
- Ask before: creating more than one backend service or adding a non-HTTP
  communication channel.
