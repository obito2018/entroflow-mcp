import { Env } from "../lib/types";
import { jsonResponse, badRequest, uuid, now, hashPassword } from "../lib/utils";

// 一次性初始化接口，创建第一个 super admin
// 调用方式：POST /v1/init { secret, email, password, name }
// 创建后应立即在 Worker 中移除此路由或设置 INIT_DONE 标志
export async function handleInitRoute(path: string, request: Request, env: Env): Promise<Response | null> {
  if (path !== "/v1/init" || request.method !== "POST") return null;

  // 检查是否已有管理员
  const existing = await env.DB.prepare("SELECT COUNT(*) as c FROM admins").first<{ c: number }>();
  if (existing && existing.c > 0) {
    return jsonResponse({ error: "Already initialized" }, 400);
  }

  let body: any;
  try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }

  const { secret, email, password, name } = body;

  // 简单的初始化密钥保护，通过 Worker Secret 配置
  if (!secret || secret !== (env as any).INIT_SECRET) {
    return jsonResponse({ error: "Invalid secret" }, 403);
  }

  if (!email?.trim()) return badRequest("email is required");
  if (!password || password.length < 8) return badRequest("password must be at least 8 characters");
  if (!name?.trim()) return badRequest("name is required");

  const id = uuid();
  const hash = await hashPassword(password);
  const ts = now();

  await env.DB.prepare(
    "INSERT INTO admins (id, email, name, password_hash, role, created_at) VALUES (?, ?, ?, ?, 'super', ?)"
  ).bind(id, email.toLowerCase(), name.trim(), hash, ts).run();

  return jsonResponse({ success: true, id }, 201);
}
