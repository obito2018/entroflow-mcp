import { Env } from "../lib/types";
import { jsonResponse, badRequest, unauthorized, uuid, now, signJwt, hashPassword, verifyPassword, getAuthToken, verifyJwt, serverError } from "../lib/utils";
import { sendEmail, verifyEmailTemplate, resetPasswordTemplate, loginCodeTemplate } from "../lib/email";

function generateCode(): string {
  return Math.floor(100000 + Math.random() * 900000).toString();
}

async function createCode(env: Env, email: string, type: string): Promise<string> {
  const code = generateCode();
  const id = uuid();
  const expiresAt = now() + 600; // 10 minutes
  // Invalidate previous codes of same type
  await env.DB.prepare("UPDATE email_codes SET used = 1 WHERE email = ? AND type = ? AND used = 0").bind(email, type).run();
  await env.DB.prepare(
    "INSERT INTO email_codes (id, email, code, type, expires_at, used, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)"
  ).bind(id, email.toLowerCase(), code, type, expiresAt, now()).run();
  return code;
}

async function verifyCode(env: Env, email: string, code: string, type: string): Promise<boolean> {
  const record = await env.DB.prepare(
    "SELECT id, expires_at FROM email_codes WHERE email = ? AND code = ? AND type = ? AND used = 0"
  ).bind(email.toLowerCase(), code, type).first<{ id: string; expires_at: number }>();
  if (!record) return false;
  if (record.expires_at < now()) return false;
  await env.DB.prepare("UPDATE email_codes SET used = 1 WHERE id = ?").bind(record.id).run();
  return true;
}

export async function handleEmailAuthRoutes(path: string, request: Request, env: Env): Promise<Response | null> {

  // POST /v1/auth/send-code — send verification/login/reset code
  if (path === "/v1/auth/send-code" && request.method === "POST") {
    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
    const { email, type } = body;
    if (!email?.trim()) return badRequest("email is required");
    if (!["verify", "login", "reset"].includes(type)) return badRequest("type must be verify, login, or reset");

    const emailLower = email.toLowerCase().trim();

    // For reset: check user exists
    if (type === "reset") {
      const user = await env.DB.prepare("SELECT id FROM users WHERE email = ?").bind(emailLower).first();
      if (!user) return badRequest("No account found with this email");
    }

    // For login code: check user exists
    if (type === "login") {
      const user = await env.DB.prepare("SELECT id FROM users WHERE email = ?").bind(emailLower).first();
      if (!user) return badRequest("No account found with this email");
    }

    const code = await createCode(env, emailLower, type);

    let subject = "";
    let html = "";
    if (type === "verify") {
      subject = "验证你的 EntroFlow 邮箱 / Verify your EntroFlow email";
      html = verifyEmailTemplate(code);
    } else if (type === "reset") {
      subject = "重置 EntroFlow 密码 / Reset your EntroFlow password";
      html = resetPasswordTemplate(code);
    } else {
      subject = "EntroFlow 登录验证码 / EntroFlow login code";
      html = loginCodeTemplate(code);
    }

    const result = await sendEmail(emailLower, subject, html, env.RESEND_API_KEY);
    if (!result.ok) return new Response(JSON.stringify({ error: "Failed to send email", detail: result.error }), {
      status: 500, headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
    });

    return jsonResponse({ success: true, message: "Code sent" });
  }

  // POST /v1/auth/verify-email — verify email with code
  if (path === "/v1/auth/verify-email" && request.method === "POST") {
    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
    const { email, code } = body;
    if (!email?.trim() || !code?.trim()) return badRequest("email and code required");

    const valid = await verifyCode(env, email, code, "verify");
    if (!valid) return badRequest("Invalid or expired code");

    await env.DB.prepare("UPDATE users SET email_verified = 1 WHERE email = ?").bind(email.toLowerCase()).run();
    return jsonResponse({ success: true });
  }

  // POST /v1/auth/login-code — login with email code
  if (path === "/v1/auth/login-code" && request.method === "POST") {
    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
    const { email, code } = body;
    if (!email?.trim() || !code?.trim()) return badRequest("email and code required");

    const valid = await verifyCode(env, email, code, "login");
    if (!valid) return badRequest("Invalid or expired code");

    const user = await env.DB.prepare(
      "SELECT id, email, name, provider FROM users WHERE email = ?"
    ).bind(email.toLowerCase()).first<{ id: string; email: string; name: string; provider: string }>();
    if (!user) return unauthorized("User not found");

    await env.DB.prepare("UPDATE users SET last_login_at = ? WHERE id = ?").bind(now(), user.id).run();
    if (!env.JWT_SECRET) return serverError("JWT_SECRET not configured");
    const token = await signJwt({ sub: user.id, email: user.email, provider: user.provider }, env.JWT_SECRET);
    return jsonResponse({ token, user: { id: user.id, email: user.email, name: user.name, provider: user.provider } });
  }

  // POST /v1/auth/reset-password — reset password with code
  if (path === "/v1/auth/reset-password" && request.method === "POST") {
    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
    const { email, code, new_password } = body;
    if (!email?.trim() || !code?.trim()) return badRequest("email and code required");
    if (!new_password || new_password.length < 8) return badRequest("password must be at least 8 characters");

    const valid = await verifyCode(env, email, code, "reset");
    if (!valid) return badRequest("Invalid or expired code");

    const hash = await hashPassword(new_password);
    await env.DB.prepare(
      "UPDATE users SET password_hash = ?, updated_at = ? WHERE email = ?"
    ).bind(hash, now(), email.toLowerCase()).run();

    return jsonResponse({ success: true });
  }

  return null;
}
