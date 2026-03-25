import { Env } from "../lib/types";
import { jsonResponse, notFound } from "../lib/utils";

export async function handleAssetRoutes(path: string, request: Request, env: Env): Promise<Response | null> {

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
