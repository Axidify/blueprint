# Blueprint setup. Run setup.cmd (double-click) or: powershell -ExecutionPolicy Bypass -File setup.ps1
# Safe to run again at any time: it only installs what is missing.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
Write-Host ""
Write-Host "Blueprint setup" -ForegroundColor Cyan
Write-Host "------------------"

# 1. Python
$python = $null
foreach ($cmd in @("python", "py")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        $v = & $cmd -c "import sys; print(sys.version_info >= (3, 10))" 2>$null
        if ($v -eq "True") { $python = $cmd; break }
    }
}
if (-not $python) {
    Write-Host "Python 3.10 or newer was not found." -ForegroundColor Red
    Write-Host "Install Python 3.12 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run setup again."
    exit 1
}
Write-Host "Installing Python packages..."
& $python -m pip install --user --quiet --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Host "pip install failed; see the messages above." -ForegroundColor Red; exit 1 }

# 2. Node (screenshots only)
if (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host "Installing screenshot tooling..."
    npm install --no-audit --no-fund --silent
} else {
    Write-Host "Node.js not found: install the LTS version from https://nodejs.org/ and run setup again (needed for screenshots)." -ForegroundColor Yellow
}

# 3. Workspace: company profile, branding, knowledge, projects and inbox.
#    ./workspace by default; set "workspace_dir" in .blueprint-local.json to use a shared folder
#    (for example OneDrive or SharePoint) so the whole team works on the same projects and knowledge.
$local = Join-Path $PSScriptRoot ".blueprint-local.json"
if (-not (Test-Path $local)) {
    '{ "workspace_dir": "" }' | Out-File -FilePath $local -Encoding utf8
}
$cfg = Get-Content $local -Raw | ConvertFrom-Json
$ws = if ($cfg.workspace_dir) { $cfg.workspace_dir } else { Join-Path $PSScriptRoot "workspace" }
$templates = Join-Path $PSScriptRoot "templates"
foreach ($d in @("", "branding", "projects", "inbox", "knowledge")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $ws $d) | Out-Null
}
if (-not (Test-Path (Join-Path $ws "company.yaml"))) {
    Copy-Item (Join-Path $templates "company.yaml") (Join-Path $ws "company.yaml")
    Write-Host "Created $ws\company.yaml - put your company name in it." -ForegroundColor Yellow
}
# Seed the knowledge base with the starter files the workspace does not have yet (never overwrite).
Get-ChildItem (Join-Path $templates "knowledge") -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring((Join-Path $templates "knowledge").Length + 1)
    $target = Join-Path (Join-Path $ws "knowledge") $rel
    if (-not (Test-Path $target)) {
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        Copy-Item $_.FullName $target
    }
}
# projects\, knowledge\ and inbox\ in the app folder are links into the workspace (re-made on every run,
# so they survive the app folder being moved or renamed).
foreach ($name in @("projects", "knowledge", "inbox")) {
    $link = Join-Path $PSScriptRoot $name
    $target = Join-Path $ws $name
    $item = Get-Item $link -Force -ErrorAction SilentlyContinue
    if ($item -and $item.LinkType -eq "Junction") {
        cmd /c rmdir "$link" | Out-Null
    } elseif ($item) {
        if ((Get-ChildItem $link -Force | Measure-Object).Count -gt 0) {
            Write-Host "$name\ is a real folder with files in it. Move its contents into $target, delete it, then run setup again." -ForegroundColor Yellow
            continue
        }
        Remove-Item $link
    }
    cmd /c mklink /J "$link" "$target" | Out-Null
}
Write-Host "Workspace: $ws"

# 4. Check everything
Write-Host ""
& $python -I tools/doctor.py
