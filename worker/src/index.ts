export interface Env {
  ASSETS: R2Bucket;
}

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

function notFound(msg: string): Response {
  return jsonResponse({ detail: msg }, 404);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: CORS_HEADERS });
    }

    // GET /api/server/latest
    if (path === "/api/server/latest") {
      const obj = await env.ASSETS.get("server/latest.json");
      if (!obj) return notFound("server/latest.json not found");
      const data = await obj.json();
      return jsonResponse(data);
    }

    // GET /api/server/{version}
    const serverDownload = path.match(/^\/api\/server\/([^\/]+)$/);
    if (serverDownload) {
      const version = serverDownload[1];
      const obj = await env.ASSETS.get(`server/v${version}.zip`);
      if (!obj) return notFound(`Server v${version} not found`);
      return new Response(obj.body, {
        headers: {
          ...CORS_HEADERS,
          "Content-Type": "application/zip",
          "Content-Disposition": `attachment; filename=entroflow-server-v${version}.zip`,
        },
      });
    }

    // GET /api/catalog
    if (path === "/api/catalog") {
      const obj = await env.ASSETS.get("catalog.json");
      if (!obj) return notFound("catalog.json not found");
      const data = await obj.json();
      return jsonResponse(data);
    }

    // GET /api/platforms/{platform}/latest
    const platformLatest = path.match(/^\/api\/platforms\/([^\/]+)\/latest$/);
    if (platformLatest) {
      const platform = platformLatest[1];
      const obj = await env.ASSETS.get(`platforms/${platform}/latest.json`);
      if (!obj) return notFound(`Platform '${platform}' not found`);
      const data = await obj.json();
      return jsonResponse(data);
    }

    // GET /api/platforms/{platform}/{version}
    const platformDownload = path.match(/^\/api\/platforms\/([^\/]+)\/([^\/]+)$/);
    if (platformDownload && platformDownload[2] !== "latest") {
      const [, platform, version] = platformDownload;
      const obj = await env.ASSETS.get(`platforms/${platform}/v${version}.zip`);
      if (!obj) return notFound(`Platform '${platform}' v${version} not found`);
      return new Response(obj.body, {
        headers: {
          ...CORS_HEADERS,
          "Content-Type": "application/zip",
          "Content-Disposition": `attachment; filename=${platform}-v${version}.zip`,
        },
      });
    }

    // GET /api/platforms/{platform}/devices/{model}/latest
    const deviceLatest = path.match(/^\/api\/platforms\/([^\/]+)\/devices\/([^\/]+)\/latest$/);
    if (deviceLatest) {
      const [, platform, model] = deviceLatest;
      const obj = await env.ASSETS.get(`platforms/${platform}/devices/${model}/latest.json`);
      if (!obj) return notFound(`Device '${model}' not found`);
      const data = await obj.json();
      return jsonResponse(data);
    }

    // GET /api/platforms/{platform}/devices/{model}/action_specs
    const deviceActionSpecs = path.match(/^\/api\/platforms\/([^\/]+)\/devices\/([^\/]+)\/action_specs$/);
    if (deviceActionSpecs) {
      const [, platform, model] = deviceActionSpecs;
      const obj = await env.ASSETS.get(`platforms/${platform}/devices/${model}/action_specs.md`);
      if (!obj) return notFound(`action_specs for '${model}' not found`);
      const text = await obj.text();
      return new Response(text, {
        headers: { ...CORS_HEADERS, "Content-Type": "text/markdown; charset=utf-8" },
      });
    }

    // GET /api/platforms/{platform}/devices/{model}/{version}
    const deviceDownload = path.match(/^\/api\/platforms\/([^\/]+)\/devices\/([^\/]+)\/([^\/]+)$/);
    if (deviceDownload && deviceDownload[3] !== "latest") {
      const [, platform, model, version] = deviceDownload;
      const obj = await env.ASSETS.get(`platforms/${platform}/devices/${model}/v${version}.zip`);
      if (!obj) return notFound(`Device '${model}' v${version} not found`);
      return new Response(obj.body, {
        headers: {
          ...CORS_HEADERS,
          "Content-Type": "application/zip",
          "Content-Disposition": `attachment; filename=${model}-v${version}.zip`,
        },
      });
    }

    return notFound("Not found");
  },
};
