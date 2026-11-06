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

# 2. Node: screenshot tooling and the document fonts
if (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host "Installing screenshot tooling and fonts..."
    # --no-save: install exactly what package-lock.json lists and never rewrite it, so the folder stays as it was
    # cloned (a rewritten lock file would stop the next git pull).
    npm install --no-save --no-audit --no-fund --silent
} else {
    Write-Host "Node.js not found: install the LTS version from https://nodejs.org/ and run setup again (needed for screenshots and fonts)." -ForegroundColor Yellow
}

# 2b. Fonts used by the document design (Geist and Geist Mono, SIL Open Font License), installed for this
#     Windows user only, so no administrator rights are needed. Restart Word after the first install.
$fontSrc = Join-Path $PSScriptRoot "node_modules\geist\dist\fonts"
if (Test-Path $fontSrc) {
    $fontDir = Join-Path $env:LOCALAPPDATA "Microsoft\Windows\Fonts"
    $regKey = "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts"
    New-Item -ItemType Directory -Force -Path $fontDir | Out-Null
    if (-not (Test-Path $regKey)) { New-Item -Path $regKey -Force | Out-Null }
    $fonts = @(
        @("geist-sans\Geist-Regular.ttf", "Geist Regular (TrueType)"),
        @("geist-sans\Geist-Italic.ttf", "Geist Italic (TrueType)"),
        @("geist-sans\Geist-Medium.ttf", "Geist Medium (TrueType)"),
        @("geist-sans\Geist-SemiBold.ttf", "Geist SemiBold (TrueType)"),
        @("geist-sans\Geist-Bold.ttf", "Geist Bold (TrueType)"),
        @("geist-sans\Geist-BoldItalic.ttf", "Geist Bold Italic (TrueType)"),
        @("geist-mono\GeistMono-Regular.ttf", "Geist Mono Regular (TrueType)"),
        @("geist-mono\GeistMono-Medium.ttf", "Geist Mono Medium (TrueType)")
    )
    $added = 0
    foreach ($f in $fonts) {
        $src = Join-Path $fontSrc $f[0]
        $dest = Join-Path $fontDir (Split-Path $f[0] -Leaf)
        if (-not (Test-Path $src)) { continue }
        if (-not (Test-Path $dest)) { Copy-Item $src $dest; $added++ }
        New-ItemProperty -Path $regKey -Name $f[1] -Value $dest -PropertyType String -Force | Out-Null
    }
    # Make the fonts available in this Windows session straight away (otherwise only after signing in again).
    Add-Type -Namespace Blueprint -Name Fonts -MemberDefinition @'
[DllImport("gdi32.dll", CharSet = CharSet.Unicode)] public static extern int AddFontResourceW(string file);
[DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern System.IntPtr SendMessageTimeoutW(System.IntPtr hWnd, uint msg, System.UIntPtr w, System.IntPtr l, uint flags, uint timeout, out System.UIntPtr result);
'@ -ErrorAction SilentlyContinue
    foreach ($f in $fonts) {
        $dest = Join-Path $fontDir (Split-Path $f[0] -Leaf)
        if (Test-Path $dest) { [Blueprint.Fonts]::AddFontResourceW($dest) | Out-Null }
    }
    $r = [System.UIntPtr]::Zero
    [Blueprint.Fonts]::SendMessageTimeoutW([System.IntPtr]0xffff, 0x001D, [System.UIntPtr]::Zero, [System.IntPtr]::Zero, 2, 1000, [ref]$r) | Out-Null
    if ($added) { Write-Host "Installed $added font files (Geist, Geist Mono). Restart Word if it is open." }
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
# Files renamed in 0.4.0 (SRS -> requirements document). Rename them in place so nothing is lost.
foreach ($pair in @(@("knowledge\srs-standard.md", "knowledge\requirements-standard.md"),
                    @("branding\srs-template.docx", "branding\document-template.docx"),
                    @("branding\srs-boilerplate.yaml", "branding\document-boilerplate.yaml"),
                    @("branding\srs-format.yaml", "branding\document-format.yaml"))) {
    $old = Join-Path $ws $pair[0]; $new = Join-Path $ws $pair[1]
    if ((Test-Path $old) -and -not (Test-Path $new)) {
        Move-Item $old $new
        Write-Host "Renamed $($pair[0]) to $($pair[1])"
    }
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
# Where Blueprint is on this machine, for the "Open the mock-up" shortcut in each project folder: the workspace
# is shared, and the app can be in a different place on each person's machine.
$pointer = Join-Path $env:USERPROFILE ".blueprint"
New-Item -ItemType Directory -Force -Path $pointer | Out-Null
[System.IO.File]::WriteAllText((Join-Path $pointer "app-path"), $PSScriptRoot, (New-Object System.Text.UTF8Encoding $false))

# 4. Check everything
Write-Host ""
& $python -I tools/doctor.py
