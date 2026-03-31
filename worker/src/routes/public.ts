import { Env } from "../lib/types";
import { jsonResponse, notFound, badRequest, uuid, now, getAuthToken, verifyJwt } from "../lib/utils";

async function ensureAgentInstallTables(env: Env): Promise<void> {
  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS agent_install_platforms (
      id           TEXT PRIMARY KEY,
      install_id   TEXT NOT NULL,
      platform_key TEXT NOT NULL,
      platform_label TEXT NOT NULL,
      created_at   INTEGER NOT NULL,
      updated_at   INTEGER NOT NULL,
      UNIQUE(install_id, platform_key)
    )
  `).run();
  await env.DB.prepare(
    "CREATE INDEX IF NOT EXISTS idx_agent_install_platforms_install ON agent_install_platforms(install_id)"
  ).run();
  await env.DB.prepare(
    "CREATE INDEX IF NOT EXISTS idx_agent_install_platforms_platform ON agent_install_platforms(platform_key)"
  ).run();
}

function normalizeAgentPlatforms(input: unknown): Array<{ key: string; label: string }> {
  if (!Array.isArray(input)) return [];

  const normalized: Array<{ key: string; label: string }> = [];
  const seen = new Set<string>();

  for (const item of input) {
    if (typeof item !== "string") continue;
    const label = item.trim();
    if (!label) continue;
    const key = label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    if (!key || seen.has(key)) continue;
    seen.add(key);
    normalized.push({ key, label });
  }

  return normalized;
}

export async function handlePublicRoutes(path: string, request: Request, env: Env): Promise<Response | null> {

  // GET /v1/stats
  if (path === "/v1/stats" && request.method === "GET") {
    await ensureAgentInstallTables(env);

    const [devicesResult, platformsResult, agentInstallsResult, downloadsResult] = await Promise.all([
      env.DB.prepare("SELECT COUNT(*) as count FROM devices WHERE status = 'published'").first<{ count: number }>(),
      env.DB.prepare("SELECT COUNT(*) as count FROM hardware_platforms WHERE status = 'published'").first<{ count: number }>(),
      env.DB.prepare("SELECT COUNT(*) as count FROM agent_install_platforms").first<{ count: number }>(),
      env.DB.prepare("SELECT COALESCE(SUM(downloads_count), 0) as count FROM devices WHERE status = 'published'").first<{ count: number }>(),
    ]);
    return jsonResponse({
      devices_count: devicesResult?.count ?? 0,
      platforms_count: platformsResult?.count ?? 0,
      agent_installs_count: agentInstallsResult?.count ?? 0,
      downloads_total: downloadsResult?.count ?? 0,
    });
  }

  // POST /v1/agent-installs/report
  if (path === "/v1/agent-installs/report" && request.method === "POST") {
    await ensureAgentInstallTables(env);

    const body = await request.json().catch(() => null) as {
      install_id?: unknown;
      platforms?: unknown;
    } | null;

    const installId = typeof body?.install_id === "string" ? body.install_id.trim() : "";
    if (!installId) return badRequest("install_id is required");
    if (installId.length > 128) return badRequest("install_id is invalid");

    const platforms = normalizeAgentPlatforms(body?.platforms);
    const timestamp = now();

    await env.DB.prepare("DELETE FROM agent_install_platforms WHERE install_id = ?").bind(installId).run();

    for (const platform of platforms) {
      await env.DB.prepare(`
        INSERT INTO agent_install_platforms (id, install_id, platform_key, platform_label, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
      `).bind(uuid(), installId, platform.key, platform.label, timestamp, timestamp).run();
    }

    return jsonResponse({
      ok: true,
      install_id: installId,
      platforms_count: platforms.length,
      platforms,
    });
  }

  // GET /v1/ai-platforms
  if (path === "/v1/ai-platforms" && request.method === "GET") {
    const { results } = await env.DB.prepare(
      "SELECT id, name_en, name_zh, logo_url FROM ai_platforms WHERE is_active = 1 ORDER BY sort_order ASC"
    ).all();
    return jsonResponse(results);
  }

  // GET /v1/platforms
  if (path === "/v1/platforms" && request.method === "GET") {
    const url = new URL(request.url);
    const lang = url.searchParams.get("lang") || "en";
    const { results } = await env.DB.prepare(`
      SELECT
        p.id, p.name_en, p.name_zh, p.sort_order, p.description_en, p.description_zh,
        p.logo_url, p.website_url,
        COUNT(d.id) as device_count
      FROM hardware_platforms p
      LEFT JOIN devices d ON d.platform_id = p.id AND d.status = 'published'
      WHERE p.status = 'published'
      GROUP BY p.id
      ORDER BY p.sort_order ASC, p.name_en ASC
    `).all();
    return jsonResponse(results);
  }

  // GET /v1/platforms/:id
  const platformDetail = path.match(/^\/v1\/platforms\/([^/]+)$/);
  if (platformDetail && request.method === "GET") {
    const id = platformDetail[1];
    const platform = await env.DB.prepare(`
      SELECT p.*, COUNT(d.id) as device_count
      FROM hardware_platforms p
      LEFT JOIN devices d ON d.platform_id = p.id AND d.status = 'published'
      WHERE p.id = ? AND p.status = 'published'
      GROUP BY p.id
    `).bind(id).first();
    if (!platform) return notFound(`Platform '${id}' not found`);
    return jsonResponse(platform);
  }

  // GET /v1/devices
  if (path === "/v1/devices" && request.method === "GET") {
    const url = new URL(request.url);
    const platform = url.searchParams.get("platform") || "";
    const search = url.searchParams.get("search") || "";
    const featured = url.searchParams.get("featured") || "";
    const page = Math.max(1, parseInt(url.searchParams.get("page") || "1"));
    const limit = Math.min(50, parseInt(url.searchParams.get("limit") || "20"));
    const offset = (page - 1) * limit;

    let where = "d.status = 'published'";
    const bindings: unknown[] = [];

    if (platform) {
      where += " AND d.platform_id = ?";
      bindings.push(platform);
    }
    if (search) {
      where += " AND (d.name_en LIKE ? OR d.name_zh LIKE ? OR d.product_id LIKE ?)";
      bindings.push(`%${search}%`, `%${search}%`, `%${search}%`);
    }
    if (featured === "true") {
      where += " AND d.is_featured = 1";
    }

    const [itemsResult, countResult] = await Promise.all([
      env.DB.prepare(`
        SELECT d.id, d.product_id, d.name_en, d.name_zh, d.platform_id,
               d.downloads_count, d.detail_image_url, d.github_url, d.is_featured,
               p.name_en as platform_name_en, p.name_zh as platform_name_zh, p.logo_url as platform_logo_url
        FROM devices d
        LEFT JOIN hardware_platforms p ON p.id = d.platform_id
        WHERE ${where}
        ORDER BY d.is_featured DESC, d.downloads_count DESC
        LIMIT ? OFFSET ?
      `).bind(...bindings, limit, offset).all(),
      env.DB.prepare(`SELECT COUNT(*) as count FROM devices d WHERE ${where}`)
        .bind(...bindings).first<{ count: number }>(),
    ]);

    return jsonResponse({
      items: itemsResult.results,
      total: countResult?.count ?? 0,
      page,
      limit,
    });
  }

  // GET /v1/devices/:product_id
  const deviceDetail = path.match(/^\/v1\/devices\/([^/]+)$/);
  if (deviceDetail && request.method === "GET") {
    const product_id = deviceDetail[1];
    const device = await env.DB.prepare(`
      SELECT d.*, p.name_en as platform_name_en, p.name_zh as platform_name_zh,
             p.logo_url as platform_logo_url, p.website_url as platform_website_url
      FROM devices d
      LEFT JOIN hardware_platforms p ON p.id = d.platform_id
      WHERE d.product_id = ? AND d.status = 'published'
    `).bind(product_id).first();
    if (!device) return notFound(`Device '${product_id}' not found`);

    const { results: versions } = await env.DB.prepare(
      "SELECT id, version, is_latest, zip_r2_key, action_specs_r2_key, readme_r2_key, published_at FROM device_versions WHERE device_id = ? ORDER BY published_at DESC"
    ).bind((device as any).id).all();

    return jsonResponse({ ...device, versions });
  }

  // GET /v1/devices/:product_id/versions
  const deviceVersions = path.match(/^\/v1\/devices\/([^/]+)\/versions$/);
  if (deviceVersions && request.method === "GET") {
    const product_id = deviceVersions[1];
    const device = await env.DB.prepare("SELECT id FROM devices WHERE product_id = ? AND status = 'published'").bind(product_id).first<{ id: string }>();
    if (!device) return notFound(`Device '${product_id}' not found`);
    const { results } = await env.DB.prepare(
      "SELECT version, is_latest, published_at FROM device_versions WHERE device_id = ? ORDER BY published_at DESC"
    ).bind(device.id).all();
    return jsonResponse(results);
  }

  // GET /v1/docs
  if (path === "/v1/docs" && request.method === "GET") {
    const url = new URL(request.url);
    const lang = url.searchParams.get("lang") || "en";
    const { results: sections } = await env.DB.prepare(
      "SELECT id, key, title_en, title_zh, sort_order FROM doc_sections ORDER BY sort_order ASC"
    ).all();

    const docs = await Promise.all(sections.map(async (section: any) => {
      const { results: items } = await env.DB.prepare(
        "SELECT slug, title_en, title_zh, sort_order FROM doc_items WHERE section_id = ? AND status = 'published' ORDER BY sort_order ASC"
      ).bind(section.id).all();
      return { ...section, items };
    }));

    return jsonResponse(docs);
  }

  // GET /v1/docs/:slug
  const docItem = path.match(/^\/v1\/docs\/([^/]+)$/);
  if (docItem && request.method === "GET") {
    const slug = docItem[1];
    const url = new URL(request.url);
    const lang = url.searchParams.get("lang") || "en";
    const item = await env.DB.prepare(
      "SELECT slug, title_en, title_zh, content_en, content_zh FROM doc_items WHERE slug = ? AND status = 'published'"
    ).bind(slug).first();
    if (!item) return notFound(`Doc '${slug}' not found`);
    return jsonResponse(item);
  }

  // POST /v1/feedback
  if (path === "/v1/feedback" && request.method === "POST") {
    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }

    const { content, email } = body;
    if (!content?.trim()) return badRequest("content is required");

    // 检查是否登录
    let userId: string | null = null;
    let loginType = "guest";
    let userEmail: string | null = email || null;

    const token = getAuthToken(request);
    if (token) {
      const payload = await verifyJwt(token, env.JWT_SECRET);
      if (payload) {
        userId = payload.sub;
        loginType = payload.provider || "email";
        if (loginType === "email") userEmail = payload.email; // 邮箱登录自动带入
      }
    }

    if (!userEmail?.trim() && loginType === "guest") return badRequest("email is required for guests");

    await env.DB.prepare(
      "INSERT INTO feedback (id, email, user_id, login_type, content, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'new', ?, ?)"
    ).bind(uuid(), userEmail, userId, loginType, content.trim(), now(), now()).run();

    return jsonResponse({ success: true }, 201);
  }

  // POST /v1/business
  if (path === "/v1/business" && request.method === "POST") {
    let body: any;
    try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }

    const { company, email, content } = body;
    if (!company?.trim()) return badRequest("company is required");
    if (!email?.trim()) return badRequest("email is required");
    if (!content?.trim()) return badRequest("content is required");

    await env.DB.prepare(
      "INSERT INTO business_inquiries (id, company, email, content, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'new', ?, ?)"
    ).bind(uuid(), company.trim(), email.trim(), content.trim(), now(), now()).run();

    return jsonResponse({ success: true }, 201);
  }

  return null;
}
