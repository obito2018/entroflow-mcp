import { Env } from "../lib/types";
import { jsonResponse, notFound, unauthorized, badRequest, forbidden, uuid, now, signJwt, verifyJwt, hashPassword, verifyPassword, getAuthToken } from "../lib/utils";

async function requireAdmin(request: Request, env: Env): Promise<{ id: string; role: string } | Response> {
  const token = getAuthToken(request);
  if (!token) return unauthorized();
  const payload = await verifyJwt(token, env.ADMIN_JWT_SECRET);
  if (!payload || !payload.role) return unauthorized("Invalid admin token");
  return { id: payload.sub, role: payload.role };
}

// Regenerate catalog.json in R2 from published platforms in D1
async function syncCatalogToR2(env: Env): Promise<void> {
  try {
    const { results } = await env.DB.prepare(
      "SELECT id, name_en, name_zh, aliases FROM hardware_platforms WHERE status = 'published' ORDER BY name_en ASC"
    ).all();

    const platforms = results.map((p: any) => {
      let aliases: string[] = [];
      if (p.aliases) {
        try { aliases = JSON.parse(p.aliases); } catch { aliases = []; }
      }
      const entry: any = {
        id: p.id,
        display_name: p.name_en,
        aliases: [p.id, p.name_en, ...(p.name_zh ? [p.name_zh] : []), ...aliases]
          .filter(Boolean)
          .filter((v, i, arr) => arr.indexOf(v) === i), // deduplicate
      };
      if (p.name_zh) entry.display_name_zh = p.name_zh;
      return entry;
    });

    const catalog = JSON.stringify({ platforms }, null, 2);
    await env.ASSETS.put("catalog.json", catalog, {
      httpMetadata: { contentType: "application/json" },
    });
  } catch (e) {
    // Non-fatal: log but don't fail the request
    console.error("Failed to sync catalog.json:", e);
  }
}

export async function handleAdminRoutes(path: string, request: Request, env: Env): Promise<Response | null> {

  // POST /v1/admin/auth/login
  if (path === "/v1/admin/auth/login" && request.method === "POST") {
    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
    const { email, password } = body;
    if (!email || !password) return badRequest("email and password required");

    const admin = await env.DB.prepare(
      "SELECT id, email, name, password_hash, role FROM admins WHERE email = ?"
    ).bind(email.toLowerCase()).first<{ id: string; email: string; name: string; password_hash: string; role: string }>();

    if (!admin) return unauthorized("Invalid credentials");
    const valid = await verifyPassword(password, admin.password_hash);
    if (!valid) return unauthorized("Invalid credentials");

    await env.DB.prepare("UPDATE admins SET last_login_at = ? WHERE id = ?").bind(now(), admin.id).run();
    const token = await signJwt({ sub: admin.id, email: admin.email, role: admin.role }, env.ADMIN_JWT_SECRET);
    return jsonResponse({ token, admin: { id: admin.id, email: admin.email, name: admin.name, role: admin.role } });
  }

  // All routes below require admin auth
  if (!path.startsWith("/v1/admin/")) return null;

  const admin = await requireAdmin(request, env);
  if (admin instanceof Response) return admin;

  // GET /v1/admin/stats
  if (path === "/v1/admin/stats" && request.method === "GET") {
    const [devices, platforms, downloads, feedbackNew, businessNew, users, installIds] = await Promise.all([
      env.DB.prepare("SELECT COUNT(*) as c FROM devices").first<{ c: number }>(),
      env.DB.prepare("SELECT COUNT(*) as c FROM hardware_platforms").first<{ c: number }>(),
      env.DB.prepare("SELECT COUNT(*) as c FROM download_logs").first<{ c: number }>(),
      env.DB.prepare("SELECT COUNT(*) as c FROM feedback WHERE status = 'new'").first<{ c: number }>(),
      env.DB.prepare("SELECT COUNT(*) as c FROM business_inquiries WHERE status = 'new'").first<{ c: number }>(),
      env.DB.prepare("SELECT COUNT(*) as c FROM users").first<{ c: number }>(),
      env.DB.prepare("SELECT COUNT(DISTINCT install_id) as c FROM download_logs WHERE install_id IS NOT NULL").first<{ c: number }>(),
    ]);
    return jsonResponse({
      devices_total: devices?.c ?? 0,
      platforms_total: platforms?.c ?? 0,
      downloads_total: downloads?.c ?? 0,
      feedback_new: feedbackNew?.c ?? 0,
      business_new: businessNew?.c ?? 0,
      users_total: users?.c ?? 0,
      install_ids_total: installIds?.c ?? 0,
    });
  }

  // ── User Management ──────────────────────────────────────────────────────

  if (path === "/v1/admin/users" && request.method === "GET") {
    const url = new URL(request.url);
    const search = url.searchParams.get("search") || "";
    const provider = url.searchParams.get("provider") || "";
    const page = Math.max(1, parseInt(url.searchParams.get("page") || "1"));
    const limit = 20;
    const offset = (page - 1) * limit;

    let where = "1=1";
    const bindings: unknown[] = [];
    if (search) { where += " AND (u.email LIKE ? OR u.name LIKE ?)"; bindings.push(`%${search}%`, `%${search}%`); }
    if (provider) { where += " AND u.provider = ?"; bindings.push(provider); }

    const [items, count] = await Promise.all([
      env.DB.prepare(`
        SELECT
          u.id, u.email, u.name, u.provider, u.avatar_url,
          u.created_at, u.last_login_at,
          COUNT(DISTINCT dl.id) as downloads_total,
          COUNT(DISTINCT dl.device_id) as devices_downloaded,
          COUNT(DISTINCT d.platform_id) as platforms_downloaded,
          MAX(dl.created_at) as last_download_at
        FROM users u
        LEFT JOIN download_logs dl ON dl.user_id = u.id
        LEFT JOIN devices d ON d.id = dl.device_id
        WHERE ${where}
        GROUP BY u.id
        ORDER BY u.created_at DESC
        LIMIT ? OFFSET ?
      `).bind(...bindings, limit, offset).all(),
      env.DB.prepare(`SELECT COUNT(*) as c FROM users u WHERE ${where}`).bind(...bindings).first<{ c: number }>(),
    ]);
    return jsonResponse({ items: items.results, total: count?.c ?? 0, page, limit });
  }

  // GET /v1/admin/install-ids
  if (path === "/v1/admin/install-ids" && request.method === "GET") {
    const url = new URL(request.url);
    const page = Math.max(1, parseInt(url.searchParams.get("page") || "1"));
    const limit = 20;
    const offset = (page - 1) * limit;

    const [items, count] = await Promise.all([
      env.DB.prepare(`
        SELECT
          dl.install_id,
          COUNT(DISTINCT dl.id) as downloads_total,
          COUNT(DISTINCT dl.device_id) as devices_downloaded,
          COUNT(DISTINCT d.platform_id) as platforms_downloaded,
          MIN(dl.created_at) as first_seen_at,
          MAX(dl.created_at) as last_seen_at
        FROM download_logs dl
        LEFT JOIN devices d ON d.id = dl.device_id
        WHERE dl.install_id IS NOT NULL
        GROUP BY dl.install_id
        ORDER BY last_seen_at DESC
        LIMIT ? OFFSET ?
      `).bind(limit, offset).all(),
      env.DB.prepare("SELECT COUNT(DISTINCT install_id) as c FROM download_logs WHERE install_id IS NOT NULL").first<{ c: number }>(),
    ]);
    return jsonResponse({ items: items.results, total: count?.c ?? 0, page, limit });
  }

  // ── Platform Management ──────────────────────────────────────────────────

  if (path === "/v1/admin/platforms") {
    if (request.method === "GET") {
      const url = new URL(request.url);
      const search = url.searchParams.get("search") || "";
      const status = url.searchParams.get("status") || "";
      const page = Math.max(1, parseInt(url.searchParams.get("page") || "1"));
      const limit = 20;
      const offset = (page - 1) * limit;

      let where = "1=1";
      const bindings: unknown[] = [];
      if (search) { where += " AND (name_en LIKE ? OR name_zh LIKE ? OR id LIKE ?)"; bindings.push(`%${search}%`, `%${search}%`, `%${search}%`); }
      if (status) { where += " AND status = ?"; bindings.push(status); }

      const [items, count] = await Promise.all([
        env.DB.prepare(`SELECT * FROM hardware_platforms WHERE ${where} ORDER BY created_at DESC LIMIT ? OFFSET ?`).bind(...bindings, limit, offset).all(),
        env.DB.prepare(`SELECT COUNT(*) as c FROM hardware_platforms WHERE ${where}`).bind(...bindings).first<{ c: number }>(),
      ]);
      return jsonResponse({ items: items.results, total: count?.c ?? 0, page, limit });
    }

    if (request.method === "POST") {
      let body: any;
      try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
      const { id, name_en, name_zh, aliases, description_en, description_zh, logo_url, website_url, status = "draft" } = body;
      if (!id?.trim()) return badRequest("id is required");
      if (!name_en?.trim()) return badRequest("name_en is required");

      // aliases can be array or comma-separated string — normalize to JSON array string
      const aliasesJson = aliases
        ? JSON.stringify(Array.isArray(aliases) ? aliases : aliases.split(',').map((s: string) => s.trim()).filter(Boolean))
        : null;

      const ts = now();
      await env.DB.prepare(
        "INSERT INTO hardware_platforms (id, name_en, name_zh, aliases, description_en, description_zh, logo_url, website_url, status, created_by, updated_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
      ).bind(id.trim(), name_en.trim(), name_zh || null, aliasesJson, description_en || null, description_zh || null, logo_url || null, website_url || null, status, admin.id, admin.id, ts, ts).run();
      if (status === "published") await syncCatalogToR2(env);
      return jsonResponse({ success: true }, 201);
    }
  }

  const platformById = path.match(/^\/v1\/admin\/platforms\/([^/]+)$/);
  if (platformById) {
    const id = platformById[1];
    if (request.method === "PUT") {
      let body: any;
      try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
      const { name_en, name_zh, aliases, description_en, description_zh, logo_url, website_url, status } = body;
      const aliasesJson = aliases !== undefined
        ? JSON.stringify(Array.isArray(aliases) ? aliases : aliases.split(',').map((s: string) => s.trim()).filter(Boolean))
        : null;
      await env.DB.prepare(
        "UPDATE hardware_platforms SET name_en=COALESCE(?,name_en), name_zh=COALESCE(?,name_zh), aliases=COALESCE(?,aliases), description_en=COALESCE(?,description_en), description_zh=COALESCE(?,description_zh), logo_url=COALESCE(?,logo_url), website_url=COALESCE(?,website_url), status=COALESCE(?,status), updated_by=?, updated_at=? WHERE id=?"
      ).bind(name_en||null, name_zh||null, aliasesJson, description_en||null, description_zh||null, logo_url||null, website_url||null, status||null, admin.id, now(), id).run();
      await syncCatalogToR2(env);
      return jsonResponse({ success: true });
    }
    if (request.method === "DELETE") {
      if (admin.role !== "super") return forbidden("Super admin required");
      await env.DB.prepare("DELETE FROM hardware_platforms WHERE id = ?").bind(id).run();
      await syncCatalogToR2(env);
      return jsonResponse({ success: true });
    }
  }

  // ── Device Management ────────────────────────────────────────────────────

  if (path === "/v1/admin/devices") {
    if (request.method === "GET") {
      const url = new URL(request.url);
      const search = url.searchParams.get("search") || "";
      const platform = url.searchParams.get("platform") || "";
      const status = url.searchParams.get("status") || "";
      const page = Math.max(1, parseInt(url.searchParams.get("page") || "1"));
      const limit = 20;
      const offset = (page - 1) * limit;

      let where = "1=1";
      const bindings: unknown[] = [];
      if (search) { where += " AND (d.name_en LIKE ? OR d.name_zh LIKE ? OR d.product_id LIKE ?)"; bindings.push(`%${search}%`, `%${search}%`, `%${search}%`); }
      if (platform) { where += " AND d.platform_id = ?"; bindings.push(platform); }
      if (status) { where += " AND d.status = ?"; bindings.push(status); }

      const [items, count] = await Promise.all([
        env.DB.prepare(`SELECT d.*, p.name_en as platform_name FROM devices d LEFT JOIN hardware_platforms p ON p.id = d.platform_id WHERE ${where} ORDER BY d.created_at DESC LIMIT ? OFFSET ?`).bind(...bindings, limit, offset).all(),
        env.DB.prepare(`SELECT COUNT(*) as c FROM devices d WHERE ${where}`).bind(...bindings).first<{ c: number }>(),
      ]);
      return jsonResponse({ items: items.results, total: count?.c ?? 0, page, limit });
    }

    if (request.method === "POST") {
      let body: any;
      try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
      const { product_id, name_en, name_zh, platform_id, detail_image_url, github_url, is_featured = 0, status = "draft" } = body;
      if (!product_id?.trim()) return badRequest("product_id is required");
      if (!name_en?.trim()) return badRequest("name_en is required");
      if (!platform_id?.trim()) return badRequest("platform_id is required");

      const id = uuid();
      const ts = now();
      await env.DB.prepare(
        "INSERT INTO devices (id, product_id, name_en, name_zh, platform_id, detail_image_url, github_url, is_featured, status, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
      ).bind(id, product_id.trim(), name_en.trim(), name_zh||null, platform_id.trim(), detail_image_url||null, github_url||null, is_featured?1:0, status, admin.id, ts, ts).run();
      return jsonResponse({ id }, 201);
    }
  }

  const deviceById = path.match(/^\/v1\/admin\/devices\/([^/]+)$/);
  if (deviceById) {
    const id = deviceById[1];
    if (request.method === "PUT") {
      let body: any;
      try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
      const { name_en, name_zh, platform_id, detail_image_url, github_url, is_featured, status } = body;
      await env.DB.prepare(
        "UPDATE devices SET name_en=COALESCE(?,name_en), name_zh=COALESCE(?,name_zh), platform_id=COALESCE(?,platform_id), detail_image_url=COALESCE(?,detail_image_url), github_url=COALESCE(?,github_url), is_featured=COALESCE(?,is_featured), status=COALESCE(?,status), updated_at=? WHERE id=?"
      ).bind(name_en||null, name_zh||null, platform_id||null, detail_image_url||null, github_url||null, is_featured!=null?is_featured:null, status||null, now(), id).run();
      return jsonResponse({ success: true });
    }
    if (request.method === "DELETE") {
      if (admin.role !== "super") return forbidden("Super admin required");
      await env.DB.prepare("DELETE FROM device_versions WHERE device_id = ?").bind(id).run();
      await env.DB.prepare("DELETE FROM devices WHERE id = ?").bind(id).run();
      return jsonResponse({ success: true });
    }
  }

  // ── Device Versions ──────────────────────────────────────────────────────

  const deviceVersions = path.match(/^\/v1\/admin\/devices\/([^/]+)\/versions$/);
  if (deviceVersions) {
    const deviceId = deviceVersions[1];
    if (request.method === "GET") {
      const { results } = await env.DB.prepare(
        "SELECT * FROM device_versions WHERE device_id = ? ORDER BY created_at DESC"
      ).bind(deviceId).all();
      return jsonResponse(results);
    }
    if (request.method === "POST") {
      let body: any;
      try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
      const { version, zip_r2_key, action_specs_r2_key, readme_r2_key, is_latest = false } = body;
      if (!version?.trim()) return badRequest("version is required");

      const id = uuid();
      const ts = now();
      if (is_latest) {
        await env.DB.prepare("UPDATE device_versions SET is_latest = 0 WHERE device_id = ?").bind(deviceId).run();
      }
      await env.DB.prepare(
        "INSERT INTO device_versions (id, device_id, version, is_latest, zip_r2_key, action_specs_r2_key, readme_r2_key, published_at, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
      ).bind(id, deviceId, version.trim(), is_latest?1:0, zip_r2_key||null, action_specs_r2_key||null, readme_r2_key||null, ts, admin.id, ts).run();
      return jsonResponse({ id }, 201);
    }
  }

  // ── File Upload ──────────────────────────────────────────────────────────

  if (path === "/v1/admin/upload" && request.method === "POST") {
    const formData = await request.formData();
    const file = formData.get("file") as File | null;
    const type = formData.get("type") as string | null;
    if (!file) return badRequest("file is required");
    if (!type) return badRequest("type is required");

    const ext = file.name.split(".").pop() || "bin";
    const key = `uploads/${type}/${uuid()}.${ext}`;
    await env.ASSETS.put(key, file.stream(), {
      httpMetadata: { contentType: file.type || "application/octet-stream" },
    });

    const url = `https://entroflow.ai/api/uploads/${key}`;
    return jsonResponse({ url, r2_key: key }, 201);
  }

  // ── Docs Management ──────────────────────────────────────────────────────

  if (path === "/v1/admin/docs" && request.method === "GET") {
    const { results: sections } = await env.DB.prepare("SELECT * FROM doc_sections ORDER BY sort_order ASC").all();
    const docs = await Promise.all(sections.map(async (s: any) => {
      const { results: items } = await env.DB.prepare("SELECT * FROM doc_items WHERE section_id = ? ORDER BY sort_order ASC").bind(s.id).all();
      return { ...s, items };
    }));
    return jsonResponse(docs);
  }

  if (path === "/v1/admin/docs/sections" && request.method === "POST") {
    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
    const { key, title_en, title_zh, sort_order = 0 } = body;
    if (!key?.trim() || !title_en?.trim()) return badRequest("key and title_en required");
    const id = uuid();
    await env.DB.prepare("INSERT INTO doc_sections (id, key, title_en, title_zh, sort_order) VALUES (?, ?, ?, ?, ?)")
      .bind(id, key.trim(), title_en.trim(), title_zh||null, sort_order).run();
    return jsonResponse({ id }, 201);
  }

  if (path === "/v1/admin/docs/items" && request.method === "POST") {
    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
    const { section_id, slug, title_en, title_zh, content_en = "", content_zh = "", sort_order = 0, status = "draft" } = body;
    if (!section_id || !slug?.trim() || !title_en?.trim()) return badRequest("section_id, slug, title_en required");
    const id = uuid();
    const ts = now();
    await env.DB.prepare(
      "INSERT INTO doc_items (id, section_id, slug, title_en, title_zh, content_en, content_zh, sort_order, status, updated_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ).bind(id, section_id, slug.trim(), title_en.trim(), title_zh||null, content_en, content_zh, sort_order, status, admin.id, ts, ts).run();
    return jsonResponse({ id }, 201);
  }

  const docItemById = path.match(/^\/v1\/admin\/docs\/items\/([^/]+)$/);
  if (docItemById) {
    const id = docItemById[1];
    if (request.method === "PUT") {
      let body: any;
      try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
      const { title_en, title_zh, content_en, content_zh, sort_order, status } = body;
      await env.DB.prepare(
        "UPDATE doc_items SET title_en=COALESCE(?,title_en), title_zh=COALESCE(?,title_zh), content_en=COALESCE(?,content_en), content_zh=COALESCE(?,content_zh), sort_order=COALESCE(?,sort_order), status=COALESCE(?,status), updated_by=?, updated_at=? WHERE id=?"
      ).bind(title_en||null, title_zh||null, content_en||null, content_zh||null, sort_order!=null?sort_order:null, status||null, admin.id, now(), id).run();
      return jsonResponse({ success: true });
    }
    if (request.method === "DELETE") {
      await env.DB.prepare("DELETE FROM doc_items WHERE id = ?").bind(id).run();
      return jsonResponse({ success: true });
    }
  }

  // ── Feedback Management ──────────────────────────────────────────────────

  if (path === "/v1/admin/feedback" && request.method === "GET") {
    const url = new URL(request.url);
    const search = url.searchParams.get("search") || "";
    const status = url.searchParams.get("status") || "";
    const page = Math.max(1, parseInt(url.searchParams.get("page") || "1"));
    const limit = 20;
    const offset = (page - 1) * limit;

    let where = "1=1";
    const bindings: unknown[] = [];
    if (search) { where += " AND (email LIKE ? OR content LIKE ?)"; bindings.push(`%${search}%`, `%${search}%`); }
    if (status) { where += " AND status = ?"; bindings.push(status); }

    const [items, count] = await Promise.all([
      env.DB.prepare(`SELECT f.*, a.name as assignee_name FROM feedback f LEFT JOIN admins a ON a.id = f.assignee_id WHERE ${where} ORDER BY f.created_at DESC LIMIT ? OFFSET ?`).bind(...bindings, limit, offset).all(),
      env.DB.prepare(`SELECT COUNT(*) as c FROM feedback WHERE ${where}`).bind(...bindings).first<{ c: number }>(),
    ]);
    return jsonResponse({ items: items.results, total: count?.c ?? 0, page, limit });
  }

  const feedbackById = path.match(/^\/v1\/admin\/feedback\/([^/]+)$/);
  if (feedbackById && request.method === "PUT") {
    const id = feedbackById[1];
    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
    const { status, note } = body;
    const assignee_id = status === "in_review" || status === "resolved" ? admin.id : null;
    await env.DB.prepare(
      "UPDATE feedback SET status=COALESCE(?,status), note=COALESCE(?,note), assignee_id=COALESCE(?,assignee_id), updated_at=? WHERE id=?"
    ).bind(status||null, note||null, assignee_id, now(), id).run();
    return jsonResponse({ success: true });
  }

  // ── Business Inquiries ───────────────────────────────────────────────────

  if (path === "/v1/admin/business" && request.method === "GET") {
    const url = new URL(request.url);
    const search = url.searchParams.get("search") || "";
    const status = url.searchParams.get("status") || "";
    const page = Math.max(1, parseInt(url.searchParams.get("page") || "1"));
    const limit = 20;
    const offset = (page - 1) * limit;

    let where = "1=1";
    const bindings: unknown[] = [];
    if (search) { where += " AND (company LIKE ? OR email LIKE ? OR content LIKE ?)"; bindings.push(`%${search}%`, `%${search}%`, `%${search}%`); }
    if (status) { where += " AND status = ?"; bindings.push(status); }

    const [items, count] = await Promise.all([
      env.DB.prepare(`SELECT b.*, a.name as assignee_name FROM business_inquiries b LEFT JOIN admins a ON a.id = b.assignee_id WHERE ${where} ORDER BY b.created_at DESC LIMIT ? OFFSET ?`).bind(...bindings, limit, offset).all(),
      env.DB.prepare(`SELECT COUNT(*) as c FROM business_inquiries WHERE ${where}`).bind(...bindings).first<{ c: number }>(),
    ]);
    return jsonResponse({ items: items.results, total: count?.c ?? 0, page, limit });
  }

  const businessById = path.match(/^\/v1\/admin\/business\/([^/]+)$/);
  if (businessById && request.method === "PUT") {
    const id = businessById[1];
    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
    const { status, note } = body;
    const assignee_id = status === "in_review" || status === "resolved" ? admin.id : null;
    await env.DB.prepare(
      "UPDATE business_inquiries SET status=COALESCE(?,status), note=COALESCE(?,note), assignee_id=COALESCE(?,assignee_id), updated_at=? WHERE id=?"
    ).bind(status||null, note||null, assignee_id, now(), id).run();
    return jsonResponse({ success: true });
  }

  // ── AI Platforms ─────────────────────────────────────────────────────────

  if (path === "/v1/admin/ai-platforms") {
    if (request.method === "GET") {
      const { results } = await env.DB.prepare("SELECT * FROM ai_platforms ORDER BY sort_order ASC").all();
      return jsonResponse(results);
    }
    if (request.method === "POST") {
      let body: any;
      try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
      const { id, name_en, name_zh, logo_url, sort_order = 0, is_active = 1 } = body;
      if (!id?.trim() || !name_en?.trim()) return badRequest("id and name_en required");
      const ts = now();
      await env.DB.prepare(
        "INSERT INTO ai_platforms (id, name_en, name_zh, logo_url, sort_order, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
      ).bind(id.trim(), name_en.trim(), name_zh||null, logo_url||null, sort_order, is_active?1:0, ts, ts).run();
      return jsonResponse({ success: true }, 201);
    }
  }

  const aiPlatformById = path.match(/^\/v1\/admin\/ai-platforms\/([^/]+)$/);
  if (aiPlatformById) {
    const id = aiPlatformById[1];
    if (request.method === "PUT") {
      let body: any;
      try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
      const { name_en, name_zh, logo_url, sort_order, is_active } = body;
      await env.DB.prepare(
        "UPDATE ai_platforms SET name_en=COALESCE(?,name_en), name_zh=COALESCE(?,name_zh), logo_url=COALESCE(?,logo_url), sort_order=COALESCE(?,sort_order), is_active=COALESCE(?,is_active), updated_at=? WHERE id=?"
      ).bind(name_en||null, name_zh||null, logo_url||null, sort_order!=null?sort_order:null, is_active!=null?is_active:null, now(), id).run();
      return jsonResponse({ success: true });
    }
    if (request.method === "DELETE") {
      await env.DB.prepare("DELETE FROM ai_platforms WHERE id = ?").bind(id).run();
      return jsonResponse({ success: true });
    }
  }

  return null;
}
