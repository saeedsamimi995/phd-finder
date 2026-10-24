$ErrorActionPreference = "Stop"
Set-Location -LiteralPath "D:\Projects\phd finder"

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        .\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
    }
}

$python = ".\.venv\Scripts\python.exe"
& $python -m phd_finder daily
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Daily run finished (auto_apply is on)."
Write-Host "  - Email openings: sent when config/gmail_credentials.json is set up."
Write-Host "  - Portal openings: packages in output\packages\<id> — submit the form, then mark-applied."
Write-Host "Table: output\daily_$(Get-Date -Format yyyy-MM-dd).xlsx"
