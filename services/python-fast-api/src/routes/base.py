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
}

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
            if d not in {".git", "node_modules", "__pycache__", "dist", "build", ".venv", "venv"}
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

            imports = _extract_imports(content)
            exports = _extract_exports(content, ext)
            results.append(
                {
                    "file_path": rel_path,
                    "file_type": ext,
                    "imports": sorted(imports),
                    "exported_items": sorted(exports),
                    "line_count": len(content.splitlines()),
                }
            )

    return results


def _extract_imports(content: str) -> set[str]:
    found: set[str] = set()
    for match in re.findall(r"(?:from|import)\s+([\w./-]+)", content):
        found.add(match)
    for match in re.findall(r"import\s+.+?\s+from\s+[\"']([^\"']+)[\"']", content):
        found.add(match)
    return found


def _extract_exports(content: str, ext: str) -> set[str]:
    found: set[str] = set()

    if ext == ".py":
        for name in re.findall(r"^\s*(?:def|class)\s+(\w+)", content, flags=re.MULTILINE):
            found.add(name)
        return found

    for name in re.findall(r"export\s+(?:default\s+)?(?:class|function|const|let|var)?\s*(\w+)", content):
        if name:
            found.add(name)
    return found


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


def _generate_dataflows(files: list[dict], ai_insights: dict | None) -> list[dict]:
    """Generate data flow paths, optionally using AI insights."""
    flows = []
    
    if ai_insights and "data_flows" in ai_insights:
        # Use AI-identified flows
        for flow in ai_insights.get("data_flows", [])[:3]:
            if isinstance(flow, dict):
                flows.append({
                    "name": flow.get("name", "AI-Identified Flow"),
                    "start": flow.get("start", files[0]["file_path"] if files else "entry"),
                    "end": flow.get("end", files[-1]["file_path"] if files else "exit"),
                    "steps": flow.get("steps", []),
                    "description": flow.get("description", ""),
                })
            else:
                # flow is a string
                flows.append({
                    "name": "Data Flow",
                    "start": files[0]["file_path"] if files else "entry",
                    "end": files[-1]["file_path"] if files else "exit",
                    "steps": [],
                    "description": str(flow),
                })
    
    # Always add a primary flow based on file structure
    if files:
        flows.append({
            "name": "Primary Data Flow",
            "start": files[0]["file_path"],
            "end": files[-1]["file_path"],
            "steps": [f["file_path"] for f in files[1:6]],
            "description": f"Flow from {files[0]['file_path']} to {files[-1]['file_path']}",
        })
    else:
        flows.append({
            "name": "Primary Data Flow",
            "start": "entry",
            "end": "exit",
            "steps": [],
            "description": "No files to analyze",
        })
    
    return flows


def _generate_component_diagram(files: list[dict], ai_insights: dict | None = None) -> str:
    lines = ["graph TB"]
    nodes = []
    
    # Add AI-identified main components if available
    if ai_insights and "main_components" in ai_insights:
        for component in ai_insights.get("main_components", [])[:10]:
            comp_id = _sanitize_mermaid_id(component)
            safe_label = component.replace('"', '')
            lines.append(f'  {comp_id}["{safe_label}"]')
            nodes.append(comp_id)
    
    # Add file-based components (limit to avoid huge graphs)
    for idx, f in enumerate(files[:20]):
        if len(nodes) >= 20:
            break
        node = _sanitize_mermaid_id(f["file_path"])
        label = Path(f["file_path"]).name
        lines.append(f'  {node}["{label}"]')
        nodes.append(node)
    
    # Add some connections between nodes
    for i in range(min(len(nodes) - 1, 10)):
        lines.append(f"  {nodes[i]} --> {nodes[i + 1]}")
    
    return "\n".join(lines)


def _generate_class_diagram(files: list[dict], ai_insights: dict | None = None) -> str:
    lines = ["classDiagram"]
    
    # Add classes from exported items
    class_count = 0
    for f in files[:15]:
        for symbol in f.get("exported_items", [])[:3]:
            if class_count >= 15:
                break
            safe_symbol = re.sub(r'[^a-zA-Z0-9_]', '', symbol)
            if safe_symbol:
                lines.append(f"  class {safe_symbol}")
                class_count += 1
        if class_count >= 15:
            break
    
    # Add some relationships if we have AI insights
    if ai_insights and "main_components" in ai_insights and len(lines) > 1:
        components = ai_insights.get("main_components", [])[:3]
        if len(components) > 1:
            for i in range(len(components) - 1):
                src = re.sub(r'[^a-zA-Z0-9_]', '', components[i])
                dst = re.sub(r'[^a-zA-Z0-9_]', '', components[i + 1])
                if src and dst:
                    lines.append(f"  {src} --> {dst}")
    
    if len(lines) == 1:
        lines.append("  class NoExports")
    
    return "\n".join(lines)


def _generate_dependency_diagram(files: list[dict], ai_insights: dict | None = None) -> str:
    lines = ["graph LR"]
    nodes_added: set[str] = set()
    edges: set[str] = set()
    
    # Add file-based dependencies (limited)
    edge_count = 0
    for f in files[:20]:
        if edge_count >= 25:
            break
        src = _sanitize_mermaid_id(f["file_path"])
        src_label = Path(f["file_path"]).name
        
        for imp in f.get("imports", [])[:2]:
            if edge_count >= 25:
                break
            dst = _sanitize_mermaid_id(imp)
            if src and dst and src != dst:
                if src not in nodes_added:
                    lines.append(f'  {src}["{src_label}"]')
                    nodes_added.add(src)
                if dst not in nodes_added:
                    lines.append(f'  {dst}["{dst[:20]}"]')
                    nodes_added.add(dst)
                edges.add(f"  {src} --> {dst}")
                edge_count += 1
    
    lines.extend(sorted(edges))
    if len(lines) == 1:
        lines.append("  A[No dependencies]")
        lines.append("  B[Check source files]")
        lines.append("  A --> B")

    return "\n".join(lines)


def _generate_flowchart_diagram(files: list[dict], ai_insights: dict | None = None) -> str:
    lines = ["flowchart TD"]

    if not files:
        lines.append("  start([No source files found])")
        lines.append("  start --> end([Upload a codebase])")
        return "\n".join(lines)

    # Create a flow from files
    chain = files[:10]
    for idx, file_info in enumerate(chain):
        node_id = f"n{idx}"
        label = Path(file_info["file_path"]).name
        label = label.replace('"', '')
        lines.append(f'  {node_id}["{label}"]')

    for idx in range(len(chain) - 1):
        lines.append(f"  n{idx} --> n{idx + 1}")

    # Add architecture pattern if available
    if ai_insights and "architecture_pattern" in ai_insights and len(chain) > 0:
        pattern = ai_insights.get("architecture_pattern", "Unknown")
        pattern = pattern.replace('"', '').replace("'", '')
        lines.append(f'  pattern["{pattern} Pattern"]')
        lines.append("  n0 --> pattern")

    return "\n".join(lines)


def _sanitize_mermaid_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", value)
    return cleaned if cleaned and cleaned[0].isalpha() else f"n_{cleaned}"
