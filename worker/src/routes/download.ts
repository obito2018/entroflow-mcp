import { Env } from "../lib/types";
import { jsonResponse, notFound, unauthorized, badRequest, uuid, now, getAuthToken, verifyJwt } from "../lib/utils";

export async function handleDownloadRoutes(path: string, request: Request, env: Env): Promise<Response | null> {

  // POST /v1/devices/:product_id/download
  const downloadMatch = path.match(/^\/v1\/devices\/([^/]+)\/download$/);
  if (downloadMatch && request.method === "POST") {
    const product_id = downloadMatch[1];

    // 需要登录
    const token = getAuthToken(request);
    if (!token) return unauthorized("Login required to download");
    const payload = await verifyJwt(token, env.JWT_SECRET);
    if (!payload) return unauthorized("Invalid or expired token");

    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
    const { version } = body;

    // 查设备
    const device = await env.DB.prepare(
      "SELECT id, product_id, platform_id FROM devices WHERE product_id = ? AND status = 'published'"
    ).bind(product_id).first<{ id: string; product_id: string; platform_id: string }>();
    if (!device) return notFound(`Device '${product_id}' not found`);

    // 查版本
    let ver: any;
    if (version) {
      ver = await env.DB.prepare(
        "SELECT version, zip_r2_key FROM device_versions WHERE device_id = ? AND version = ?"
      ).bind(device.id, version).first();
    } else {
      ver = await env.DB.prepare(
        "SELECT version, zip_r2_key FROM device_versions WHERE device_id = ? AND is_latest = 1"
      ).bind(device.id).first();
    }
    if (!ver) return notFound("Version not found");

    // 记录下载日志
    const ip = request.headers.get("CF-Connecting-IP") || "";
    await env.DB.prepare(
      "INSERT INTO download_logs (id, device_id, version, channel, user_id, ip, created_at) VALUES (?, ?, ?, 'web', ?, ?, ?)"
    ).bind(uuid(), device.id, ver.version, payload.sub, ip, now()).run();

    // 更新下载计数
    await env.DB.prepare(
      "UPDATE devices SET downloads_count = downloads_count + 1 WHERE id = ?"
    ).bind(device.id).run();

    // 生成 R2 presigned URL（有效期 5 分钟）
    // Workers 目前不支持 R2 presigned URL，直接返回下载路径让前端走 /api/* 路由
    const downloadUrl = `/api/platforms/${device.platform_id}/devices/${product_id}/${ver.version}`;

    return jsonResponse({ download_url: downloadUrl, version: ver.version, expires_in: 300 });
  }

  return null;
}
