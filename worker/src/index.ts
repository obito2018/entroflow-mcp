import { Env } from "./lib/types";
import { CORS_HEADERS, notFound } from "./lib/utils";
import { handleAssetRoutes } from "./routes/assets";
import { handlePublicRoutes } from "./routes/public";
import { handleAuthRoutes } from "./routes/auth";
import { handleOAuthRoutes } from "./routes/oauth";
import { handleEmailAuthRoutes } from "./routes/email_auth";
import { handleDownloadRoutes } from "./routes/download";
import { handleAdminRoutes, handleInternalPublishRoutes } from "./routes/admin";
import { handleTempQrRoutes } from "./routes/temp_qr";

export { Env };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      const url = new URL(request.url);
      const path = url.pathname;

      if (request.method === "OPTIONS") {
        return new Response(null, { headers: CORS_HEADERS });
      }

      // /api/* - R2 asset routes
      if (path.startsWith("/api/")) {
        const res = await handleAssetRoutes(path, request, env);
        if (res) return res;
      }

      // /v1/admin/* - Admin routes
      if (path.startsWith("/v1/admin/")) {
        const res = await handleAdminRoutes(path, request, env);
        if (res) return res;
      }

      // /v1/internal/* - Internal publish routes
      if (path.startsWith("/v1/internal/")) {
        const res = await handleInternalPublishRoutes(path, request, env);
        if (res) return res;
      }

      // /v1/tmp/login-qr* - short-lived public QR image fallback for remote agents
      if (path.startsWith("/v1/tmp/login-qr")) {
        const res = await handleTempQrRoutes(path, request, env);
        if (res) return res;
      }

      // /v1/auth/google* and /v1/auth/github* - OAuth routes
      if (path.startsWith("/v1/auth/google") || path.startsWith("/v1/auth/github")) {
        const res = await handleOAuthRoutes(path, request, env);
        if (res) return res;
      }

      // /v1/auth/send-code, verify-email, login-code, reset-password - Email code routes
      if (
        path.startsWith("/v1/auth/send-code") ||
        path.startsWith("/v1/auth/verify-email") ||
        path.startsWith("/v1/auth/login-code") ||
        path.startsWith("/v1/auth/reset-password")
      ) {
        const res = await handleEmailAuthRoutes(path, request, env);
        if (res) return res;
      }

      // /v1/auth/* - Email auth routes
      if (path.startsWith("/v1/auth/")) {
        const res = await handleAuthRoutes(path, request, env);
        if (res) return res;
      }

      // /v1/devices/:id/download - Download route
      if (path.includes("/download")) {
        const res = await handleDownloadRoutes(path, request, env);
        if (res) return res;
      }

      // /v1/* - Public routes
      if (path.startsWith("/v1/")) {
        const res = await handlePublicRoutes(path, request, env);
        if (res) return res;
      }

      return notFound("Not found");
    } catch (err: any) {
      return new Response(JSON.stringify({ error: "Worker error", detail: err?.message ?? String(err) }), {
        status: 500,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
      });
    }
  },
};
