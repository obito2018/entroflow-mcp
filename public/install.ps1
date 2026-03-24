# EntroFlow 安装脚本 (Windows PowerShell)
$ErrorActionPreference = "Stop"

$ENTROFLOW_DIR = "$env:USERPROFILE\.entroflow"
$API_BASE = "https://entroflow.ai/api"
$GITHUB_ZIP = "https://github.com/obito2018/entroflow-mcp/archive/refs/heads/main.zip"

Write-Host "=== EntroFlow 安装程序 ===" -ForegroundColor Cyan
Write-Host ""

# 1. 检查 Python
$PYTHON = $null
foreach ($cmd in @("python", "python3")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3") {
            $PYTHON = (Get-Command $cmd).Source
            break
        }
    } catch {}
}

if (-not $PYTHON) {
    Write-Host "错误：未检测到 Python3。" -ForegroundColor Red
    Write-Host "请先安装 Python 3.10 或以上版本：https://www.python.org/downloads/"
    Write-Host "安装时请勾选 'Add Python to PATH'"
    exit 1
}

Write-Host "Python: $PYTHON"
Write-Host ""

# 2. 下载 MCP Server 代码
Write-Host "正在下载 EntroFlow MCP Server..."
$TMP_ZIP = "$env:TEMP\entroflow_main.zip"
$TMP_DIR = "$env:TEMP\entroflow_extract"

# 跳过 SSL 验证（临时，等正式域名配好后去掉）
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
Invoke-WebRequest -Uri $GITHUB_ZIP -OutFile $TMP_ZIP -UseBasicParsing

if (Test-Path $TMP_DIR) { Remove-Item -Recurse -Force $TMP_DIR }
Expand-Archive -Path $TMP_ZIP -DestinationPath $TMP_DIR -Force

$SRC_DIR = "$TMP_DIR\entroflow-mcp-main"

# 保留用户数据，只覆盖代码文件
New-Item -ItemType Directory -Force -Path $ENTROFLOW_DIR | Out-Null
foreach ($item in @("server.py", "skill.md", "requirements.txt", "core", "tools", "assets")) {
    $src = "$SRC_DIR\$item"
    if (Test-Path $src) {
        Copy-Item -Recurse -Force $src "$ENTROFLOW_DIR\"
    }
}

Remove-Item -Force $TMP_ZIP
Remove-Item -Recurse -Force $TMP_DIR
Write-Host "MCP Server 代码已安装到 $ENTROFLOW_DIR"
Write-Host ""

# 3. 安装 Python 依赖
Write-Host "正在安装 Python 依赖..."
& $PYTHON -m pip install -r "$ENTROFLOW_DIR\requirements.txt" -q
Write-Host "依赖安装完成"
Write-Host ""

# 4. 检测并注册 Agent
Write-Host "正在检测已安装的 Agent..."
$REGISTERED = @()

# Claude Code
if (Get-Command "claude" -ErrorAction SilentlyContinue) {
    & claude mcp add -s user --transport stdio entroflow -- $PYTHON "$ENTROFLOW_DIR\server.py" 2>$null
    $REGISTERED += "Claude Code"
}

# Cursor
$CURSOR_DIR = "$env:USERPROFILE\.cursor"
$CURSOR_CONFIG = "$CURSOR_DIR\mcp.json"
if (Test-Path $CURSOR_DIR) {
    if (-not (Test-Path $CURSOR_CONFIG)) {
        '{"mcpServers":{}}' | Out-File -Encoding utf8 $CURSOR_CONFIG
    }
    & $PYTHON -c @"
import json
with open(r'$CURSOR_CONFIG', 'r', encoding='utf-8') as f:
    cfg = json.load(f)
cfg.setdefault('mcpServers', {})['entroflow'] = {
    'command': r'$PYTHON',
    'args': [r'$ENTROFLOW_DIR\server.py']
}
with open(r'$CURSOR_CONFIG', 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
"@
    $REGISTERED += "Cursor"
}

# Windsurf
$WINDSURF_DIR = "$env:USERPROFILE\.codeium\windsurf"
$WINDSURF_CONFIG = "$WINDSURF_DIR\mcp_config.json"
if (Test-Path $WINDSURF_DIR) {
    if (-not (Test-Path $WINDSURF_CONFIG)) {
        '{"mcpServers":{}}' | Out-File -Encoding utf8 $WINDSURF_CONFIG
    }
    & $PYTHON -c @"
import json
with open(r'$WINDSURF_CONFIG', 'r', encoding='utf-8') as f:
    cfg = json.load(f)
cfg.setdefault('mcpServers', {})['entroflow'] = {
    'command': r'$PYTHON',
    'args': [r'$ENTROFLOW_DIR\server.py']
}
with open(r'$WINDSURF_CONFIG', 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
"@
    $REGISTERED += "Windsurf"
}

# Codex
$CODEX_DIR = "$env:USERPROFILE\.codex"
$CODEX_CONFIG = "$CODEX_DIR\config.toml"
if (Test-Path $CODEX_DIR) {
    $toml_entry = "`n[mcp_servers.entroflow]`ncommand = `"$PYTHON $ENTROFLOW_DIR\server.py`"`n"
    if (-not (Test-Path $CODEX_CONFIG) -or -not (Select-String -Path $CODEX_CONFIG -Pattern "mcp_servers.entroflow" -Quiet)) {
        Add-Content -Path $CODEX_CONFIG -Value $toml_entry -Encoding utf8
    }
    $REGISTERED += "Codex"
}

# Trae
$TRAE_DIR = "$env:USERPROFILE\.trae"
$TRAE_CONFIG = "$TRAE_DIR\mcp.json"
if (Test-Path $TRAE_DIR) {
    if (-not (Test-Path $TRAE_CONFIG)) {
        '{"mcpServers":{}}' | Out-File -Encoding utf8 $TRAE_CONFIG
    }
    & $PYTHON -c @"
import json
with open(r'$TRAE_CONFIG', 'r', encoding='utf-8') as f:
    cfg = json.load(f)
cfg.setdefault('mcpServers', {})['entroflow'] = {
    'command': r'$PYTHON',
    'args': [r'$ENTROFLOW_DIR\server.py']
}
with open(r'$TRAE_CONFIG', 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
"@
    $REGISTERED += "Trae"
}

Write-Host ""
if ($REGISTERED.Count -gt 0) {
    Write-Host "已注册到以下 Agent：$($REGISTERED -join ', ')" -ForegroundColor Green
} else {
    Write-Host "未检测到已安装的 Agent，请手动注册 MCP：" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Claude Code:"
    Write-Host "    claude mcp add -s user --transport stdio entroflow -- `"$PYTHON`" `"$ENTROFLOW_DIR\server.py`""
    Write-Host ""
    Write-Host "  Cursor (~\.cursor\mcp.json):"
    Write-Host '    {"mcpServers":{"entroflow":{"command":"' + $PYTHON + '","args":["' + "$ENTROFLOW_DIR\server.py" + '"]}}}'
    Write-Host ""
    Write-Host "  Windsurf (~\.codeium\windsurf\mcp_config.json):"
    Write-Host '    {"mcpServers":{"entroflow":{"command":"' + $PYTHON + '","args":["' + "$ENTROFLOW_DIR\server.py" + '"]}}}'
}

Write-Host ""
Write-Host "=== 安装完成 ===" -ForegroundColor Cyan
Write-Host "重启 Agent 后 EntroFlow 工具即可使用。"
Write-Host "如需注册新增的 Agent，请重新运行此脚本。"
