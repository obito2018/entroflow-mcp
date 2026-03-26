import { Env } from "../lib/types";
import { jsonResponse, notFound } from "../lib/utils";

export async function handleAssetRoutes(path: string, request: Request, env: Env): Promise<Response | null> {

  // GET /api/install-device.ps1?model=&platform=&version=
  if (path === "/api/install-device.ps1" && request.method === "GET") {
    const url = new URL(request.url);
    const model = url.searchParams.get("model") || "";
    const platform = url.searchParams.get("platform") || "";
    const version = url.searchParams.get("version") || "latest";
    if (!model || !platform) return notFound("model and platform are required");

    const script = `# EntroFlow Device Installer (Windows PowerShell)
$ENTROFLOW_DIR = "$env:USERPROFILE\\.entroflow"
$API_BASE = "https://api.entroflow.ai/api"
$PLATFORM = "${platform}"
$MODEL = "${model}"
$VERSION = "${version}"

function Download-And-Extract($url, $dest) {
    $tmp = "$env:TEMP\\entroflow_tmp.zip"
    Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Expand-Archive -Path $tmp -DestinationPath $dest -Force
    Remove-Item -Force $tmp
}

# 1. Install platform connector if not present
$connectorDir = "$ENTROFLOW_DIR\\assets\\$PLATFORM\\connector"
if (-not (Test-Path $connectorDir)) {
    Write-Host "Installing platform connector: $PLATFORM..."
    $latestUrl = "$API_BASE/platforms/$PLATFORM/latest"
    $ver = (Invoke-WebRequest -Uri $latestUrl -UseBasicParsing | ConvertFrom-Json).version
    Download-And-Extract "$API_BASE/platforms/$PLATFORM/$ver" $connectorDir
    Write-Host "Platform connector installed (v$ver)"
} else {
    Write-Host "Platform connector already installed: $PLATFORM"
}

# 2. Install device driver
$deviceDir = "$ENTROFLOW_DIR\\assets\\$PLATFORM\\devices\\$MODEL"
Write-Host "Installing device driver: $MODEL..."
if ($VERSION -eq "latest") {
    $latestUrl = "$API_BASE/platforms/$PLATFORM/devices/$MODEL/latest"
    $VERSION = (Invoke-WebRequest -Uri $latestUrl -UseBasicParsing | ConvertFrom-Json).version
}
Download-And-Extract "$API_BASE/platforms/$PLATFORM/devices/$MODEL/$VERSION" $deviceDir
Write-Host "Device driver installed: $MODEL v$VERSION"
Write-Host ""
Write-Host "Done. Restart your Agent to use the new driver."
`;

    return new Response(script, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-cache",
      },
    });
  }

  // GET /api/install-device.sh?model=&platform=&version=
  if (path === "/api/install-device.sh" && request.method === "GET") {
    const url = new URL(request.url);
    const model = url.searchParams.get("model") || "";
    const platform = url.searchParams.get("platform") || "";
    const version = url.searchParams.get("version") || "latest";
    if (!model || !platform) return notFound("model and platform are required");

    const script = `#!/bin/bash
# EntroFlow Device Installer (macOS/Linux)
ENTROFLOW_DIR="$HOME/.entroflow"
API_BASE="https://api.entroflow.ai/api"
PLATFORM="${platform}"
MODEL="${model}"
VERSION="${version}"

download_and_extract() {
    local url="$1"
    local dest="$2"
    local tmp="/tmp/entroflow_tmp.zip"
    curl -fsSL "$url" -o "$tmp"
    mkdir -p "$dest"
    unzip -q -o "$tmp" -d "$dest"
    rm -f "$tmp"
}

# 1. Install platform connector if not present
CONNECTOR_DIR="$ENTROFLOW_DIR/assets/$PLATFORM/connector"
if [ ! -d "$CONNECTOR_DIR" ]; then
    echo "Installing platform connector: $PLATFORM..."
    VER=$(curl -fsSL "$API_BASE/platforms/$PLATFORM/latest" | python3 -c "import json,sys; print(json.load(sys.stdin)['version'])")
    download_and_extract "$API_BASE/platforms/$PLATFORM/$VER" "$CONNECTOR_DIR"
    echo "Platform connector installed (v$VER)"
else
    echo "Platform connector already installed: $PLATFORM"
fi

# 2. Install device driver
DEVICE_DIR="$ENTROFLOW_DIR/assets/$PLATFORM/devices/$MODEL"
echo "Installing device driver: $MODEL..."
if [ "$VERSION" = "latest" ]; then
    VERSION=$(curl -fsSL "$API_BASE/platforms/$PLATFORM/devices/$MODEL/latest" | python3 -c "import json,sys; print(json.load(sys.stdin)['version'])")
fi
download_and_extract "$API_BASE/platforms/$PLATFORM/devices/$MODEL/$VERSION" "$DEVICE_DIR"
echo "Device driver installed: $MODEL v$VERSION"
echo ""
echo "Done. Restart your Agent to use the new driver."
`;

    return new Response(script, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-cache",
      },
    });
  }

  // GET /api/uploads/* — serve uploaded files from R2
  if (path.startsWith("/api/uploads/")) {
    const key = path.slice("/api/uploads/".length);
    const obj = await env.ASSETS.get(key);
    if (!obj) return notFound(`File not found: ${key}`);
    const contentType = obj.httpMetadata?.contentType || "application/octet-stream";
    return new Response(obj.body, {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": contentType,
        "Cache-Control": "public, max-age=31536000",
      },
    });
  }

  // GET /api/server/latest
  if (path === "/api/server/latest") {
    const obj = await env.ASSETS.get("server/latest.json");
    if (!obj) return notFound("server/latest.json not found");
    return jsonResponse(await obj.json());
  }

  // GET /api/server/{version}
  const serverDownload = path.match(/^\/api\/server\/([^/]+)$/);
  if (serverDownload) {
    const version = serverDownload[1];
    const obj = await env.ASSETS.get(`server/v${version}.zip`);
    if (!obj) return notFound(`Server v${version} not found`);
    return new Response(obj.body, {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/zip",
        "Content-Disposition": `attachment; filename=entroflow-server-v${version}.zip`,
      },
    });
  }

  // GET /api/catalog
  if (path === "/api/catalog") {
    const obj = await env.ASSETS.get("catalog.json");
    if (!obj) return notFound("catalog.json not found");
    return jsonResponse(await obj.json());
  }

  // GET /api/platforms/{platform}/latest
  const platformLatest = path.match(/^\/api\/platforms\/([^/]+)\/latest$/);
  if (platformLatest) {
    const platform = platformLatest[1];
    const obj = await env.ASSETS.get(`platforms/${platform}/latest.json`);
    if (!obj) return notFound(`Platform '${platform}' not found`);
    return jsonResponse(await obj.json());
  }

  // GET /api/platforms/{platform}/{version}
  const platformDownload = path.match(/^\/api\/platforms\/([^/]+)\/([^/]+)$/);
  if (platformDownload && platformDownload[2] !== "latest") {
    const [, platform, version] = platformDownload;
    const obj = await env.ASSETS.get(`platforms/${platform}/v${version}.zip`);
    if (!obj) return notFound(`Platform '${platform}' v${version} not found`);
    return new Response(obj.body, {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/zip",
        "Content-Disposition": `attachment; filename=${platform}-v${version}.zip`,
      },
    });
  }

  // GET /api/platforms/{platform}/devices/{model}/action_specs
  const deviceActionSpecs = path.match(/^\/api\/platforms\/([^/]+)\/devices\/([^/]+)\/action_specs$/);
  if (deviceActionSpecs) {
    const [, platform, model] = deviceActionSpecs;
    const obj = await env.ASSETS.get(`platforms/${platform}/devices/${model}/action_specs.md`);
    if (!obj) return notFound(`action_specs for '${model}' not found`);
    return new Response(await obj.text(), {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "text/markdown; charset=utf-8",
      },
    });
  }

  // GET /api/platforms/{platform}/devices/{model}/latest
  const deviceLatest = path.match(/^\/api\/platforms\/([^/]+)\/devices\/([^/]+)\/latest$/);
  if (deviceLatest) {
    const [, platform, model] = deviceLatest;
    const obj = await env.ASSETS.get(`platforms/${platform}/devices/${model}/latest.json`);
    if (!obj) return notFound(`Device '${model}' not found`);
    return jsonResponse(await obj.json());
  }

  // GET /api/platforms/{platform}/devices/{model}/{version}
  const deviceDownload = path.match(/^\/api\/platforms\/([^/]+)\/devices\/([^/]+)\/([^/]+)$/);
  if (deviceDownload && deviceDownload[3] !== "latest") {
    const [, platform, model, version] = deviceDownload;
    const obj = await env.ASSETS.get(`platforms/${platform}/devices/${model}/v${version}.zip`);
    if (!obj) return notFound(`Device '${model}' v${version} not found`);
    return new Response(obj.body, {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": "application/zip",
        "Content-Disposition": `attachment; filename=${model}-v${version}.zip`,
      },
    });
  }

  return null;
}
