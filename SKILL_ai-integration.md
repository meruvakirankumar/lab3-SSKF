# Skill: OpenAI/OpenRouter API Integration

Expertise in integrating and optimizing AI-powered code analysis using OpenAI and OpenRouter APIs, including authentication, prompt engineering, error handling, and Azure deployment configuration.

## Overview

The Code Architecture Analyzer integrates with OpenAI/OpenRouter to enhance diagram generation with AI insights. This includes:
- API routing based on key format
- Prompt engineering for architecture analysis
- JSON response parsing
- Error handling and graceful degradation
- Azure OpenAI deployment support

---

## API Authentication & Routing

### Key Format Detection
```python
# In services/python-fast-api/src/routes/base.py

OPENAPI_KEY = os.environ.get("OPENAPI_KEY")  # From config/openapi-key.env
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION")

def _get_openai_analysis(files: list[dict]) -> dict | None:
    if not OPENAPI_KEY:
        logger.warning("OpenAPI key not configured")
        return None
    
    # Detect API provider by key prefix
    is_openrouter = OPENAPI_KEY.startswith("sk-or-")
    is_azure = OPENAPI_KEY.startswith("sk-") and AZURE_OPENAI_DEPLOYMENT
    
    if is_openrouter:
        api_url = "https://openrouter.ai/api/v1/chat/completions"
        model_name = "openai/gpt-4o-mini"
    elif is_azure:
        api_url = f"https://{AZURE_OPENAI_DEPLOYMENT}.openai.azure.com/..."
        model_name = "gpt-5.4"  # From Azure
    else:
        # Default OpenAI
        api_url = "https://api.openai.com/v1/chat/completions"
        model_name = "gpt-4o-mini"
    
    return api_url, model_name
```

### Authentication Headers
```python
headers = {
    "Authorization": f"Bearer {OPENAPI_KEY}",
    "Content-Type": "application/json",
}

# OpenRouter-specific headers
if is_openrouter:
    headers["HTTP-Referer"] = "https://local.code-architecture-analyzer"
    headers["X-Title"] = "Code Architecture Analyzer"

# Azure-specific headers
if is_azure:
    headers["api-key"] = OPENAPI_KEY
    # API key goes in header, not Bearer token
```

---

## Prompt Engineering

### Architecture Analysis Prompt
```python
def _create_analysis_prompt(files: list[dict]) -> str:
    """Create a prompt that elicits structured JSON insights from the codebase."""
    
    code_summary = _prepare_code_summary(files)
    
    prompt = f"""Analyze this codebase architecture and provide insights:

{code_summary}

Please provide a JSON response with:
1. "architecture_pattern": The main architecture pattern (e.g., MVC, microservices, monolithic, MVVM, etc.)
2. "main_components": List of 3-5 main architectural components (names only)
3. "key_responsibilities": Object mapping each component to its primary responsibility
4. "data_flows": List of primary data flow paths with format: 
   {{"name": "Flow Name", "start": "Component", "end": "Component", "steps": ["step1", "step2"]}}
5. "dependencies": List of major external dependencies (libraries, frameworks)
6. "technologies": List of detected technologies/frameworks (e.g., "React", "FastAPI", "PostgreSQL")
7. "quality_assessment": Brief (1-2 sentence) assessment of code organization and maintainability

Respond ONLY with valid JSON (no markdown, no explanation). Example structure:
{{
  "architecture_pattern": "REST API + React Frontend",
  "main_components": ["API Server", "File Scanner", "Diagram Generator", "Frontend"],
  ...
}}"""
    
    return prompt
```

### Best Practices for Prompts
1. **Be Specific:** Tell AI exactly what JSON structure to return
2. **Examples:** Include example responses so AI knows format
3. **Constraints:** Limit output (number of components, items per list)
4. **Language:** Use clear, non-ambiguous language
5. **Escape:** Properly escape quote characters in JSON strings

---

## API Request Payload

### Full Request Structure
```python
payload = {
    "model": model_name,  # e.g., "gpt-4o-mini" or "openai/gpt-4o-mini"
    "messages": [
        {
            "role": "user",
            "content": prompt,
        }
    ],
    "temperature": 0.7,  # Balanced: not too creative, not too strict
    "max_tokens": 2000,  # Limit response length
}

# Azure-specific: Add deployment and API version
if AZURE_OPENAI_DEPLOYMENT:
    payload["deployment"] = AZURE_OPENAI_DEPLOYMENT
if AZURE_OPENAI_API_VERSION:
    payload["api_version"] = AZURE_OPENAI_API_VERSION

# Send request
response = requests.post(
    api_url,
    json=payload,
    headers=headers,
    timeout=(OPENAI_CONNECT_TIMEOUT_SECONDS, OPENAI_TIMEOUT_SECONDS),  # (connection, read)
)
```

### Temperature & Tokens
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `temperature` | 0.7 | Balanced creativity; consistent architecture analysis |
| `max_tokens` | 2000 | Enough for JSON response, prevents runaway generation |
| `top_p` | - | Not set; defaults to 1.0 (use all tokens) |
| `frequency_penalty` | - | Not set; not needed for this use case |

---

## Response Parsing

### Success Path
```python
try:
    response = requests.post(api_url, json=payload, headers=headers, timeout=...)
    
    if response.status_code == 200:
        result = response.json()
        
        # Extract message content
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        # Parse JSON from response
        try:
            insights = json.loads(content)
            logger.info("✓ OpenAI analysis completed successfully")
            return insights
        
        except json.JSONDecodeError:
            logger.warning("⚠ Failed to parse OpenAI response as JSON")
            # Try extracting JSON from response if wrapped in markdown
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                insights = json.loads(json_match.group())
                return insights
            return None
    
    else:
        handle_error(response.status_code, response.text)

except requests.exceptions.RequestException as exc:
    logger.warning(f"❌ Network error calling OpenAI: {exc}")
    return None
```

### Response Structure
```json
{
  "choices": [
    {
      "message": {
        "content": "{...JSON HERE...}"  // String containing JSON object
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 567,
    "total_tokens": 1801
  }
}
```

---

## Error Handling & Recovery

### Authorization Errors (401, 403)
```python
if response.status_code in {401, 403}:
    global OPENAI_DISABLED
    OPENAI_DISABLED = True  # Prevent retries
    logger.error(f"🔐 OpenAI auth failed: {response.status_code}")
    logger.error("Invalid API key or insufficient permissions")
    return None  # Graceful fallback

# Never retry auth errors; set flag to disable AI features
```

### Rate Limiting (429)
```python
if response.status_code == 429:
    logger.warning("⏱️ OpenAI rate limit hit; analysis will proceed without AI")
    # Don't disable permanently; retry in next request
    return None
```

### Timeout Handling
```python
try:
    response = requests.post(..., timeout=(2, 5))  # 2s connect, 5s read
except requests.exceptions.ReadTimeout:
    logger.warning(f"⏱️ OpenAI timeout after {OPENAI_TIMEOUT_SECONDS}s")
    return None
except requests.exceptions.ConnectTimeout:
    logger.warning(f"⏱️ OpenAI connection timeout after {OPENAI_CONNECT_TIMEOUT_SECONDS}s")
    return None
```

### Network Errors
```python
except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
    logger.warning(f"🌐 Network error: {exc}")
    OPENAI_DISABLED = True
    return None
```

### Graceful Degradation
```python
def _store_analysis(project_id: str, files: list[dict]) -> None:
    # Try AI analysis, but don't fail the entire pipeline
    ai_insights = None
    if OPENAPI_KEY and len(files) <= OPENAI_MAX_FILES:
        ai_insights = _get_openai_analysis(files)
        if ai_insights:
            INSIGHTS_DB[project_id] = ai_insights
            logger.info("✓ AI insights stored")
        else:
            logger.info("⚠ AI analysis unavailable; using local patterns only")
    
    # Generate diagrams regardless of AI availability
    diagrams = {
        "component": _generate_component_diagram(files, ai_insights),  # ai_insights can be None
        "class": _generate_class_diagram(files, ai_insights),
        # ... etc
    }
    
    # Analysis completes successfully even if AI fails
```

---

## Performance Tuning

### File Limit Strategy
```python
OPENAI_MAX_FILES = int(os.environ.get("ANALYZER_OPENAI_MAX_FILES", "120"))

if len(files) > OPENAI_MAX_FILES:
    logger.info(f"Skipping OpenAI: {len(files)} files exceed limit {OPENAI_MAX_FILES}")
    # Proceed with local analysis only
    ai_insights = None
```

### Token Limits
```
Budget: ~2000 tokens max
Split:
  - Prompt: ~1000 tokens (code summary)
  - Response: ~1000 tokens (JSON insights)

Code summary strategy:
  - Show first 20 files only
  - Show top 3 imports/exports per file
  - Group by language
```

### Metrics to Monitor
```python
analysis_start = time.perf_counter()
ai_insights = _get_openai_analysis(files)
ai_ms = int((time.perf_counter() - analysis_start) * 1000)

logger.info(f"AI analysis: {ai_ms}ms for {len(files)} files")
# Target: <5000ms for analysis to complete "quickly"
```

---

## Azure OpenAI Deployment

### Configuration
```bash
# config/openapi-key.env
OPENAPI_KEY=sk-...                              # Azure key format
AZURE_OPENAI_DEPLOYMENT=gpt-5.4                 # Deployment name
AZURE_OPENAI_API_VERSION=2024-12-01-preview     # API version
```

### Request Differences
```python
# Standard OpenAI
{
  "model": "gpt-4o-mini",
  "messages": [...],
}

# Azure OpenAI
{
  "model": "gpt-4o-mini",
  "deployment": "gpt-5.4",        # Added
  "api_version": "2024-12-01-preview",  # Added
  "messages": [...],
}
```

### Header Changes
```python
if is_azure:
    headers = {
        "api-key": OPENAPI_KEY,  # Use api-key header
        "Content-Type": "application/json",
    }
    # No "Authorization: Bearer" header for Azure
```

---

## Testing OpenAI Integration

### Unit Test (Mock)
```python
def test_get_openai_analysis_success(mocker):
    # Mock successful API response
    mock_response = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "architecture_pattern": "REST API",
                    "main_components": ["API", "DB"],
                    ...
                })
            }
        }]
    }
    
    mocker.patch("requests.post", return_value=Mock(
        status_code=200,
        json=lambda: mock_response
    ))
    
    mock_files = [{"file_path": "api.py", ...}]
    result = _get_openai_analysis(mock_files)
    
    assert result["architecture_pattern"] == "REST API"

def test_get_openai_analysis_auth_failure(mocker):
    mocker.patch("requests.post", return_value=Mock(status_code=401))
    
    result = _get_openai_analysis([])
    assert result is None
    assert OPENAI_DISABLED is True  # Should disable further attempts

def test_get_openai_analysis_timeout(mocker):
    mocker.patch("requests.post", side_effect=requests.exceptions.Timeout())
    
    result = _get_openai_analysis([])
    assert result is None
```

### Integration Test
```python
def test_full_pipeline_with_ai(small_codebase_zip):
    # Upload and analyze a real small codebase
    project = upload_codebase(small_codebase_zip, "Test Project")
    analyze_project(project["id"])
    
    insights = get_insights(project["id"])
    assert insights is not None
    assert "architecture_pattern" in insights
    assert "main_components" in insights
```

### Manual Testing
```bash
# Test with live API
curl -X POST https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAPI_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Analyze: ..."}],
    "temperature": 0.7
  }'
```

---

## Cost Optimization

### Request Strategies
1. **Batch Analysis:** Call API once per project, not per diagram
2. **File Limit:** Cap at 120 files to keep prompt <1000 tokens
3. **Caching:** Store insights in `INSIGHTS_DB` (per project, one call)
4. **Fallback:** Always have local diagram fallback

### Token Usage Estimates
```
Small project (20 files):    ~400 tokens → ~$0.0002
Medium project (100 files):  ~1000 tokens → ~$0.0005
Large project (250 files):   ~2000 tokens (capped) → ~$0.001
```

---

## References
- [OpenAI API Docs](https://platform.openai.com/docs/api-reference)
- [OpenRouter Docs](https://openrouter.ai/docs)
- [Azure OpenAI Docs](https://learn.microsoft.com/en-us/azure/ai-services/openai/)
- Code: `services/python-fast-api/src/routes/base.py` (`_get_openai_analysis`, `_prepare_code_summary`)
- Config: `config/openapi-key.env`
