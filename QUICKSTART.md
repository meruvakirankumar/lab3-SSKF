# Quick Start Guide — Code Architecture Analyzer

You have a complete React + FastAPI web app ready to run. Here's how to get it up in ~5 minutes.

## Step 1: Backend Setup (Terminal 1)

```bash
cd backend
pip install -r requirements.txt
python main.py
```

✅ Backend running on `http://localhost:8000`
✅ API docs at `http://localhost:8000/docs`

## Step 2: Frontend Setup (Terminal 2)

```bash
cd frontend
npm install
npm run dev
```

✅ Frontend running on `http://localhost:5173`

## Step 3: Test the App

1. Open `http://localhost:5173` in your browser
2. Enter a project name, e.g.: `My Sample App`
3. Upload the sample codebase:
   ```bash
   cd sample-codebase
   zip -r ../sample-codebase.zip .
   cd ..
   ```
   Then select `sample-codebase.zip` in the form and click **Upload & Analyze**
4. Wait 2-3 seconds for results
5. View architecture diagrams and data flows

## What You'll See

- **Component Diagram** — Directory and file structure
- **Class Diagram** — Exported classes and functions
- **Dependency Diagram** — Import relationships
- **Data Flow Details** — Primary execution paths

## Architecture

```
React Frontend (port 5173)
         ↓ (HTTP/REST)
FastAPI Backend (port 8000)
         ↓ (analyze)
File Scanner → Diagram Generator → Mermaid Output
```

## Next: Customize & Extend

- **Add more languages:** Edit `supported_extensions` in `app/services/analyzer.py`
- **Generate better diagrams:** Enhance `generate_mermaid_diagram()` logic
- **Add Couchbase:** Replace in-memory dicts with Couchbase collections
- **Background jobs:** Use Celery for large codebases

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Port 8000 in use | `lsof -i :8000` then `kill <PID>` |
| Port 5173 in use | Change in `vite.config.ts` |
| npm not found | Install Node.js from nodejs.org |
| pip install fails | Use `pip install --upgrade pip` first |
| CORS errors | Check vite.config.ts proxy config points to `:8000` |

## Demo Checklist

- [ ] Backend starts without errors
- [ ] Frontend loads in browser
- [ ] Upload form accepts zip files
- [ ] Analysis completes with no 500 errors
- [ ] Diagrams render (mermaid or text)
- [ ] Status updates from pending → complete
- [ ] Can navigate back and upload again

You're ready to ship! 🚀
