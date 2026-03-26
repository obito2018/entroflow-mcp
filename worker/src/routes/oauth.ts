import { Env } from "../lib/types";
import { jsonResponse, badRequest, uuid, now, signJwt } from "../lib/utils";

const FRONTEND_URL = "https://entroflow.ai";
const API_BASE = "https://api.entroflow.ai";

export async function handleOAuthRoutes(path: string, request: Request, env: Env): Promise<Response | null> {

  // GET /v1/auth/google
  if (path === "/v1/auth/google" && request.method === "GET") {
    const state = uuid();
    const params = new URLSearchParams({
      client_id: env.GOOGLE_CLIENT_ID,
      redirect_uri: `${API_BASE}/v1/auth/google/callback`,
      response_type: "code",
      scope: "openid email profile",
      state,
      access_type: "offline",
      prompt: "select_account",
    });
    return Response.redirect(`https://accounts.google.com/o/oauth2/v2/auth?${params}`, 302);
  }

  // GET /v1/auth/google/callback
  if (path === "/v1/auth/google/callback" && request.method === "GET") {
    const url = new URL(request.url);
    const code = url.searchParams.get("code");
    const error = url.searchParams.get("error");

    if (error || !code) {
      return Response.redirect(`${FRONTEND_URL}?auth_error=google_denied`, 302);
    }

    try {
      // Exchange code for tokens
      const tokenRes = await fetch("https://oauth2.googleapis.com/token", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          code,
          client_id: env.GOOGLE_CLIENT_ID,
          client_secret: env.GOOGLE_CLIENT_SECRET,
          redirect_uri: `${API_BASE}/v1/auth/google/callback`,
          grant_type: "authorization_code",
        }),
      });
      const tokenData = await tokenRes.json() as any;
      if (!tokenData.access_token) throw new Error("No access token");

      // Get user info
      const userRes = await fetch("https://www.googleapis.com/oauth2/v2/userinfo", {
        headers: { Authorization: `Bearer ${tokenData.access_token}` },
      });
      const userInfo = await userRes.json() as any;
      if (!userInfo.email) throw new Error("No email from Google");

      // Upsert user
      const existing = await env.DB.prepare(
        "SELECT id FROM users WHERE provider = 'google' AND provider_id = ?"
      ).bind(userInfo.id).first<{ id: string }>();

      let userId: string;
      const ts = now();

      if (existing) {
        userId = existing.id;
        await env.DB.prepare(
          "UPDATE users SET name=?, avatar_url=?, last_login_at=?, updated_at=? WHERE id=?"
        ).bind(userInfo.name || null, userInfo.picture || null, ts, ts, userId).run();
      } else {
        // Check if email already registered with different provider
        const byEmail = await env.DB.prepare(
          "SELECT id FROM users WHERE email = ?"
        ).bind(userInfo.email.toLowerCase()).first<{ id: string }>();

        if (byEmail) {
          // Link Google to existing account
          userId = byEmail.id;
          await env.DB.prepare(
            "UPDATE users SET provider_id=?, avatar_url=?, last_login_at=?, updated_at=? WHERE id=?"
          ).bind(userInfo.id, userInfo.picture || null, ts, ts, userId).run();
        } else {
          userId = uuid();
          await env.DB.prepare(
            "INSERT INTO users (id, email, name, avatar_url, provider, provider_id, email_verified, created_at, updated_at) VALUES (?, ?, ?, ?, 'google', ?, 1, ?, ?)"
          ).bind(userId, userInfo.email.toLowerCase(), userInfo.name || null, userInfo.picture || null, userInfo.id, ts, ts).run();
        }
      }

      const token = await signJwt({ sub: userId, email: userInfo.email.toLowerCase(), provider: "google" }, env.JWT_SECRET);
      return Response.redirect(`${FRONTEND_URL}?auth_token=${token}`, 302);

    } catch (e) {
      return Response.redirect(`${FRONTEND_URL}?auth_error=google_failed`, 302);
    }
  }

  // GET /v1/auth/github
  if (path === "/v1/auth/github" && request.method === "GET") {
    const state = uuid();
    const params = new URLSearchParams({
      client_id: env.GITHUB_CLIENT_ID,
      redirect_uri: `${API_BASE}/v1/auth/github/callback`,
      scope: "user:email",
      state,
    });
    return Response.redirect(`https://github.com/login/oauth/authorize?${params}`, 302);
  }

  // GET /v1/auth/github/callback
  if (path === "/v1/auth/github/callback" && request.method === "GET") {
    const url = new URL(request.url);
    const code = url.searchParams.get("code");
    const error = url.searchParams.get("error");

    if (error || !code) {
      return Response.redirect(`${FRONTEND_URL}?auth_error=github_denied`, 302);
    }

    try {
      // Exchange code for token
      const tokenRes = await fetch("https://github.com/login/oauth/access_token", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({
          client_id: env.GITHUB_CLIENT_ID,
          client_secret: env.GITHUB_CLIENT_SECRET,
          code,
          redirect_uri: `${API_BASE}/v1/auth/github/callback`,
        }),
      });
      const tokenData = await tokenRes.json() as any;
      if (!tokenData.access_token) throw new Error("No access token");

      // Get user info
      const [userRes, emailsRes] = await Promise.all([
        fetch("https://api.github.com/user", {
          headers: {
            Authorization: `Bearer ${tokenData.access_token}`,
            "User-Agent": "EntroFlow",
          },
        }),
        fetch("https://api.github.com/user/emails", {
          headers: {
            Authorization: `Bearer ${tokenData.access_token}`,
            "User-Agent": "EntroFlow",
          },
        }),
      ]);

      const userInfo = await userRes.json() as any;
      const emails = await emailsRes.json() as any[];

      // Get primary verified email
      const primaryEmail = emails.find((e: any) => e.primary && e.verified)?.email
        || emails.find((e: any) => e.verified)?.email
        || userInfo.email;

      if (!primaryEmail) throw new Error("No verified email from GitHub");

      // Upsert user
      const existing = await env.DB.prepare(
        "SELECT id FROM users WHERE provider = 'github' AND provider_id = ?"
      ).bind(String(userInfo.id)).first<{ id: string }>();

      let userId: string;
      const ts = now();

      if (existing) {
        userId = existing.id;
        await env.DB.prepare(
          "UPDATE users SET name=?, avatar_url=?, last_login_at=?, updated_at=? WHERE id=?"
        ).bind(userInfo.name || userInfo.login, userInfo.avatar_url || null, ts, ts, userId).run();
      } else {
        const byEmail = await env.DB.prepare(
          "SELECT id FROM users WHERE email = ?"
        ).bind(primaryEmail.toLowerCase()).first<{ id: string }>();

        if (byEmail) {
          userId = byEmail.id;
          await env.DB.prepare(
            "UPDATE users SET provider_id=?, avatar_url=?, last_login_at=?, updated_at=? WHERE id=?"
          ).bind(String(userInfo.id), userInfo.avatar_url || null, ts, ts, userId).run();
        } else {
          userId = uuid();
          await env.DB.prepare(
            "INSERT INTO users (id, email, name, avatar_url, provider, provider_id, email_verified, created_at, updated_at) VALUES (?, ?, ?, ?, 'github', ?, 1, ?, ?)"
          ).bind(userId, primaryEmail.toLowerCase(), userInfo.name || userInfo.login, userInfo.avatar_url || null, String(userInfo.id), ts, ts).run();
        }
      }

      const token = await signJwt({ sub: userId, email: primaryEmail.toLowerCase(), provider: "github" }, env.JWT_SECRET);
      return Response.redirect(`${FRONTEND_URL}?auth_token=${token}`, 302);

    } catch (e) {
      return Response.redirect(`${FRONTEND_URL}?auth_error=github_failed`, 302);
    }
  }

  return null;
}
