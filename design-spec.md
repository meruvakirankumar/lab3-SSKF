# System Design Specification

> Fill in each section below to describe what you're building. This document
> will serve as the single source of truth for your project scope and
> architecture decisions.

## 1. Project Overview

**Code Architecture Analyzer** is a web application that allows developers to upload a zip file containing their codebase and receive instant visualizations of the code architecture and data flow patterns. The system analyzes imports, exports, and dependency relationships, then generates Mermaid diagrams showing component structure, class hierarchies, and data flow paths. Built for workshops and rapid architecture reviews.

## 2. Problem Statement

Developers often need to understand an unfamiliar codebase quickly—for onboarding, audits, or documentation. Manual inspection is time-consuming and error-prone. This system automates the discovery of code structure and relationships, providing instant visual feedback on how components interact.

## 3. Functional Requirements

- [x] The system shall accept zip file uploads containing source code.
- [x] The system shall extract and scan source files in supported languages (.py, .js, .jsx, .ts, .tsx, .java, .go, .rb, .php, .cs, .c, .cpp).
- [x] The system shall parse imports and exports from each file.
- [x] The system shall generate three architecture diagrams: component (file structure), class (exported symbols), and dependency (import relationships).
- [x] The system shall return diagrams in Mermaid format for web rendering.
- [x] The system shall identify and visualize primary data flow paths through the codebase.
- [x] The system shall display analysis results with project metadata and file statistics.
- [x] The system shall handle analysis errors gracefully and report failure status.

## 4. Non-Functional Requirements

- [ ] Analysis completes within 5 seconds for codebases under 500 files.
- [ ] Diagrams render without lag in modern browsers (Chrome, Firefox, Safari).
- [ ] Max upload size: 50MB zip files.
- [ ] No authentication required (workshop scope).
- [ ] Input sanitization to prevent path traversal attacks during zip extraction.
- [ ] Responsive UI works on desktop and tablet screens.

## 5. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Browser (React SPA)                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Upload Form │ Project View │ Diagram Display        │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP/REST (JSON)
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Backend                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ POST /api/upload         → Store zip, start analysis │  │
│  │ GET  /api/projects/{id}  → Return project metadata   │  │
│  │ GET  /api/.../diagrams   → Return Mermaid diagrams   │  │
│  │ GET  /api/.../dataflows  → Return data flow paths    │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ↓             ↓             ↓
    ┌─────────┐  ┌─────────┐  ┌──────────┐
    │Analyzer │  │Diagrams │  │DataFlows │
    │Service  │  │  Store  │  │ Store    │
    └─────────┘  └─────────┘  └──────────┘
         ↑
    ┌─────────┐
    │File Sys │ (temp uploads)
    └─────────┘
```

For production: Replace in-memory storage with Couchbase collections.

## 6. Components

| Component | Responsibility | Exposes |
|-----------|---------------|---------|
| **React Frontend** | User interface for upload and result display | HTML5 form, live status, diagram rendering |
| **FastAPI Server** | HTTP API, request handling, orchestration | POST /api/upload, GET /api/projects/{id}, GET /api/.../diagrams, GET /api/.../dataflows |
| **Analyzer Service** | File scanning, import/export parsing, diagram generation | `scan_codebase()`, `extract_imports()`, `extract_exports()`, `generate_mermaid_diagram()` |
| **File System** | Temporary storage for uploaded zips and extracted files | `/tmp/code_analyzer_uploads/` |
| **In-Memory Store** | Request-scoped project, diagram, and dataflow records | `projects_db`, `diagrams_db`, `dataflows_db` dictionaries |

## 7. Data Flow

**Primary User Flow: Upload & Analyze**

1. User opens React frontend and selects a zip file + project name.
2. Frontend calls `POST /api/upload` with FormData (file + project_name).
3. Backend receives upload, stores file in `/tmp/code_analyzer_uploads/`.
4. Backend extracts zip safely (sanitizes paths) to `{project_id}/` subdirectory.
5. Backend creates CodebaseProject record with status = 'analyzing'.
6. Analyzer Service scans directory recursively:
   - Identifies all supported source files.
   - Extracts imports, exports, and metadata per file.
   - Groups files by directory.
7. Analyzer generates three Mermaid diagrams (component, class, dependency).
8. Analyzer creates DataFlow records representing primary flow paths.
9. Backend updates CodebaseProject status = 'complete'.
10. Frontend polls or receives notification; displays results.
11. User views diagrams and data flow paths; can export or review code structure.

## 8. Client-Server Relationships

**Client (React):**
- Runs entirely in the browser (no authentication, no server-side rendering).
- Handles UI state, form submission, diagram rendering.
- Calls backend API via axios for all data operations.

**Server (FastAPI):**
- Stateless HTTP API (in workshop mode; can be stateful with reverse proxy).
- Handles file uploads, analysis orchestration, and response serialization.
- Stores analysis results in memory (workshop) or Couchbase (production).

**API Contract:**
- Request/response format: JSON (Pydantic models).
- Error responses: `{ success: false, error: "message" }`.
- Success responses: `{ success: true, data: {...} }`.
- CORS enabled for `localhost:5173` and `localhost:3000`.
- No authentication headers required.

## 9. Invariances & Constraints

- **Zip Extraction Safety:** Never extract files outside the target directory (no path traversal).
- **Project Uniqueness:** Each upload receives a unique UUID; no overwrite of previous analyses.
- **Supported Files Only:** Only analyze recognized source file extensions; ignore binaries, media, etc.
- **File Limits:** Max 500 files per analysis; max 50 files per diagram to prevent visual clutter.
- **Status Transitions:** Analysis status is one-way: pending → analyzing → complete (or failed, always final).
- **Transient Data:** Uploaded zips and extracted files are temporary; cleaned up after analysis or on server shutdown.
- **No Side Effects:** Analysis does not modify the uploaded code; read-only scanning.

## 10. Milestones

| # | Milestone | Deliverable | Definition of Done |
|---|-----------|-------------|-------------------|
| 1 | **Upload & Extract** | File upload form + backend extraction | React form submits zip; backend extracts safely to temp dir; returns project ID |
| 2 | **Code Analysis** | File scanner + import/export parser | Analyzer scans all supported file types; extracts 10+ imports/exports per file; handles errors |
| 3 | **Diagram Generation** | Mermaid diagrams (component, class, dependency) | 3 diagrams generated per project; render without errors in browser; valid Mermaid syntax |
| 4 | **Data Flow Detection** | Identify and visualize primary flow paths | At least 1 data flow path detected per project; shows start→steps→end chain |
| 5 | **Full Integration** | End-to-end workflow + results display | Upload → analyze → view diagrams/flows; no broken links or 500 errors |
| 6 | **Polish & Demo** | README + deployment guide + demo script | App runs in <5 min setup; demo codebase provided; clear handoff docs |
