import { Env } from "../lib/types";
import { badRequest, jsonResponse, notFound } from "../lib/utils";

const MAX_QR_BYTES = 512 * 1024;
const DEFAULT_TTL_SECONDS = 600;
const MAX_TTL_SECONDS = 600;
const KEY_PREFIX = "tmp/login-qr";

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function contentTypeFromBytes(bytes: Uint8Array): string | null {
  if (bytes.length >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) {
    return "image/png";
  }
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
    return "image/jpeg";
  }
  if (
    bytes.length >= 12 &&
    bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46 &&
    bytes[8] === 0x57 && bytes[9] === 0x45 && bytes[10] === 0x42 && bytes[11] === 0x50
  ) {
    return "image/webp";
  }
  return null;
}

function clampTtl(raw: unknown): number {
  const parsed = Number.parseInt(String(raw || DEFAULT_TTL_SECONDS), 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return DEFAULT_TTL_SECONDS;
  return Math.min(parsed, MAX_TTL_SECONDS);
}

async function makeToken(): Promise<string> {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return base64Url(bytes);
}

export async function handleTempQrRoutes(path: string, request: Request, env: Env): Promise<Response | null> {
  if (path === "/v1/tmp/login-qr" && request.method === "POST") {
    const formData = await request.formData();
    const file = formData.get("file") as File | null;
    if (!file) return badRequest("file is required");
    if (file.size <= 0 || file.size > MAX_QR_BYTES) return badRequest("file size must be between 1 byte and 512 KiB");

    const bytes = new Uint8Array(await file.arrayBuffer());
    const contentType = contentTypeFromBytes(bytes);
    if (!contentType) return badRequest("file must be a PNG, JPEG, or WebP image");

    const ttlSeconds = clampTtl(formData.get("ttl_seconds"));
    const expiresAt = Math.floor(Date.now() / 1000) + ttlSeconds;
    const token = await makeToken();
    const key = `${KEY_PREFIX}/${token}`;

    await env.ASSETS.put(key, bytes, {
      httpMetadata: { contentType },
      customMetadata: { expires_at: String(expiresAt) },
    });

    const url = new URL(request.url);
    const publicUrl = `${url.origin}/v1/tmp/login-qr/${token}`;
    return jsonResponse({ ok: true, url: publicUrl, token, expires_in: ttlSeconds, expires_at: expiresAt }, 201);
  }

  const match = path.match(/^\/v1\/tmp\/login-qr\/([A-Za-z0-9_-]{32,128})$/);
  if (match && (request.method === "GET" || request.method === "HEAD")) {
    const token = match[1];
    const key = `${KEY_PREFIX}/${token}`;
    const obj = await env.ASSETS.get(key);
    if (!obj) return notFound("QR image not found or expired");

    const expiresAt = Number.parseInt(obj.customMetadata?.expires_at || "0", 10);
    if (!expiresAt || expiresAt < Math.floor(Date.now() / 1000)) {
      await env.ASSETS.delete(key);
      return jsonResponse({ error: "QR image expired" }, 410);
    }

    return new Response(request.method === "HEAD" ? null : obj.body, {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Content-Type": obj.httpMetadata?.contentType || "image/png",
        "Cache-Control": "private, no-store, max-age=0",
        "X-Content-Type-Options": "nosniff",
      },
    });
  }

  return null;
}
