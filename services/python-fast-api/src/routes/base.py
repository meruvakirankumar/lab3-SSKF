from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import time
import uuid
import zipfile
import requests

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from utils import log

logger = log.get_logger(__name__)
router = APIRouter()

# Load OpenAPI key from environment or config file
OPENAPI_KEY = os.environ.get("OPENAPI_KEY")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION")

if not OPENAPI_KEY:
    # Try to load from mounted config file
    config_paths = [
        Path("/config/openapi-key.env"),
        Path("./../../config/openapi-key.env"),
    ]
    
    for key_file in config_paths:
        logger.info(f"Checking for OpenAPI key in {key_file}")
        if key_file.exists():
            logger.info(f"Found {key_file}, reading...")
            try:
                with open(key_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("OPENAPI_KEY="):
                            OPENAPI_KEY = line.split("=", 1)[1].strip('"').strip("'")
                            logger.info(f"✓ OpenAPI key loaded from {key_file}")
                        elif line.startswith("AZURE_OPENAI_DEPLOYMENT="):
                            AZURE_OPENAI_DEPLOYMENT = line.split("=", 1)[1].strip('"').strip("'")
                        elif line.startswith("AZURE_OPENAI_API_VERSION="):
                            AZURE_OPENAI_API_VERSION = line.split("=", 1)[1].strip('"').strip("'")
                if OPENAPI_KEY:
                    break
            except Exception as e:
                logger.warning(f"Failed to read {key_file}: {e}")

if OPENAPI_KEY:
    logger.info("✓ OpenAI API integration ENABLED")
else:
    logger.warning("✗ OpenAPI key not found - analysis will use local pattern extraction only")

UPLOAD_ROOT = Path(os.environ.get("UPLOAD_DIR", Path.home() / "code_analyzer_uploads"))
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rb",
    ".php",
    ".cs",
    ".c",
    ".cpp",
    ".razor",
}

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".razor": "C#",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".cpp": "C++",
}

LANGUAGE_COLORS: dict[str, str] = {
    "Python": "#3776ab",
    "JavaScript": "#f7df1e",
    "TypeScript": "#3178c6",
    "Java": "#b07219",
    "Go": "#00add8",
    "Ruby": "#701516",
    "PHP": "#4f5d95",
    "C#": "#178600",
    "C": "#555555",
    "C++": "#f34b7d",
}

# (config_filename, substring_to_match, framework_name)
FRAMEWORK_INDICATORS: list[tuple[str, str, str]] = [
    ("package.json", '"react"', "React"),
    ("package.json", '"next"', "Next.js"),
    ("package.json", '"vue"', "Vue.js"),
    ("package.json", '"@angular/core"', "Angular"),
    ("package.json", '"svelte"', "Svelte"),
    ("package.json", '"express"', "Express"),
    ("package.json", '"fastify"', "Fastify"),
    ("package.json", '"tailwindcss"', "Tailwind CSS"),
    ("package.json", '"vite"', "Vite"),
    ("package.json", '"react-router"', "React Router"),
    ("requirements.txt", "fastapi", "FastAPI"),
    ("requirements.txt", "django", "Django"),
    ("requirements.txt", "flask", "Flask"),
    ("requirements.txt", "sqlalchemy", "SQLAlchemy"),
    ("requirements.txt", "celery", "Celery"),
    ("pyproject.toml", "fastapi", "FastAPI"),
    ("pyproject.toml", "django", "Django"),
    ("pyproject.toml", "flask", "Flask"),
    ("pyproject.toml", "pydantic", "Pydantic"),
    ("pyproject.toml", "uvicorn", "Uvicorn"),
    ("go.mod", "gin-gonic", "Gin"),
    ("go.mod", "echo", "Echo"),
    ("go.mod", "fiber", "Fiber"),
    ("pom.xml", "spring-boot", "Spring Boot"),
    ("pom.xml", "spring-web", "Spring Web"),
    ("build.gradle", "spring-boot", "Spring Boot"),
    ("Gemfile", "rails", "Ruby on Rails"),
    ("composer.json", "laravel", "Laravel"),
    ("composer.json", "symfony", "Symfony"),
    # .NET / Blazor — detected from .csproj content
    (".csproj", "Microsoft.AspNetCore.Components.WebServer", "Blazor Server"),
    (".csproj", "blazor.server", "Blazor Server"),
    (".csproj", "Microsoft.AspNetCore.Components.WebAssembly", "Blazor WebAssembly"),
    (".csproj", "Microsoft.AspNetCore.Components", "Blazor"),
    (".csproj", "Microsoft.EntityFrameworkCore", "Entity Framework Core"),
    (".csproj", "Microsoft.AspNetCore", "ASP.NET Core"),
    (".csproj", "microsoft.net.sdk.web", "ASP.NET Core"),
    (".csproj", "microsoft.net.sdk.razorpages", "Razor Pages"),
]

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
SCAN_MAX_FILES = int(os.environ.get("ANALYZER_SCAN_MAX_FILES", "250"))
SCAN_MAX_FILE_BYTES = int(os.environ.get("ANALYZER_SCAN_MAX_FILE_BYTES", "200000"))
OPENAI_MAX_FILES = int(os.environ.get("ANALYZER_OPENAI_MAX_FILES", "120"))
OPENAI_TIMEOUT_SECONDS = int(os.environ.get("ANALYZER_OPENAI_TIMEOUT_SECONDS", "5"))
OPENAI_CONNECT_TIMEOUT_SECONDS = int(os.environ.get("ANALYZER_OPENAI_CONNECT_TIMEOUT_SECONDS", "2"))

# Workshop scope: lightweight in-memory persistence.
PROJECTS_DB: dict[str, dict] = {}
DIAGRAMS_DB: dict[str, dict] = {}
DATAFLOWS_DB: dict[str, dict] = {}
INSIGHTS_DB: dict[str, dict] = {}
OPENAI_DISABLED = False


@router.get("/")
async def root():
    return {"message": "Code Architecture Analyzer API"}


@router.post("/api/upload")
async def upload_codebase(
    file: UploadFile = File(...),
    project_name: str = Form(...),
):
    """Upload a zip file and register a project for later analysis."""
    if not project_name.strip():
        raise HTTPException(status_code=400, detail="project_name is required")

    filename = file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip uploads are supported")

    project_id = str(uuid.uuid4())
    project_dir = UPLOAD_ROOT / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    archive_path = project_dir / "upload.zip"

    file_size = 0
    try:
        with archive_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=400, detail="Upload exceeds 2GB limit")
                out.write(chunk)
    except HTTPException:
        if archive_path.exists():
            archive_path.unlink(missing_ok=True)
        raise

    project = {
        "id": project_id,
        "project_name": project_name.strip(),
        "upload_timestamp": datetime.now(timezone.utc).isoformat(),
        "zip_filename": filename,
        "file_size_bytes": file_size,
        "status": "pending",
        "error_message": None,
        "extract_path": str(project_dir / "extracted"),
    }
    PROJECTS_DB[project_id] = project

    try:
        _safe_extract_zip(archive_path, project_dir / "extracted")
    except Exception as exc:
        logger.exception("Extraction failed for project %s", project_id)
        project["status"] = "failed"
        project["error_message"] = str(exc)

    return {
        "success": True,
        "data": {
            "id": project["id"],
            "project_name": project["project_name"],
            "upload_timestamp": project["upload_timestamp"],
            "zip_filename": project["zip_filename"],
            "file_size_bytes": project["file_size_bytes"],
            "status": project["status"],
            "error_message": project["error_message"],
        },
    }


@router.post("/api/projects/{project_id}/analyze")
async def analyze_project(project_id: str):
    """Run code analysis for an uploaded project and generate diagrams."""
    project = PROJECTS_DB.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project["status"] == "failed":
        raise HTTPException(status_code=400, detail="Project is in failed state")

    extract_path = Path(project["extract_path"])
    if not extract_path.exists():
        raise HTTPException(status_code=400, detail="Upload extraction path not found")

    project["status"] = "analyzing"
    project["error_message"] = None

    try:
        analysis_start = time.perf_counter()
        # Clear old analysis artifacts when re-running analysis.
        stale_diagrams = [k for k, v in DIAGRAMS_DB.items() if v["project_id"] == project_id]
        for key in stale_diagrams:
            del DIAGRAMS_DB[key]

        stale_flows = [k for k, v in DATAFLOWS_DB.items() if v["project_id"] == project_id]
        for key in stale_flows:
            del DATAFLOWS_DB[key]

        scan_start = time.perf_counter()
        files = _scan_codebase(extract_path, max_files=SCAN_MAX_FILES)
        scan_ms = int((time.perf_counter() - scan_start) * 1000)
        logger.info("Scanned %s files in %sms for project %s", len(files), scan_ms, project_id)

        lang_data = _detect_languages(files, extract_path)
        project["languages"] = lang_data["languages"]
        project["frameworks"] = lang_data["frameworks"]
        project["primary_language"] = lang_data["primary_language"]
        project["total_files_analyzed"] = lang_data["total_files_analyzed"]
        project["total_lines"] = lang_data["total_lines"]
        logger.info("Detected languages %s for project %s", [l["name"] for l in lang_data["languages"]], project_id)

        store_start = time.perf_counter()
        _store_analysis(project_id, files)
        store_ms = int((time.perf_counter() - store_start) * 1000)
        total_ms = int((time.perf_counter() - analysis_start) * 1000)
        logger.info("Stored analysis in %sms (total %sms) for project %s", store_ms, total_ms, project_id)
        project["status"] = "complete"
    except Exception as exc:
        logger.exception("Analysis failed for project %s", project_id)
        project["status"] = "failed"
        project["error_message"] = str(exc)

    return {
        "success": True,
        "data": {
            "id": project["id"],
            "project_name": project["project_name"],
            "upload_timestamp": project["upload_timestamp"],
            "zip_filename": project["zip_filename"],
            "file_size_bytes": project["file_size_bytes"],
            "status": project["status"],
            "error_message": project["error_message"],
            "languages": project.get("languages", []),
            "frameworks": project.get("frameworks", []),
            "primary_language": project.get("primary_language", "Unknown"),
            "total_files_analyzed": project.get("total_files_analyzed", 0),
            "total_lines": project.get("total_lines", 0),
        },
    }


@router.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    """Get project metadata and analysis status."""
    project = PROJECTS_DB.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"success": True, "data": project}


@router.get("/api/projects/{project_id}/diagrams")
async def get_diagrams(project_id: str):
    """Fetch generated architecture diagrams for a project."""
    if project_id not in PROJECTS_DB:
        raise HTTPException(status_code=404, detail="Project not found")
    diagrams = [d for d in DIAGRAMS_DB.values() if d["project_id"] == project_id]
    return {"success": True, "data": diagrams}


@router.get("/api/projects/{project_id}/dataflows")
async def get_dataflows(project_id: str):
    """Fetch detected data flow paths for a project."""
    if project_id not in PROJECTS_DB:
        raise HTTPException(status_code=404, detail="Project not found")
    flows = [f for f in DATAFLOWS_DB.values() if f["project_id"] == project_id]
    return {"success": True, "data": flows}


@router.get("/api/projects/{project_id}/insights")
async def get_insights(project_id: str):
    """Fetch AI-generated insights for a project."""
    if project_id not in PROJECTS_DB:
        raise HTTPException(status_code=404, detail="Project not found")
    insights = INSIGHTS_DB.get(project_id)
    if not insights:
        return {"success": True, "data": None}
    return {"success": True, "data": insights}


def _safe_extract_zip(zip_path: Path, output_dir: Path) -> Path:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            candidate = (output_dir / info.filename).resolve()
            if not str(candidate).startswith(str(output_dir.resolve())):
                raise ValueError("Unsafe zip path detected")
        zf.extractall(output_dir)

    return output_dir


def _scan_codebase(root: Path, max_files: int = SCAN_MAX_FILES) -> list[dict]:
    results: list[dict] = []

    for current_root, dirs, files in os.walk(root):
        dirs[:] = [
            d
            for d in dirs
            if d not in {
                ".git", "node_modules", "__pycache__", "dist", "build",
                ".venv", "venv", "obj", "bin", ".vs", ".idea",
                "Migrations", ".nuget", "packages", "TestResults",
            }
        ]

        for file_name in files:
            if len(results) >= max_files:
                return results

            ext = Path(file_name).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            abs_path = Path(current_root) / file_name
            rel_path = abs_path.relative_to(root).as_posix()

            try:
                with abs_path.open("rb") as fh:
                    raw = fh.read(SCAN_MAX_FILE_BYTES)
                content = raw.decode("utf-8", errors="ignore")
            except Exception:
                continue

            imports = _extract_imports(content, ext)
            exports = _extract_exports(content, ext)
            namespace = _extract_namespace(content, ext)
            is_page = bool(re.search(r"^@page\s+", content, re.MULTILINE)) if ext == ".razor" else False
            results.append(
                {
                    "file_path": rel_path,
                    "file_type": ext,
                    "imports": sorted(imports),
                    "exported_items": sorted(exports),
                    "line_count": len(content.splitlines()),
                    "namespace": namespace,
                    "is_page": is_page,
                }
            )

    return results


# Third-party / stdlib prefixes to exclude from internal import tracking
_STDLIB_PREFIXES = {
    "os", "sys", "re", "json", "time", "uuid", "math", "abc", "io", "ast",
    "copy", "enum", "typing", "pathlib", "shutil", "zipfile", "datetime",
    "collections", "itertools", "functools", "contextlib", "dataclasses",
    "asyncio", "concurrent", "threading", "subprocess", "logging",
    "unittest", "http", "urllib", "email", "html", "xml", "csv", "hashlib",
    "base64", "struct", "socket", "ssl", "signal", "traceback", "warnings",
    # Popular third-party
    "fastapi", "starlette", "pydantic", "uvicorn", "requests", "httpx",
    "aiohttp", "sqlalchemy", "alembic", "celery", "redis", "pymongo",
    "boto3", "botocore", "django", "flask", "pytest", "click", "typer",
    "rich", "yaml", "toml", "dotenv", "jwt", "cryptography",
    "react", "next", "vue", "angular", "svelte", "express", "lodash",
    "axios", "fetch", "zod", "vite", "tailwind", "radix",
}

# C# / .NET external namespace roots to exclude
_CSHARP_EXTERNAL_ROOTS = {
    "system", "microsoft", "newtonsoft", "autofac", "castle",
    "fluentvalidation", "automapper", "mediatr", "serilog", "nlog",
    "xunit", "nunit", "moq", "humanizer", "polly", "npgsql",
    "mysql", "mongodb", "stackexchange", "grpc", "protobuf",
    "blazorise", "mudblazor", "radzen", "syncfusion", "telerik",
    "bunit", "spectre",
}


def _is_external_csharp_namespace(ns: str) -> bool:
    root = ns.split(".")[0].lower()
    return root in _CSHARP_EXTERNAL_ROOTS


def _is_internal_import(imp: str) -> bool:
    """Return True only for relative or project-local import paths (JS/TS/Python)."""
    if imp.startswith("."):
        return True
    if "/" in imp or "\\" in imp:
        return True
    root = imp.split(".")[0].split("/")[0].lower()
    return root not in _STDLIB_PREFIXES


def _extract_namespace(content: str, ext: str) -> str:
    """Extract the declared namespace/module from a source file."""
    if ext == ".cs":
        # File-scoped: namespace Foo.Bar;
        m = re.search(r"^namespace\s+([\w.]+)\s*;", content, re.MULTILINE)
        if m:
            return m.group(1)
        # Block-scoped: namespace Foo.Bar {
        m = re.search(r"^namespace\s+([\w.]+)\s*\{", content, re.MULTILINE)
        return m.group(1) if m else ""
    if ext == ".razor":
        m = re.search(r"^@namespace\s+([\w.]+)", content, re.MULTILINE)
        return m.group(1) if m else ""
    return ""


def _extract_imports(content: str, ext: str = "") -> set[str]:
    found: set[str] = set()
    if ext == ".cs":
        # using MyApp.Services; / using static MyApp.Utils.Helpers;
        for m in re.findall(r"^using\s+(?:static\s+)?([\w.]+)\s*;", content, re.MULTILINE):
            if not _is_external_csharp_namespace(m):
                found.add(m)
        return found
    if ext == ".razor":
        # @using MyApp.Services
        for m in re.findall(r"^@using\s+([\w.]+)", content, re.MULTILINE):
            if not _is_external_csharp_namespace(m):
                found.add(m)
        # @inject ServiceType varName  — track the type namespace
        for m in re.findall(r"^@inject\s+([\w.]+)", content, re.MULTILINE):
            if not _is_external_csharp_namespace(m):
                found.add(m)
        # <ComponentName … /> where ComponentName starts with uppercase
        for m in re.findall(r"<([A-Z]\w+)[\s/>]", content):
            found.add(f"__component__{m}")
        return found
    # JS/TS: import ... from '...' or require('...')
    for match in re.findall(r"(?:import|require)\s*(?:[^'\"]*from\s*)?['\"]([^'\"]+)['\"]", content):
        if _is_internal_import(match):
            found.add(match)
    # Python: from X import ... / import X
    for match in re.findall(r"^\s*(?:from|import)\s+([\w./]+)", content, flags=re.MULTILINE):
        if _is_internal_import(match):
            found.add(match)
    return found


def _extract_exports(content: str, ext: str) -> set[str]:
    found: set[str] = set()

    if ext == ".cs":
        # public/internal/protected class|interface|enum|record|struct
        for name in re.findall(
            r"(?:public|internal|protected)\s+(?:abstract\s+|sealed\s+|static\s+|partial\s+)*"
            r"(?:class|interface|enum|record|struct)\s+(\w+)",
            content,
            re.MULTILINE,
        ):
            found.add(name)
        return found

    if ext == ".razor":
        # Component name = filename stem (set in scan loop from file_path)
        # Parameters exposed via [Parameter]
        for name in re.findall(r"\[Parameter\]\s*\n\s*public\s+\S+\s+(\w+)", content):
            found.add(name)
        # @code block public methods/properties
        for name in re.findall(r"public\s+(?:async\s+)?(?:\S+\s+)?(\w+)\s*[\({]", content):
            found.add(name)
        return found

    if ext == ".py":
        for name in re.findall(r"^\s*(?:def|class)\s+(\w+)", content, flags=re.MULTILINE):
            found.add(name)
        return found

    for name in re.findall(r"export\s+(?:default\s+)?(?:class|function|const|let|var)?\s*(\w+)", content):
        if name:
            found.add(name)
    return found


def _detect_languages(files: list[dict], extract_path: Path) -> dict:
    """Detect programming languages and frameworks from scanned files."""
    from collections import defaultdict

    lang_files: defaultdict[str, int] = defaultdict(int)
    lang_lines: defaultdict[str, int] = defaultdict(int)

    for f in files:
        ext = f.get("file_type", "")
        lang = EXTENSION_TO_LANGUAGE.get(ext)
        if lang:
            lang_files[lang] += 1
            lang_lines[lang] += f.get("line_count", 0)

    total_files = sum(lang_files.values()) or 1

    languages = []
    for lang, count in sorted(lang_files.items(), key=lambda x: -x[1]):
        languages.append({
            "name": lang,
            "file_count": count,
            "line_count": lang_lines[lang],
            "percentage": round(count / total_files * 100, 1),
            "color": LANGUAGE_COLORS.get(lang, "#8e8e8e"),
        })

    # Detect frameworks by scanning well-known config files
    frameworks: list[str] = []
    seen: set[str] = set()

    for config_file, keyword, framework in FRAMEWORK_INDICATORS:
        if framework in seen:
            continue
        for match in extract_path.rglob(config_file):
            try:
                content = match.read_text(encoding="utf-8", errors="ignore").lower()
                if keyword.lower() in content:
                    frameworks.append(framework)
                    seen.add(framework)
                    break
            except Exception:
                continue

    return {
        "languages": languages,
        "frameworks": frameworks,
        "primary_language": languages[0]["name"] if languages else "Unknown",
        "total_files_analyzed": len(files),
        "total_lines": sum(lang_lines.values()),
    }


def _store_analysis(project_id: str, files: list[dict]) -> None:
    """Store analysis results. If OpenAPI is available, use it for enhanced analysis."""
    
    # Get OpenAI insights if API key is available
    ai_insights = None
    if OPENAPI_KEY and len(files) <= OPENAI_MAX_FILES:
        ai_insights = _get_openai_analysis(files)
        if ai_insights:
            INSIGHTS_DB[project_id] = ai_insights
    elif OPENAPI_KEY:
        logger.info(
            "Skipping OpenAI analysis for project %s because file count %s exceeds limit %s",
            project_id,
            len(files),
            OPENAI_MAX_FILES,
        )
    
    diagrams = {
        "component": _generate_component_diagram(files, ai_insights),
        "class": _generate_class_diagram(files, ai_insights),
        "dependency": _generate_dependency_diagram(files, ai_insights),
        "flowchart": _generate_flowchart_diagram(files, ai_insights),
    }

    component_count = sum(1 for f in files if f.get("exported_items"))
    now = datetime.now(timezone.utc).isoformat()

    for diagram_type, content in diagrams.items():
        diagram_id = str(uuid.uuid4())
        DIAGRAMS_DB[diagram_id] = {
            "id": diagram_id,
            "project_id": project_id,
            "diagram_type": diagram_type,
            "diagram_format": "mermaid",
            "diagram_content": content,
            "generated_timestamp": now,
            "file_count": len(files),
            "component_count": component_count,
            "ai_enhanced": bool(ai_insights),
        }

    # Generate flows with AI insights if available
    flows = _generate_dataflows(files, ai_insights)
    for flow in flows:
        flow_id = str(uuid.uuid4())
        DATAFLOWS_DB[flow_id] = {
            "id": flow_id,
            "project_id": project_id,
            "flow_name": flow["name"],
            "start_component": flow["start"],
            "end_component": flow["end"],
            "steps": flow["steps"],
            "description": flow["description"],
        }


def _get_openai_analysis(files: list[dict]) -> dict | None:
    """Call OpenAI API to analyze the codebase and get architectural insights."""
    global OPENAI_DISABLED

    if OPENAI_DISABLED or not OPENAPI_KEY or not files:
        return None
    
    try:
        # Prepare code summary for OpenAI
        code_summary = _prepare_code_summary(files)
        
        prompt = f"""Analyze this codebase architecture and provide insights:

{code_summary}

Please provide a JSON response with:
1. "architecture_pattern": The main architecture pattern (e.g., MVC, microservices, monolithic, etc.)
2. "main_components": List of 3-5 main architectural components
3. "key_responsibilities": What each main component does
4. "data_flows": List of primary data flow paths
5. "dependencies": Major external dependencies
6. "technologies": List of detected technologies/frameworks
7. "quality_assessment": Brief assessment of code organization

Respond only with valid JSON."""

        is_openrouter = OPENAPI_KEY.startswith("sk-or-")
        api_url = (
            "https://openrouter.ai/api/v1/chat/completions"
            if is_openrouter
            else "https://api.openai.com/v1/chat/completions"
        )
        model_name = "openai/gpt-5.4" if is_openrouter else "gpt-5.4"

        headers = {
            "Authorization": f"Bearer {OPENAPI_KEY}",
            "Content-Type": "application/json",
        }
        if is_openrouter:
            headers["HTTP-Referer"] = "https://local.code-architecture-analyzer"
            headers["X-Title"] = "Code Architecture Analyzer"

        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0.7,
        }
        
        # Add Azure OpenAI configuration if available
        if AZURE_OPENAI_DEPLOYMENT:
            payload["deployment"] = AZURE_OPENAI_DEPLOYMENT
        if AZURE_OPENAI_API_VERSION:
            payload["api_version"] = AZURE_OPENAI_API_VERSION
        
        response = requests.post(
            api_url,
            json=payload,
            headers=headers,
            timeout=(OPENAI_CONNECT_TIMEOUT_SECONDS, OPENAI_TIMEOUT_SECONDS),
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Try to parse JSON from response
            try:
                insights = json.loads(content)
                logger.info("OpenAI analysis completed successfully")
                return insights
            except json.JSONDecodeError:
                logger.warning("Failed to parse OpenAI response as JSON")
                return None
        else:
            response_text = response.text
            if response.status_code in {401, 403}:
                OPENAI_DISABLED = True
                logger.warning("Disabling AI analysis after authorization failure")
            logger.warning(f"OpenAI API error: {response.status_code} - {response_text}")
            return None
            
    except requests.exceptions.RequestException as exc:
        OPENAI_DISABLED = True
        logger.warning("Disabling AI analysis after network error: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Error calling OpenAI API: %s", exc)
        return None


def _prepare_code_summary(files: list[dict]) -> str:
    """Prepare a summary of the codebase for OpenAI analysis."""
    summary_lines = [
        f"Total files: {len(files)}",
        f"Total lines of code: {sum(f.get('line_count', 0) for f in files)}",
        "",
        "File Structure:",
    ]
    
    for f in files[:20]:
        imports = ", ".join(f.get("imports", [])[:3])
        exports = ", ".join(f.get("exported_items", [])[:3])
        summary = f"  {f['file_path']} ({f['line_count']} lines)"
        if exports:
            summary += f" exports: {exports}"
        if imports:
            summary += f" | imports: {imports}"
        summary_lines.append(summary)
    
    if len(files) > 20:
        summary_lines.append(f"  ... and {len(files) - 20} more files")
    
    return "\n".join(summary_lines)


def _build_import_graph(files: list[dict]) -> dict[str, list[str]]:
    """
    Build a directed graph: file_path -> list of file_paths it imports.
    Handles:
      - JS/TS/Python: resolves relative & absolute paths against known files.
      - C#/.razor: resolves 'using' namespace directives against declared namespaces,
        links .razor files to their .cs code-behind counterparts, and resolves
        Razor component references (<ComponentName />) by filename stem.
    """
    path_set = {f["file_path"] for f in files}

    # Build namespace → file map for C# files
    ns_to_file: dict[str, str] = {}
    for f in files:
        ns = f.get("namespace", "")
        if ns:
            ns_to_file[ns] = f["file_path"]

    # Build component-name → file map for .razor files (stem = component name)
    razor_name_to_file: dict[str, str] = {
        Path(f["file_path"]).stem: f["file_path"]
        for f in files
        if f["file_type"] == ".razor"
    }

    def resolve_js_py(importing_file: str, raw_import: str) -> str | None:
        base_dir = str(Path(importing_file).parent)
        candidates = []
        if raw_import.startswith("."):
            joined = (Path(base_dir) / raw_import).as_posix()
            candidates.append(joined)
        else:
            candidates.append(raw_import)

        for cand in candidates:
            if cand in path_set:
                return cand
            for ext in (".ts", ".tsx", ".js", ".jsx", ".py"):
                if (cand + ext) in path_set:
                    return cand + ext
                index = cand.rstrip("/") + "/index" + ext
                if index in path_set:
                    return index
            if "." in cand and "/" not in cand:
                as_path = cand.replace(".", "/") + ".py"
                if as_path in path_set:
                    return as_path
        return None

    def resolve_csharp(importing_file: str, raw: str) -> str | None:
        # Component reference marker from Razor (e.g. __component__NavMenu)
        if raw.startswith("__component__"):
            name = raw[len("__component__"):]
            return razor_name_to_file.get(name)

        # Exact namespace match
        if raw in ns_to_file:
            target = ns_to_file[raw]
            return target if target != importing_file else None

        # Prefix match: 'using MyApp.Services' matches namespace 'MyApp.Services.Auth'
        best: str | None = None
        for ns, fp in ns_to_file.items():
            if fp == importing_file:
                continue
            if ns.startswith(raw + ".") or raw.startswith(ns + "."):
                # Pick the most specific match
                if best is None or len(ns) > len(ns_to_file.get(best, "")):
                    best = fp
        return best

    graph: dict[str, list[str]] = {}
    for f in files:
        ext = f["file_type"]
        resolved: list[str] = []

        if ext in (".cs", ".razor"):
            for raw in f.get("imports", []):
                target = resolve_csharp(f["file_path"], raw)
                if target and target not in resolved:
                    resolved.append(target)
            # Link .razor to its .cs code-behind (MyPage.razor ↔ MyPage.razor.cs)
            if ext == ".razor":
                codebehind = f["file_path"] + ".cs"
                if codebehind in path_set and codebehind not in resolved:
                    resolved.append(codebehind)
        else:
            for raw in f.get("imports", []):
                target = resolve_js_py(f["file_path"], raw)
                if target and target != f["file_path"] and target not in resolved:
                    resolved.append(target)

        graph[f["file_path"]] = resolved

    return graph


def _find_entry_points(files: list[dict], graph: dict[str, list[str]]) -> list[str]:
    """
    Heuristically find entry-point files.
    Priority:
      1. C#/Blazor: Program.cs → Startup.cs → App.razor
      2. Other languages: common entry-point names (main, index, app, server)
      3. Graph roots: files not imported by any other file
    """
    ENTRY_NAMES = {
        # C# / Blazor
        "program.cs", "startup.cs", "app.razor",
        # Web/JS
        "main.py", "index.ts", "index.tsx", "index.js", "app.py",
        "server.py", "server.ts", "app.ts", "app.tsx",
        # Generic
        "main", "index", "app", "server", "entry", "client",
    }
    all_paths = [f["file_path"] for f in files]
    imported_by_others: set[str] = set()
    for targets in graph.values():
        imported_by_others.update(targets)

    # Named entries first (ordered by priority)
    entry_points: list[str] = []
    for priority_name in ["program.cs", "startup.cs", "app.razor"]:
        for p in all_paths:
            if Path(p).name.lower() == priority_name and p not in entry_points:
                entry_points.append(p)

    for p in all_paths:
        name = Path(p).name.lower()
        stem = Path(p).stem.lower()
        if (name in ENTRY_NAMES or stem in ENTRY_NAMES) and p not in entry_points:
            entry_points.append(p)

    # Blazor @page components as secondary entry points
    for f in files:
        if f.get("is_page") and f["file_path"] not in entry_points:
            entry_points.append(f["file_path"])

    # Graph roots (not imported by anyone)
    for p in all_paths:
        if p not in imported_by_others and p not in entry_points:
            entry_points.append(p)

    return entry_points or all_paths[:1]


def _trace_flow(start: str, graph: dict[str, list[str]], max_depth: int = 8) -> list[str]:
    """BFS from start following the import graph, returning the visited path."""
    visited: list[str] = []
    queue = [start]
    seen: set[str] = {start}
    while queue and len(visited) < max_depth:
        node = queue.pop(0)
        visited.append(node)
        for dep in graph.get(node, []):
            if dep not in seen:
                seen.add(dep)
                queue.append(dep)
    return visited


def _generate_dataflows(files: list[dict], ai_insights: dict | None) -> list[dict]:
    """Generate named data flow paths with human-readable steps."""
    flows = []

    if ai_insights and "data_flows" in ai_insights:
        for flow in ai_insights.get("data_flows", [])[:3]:
            if isinstance(flow, dict):
                flows.append({
                    "name": flow.get("name", "AI-Identified Flow"),
                    "start": flow.get("start", ""),
                    "end": flow.get("end", ""),
                    "steps": flow.get("steps", []),
                    "description": flow.get("description", ""),
                })

    if not files:
        flows.append({"name": "No files", "start": "Browser", "end": "Server", "steps": [], "description": "No source files found"})
        return flows

    if _is_dotnet_project(files):
        flows.extend(_generate_blazor_dataflows(files))
    else:
        flows.extend(_generate_generic_dataflows(files))

    return flows


def _generate_blazor_dataflows(files: list[dict]) -> list[dict]:
    """Generate semantic data flow descriptions for Blazor Server applications."""
    from collections import defaultdict
    flows = []

    layer_files: defaultdict[str, list[dict]] = defaultdict(list)
    for f in files:
        layer_files[_classify_blazor_file(f)].append(f)

    pages    = layer_files.get("Pages", [])
    services = layer_files.get("Services", [])
    data_ctx = layer_files.get("Data / DbContext", [])
    models   = layer_files.get("Models / Entities", [])
    shell    = layer_files.get("App Shell", [])
    shared   = layer_files.get("Shared / Layout", [])
    comps    = layer_files.get("Components", [])
    hubs     = layer_files.get("SignalR Hubs", [])
    entry    = layer_files.get("Entry Point", [])

    graph = _build_import_graph(files)

    # ── Flow 1: Full User Request → Render cycle ──────────────────────────
    request_steps = [
        "Browser sends HTTP request to ASP.NET Core Kestrel server",
        "ASP.NET Core middleware pipeline processes the request (auth, routing, etc.)",
    ]
    if entry:
        request_steps.append(f"{Path(entry[0]['file_path']).name} configures services and the HTTP pipeline")
    if shell:
        app_razor = next((f for f in shell if Path(f["file_path"]).name.lower() == "app.razor"), shell[0])
        request_steps.append(f"{Path(app_razor['file_path']).name} Router matches URL and selects the target Page")
    if shared:
        layout = next((f for f in shared if "layout" in f["file_path"].lower()), shared[0])
        request_steps.append(f"{Path(layout['file_path']).name} renders the page shell (nav, header, etc.)")
    if pages:
        request_steps.append(f"Target Page component (e.g. {Path(pages[0]['file_path']).name}) initialises via OnInitializedAsync")
    if services:
        request_steps.append(f"Page calls injected service (e.g. {Path(services[0]['file_path']).name}) to load data")
    if data_ctx:
        request_steps.append(f"{Path(data_ctx[0]['file_path']).name} executes a parameterised SQL query against the database")
    if models:
        request_steps.append(f"Query results are mapped to {Path(models[0]['file_path']).name} model objects")
    if pages:
        request_steps.append("Model data is bound to component properties and Razor markup re-renders")
    request_steps.append("Blazor Server pushes the minimal HTML diff back to the browser over SignalR WebSocket")

    flows.append({
        "name": "User Request → Page Render",
        "start": "Browser (HTTP Request)",
        "end": "Browser (Rendered HTML via SignalR)",
        "steps": request_steps,
        "description": "Complete lifecycle of a page load in Blazor Server: from HTTP request through the circuit, data retrieval, and DOM update.",
    })

    # ── Flow 2: User Interaction / Event ──────────────────────────────────
    if pages or comps:
        event_target = pages[0] if pages else comps[0]
        event_steps = [
            "User interacts with a DOM element (e.g. button click, form input)",
            "Browser sends the event payload to the server over the existing SignalR WebSocket",
            f"{Path(event_target['file_path']).name} receives the event in the corresponding C# event handler (e.g. OnClick, OnValidSubmit)",
        ]
        if services:
            event_steps.append(f"Handler calls {Path(services[0]['file_path']).name} to perform business logic or persist data")
        if data_ctx:
            event_steps.append(f"{Path(data_ctx[0]['file_path']).name} executes INSERT / UPDATE / DELETE via EF Core")
            event_steps.append("EF Core wraps the operation in a transaction and calls SaveChangesAsync()")
        event_steps.append("Component state is updated; StateHasChanged() may be called explicitly")
        event_steps.append("Blazor diffs the new render tree against the previous one")
        event_steps.append("Only the changed DOM nodes are pushed to the browser over SignalR")

        flows.append({
            "name": "User Interaction → State Update",
            "start": "Browser DOM Event",
            "end": "Browser DOM Update (SignalR diff)",
            "steps": event_steps,
            "description": "How a user event (click, form submit) travels through the Blazor circuit, triggers business logic, persists data, and updates the UI.",
        })

    # ── Flow 3: Dependency Injection / Service Wiring ─────────────────────
    if services or data_ctx:
        di_steps = [
            "ASP.NET Core DI container is configured in Program.cs (AddDbContext, AddScoped, AddSingleton, etc.)",
        ]
        if data_ctx:
            di_steps.append(f"{Path(data_ctx[0]['file_path']).name} is registered via builder.Services.AddDbContext<>() with the connection string from configuration")
        for svc in services[:3]:
            di_steps.append(f"{Path(svc['file_path']).name} is registered as a scoped or transient service")
        di_steps.append("When a Blazor component is instantiated, the DI container resolves all @inject dependencies")
        di_steps.append("Services are constructed with their own dependencies injected transitively")
        if data_ctx:
            di_steps.append("DbContext lifetime is scoped to the Blazor circuit (one per SignalR connection)")

        flows.append({
            "name": "Dependency Injection Wiring",
            "start": "Program.cs (Service Registration)",
            "end": "Component (@inject resolved)",
            "steps": di_steps,
            "description": "How services and DbContext are registered in the DI container and injected into Blazor components at runtime.",
        })

    # ── Flow 4: Component → Child Component data passing ──────────────────
    if comps and pages:
        param_steps = [
            f"Parent page (e.g. {Path(pages[0]['file_path']).name}) renders a child component via Razor markup",
            "Parent passes data to child via [Parameter] properties in the component's attribute syntax",
            f"Child component (e.g. {Path(comps[0]['file_path']).name}) receives parameters and renders its own Razor markup",
            "If a child needs to communicate back, it exposes an EventCallback<T> parameter",
            "Parent wires the EventCallback to a local method (e.g. @bind-Value or @onchange)",
            "Blazor reconciles the component tree top-down, only re-rendering components whose parameters changed",
        ]
        flows.append({
            "name": "Parent → Child Component Data Flow",
            "start": f"Page Component ({Path(pages[0]['file_path']).name})",
            "end": f"Child Component ({Path(comps[0]['file_path']).name})",
            "steps": param_steps,
            "description": "How data is passed down the Blazor component hierarchy using [Parameter] properties and EventCallback for upward communication.",
        })

    # ── Flow 5: SignalR Hub (if present) ──────────────────────────────────
    if hubs:
        hub_steps = [
            "Client JavaScript calls HubConnection.invoke() with a method name and payload",
            "SignalR routes the call to the matching method on the Hub class on the server",
            f"{Path(hubs[0]['file_path']).name} processes the message (validates, computes, or stores)",
        ]
        if services:
            hub_steps.append(f"Hub delegates business logic to injected {Path(services[0]['file_path']).name}")
        hub_steps.append("Hub calls Clients.All.SendAsync() / Clients.Caller.SendAsync() to push data back")
        hub_steps.append("Client-side JavaScript handler receives the broadcast and updates the UI")

        flows.append({
            "name": "SignalR Hub Message Flow",
            "start": "Browser (HubConnection.invoke)",
            "end": "Browser (HubConnection.on callback)",
            "steps": hub_steps,
            "description": f"Real-time bidirectional data flow through {Path(hubs[0]['file_path']).name}.",
        })

    return flows


def _generate_generic_dataflows(files: list[dict]) -> list[dict]:
    """Generate data flows for non-.NET projects using the import graph."""
    flows = []
    graph = _build_import_graph(files)
    entries = _find_entry_points(files, graph)

    for entry in entries[:3]:
        chain = _trace_flow(entry, graph)
        if len(chain) < 2:
            continue
        step_descs = []
        for fp in chain[1:]:
            step_descs.append(f"{Path(fp).name} — imported by {Path(chain[chain.index(fp) - 1]).name}")
        flows.append({
            "name": f"Flow from {Path(entry).name}",
            "start": Path(chain[0]).name,
            "end": Path(chain[-1]).name,
            "steps": step_descs,
            "description": f"Import chain starting at {entry}, traversing {len(chain)} modules.",
        })

    if not flows and files:
        chain = [f["file_path"] for f in files[:6]]
        flows.append({
            "name": "Module Listing",
            "start": Path(chain[0]).name,
            "end": Path(chain[-1]).name,
            "steps": [Path(fp).name for fp in chain[1:-1]],
            "description": "No resolvable import chain found; listing top-level files.",
        })

    return flows


def _classify_blazor_file(f: dict) -> str:
    """
    Return a logical Blazor layer name for a file based on path conventions.
    """
    p = f["file_path"].lower()
    name = Path(f["file_path"]).name.lower()
    ext = f["file_type"]

    if name in ("program.cs", "startup.cs"):
        return "Entry Point"
    if name in ("app.razor", "_imports.razor", "_host.cshtml"):
        return "App Shell"
    if "/pages/" in p or p.startswith("pages/"):
        return "Pages"
    if "/shared/" in p or p.startswith("shared/") or "/layout" in p:
        return "Shared / Layout"
    if "/components/" in p or p.startswith("components/"):
        return "Components"
    if "/services/" in p or p.startswith("services/"):
        return "Services"
    if "/data/" in p or p.startswith("data/") or "/dbcontext" in p:
        return "Data / DbContext"
    if "/models/" in p or p.startswith("models/") or "/entities/" in p:
        return "Models / Entities"
    if "/controllers/" in p or p.startswith("controllers/"):
        return "Controllers"
    if "/hubs/" in p or p.startswith("hubs/"):
        return "SignalR Hubs"
    if "/middleware/" in p or p.startswith("middleware/"):
        return "Middleware"
    if f.get("is_page"):
        return "Pages"
    if ext == ".razor":
        return "Components"
    if ext == ".cs":
        return "Services"
    # Fall back to top-level directory name
    parts = Path(f["file_path"]).parts
    return parts[0] if len(parts) > 1 else "Root"


def _is_dotnet_project(files: list[dict]) -> bool:
    return any(f["file_type"] in (".cs", ".razor") for f in files)


def _generate_component_diagram(files: list[dict], ai_insights: dict | None = None) -> str:
    """
    For Blazor/C# projects: group files by logical layer (Pages, Components,
    Services, Data, etc.) and draw dependency edges between layers.
    For other projects: group by top-level directory.
    """
    from collections import defaultdict
    lines = ["graph TB"]

    if _is_dotnet_project(files):
        # Blazor-aware grouping
        layer_files: defaultdict[str, list[str]] = defaultdict(list)
        for f in files:
            layer = _classify_blazor_file(f)
            layer_files[layer].append(f["file_path"])

        # Preferred display order
        layer_order = [
            "Entry Point", "App Shell", "Pages", "Shared / Layout",
            "Components", "Services", "Data / DbContext", "Models / Entities",
            "Controllers", "SignalR Hubs", "Middleware",
        ]
        remaining = [l for l in layer_files if l not in layer_order]
        ordered_layers = [l for l in layer_order if l in layer_files] + remaining

        layer_node: dict[str, str] = {}
        for layer in ordered_layers:
            fps = layer_files[layer]
            node_id = _sanitize_mermaid_id(layer)
            layer_node[layer] = node_id
            file_names = ", ".join(Path(p).name for p in fps[:3])
            if len(fps) > 3:
                file_names += f" +{len(fps) - 3} more"
            safe_label = f"{layer}\\n({file_names})".replace('"', "'")
            lines.append(f'  {node_id}["{safe_label}"]')

        # Edges from import graph between layers
        graph = _build_import_graph(files)
        file_to_layer = {fp: layer for layer, fps in layer_files.items() for fp in fps}
        edges_added: set[tuple[str, str]] = set()
        for src_file, deps in graph.items():
            src_layer = file_to_layer.get(src_file)
            for dep_file in deps:
                dst_layer = file_to_layer.get(dep_file)
                if src_layer and dst_layer and src_layer != dst_layer:
                    edge = (layer_node[src_layer], layer_node[dst_layer])
                    if edge not in edges_added:
                        lines.append(f"  {edge[0]} --> {edge[1]}")
                        edges_added.add(edge)

    else:
        # Generic: group by top-level directory
        dir_groups: defaultdict[str, list[str]] = defaultdict(list)
        for f in files:
            p = Path(f["file_path"])
            top = p.parts[0] if len(p.parts) > 1 else "root"
            dir_groups[top].append(f["file_path"])

        dir_node: dict[str, str] = {}
        for grp in sorted(dir_groups):
            node_id = _sanitize_mermaid_id(grp)
            dir_node[grp] = node_id
            file_names = ", ".join(Path(p).name for p in dir_groups[grp][:3])
            if len(dir_groups[grp]) > 3:
                file_names += f" +{len(dir_groups[grp]) - 3} more"
            safe_label = f"{grp}\\n({file_names})".replace('"', "'")
            lines.append(f'  {node_id}["{safe_label}"]')

        if ai_insights and "main_components" in ai_insights:
            for component in ai_insights.get("main_components", [])[:5]:
                comp_id = _sanitize_mermaid_id(component)
                if comp_id not in dir_node.values():
                    lines.append(f'  {comp_id}["{component.replace(chr(34), chr(39))}"]')

        graph = _build_import_graph(files)
        file_to_group = {fp: grp for grp, fps in dir_groups.items() for fp in fps}
        edges_added: set[tuple[str, str]] = set()
        for src_file, deps in graph.items():
            src_grp = file_to_group.get(src_file)
            for dep_file in deps:
                dst_grp = file_to_group.get(dep_file)
                if src_grp and dst_grp and src_grp != dst_grp:
                    edge = (dir_node[src_grp], dir_node[dst_grp])
                    if edge not in edges_added:
                        lines.append(f"  {edge[0]} --> {edge[1]}")
                        edges_added.add(edge)

    if len(lines) == 1:
        lines.append('  A["No source files found"]')

    return "\n".join(lines)


def _generate_class_diagram(files: list[dict], ai_insights: dict | None = None) -> str:
    """
    Build a class/component diagram grouped by file.
    For .cs files: shows classes/interfaces.
    For .razor files: shows the component name and its parameters.
    Draw dependency arrows between modules via the import graph.
    """
    lines = ["classDiagram"]

    file_symbols: dict[str, list[str]] = {}
    class_count = 0
    for f in files[:25]:
        if class_count >= 30:
            break
        symbols = []
        if f["file_type"] == ".razor":
            # Component name = stem
            comp_name = re.sub(r'[^a-zA-Z0-9_]', '_', Path(f["file_path"]).stem)
            if comp_name:
                symbols = [comp_name]
                lines.append(f"  class {comp_name} {{")
                if f.get("is_page"):
                    lines.append("    <<Page>>")
                else:
                    lines.append("    <<Component>>")
                for sym in f.get("exported_items", [])[:4]:
                    safe = re.sub(r'[^a-zA-Z0-9_]', '', sym)
                    if safe:
                        lines.append(f"    +{safe}()")
                lines.append("  }")
                class_count += 1
        else:
            for symbol in f.get("exported_items", [])[:5]:
                if class_count >= 30:
                    break
                safe = re.sub(r'[^a-zA-Z0-9_]', '', symbol)
                if safe:
                    symbols.append(safe)
                    class_count += 1
            if symbols:
                module_name = re.sub(r'[^a-zA-Z0-9_]', '_', Path(f["file_path"]).stem)
                if not module_name[0:1].isalpha():
                    module_name = "M_" + module_name
                lines.append(f"  class {module_name} {{")
                for sym in symbols:
                    lines.append(f"    +{sym}()")
                lines.append("  }")
        if symbols:
            file_symbols[f["file_path"]] = symbols

    # Draw relationships via import graph
    graph = _build_import_graph(files)

    def module_name_for(fp: str) -> str:
        f_obj = next((x for x in files if x["file_path"] == fp), None)
        if f_obj and f_obj["file_type"] == ".razor":
            return re.sub(r'[^a-zA-Z0-9_]', '_', Path(fp).stem)
        name = re.sub(r'[^a-zA-Z0-9_]', '_', Path(fp).stem)
        return name if name[0:1].isalpha() else "M_" + name

    edges_added: set[tuple[str, str]] = set()
    for src_file, deps in graph.items():
        if src_file not in file_symbols:
            continue
        src_mod = module_name_for(src_file)
        for dep_file in deps:
            if dep_file not in file_symbols:
                continue
            dst_mod = module_name_for(dep_file)
            if src_mod != dst_mod:
                edge = (src_mod, dst_mod)
                if edge not in edges_added:
                    lines.append(f"  {src_mod} --> {dst_mod}")
                    edges_added.add(edge)

    if len(lines) == 1:
        lines.append("  class NoExportedSymbols")

    return "\n".join(lines)


def _generate_dependency_diagram(files: list[dict], ai_insights: dict | None = None) -> str:
    """
    Draw a file-level dependency graph using the resolved import graph.
    Only nodes that participate in at least one edge are shown.
    """
    lines = ["graph LR"]
    graph = _build_import_graph(files)

    nodes_added: set[str] = set()
    edges: list[str] = []
    edge_count = 0

    for src_file, deps in graph.items():
        if not deps or edge_count >= 30:
            continue
        src_id = _sanitize_mermaid_id(src_file)
        src_label = Path(src_file).name.replace('"', "'")
        for dep_file in deps:
            if edge_count >= 30:
                break
            dst_id = _sanitize_mermaid_id(dep_file)
            dst_label = Path(dep_file).name.replace('"', "'")
            if src_id == dst_id:
                continue
            if src_id not in nodes_added:
                lines.append(f'  {src_id}["{src_label}"]')
                nodes_added.add(src_id)
            if dst_id not in nodes_added:
                lines.append(f'  {dst_id}["{dst_label}"]')
                nodes_added.add(dst_id)
            edges.append(f"  {src_id} --> {dst_id}")
            edge_count += 1

    lines.extend(edges)

    if len(nodes_added) == 0:
        lines.append('  A["No internal dependencies found"]')
        lines.append('  B["All imports are external libraries"]')
        lines.append("  A --> B")

    return "\n".join(lines)


def _get_edge_label(src_layer: str, dst_layer: str) -> str:
    """Return a meaningful edge label based on the source and destination layer."""
    label_map: dict[tuple[str, str], str] = {
        ("Entry Point",        "App Shell"):           "starts",
        ("Entry Point",        "Services"):            "registers DI",
        ("Entry Point",        "Middleware"):          "configures",
        ("App Shell",          "Pages"):               "routes to",
        ("App Shell",          "Shared / Layout"):     "renders",
        ("Shared / Layout",    "Pages"):               "hosts",
        ("Shared / Layout",    "Components"):          "renders",
        ("Pages",              "Components"):          "contains",
        ("Pages",              "Services"):            "@inject",
        ("Pages",              "Shared / Layout"):     "uses",
        ("Components",         "Services"):            "@inject",
        ("Components",         "Components"):          "renders",
        ("Services",           "Data / DbContext"):    "queries",
        ("Services",           "Models / Entities"):   "maps",
        ("Data / DbContext",   "Models / Entities"):   "returns",
        ("Controllers",        "Services"):            "calls",
        ("SignalR Hubs",       "Services"):            "uses",
        ("Middleware",         "App Shell"):           "passes to",
    }
    return label_map.get((src_layer, dst_layer), "uses")


def _generate_blazor_flowchart(files: list[dict], ai_insights: dict | None) -> str:
    """
    Generate a detailed Mermaid flowchart for Blazor Server / ASP.NET Core projects.
    Uses subgraphs for each logical layer with labelled edges.
    """
    from collections import defaultdict

    # Build per-layer file lists
    layer_files: defaultdict[str, list[dict]] = defaultdict(list)
    for f in files:
        layer = _classify_blazor_file(f)
        layer_files[layer].append(f)

    # Layer → subgraph id mapping (only include layers that have files)
    layer_sg_id: dict[str, str] = {}
    for layer in layer_files:
        layer_sg_id[layer] = _sanitize_mermaid_id("sg_" + layer)

    # Node counter
    node_counter = [0]
    node_ids: dict[str, str] = {}

    def nid(fp: str) -> str:
        if fp not in node_ids:
            node_ids[fp] = f"n{node_counter[0]}"
            node_counter[0] += 1
        return node_ids[fp]

    def node_label(f: dict) -> str:
        stem = Path(f["file_path"]).stem
        label = stem.replace('"', "'")
        if f.get("is_page"):
            # Find @page directive to add route
            return label
        return label

    lines = ["flowchart TD"]

    # Check if it's a Blazor Server project (has SignalR / circuit concept)
    has_hub = bool(layer_files.get("SignalR Hubs"))
    has_data = bool(layer_files.get("Data / DbContext"))
    has_services = bool(layer_files.get("Services"))

    # --- Browser layer (always present for web apps) ---
    lines.append("")
    lines.append("  subgraph sg_browser[\"Browser\"]")
    lines.append("    direction LR")
    lines.append("    n_user[\"User Action\"]")
    lines.append("  end")

    # --- Blazor circuit layer ---
    circuit_layers = ["Entry Point", "App Shell", "Shared / Layout", "Pages", "Components"]
    circuit_layers_present = [l for l in circuit_layers if l in layer_files]

    if circuit_layers_present:
        lines.append("")
        lines.append("  subgraph sg_circuit[\"Blazor Server Circuit\"]")
        lines.append("    direction TB")
        for layer in circuit_layers_present:
            sg = layer_sg_id[layer]
            safe_label = layer.replace('"', "'")
            lines.append(f"    subgraph {sg}[\"{safe_label}\"]")
            for f in layer_files[layer][:6]:
                n = nid(f["file_path"])
                lbl = node_label(f)
                if f.get("is_page"):
                    lines.append(f"      {n}([\"{lbl}\"])")
                elif f["file_type"] == ".razor":
                    lines.append(f"      {n}[\"{lbl}\"]")
                else:
                    lines.append(f"      {n}[\"{lbl}\"]")
            lines.append("    end")
        lines.append("  end")

    # --- Middleware layer ---
    if "Middleware" in layer_files:
        lines.append("")
        sg = layer_sg_id["Middleware"]
        lines.append(f"  subgraph {sg}[\"Middleware\"]")
        for f in layer_files["Middleware"][:4]:
            lines.append(f"    {nid(f['file_path'])}[\"{node_label(f)}\"]")
        lines.append("  end")

    # --- Service layer ---
    if has_services:
        lines.append("")
        sg = layer_sg_id["Services"]
        lines.append(f"  subgraph {sg}[\"Service Layer\"]")
        for f in layer_files["Services"][:8]:
            lines.append(f"    {nid(f['file_path'])}[\"{node_label(f)}\"]")
        lines.append("  end")

    # --- SignalR Hubs ---
    if has_hub:
        lines.append("")
        sg = layer_sg_id["SignalR Hubs"]
        lines.append(f"  subgraph {sg}[\"SignalR Hubs\"]")
        for f in layer_files["SignalR Hubs"][:4]:
            lines.append(f"    {nid(f['file_path'])}[\"{node_label(f)}\"]")
        lines.append("  end")

    # --- Controllers ---
    if "Controllers" in layer_files:
        lines.append("")
        sg = layer_sg_id["Controllers"]
        lines.append(f"  subgraph {sg}[\"Controllers\"]")
        for f in layer_files["Controllers"][:6]:
            lines.append(f"    {nid(f['file_path'])}[\"{node_label(f)}\"]")
        lines.append("  end")

    # --- Data layer ---
    if has_data or "Models / Entities" in layer_files:
        lines.append("")
        lines.append("  subgraph sg_data[\"Data Layer\"]")
        lines.append("    direction LR")
        for f in layer_files.get("Data / DbContext", [])[:4]:
            lines.append(f"    {nid(f['file_path'])}[\"{node_label(f)}\"]")
        for f in layer_files.get("Models / Entities", [])[:5]:
            lines.append(f"    {nid(f['file_path'])}[\"{node_label(f)}\"]")
        if has_data:
            lines.append("    n_db[(\"Database\")]")
        lines.append("  end")

    # --- Edges ---
    lines.append("")

    # Browser → first entry or app shell
    first_circuit = None
    for layer in ["Entry Point", "App Shell"]:
        if layer in layer_files:
            first_circuit = nid(layer_files[layer][0]["file_path"])
            break

    if first_circuit:
        lines.append(f"  n_user -->|\"HTTP / SignalR\"| {first_circuit}")

    # Import-graph edges between files with labels
    graph = _build_import_graph(files)
    file_to_layer = {f["file_path"]: _classify_blazor_file(f) for f in files}
    edges_added: set[tuple[str, str]] = set()
    edge_count = 0

    for src_file, deps in graph.items():
        if src_file not in node_ids:
            continue
        src_layer = file_to_layer.get(src_file, "")
        for dep_file in deps:
            if dep_file not in node_ids:
                continue
            dst_layer = file_to_layer.get(dep_file, "")
            src_id = nid(src_file)
            dst_id = nid(dep_file)
            edge = (src_id, dst_id)
            if edge not in edges_added and edge_count < 35:
                label = _get_edge_label(src_layer, dst_layer)
                lines.append(f"  {src_id} -->|\"{label}\"| {dst_id}")
                edges_added.add(edge)
                edge_count += 1

    # DbContext → Database node
    if has_data:
        for f in layer_files.get("Data / DbContext", [])[:1]:
            lines.append(f"  {nid(f['file_path'])} -->|\"executes SQL\"| n_db")

    return "\n".join(lines)


def _generate_generic_flowchart(files: list[dict], ai_insights: dict | None) -> str:
    """Generic flowchart for non-.NET projects: BFS from entry points with labelled edges."""
    lines = ["flowchart TD"]

    graph = _build_import_graph(files)
    entries = _find_entry_points(files, graph)

    node_ids: dict[str, str] = {}
    node_counter = [0]

    def get_node_id(fp: str) -> str:
        if fp not in node_ids:
            node_ids[fp] = f"n{node_counter[0]}"
            node_counter[0] += 1
        return node_ids[fp]

    all_edges: list[tuple[str, str]] = []
    visited_global: set[str] = set()

    for entry in entries[:2]:
        chain = _trace_flow(entry, graph, max_depth=10)
        for fp in chain:
            visited_global.add(fp)
        for i in range(len(chain) - 1):
            all_edges.append((chain[i], chain[i + 1]))

    for fp in visited_global:
        nid_val = get_node_id(fp)
        label = Path(fp).name.replace('"', "'")
        if fp in entries:
            lines.append(f'  {nid_val}(["{label}"])')
        else:
            lines.append(f'  {nid_val}["{label}"]')

    seen_edges: set[tuple[str, str]] = set()
    for src, dst in all_edges:
        src_id = get_node_id(src)
        dst_id = get_node_id(dst)
        if (src_id, dst_id) not in seen_edges:
            lines.append(f"  {src_id} --> {dst_id}")
            seen_edges.add((src_id, dst_id))

    if ai_insights and "architecture_pattern" in ai_insights and visited_global:
        pattern = ai_insights["architecture_pattern"].replace('"', "'")
        first_entry_id = get_node_id(entries[0])
        lines.append(f'  arch_pattern["{pattern} Architecture"]')
        lines.append(f"  arch_pattern --> {first_entry_id}")

    if len(lines) == 1:
        for idx, f in enumerate(files[:8]):
            nid_val = f"fb{idx}"
            label = Path(f["file_path"]).name.replace('"', "'")
            lines.append(f'  {nid_val}["{label}"]')
        for idx in range(min(len(files), 8) - 1):
            lines.append(f"  fb{idx} --> fb{idx + 1}")

    return "\n".join(lines)


def _generate_flowchart_diagram(files: list[dict], ai_insights: dict | None = None) -> str:
    if not files:
        return "flowchart TD\n  start([No source files found])\n  start --> end_node([Upload a codebase])"

    if _is_dotnet_project(files):
        return _generate_blazor_flowchart(files, ai_insights)
    return _generate_generic_flowchart(files, ai_insights)


def _sanitize_mermaid_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", value)
    return cleaned if cleaned and cleaned[0].isalpha() else f"n_{cleaned}"
