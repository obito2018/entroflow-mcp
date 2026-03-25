#!/bin/bash
set -e

ENTROFLOW_DIR="$HOME/.entroflow"
GITHUB_ZIP="https://github.com/obito2018/entroflow-mcp/archive/refs/heads/main.zip"

echo "=== EntroFlow 安装程序 ==="
echo ""

# 1. 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "错误：未检测到 Python3。"
    echo "请先安装 Python 3.10 或以上版本：https://www.python.org/downloads/"
    exit 1
fi

PYTHON=$(command -v python3)

echo "Python: $PYTHON"
echo ""

# 2. 下载 MCP Server 代码
echo "正在下载 EntroFlow MCP Server..."
TMP_ZIP="/tmp/entroflow_main.zip"
TMP_DIR="/tmp/entroflow_extract"

curl -fsSL "$GITHUB_ZIP" -o "$TMP_ZIP"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"
unzip -q "$TMP_ZIP" -d "$TMP_DIR"

# 解压后目录名为 entroflow-mcp-main
SRC_DIR="$TMP_DIR/entroflow-mcp-main"

# 保留用户数据，只覆盖代码文件
mkdir -p "$ENTROFLOW_DIR"
for item in server.py skill.md requirements.txt core tools assets; do
    if [ -e "$SRC_DIR/$item" ]; then
        cp -r "$SRC_DIR/$item" "$ENTROFLOW_DIR/"
    fi
done

rm -rf "$TMP_ZIP" "$TMP_DIR"
echo "MCP Server 代码已安装到 $ENTROFLOW_DIR"
echo ""

# 3. 安装 Python 依赖
echo "正在安装 Python 依赖..."
"$PYTHON" -m pip install -r "$ENTROFLOW_DIR/requirements.txt" -q
echo "依赖安装完成"
echo ""

# 4. 确保 config.json 存在
if [ ! -f "$ENTROFLOW_DIR/config.json" ]; then
    echo '{}' > "$ENTROFLOW_DIR/config.json"
fi

# 5. 检测并注册 Agent
echo "正在检测已安装的 Agent..."
REGISTERED=()

# Claude Code
if command -v claude &>/dev/null; then
    if claude mcp add -s user --transport stdio entroflow -- "$PYTHON" "$ENTROFLOW_DIR/server.py" 2>/dev/null; then
        REGISTERED+=("Claude Code")
    else
        # 已存在或其他错误，仍视为已注册
        REGISTERED+=("Claude Code")
    fi
fi

# Cursor
CURSOR_CONFIG="$HOME/.cursor/mcp.json"
if [ -d "$HOME/.cursor" ]; then
    mkdir -p "$HOME/.cursor"
    if [ ! -f "$CURSOR_CONFIG" ]; then
        echo '{"mcpServers":{}}' > "$CURSOR_CONFIG"
    fi
    python3 -c "
import json
with open('$CURSOR_CONFIG', 'r') as f:
    cfg = json.load(f)
cfg.setdefault('mcpServers', {})['entroflow'] = {
    'command': '$PYTHON',
    'args': ['$ENTROFLOW_DIR/server.py']
}
with open('$CURSOR_CONFIG', 'w') as f:
    json.dump(cfg, f, indent=2)
"
    REGISTERED+=("Cursor")
fi

# Windsurf
WINDSURF_CONFIG="$HOME/.codeium/windsurf/mcp_config.json"
if [ -d "$HOME/.codeium/windsurf" ]; then
    if [ ! -f "$WINDSURF_CONFIG" ]; then
        echo '{"mcpServers":{}}' > "$WINDSURF_CONFIG"
    fi
    python3 -c "
import json
with open('$WINDSURF_CONFIG', 'r') as f:
    cfg = json.load(f)
cfg.setdefault('mcpServers', {})['entroflow'] = {
    'command': '$PYTHON',
    'args': ['$ENTROFLOW_DIR/server.py']
}
with open('$WINDSURF_CONFIG', 'w') as f:
    json.dump(cfg, f, indent=2)
"
    REGISTERED+=("Windsurf")
fi

# Codex
CODEX_CONFIG="$HOME/.codex/config.toml"
if [ -d "$HOME/.codex" ]; then
    if command -v codex &>/dev/null; then
        codex mcp add entroflow -- "$PYTHON" "$ENTROFLOW_DIR/server.py" 2>/dev/null || true
    else
        # CLI 不可用，回退到直接写 config.toml
        if ! grep -q "\[mcp_servers.entroflow\]" "$CODEX_CONFIG" 2>/dev/null; then
            cat >> "$CODEX_CONFIG" <<TOML

[mcp_servers.entroflow]
command = "$PYTHON"
args = ["$ENTROFLOW_DIR/server.py"]
TOML
        fi
    fi
    REGISTERED+=("Codex")
fi

# OpenClaw
OPENCLAW_CONFIG="$HOME/.openclaw/openclaw.json"
if [ -d "$HOME/.openclaw" ]; then
    if command -v openclaw &>/dev/null; then
        openclaw mcp set entroflow "{\"command\":\"$PYTHON\",\"args\":[\"$ENTROFLOW_DIR/server.py\"]}" 2>/dev/null || true
    else
        # CLI 不可用，直接写 openclaw.json
        "$PYTHON" -c "
import json, os
path = '$OPENCLAW_CONFIG'
cfg = {}
if os.path.exists(path):
    with open(path, 'r') as f:
        cfg = json.load(f)
cfg.setdefault('mcp', {}).setdefault('servers', {})['entroflow'] = {
    'command': '$PYTHON',
    'args': ['$ENTROFLOW_DIR/server.py']
}
with open(path, 'w') as f:
    json.dump(cfg, f, indent=2)
"
    fi
    REGISTERED+=("OpenClaw")
fi

# OpenCode
OPENCODE_DIR="$HOME/.config/opencode"
OPENCODE_CONFIG="$OPENCODE_DIR/opencode.json"
if [ -d "$OPENCODE_DIR" ]; then
    if [ ! -f "$OPENCODE_CONFIG" ]; then
        echo '{}' > "$OPENCODE_CONFIG"
    fi
    "$PYTHON" -c "
import json
with open('$OPENCODE_CONFIG', 'r') as f:
    cfg = json.load(f)
cfg.setdefault('mcp', {})['entroflow'] = {
    'type': 'local',
    'command': ['$PYTHON', '$ENTROFLOW_DIR/server.py']
}
with open('$OPENCODE_CONFIG', 'w') as f:
    json.dump(cfg, f, indent=2)
"
    REGISTERED+=("OpenCode")
fi

# Antigravity
ANTIGRAVITY_DIR="$HOME/.gemini/antigravity"
ANTIGRAVITY_CONFIG="$ANTIGRAVITY_DIR/mcp_config.json"
if [ -d "$ANTIGRAVITY_DIR" ]; then
    if [ ! -f "$ANTIGRAVITY_CONFIG" ]; then
        echo '{"mcpServers":{}}' > "$ANTIGRAVITY_CONFIG"
    fi
    "$PYTHON" -c "
import json
with open('$ANTIGRAVITY_CONFIG', 'r') as f:
    cfg = json.load(f)
cfg.setdefault('mcpServers', {})['entroflow'] = {
    'command': '$PYTHON',
    'args': ['$ENTROFLOW_DIR/server.py']
}
with open('$ANTIGRAVITY_CONFIG', 'w') as f:
    json.dump(cfg, f, indent=2)
"
    REGISTERED+=("Antigravity")
fi

# Trae
TRAE_CONFIG="$HOME/.trae/mcp.json"
if [ -d "$HOME/.trae" ]; then
    if [ ! -f "$TRAE_CONFIG" ]; then
        echo '{"mcpServers":{}}' > "$TRAE_CONFIG"
    fi
    python3 -c "
import json
with open('$TRAE_CONFIG', 'r') as f:
    cfg = json.load(f)
cfg.setdefault('mcpServers', {})['entroflow'] = {
    'command': '$PYTHON',
    'args': ['$ENTROFLOW_DIR/server.py']
}
with open('$TRAE_CONFIG', 'w') as f:
    json.dump(cfg, f, indent=2)
"
    REGISTERED+=("Trae")
fi

echo ""
if [ ${#REGISTERED[@]} -gt 0 ]; then
    echo "已注册到以下 Agent：${REGISTERED[*]}"
else
    echo "未检测到已安装的 Agent，请手动注册 MCP："
    echo ""
    echo "  Claude Code:"
    echo "    claude mcp add -s user --transport stdio entroflow -- $PYTHON $ENTROFLOW_DIR/server.py"
    echo ""
    echo "  Cursor (~/.cursor/mcp.json):"
    echo '    {"mcpServers":{"entroflow":{"command":"'"$PYTHON"'","args":["'"$ENTROFLOW_DIR/server.py"'"]}}}'
    echo ""
    echo "  Windsurf (~/.codeium/windsurf/mcp_config.json):"
    echo '    {"mcpServers":{"entroflow":{"command":"'"$PYTHON"'","args":["'"$ENTROFLOW_DIR/server.py"'"]}}}'
fi

echo ""
echo "=== 安装完成 ==="
echo "重启 Agent 后 EntroFlow 工具即可使用。"
echo "如需注册新增的 Agent，请重新运行此脚本。"
