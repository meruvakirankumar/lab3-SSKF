# Load .env and run the service-config-manager locally
Get-Content "$PSScriptRoot\.env" | ForEach-Object {
    if ($_ -match '^([^#][^=]*)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
    }
}

Set-Location "$PSScriptRoot"
pip install -q -r requirements.txt
python src/main.py
