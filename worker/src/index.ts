import { Env } from "./lib/types";
import { CORS_HEADERS, notFound } from "./lib/utils";
import { handleAssetRoutes } from "./routes/assets";
import { handlePublicRoutes } from "./routes/public";
import { handleAuthRoutes } from "./routes/auth";
import { handleOAuthRoutes } from "./routes/oauth";
import { handleDownloadRoutes } from "./routes/download";
import { handleAdminRoutes } from "./routes/admin";
import { handleInitRoute } from "./routes/init";

export { Env };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      const url = new URL(request.url);
      const path = url.pathname;

      if (request.method === "OPTIONS") {
        return new Response(null, { headers: CORS_HEADERS });
      }

      // /v1/init — One-time admin initialization
      if (path === "/v1/init") {
        const res = await handleInitRoute(path, request, env);
        if (res) return res;
      }

      // /api/* — R2 asset routes (existing)
      if (path.startsWith("/api/")) {
        const res = await handleAssetRoutes(path, request, env);
        if (res) return res;
      }

      // /v1/admin/* — Admin routes
      if (path.startsWith("/v1/admin/")) {
        const res = await handleAdminRoutes(path, request, env);
        if (res) return res;
      }

      // /v1/auth/google* and /v1/auth/github* — OAuth routes
      if (path.startsWith("/v1/auth/google") || path.startsWith("/v1/auth/github")) {
        const res = await handleOAuthRoutes(path, request, env);
        if (res) return res;
      }

      // /v1/auth/* — Email auth routes
      if (path.startsWith("/v1/auth/")) {
        const res = await handleAuthRoutes(path, request, env);
        if (res) return res;
      }

      // /v1/devices/:id/download — Download route (needs auth)
      if (path.includes("/download")) {
        const res = await handleDownloadRoutes(path, request, env);
        if (res) return res;
      }

      // /v1/* — Public routes
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
