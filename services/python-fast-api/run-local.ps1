# Load .env and run the FastAPI backend locally
Get-Content "$PSScriptRoot\.env" | ForEach-Object {
    if ($_ -match '^([^#][^=]*)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
    }
}

Set-Location "$PSScriptRoot"
uv sync
uv run python src/main.py
