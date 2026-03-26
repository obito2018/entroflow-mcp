import { Env } from "../lib/types";
import { jsonResponse, badRequest, unauthorized, uuid, now, signJwt, verifyJwt, hashPassword, verifyPassword, getAuthToken, serverError } from "../lib/utils";

export async function handleAuthRoutes(path: string, request: Request, env: Env): Promise<Response | null> {

  // POST /v1/auth/register
  if (path === "/v1/auth/register" && request.method === "POST") {
    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }

    const { email, password, name } = body;
    if (!email?.trim()) return badRequest("email is required");
    if (!password || password.length < 8) return badRequest("password must be at least 8 characters");
    if (!name?.trim()) return badRequest("name is required");

    const existing = await env.DB.prepare("SELECT id FROM users WHERE email = ?").bind(email.toLowerCase()).first();
    if (existing) return badRequest("Email already registered");

    const id = uuid();
    const hash = await hashPassword(password);
    const ts = now();

    await env.DB.prepare(
      "INSERT INTO users (id, email, name, provider, password_hash, email_verified, created_at, updated_at) VALUES (?, ?, ?, 'email', ?, 0, ?, ?)"
    ).bind(id, email.toLowerCase(), name.trim(), hash, ts, ts).run();

    if (!env.JWT_SECRET) return serverError("JWT_SECRET not configured");
    const token = await signJwt({ sub: id, email: email.toLowerCase(), provider: "email" }, env.JWT_SECRET);
    return jsonResponse({ token, user: { id, email: email.toLowerCase(), name: name.trim(), provider: "email" } }, 201);
  }

  // POST /v1/auth/login
  if (path === "/v1/auth/login" && request.method === "POST") {
    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }

    const { email, password } = body;
    if (!email?.trim()) return badRequest("email is required");
    if (!password) return badRequest("password is required");

    const user = await env.DB.prepare(
      "SELECT id, email, name, password_hash FROM users WHERE email = ? AND provider = 'email'"
    ).bind(email.toLowerCase()).first<{ id: string; email: string; name: string; password_hash: string }>();

    if (!user || !user.password_hash) return unauthorized("Invalid email or password");
    const valid = await verifyPassword(password, user.password_hash);
    if (!valid) return unauthorized("Invalid email or password");

    // Update last_login_at
    await env.DB.prepare("UPDATE users SET last_login_at = ? WHERE id = ?").bind(now(), user.id).run();

    const token = await signJwt({ sub: user.id, email: user.email, provider: "email" }, env.JWT_SECRET);
    return jsonResponse({ token, user: { id: user.id, email: user.email, name: user.name, provider: "email" } });
  }

  // GET /v1/auth/me
  if (path === "/v1/auth/me" && request.method === "GET") {
    const token = getAuthToken(request);
    if (!token) return unauthorized();
    const payload = await verifyJwt(token, env.JWT_SECRET);
    if (!payload) return unauthorized("Invalid or expired token");

    const user = await env.DB.prepare(
      "SELECT id, email, name, avatar_url, provider, created_at FROM users WHERE id = ?"
    ).bind(payload.sub).first();
    if (!user) return unauthorized("User not found");
    return jsonResponse(user);
  }

  return null;
}
