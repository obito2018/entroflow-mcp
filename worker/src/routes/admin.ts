import { Env } from "../lib/types";
import { jsonResponse, notFound, unauthorized, badRequest, forbidden, uuid, now, signJwt, verifyJwt, hashPassword, verifyPassword, getAuthToken } from "../lib/utils";
import {
  buildPlatformGuideManifest,
  ensurePlatformGuideTables,
  getLatestPublishedPlatformGuide,
  getPlatformGuideLocaleKey,
  getPlatformGuideManifestKey,
  isConnectorVersionSupported,
  PlatformGuideRow,
} from "../lib/platform_guides";
import JSZip from "jszip";

async function requireAdmin(request: Request, env: Env): Promise<{ id: string; role: string } | Response> {
  const token = getAuthToken(request);
  if (!token) return unauthorized();
  const payload = await verifyJwt(token, env.ADMIN_JWT_SECRET);
  if (!payload || !payload.role) return unauthorized("Invalid admin token");
  return { id: payload.sub, role: payload.role };
}

function normalizeAliases(input: unknown, depth = 0): string[] {
  if (input == null || depth > 8) return [];

  if (Array.isArray(input)) {
    const flattened = input.flatMap((item) => normalizeAliases(item, depth + 1));
    return flattened.filter((value, index, arr) => value && arr.indexOf(value) === index);
  }

  if (typeof input !== "string") {
    return [];
  }

  const trimmed = input.trim();
  if (!trimmed) return [];

  if (
    (trimmed.startsWith("[") && trimmed.endsWith("]")) ||
    (trimmed.startsWith("\"") && trimmed.endsWith("\""))
  ) {
    try {
      return normalizeAliases(JSON.parse(trimmed), depth + 1);
    } catch {
      // Fall through to plain-text normalization.
    }
  }

  const values = trimmed
    .split(/[，,]/)
    .map((value) => value.trim().replace(/^[\s"'[\]\\]+|[\s"'[\]\\]+$/g, "").trim())
    .filter(Boolean);

  return values.filter((value, index, arr) => arr.indexOf(value) === index);
}

type PythonLiteral =
  | string
  | number
  | boolean
  | null
  | PythonLiteral[]
  | { [key: string]: PythonLiteral };

class PythonLiteralParser {
  private index = 0;

  constructor(private readonly input: string) {}

  parseValue(): PythonLiteral {
    this.skipWhitespace();
    const ch = this.peek();
    if (ch === "{") return this.parseDict();
    if (ch === "[") return this.parseList();
    if (ch === "'" || ch === "\"") return this.parseString();
    if (ch === "-" || this.isDigit(ch)) return this.parseNumber();
    return this.parseIdentifier();
  }

  private parseDict(): { [key: string]: PythonLiteral } {
    const result: { [key: string]: PythonLiteral } = {};
    this.expect("{");
    this.skipWhitespace();
    while (this.peek() !== "}") {
      const rawKey = this.parseValue();
      const key = typeof rawKey === "string" ? rawKey : String(rawKey);
      this.skipWhitespace();
      this.expect(":");
      result[key] = this.parseValue();
      this.skipWhitespace();
      if (this.peek() === ",") {
        this.index += 1;
        this.skipWhitespace();
      } else {
        break;
      }
    }
    this.expect("}");
    return result;
  }

  private parseList(): PythonLiteral[] {
    const result: PythonLiteral[] = [];
    this.expect("[");
    this.skipWhitespace();
    while (this.peek() !== "]") {
      result.push(this.parseValue());
      this.skipWhitespace();
      if (this.peek() === ",") {
        this.index += 1;
        this.skipWhitespace();
      } else {
        break;
      }
    }
    this.expect("]");
    return result;
  }

  private parseString(): string {
    const quote = this.peek();
    this.expect(quote);
    let value = "";
    while (this.index < this.input.length) {
      const ch = this.input[this.index++];
      if (ch === "\\") {
        value += this.input[this.index++] ?? "";
        continue;
      }
      if (ch === quote) return value;
      value += ch;
    }
    throw new Error("Unterminated string literal.");
  }

  private parseNumber(): number {
    const start = this.index;
    if (this.peek() === "-") this.index += 1;
    while (this.isDigit(this.peek())) this.index += 1;
    if (this.peek() === ".") {
      this.index += 1;
      while (this.isDigit(this.peek())) this.index += 1;
    }
    const raw = this.input.slice(start, this.index);
    const num = Number(raw);
    if (Number.isNaN(num)) throw new Error(`Invalid number literal: ${raw}`);
    return num;
  }

  private parseIdentifier(): PythonLiteral {
    const start = this.index;
    while (/[A-Za-z0-9_]/.test(this.peek())) this.index += 1;
    const raw = this.input.slice(start, this.index);
    if (raw === "True") return true;
    if (raw === "False") return false;
    if (raw === "None") return null;
    if (!raw) throw new Error(`Unexpected token at position ${this.index}.`);
    return raw;
  }

  private skipWhitespace() {
    while (/\s/.test(this.peek())) this.index += 1;
  }

  private expect(ch: string) {
    if (this.peek() !== ch) {
      throw new Error(`Expected '${ch}' at position ${this.index}.`);
    }
    this.index += 1;
  }

  private peek(): string {
    return this.input[this.index] ?? "";
  }

  private isDigit(ch: string): boolean {
    return ch >= "0" && ch <= "9";
  }
}

function extractAssignmentCollection(source: string, name: string): string | null {
  const matcher = new RegExp(`(?:^|\\n)${name}\\s*=\\s*([\\[{])`, "m");
  const match = matcher.exec(source);
  if (!match) return null;

  const openChar = match[1];
  const closeChar = openChar === "[" ? "]" : "}";
  const start = (match.index ?? 0) + match[0].lastIndexOf(openChar);

  let depth = 0;
  let quote: string | null = null;
  let escaped = false;

  for (let i = start; i < source.length; i += 1) {
    const ch = source[i];
    if (quote) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === "\\") {
        escaped = true;
        continue;
      }
      if (ch === quote) {
        quote = null;
      }
      continue;
    }

    if (ch === "'" || ch === "\"") {
      quote = ch;
      continue;
    }
    if (ch === openChar) depth += 1;
    if (ch === closeChar) {
      depth -= 1;
      if (depth === 0) {
        return source.slice(start, i + 1);
      }
    }
  }

  return null;
}

function parsePythonAssignment<T extends PythonLiteral>(source: string, name: string): T | null {
  const block = extractAssignmentCollection(source, name);
  if (!block) return null;
  const parser = new PythonLiteralParser(block);
  return parser.parseValue() as T;
}

function asString(value: PythonLiteral | undefined, fallback = "-"): string {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function humanizeKey(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatActionSpecArg(value: string): string {
  if (!value || value === "-") return "-";
  if (value.toLowerCase() === "none") return "None";
  return `\`${value}\``;
}

function inferStatusFields(
  actionSpecs: Array<{ [key: string]: PythonLiteral }>,
  miotMapping: { [key: string]: PythonLiteral } | null,
  statusFields: Array<{ [key: string]: PythonLiteral }> | null,
): string[] {
  if (statusFields?.length) {
    return statusFields
      .map((item) => {
        const field = asString(item.field ?? item.name);
        if (!field || field === "-") return "";
        const description = asString(item.description, humanizeKey(field));
        const type = asString(item.type, "string");
        return `| \`${field}\` | ${description} | ${type} |`;
      })
      .filter(Boolean);
  }

  if (!miotMapping) return [];

  const rows = Object.keys(miotMapping).map((field) => {
    const matchingAction = actionSpecs.find((item) => asString(item.action) === `set_${field}`);
    const description = field === "power" ? "Power state" : humanizeKey(field);
    const type = field === "power" ? "bool" : asString(matchingAction?.range);
    return `| \`${field}\` | ${description} | ${type} |`;
  });

  return rows.filter(Boolean);
}

function generateActionSpecsMarkdown(pySource: string, pyFileName: string): string {
  const deviceInfo = parsePythonAssignment<{ [key: string]: PythonLiteral }>(pySource, "DEVICE_INFO") ?? {};
  const specs = parsePythonAssignment<PythonLiteral[]>(pySource, "ACTION_SPECS");
  const miotMapping = parsePythonAssignment<{ [key: string]: PythonLiteral }>(pySource, "MIOT_MAPPING");
  const statusFields = parsePythonAssignment<PythonLiteral[]>(pySource, "STATUS_FIELDS");

  if (specs && !Array.isArray(specs)) {
    throw new Error("Device ZIP ACTION_SPECS must be a list in the Python file.");
  }

  const model = asString(deviceInfo.model, pyFileName.replace(/\.py$/i, ""));
  const deviceName = asString(deviceInfo.display_name, model);
  const platform = asString(deviceInfo.platform);
  const actionSpecs = (Array.isArray(specs) ? specs : [])
    .filter((item): item is { [key: string]: PythonLiteral } => typeof item === "object" && item !== null && !Array.isArray(item))
    .filter((item) => asString(item.action) !== "query_status");

  const rows = actionSpecs
    .map((item) => {
      const action = asString(item.action);
      const description = asString(item.description);
      const args = asString(item.args, "None");
      const range = asString(item.range);
      return `| \`${action}\` | ${description} | ${formatActionSpecArg(args)} | ${range} |`;
    });

  const parsedStatusFields = Array.isArray(statusFields)
    ? statusFields.filter(
        (item): item is { [key: string]: PythonLiteral } =>
          typeof item === "object" && item !== null && !Array.isArray(item)
      )
    : null;
  const statusRows = inferStatusFields(actionSpecs, miotMapping, parsedStatusFields);

  return [
    `# ${model} - Action Specs`,
    "",
    `**Device Name:** ${deviceName}  `,
    `**Platform:** ${platform}  `,
    `**Model:** ${model}`,
    "",
    "---",
    "",
    "## Supported Actions",
    "",
    ...(rows.length
      ? [
          "| action | Description | Parameters | Range |",
          "|--------|-------------|------------|-------|",
          ...rows,
        ]
      : [
          "No control actions available. Use `device_status`.",
        ]),
    "",
    ...(statusRows.length
      ? [
          "---",
          "",
          "## Status Fields",
          "",
          "| Field | Description | Type |",
          "|------|-------------|------|",
          ...statusRows,
          "",
        ]
      : []),
  ].join("\n");
}

async function inspectDeviceZip(arrayBuffer: ArrayBuffer): Promise<{ actionSpecsMarkdown: string; readmeContent: string | null }> {
  const zip = await JSZip.loadAsync(arrayBuffer);
  const files = Object.values(zip.files).filter((file) => !file.dir);
  const pyFiles = files.filter((file) => {
    const lower = file.name.toLowerCase();
    return lower.endsWith(".py") && !lower.includes("__pycache__/");
  });

  if (!pyFiles.length) {
    throw new Error("Device ZIP must include at least one Python driver file.");
  }

  const primaryPy =
    pyFiles.find((file) => !file.name.toLowerCase().endsWith("/__init__.py")) ??
    pyFiles[0];
  const pySource = await primaryPy.async("string");
  const actionSpecsMarkdown = generateActionSpecsMarkdown(pySource, primaryPy.name.split("/").pop() || "device.py");

  const readmeFile =
    files.find((file) => file.name.toLowerCase().endsWith("/readme.md")) ??
    files.find((file) => file.name.toLowerCase() === "readme.md");

  return {
    actionSpecsMarkdown,
    readmeContent: readmeFile ? await readmeFile.async("string") : null,
  };
}

async function inspectPlatformZip(arrayBuffer: ArrayBuffer): Promise<{ hasClientPy: boolean; hasEmbeddedDeviceList: boolean }> {
  const zip = await JSZip.loadAsync(arrayBuffer);
  const files = Object.values(zip.files).filter((file) => !file.dir);

  const hasClientPy = files.some((file) => {
    const normalized = file.name.replace(/\\/g, "/").toLowerCase();
    return normalized === "client.py" || normalized.endsWith("/client.py");
  });

  if (!hasClientPy) {
    throw new Error("Platform ZIP must include client.py.");
  }

  const hasEmbeddedDeviceList = files.some((file) => {
    const normalized = file.name.replace(/\\/g, "/").toLowerCase();
    return normalized.endsWith("_devices.json");
  });

  return {
    hasClientPy,
    hasEmbeddedDeviceList,
  };
}

type UploadedDeviceBundle = {
  zip_r2_key: string;
  action_specs_r2_key: string;
  readme_r2_key: string | null;
  generated_action_specs: string;
  has_readme: boolean;
  url: string;
};

function parseBooleanFormValue(value: string | File | null, fallback: boolean): boolean {
  if (typeof value !== "string") return fallback;
  const normalized = value.trim().toLowerCase();
  if (!normalized) return fallback;
  return ["1", "true", "yes", "on"].includes(normalized);
}

async function uploadDeviceZipBundle(
  bytes: ArrayBuffer,
  fileName: string,
  contentType: string,
  env: Env,
): Promise<UploadedDeviceBundle> {
  const inspected = await inspectDeviceZip(bytes);

  const action_specs_r2_key = `uploads/action_specs/${uuid()}.md`;
  await env.ASSETS.put(action_specs_r2_key, inspected.actionSpecsMarkdown, {
    httpMetadata: { contentType: "text/markdown; charset=utf-8" },
  });

  let readme_r2_key: string | null = null;
  if (inspected.readmeContent) {
    readme_r2_key = `uploads/readme/${uuid()}.md`;
    await env.ASSETS.put(readme_r2_key, inspected.readmeContent, {
      httpMetadata: { contentType: "text/markdown; charset=utf-8" },
    });
  }

  const ext = fileName.split(".").pop() || "bin";
  const zip_r2_key = `uploads/device_zip/${uuid()}.${ext}`;
  await env.ASSETS.put(zip_r2_key, bytes, {
    httpMetadata: { contentType: contentType || "application/octet-stream" },
  });

  return {
    zip_r2_key,
    action_specs_r2_key,
    readme_r2_key,
    generated_action_specs: inspected.actionSpecsMarkdown,
    has_readme: Boolean(inspected.readmeContent),
    url: `https://api.entroflow.ai/api/uploads/${zip_r2_key}`,
  };
}

// Auto-generate {platform}_devices.json from D1 device/version data
async function syncDeviceList(platformId: string, env: Env): Promise<void> {
  try {
    const { results } = await env.DB.prepare(
      `SELECT DISTINCT d.product_id FROM devices d
       WHERE d.platform_id = ? AND d.status = 'published'`
    ).bind(platformId).all();

    const devices = results.map((r: any) => ({ model: r.product_id }));
    const json = JSON.stringify(devices, null, 2);
    await env.ASSETS.put(`platforms/${platformId}/${platformId}_devices.json`, json, {
      httpMetadata: { contentType: "application/json" },
    });
  } catch (e) {
    console.error("Failed to sync device list:", e);
  }
}
async function syncCatalogToR2(env: Env): Promise<void> {
  try {
    const { results } = await env.DB.prepare(
      "SELECT id, name_en, name_zh, aliases FROM hardware_platforms WHERE status = 'published' ORDER BY sort_order ASC, name_en ASC"
    ).all();

    const platforms = results.map((p: any) => {
      const aliases = normalizeAliases(p.aliases);
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

async function publishAssetCopy(sourceKey: string | null | undefined, targetKey: string, contentType: string, env: Env): Promise<void> {
  if (!sourceKey) return;
  const obj = await env.ASSETS.get(sourceKey);
  if (!obj) {
    console.warn(`Source asset not found for publish: ${sourceKey}`);
    return;
  }
  await env.ASSETS.put(targetKey, await obj.arrayBuffer(), {
    httpMetadata: { contentType },
  });
}

async function syncDeviceVersionAssets(deviceId: string, versionId: string, env: Env): Promise<void> {
  try {
    const row = await env.DB.prepare(`
      SELECT
        d.product_id,
        d.platform_id,
        dv.version,
        dv.is_latest,
        dv.zip_r2_key,
        dv.action_specs_r2_key,
        dv.readme_r2_key
      FROM devices d
      INNER JOIN device_versions dv ON dv.device_id = d.id
      WHERE d.id = ? AND dv.id = ?
    `).bind(deviceId, versionId).first<{
      product_id: string;
      platform_id: string;
      version: string;
      is_latest: number;
      zip_r2_key: string | null;
      action_specs_r2_key: string | null;
      readme_r2_key: string | null;
    }>();

    if (!row) return;

    const deviceBaseKey = `platforms/${row.platform_id}/devices/${row.product_id}`;
    const versionBaseKey = `${deviceBaseKey}/v${row.version}`;

    if (row.zip_r2_key) {
      await publishAssetCopy(
        row.zip_r2_key,
        `${deviceBaseKey}/v${row.version}.zip`,
        "application/zip",
        env
      );
    }

    if (row.action_specs_r2_key) {
      await publishAssetCopy(
        row.action_specs_r2_key,
        `${versionBaseKey}/action_specs.md`,
        "text/markdown; charset=utf-8",
        env
      );
    }

    if (row.readme_r2_key) {
      await publishAssetCopy(
        row.readme_r2_key,
        `${versionBaseKey}/readme.md`,
        "text/markdown; charset=utf-8",
        env
      );
    }

    if (row.is_latest) {
      if (row.action_specs_r2_key) {
        await publishAssetCopy(
          row.action_specs_r2_key,
          `${deviceBaseKey}/action_specs.md`,
          "text/markdown; charset=utf-8",
          env
        );
      }

      if (row.readme_r2_key) {
        await publishAssetCopy(
          row.readme_r2_key,
          `${deviceBaseKey}/readme.md`,
          "text/markdown; charset=utf-8",
          env
        );
      }

      await env.ASSETS.put(
        `${deviceBaseKey}/latest.json`,
        JSON.stringify({ version: row.version }),
        { httpMetadata: { contentType: "application/json" } }
      );
    }
  } catch (e) {
    console.error("Failed to sync device version assets:", e);
  }
}

function getPlatformGuideLocales(row: Pick<PlatformGuideRow, "content_en" | "content_zh">): string[] {
  return [
    ...(row.content_en?.trim() ? ["en"] : []),
    ...(row.content_zh?.trim() ? ["zh"] : []),
  ];
}

async function getCurrentPlatformConnectorVersion(platformId: string, env: Env): Promise<string | null> {
  const latest = await env.ASSETS.get(`platforms/${platformId}/latest.json`);
  if (!latest) return null;
  try {
    const payload = await latest.json() as { version?: string | null };
    return typeof payload?.version === "string" && payload.version.trim() ? payload.version.trim() : null;
  } catch {
    return null;
  }
}

function summarizePlatformGuide(row: PlatformGuideRow | null, connectorVersion: string | null) {
  if (!row) {
    return {
      has_published_guide: false,
      guide_version: null,
      guide_updated_at: null,
      guide_locales: [],
      guide_compatible_with_connector: null,
      guide_warning: "No published platform guide yet. Connect can proceed, but guide sync will be skipped until one is published.",
    };
  }

  const compatible = isConnectorVersionSupported(
    connectorVersion,
    row.min_connector_version,
    row.max_connector_version,
  );

  return {
    has_published_guide: true,
    guide_version: row.version,
    guide_updated_at: row.published_at ?? row.updated_at,
    guide_locales: getPlatformGuideLocales(row),
    guide_compatible_with_connector: compatible,
    guide_warning: compatible
      ? null
      : `Latest published guide v${row.version} is outside connector compatibility range for connector v${connectorVersion}.`,
  };
}

async function getPlatformGuideById(env: Env, id: string): Promise<PlatformGuideRow | null> {
  await ensurePlatformGuideTables(env);
  return env.DB.prepare("SELECT * FROM platform_guides WHERE id = ?").bind(id).first<PlatformGuideRow>();
}

async function publishPlatformGuideAssets(row: PlatformGuideRow, env: Env): Promise<string> {
  const manifestKey = getPlatformGuideManifestKey(row.platform_id);
  const manifest = buildPlatformGuideManifest(row);

  if (row.content_en?.trim()) {
    await env.ASSETS.put(
      getPlatformGuideLocaleKey(row.platform_id, row.version, "en"),
      row.content_en,
      { httpMetadata: { contentType: "text/markdown; charset=utf-8" } }
    );
  }

  if (row.content_zh?.trim()) {
    await env.ASSETS.put(
      getPlatformGuideLocaleKey(row.platform_id, row.version, "zh"),
      row.content_zh,
      { httpMetadata: { contentType: "text/markdown; charset=utf-8" } }
    );
  }

  await env.ASSETS.put(manifestKey, JSON.stringify(manifest, null, 2), {
    httpMetadata: { contentType: "application/json" },
  });

  return manifestKey;
}

async function requireInternalPublisher(request: Request, env: Env): Promise<Response | null> {
  const configuredSecret = env.INTERNAL_PUBLISH_SECRET?.trim();
  if (!configuredSecret) return forbidden("Internal publish API is not configured");

  const token = getAuthToken(request);
  if (!token) return unauthorized();
  if (token !== configuredSecret) return unauthorized("Invalid publish token");

  return null;
}

type InternalDocInput = {
  slug: string;
  title_en: string;
  title_zh?: string | null;
  content_en?: string | null;
  content_zh?: string | null;
  sort_order?: number | null;
  status?: string | null;
};

function normalizeInternalDocInput(raw: any): InternalDocInput | null {
  if (!raw || typeof raw !== "object") return null;

  const slug = typeof raw.slug === "string" ? raw.slug.trim() : "";
  const title_en = typeof raw.title_en === "string" ? raw.title_en.trim() : "";
  if (!slug || !title_en) return null;

  return {
    slug,
    title_en,
    title_zh: typeof raw.title_zh === "string" ? raw.title_zh.trim() || null : null,
    content_en: typeof raw.content_en === "string" ? raw.content_en : "",
    content_zh: typeof raw.content_zh === "string" ? raw.content_zh : "",
    sort_order: typeof raw.sort_order === "number" && Number.isFinite(raw.sort_order)
      ? raw.sort_order
      : null,
    status: typeof raw.status === "string" && raw.status.trim() ? raw.status.trim() : "published",
  };
}

type InternalPlatformGuideInput = {
  platform_id: string;
  version?: string | null;
  title_en: string;
  title_zh?: string | null;
  content_en?: string | null;
  content_zh?: string | null;
  min_connector_version?: string | null;
  max_connector_version?: string | null;
};

function normalizeInternalPlatformGuideInput(raw: any): InternalPlatformGuideInput | null {
  if (!raw || typeof raw !== "object") return null;

  const platform_id = typeof raw.platform_id === "string" ? raw.platform_id.trim() : "";
  const title_en = typeof raw.title_en === "string" ? raw.title_en.trim() : "";
  if (!platform_id || !title_en) return null;

  return {
    platform_id,
    version: typeof raw.version === "string" ? raw.version.trim() || null : null,
    title_en,
    title_zh: typeof raw.title_zh === "string" ? raw.title_zh.trim() || null : null,
    content_en: typeof raw.content_en === "string" ? raw.content_en : "",
    content_zh: typeof raw.content_zh === "string" ? raw.content_zh : "",
    min_connector_version:
      typeof raw.min_connector_version === "string" ? raw.min_connector_version.trim() || null : null,
    max_connector_version:
      typeof raw.max_connector_version === "string" ? raw.max_connector_version.trim() || null : null,
  };
}

async function resolveCanonicalPlatformId(inputPlatformId: string, env: Env): Promise<string | null> {
  const exact = await env.DB.prepare(
    "SELECT id FROM hardware_platforms WHERE id = ?"
  ).bind(inputPlatformId).first<{ id: string }>();
  if (exact?.id) return exact.id;

  const normalized = inputPlatformId.trim().toLowerCase();
  if (!normalized) return null;

  const canonical = await env.DB.prepare(
    "SELECT id FROM hardware_platforms WHERE LOWER(id) = ?"
  ).bind(normalized).first<{ id: string }>();
  return canonical?.id ?? null;
}

async function upsertPublishedPlatformGuide(
  env: Env,
  guide: InternalPlatformGuideInput,
  publisherId: string,
  overwrite: boolean,
): Promise<{
  id: string;
  platform_id: string;
  version: string;
  action: "created" | "updated";
  manifest_r2_key: string;
  connector_version: string | null;
}> {
  await ensurePlatformGuideTables(env);

  const canonicalPlatformId = await resolveCanonicalPlatformId(guide.platform_id, env);
  if (!canonicalPlatformId) {
    throw new Error(`platform_id '${guide.platform_id}' is not registered`);
  }

  const connectorVersion = await getCurrentPlatformConnectorVersion(canonicalPlatformId, env);
  const version = guide.version?.trim() || connectorVersion || "";
  if (!version) {
    throw new Error(`version is required for platform '${canonicalPlatformId}' because no connector version is published yet`);
  }

  if (!guide.content_en?.trim() && !guide.content_zh?.trim()) {
    throw new Error(`platform '${canonicalPlatformId}' guide requires at least one locale content`);
  }

  const existing = await env.DB.prepare(
    "SELECT * FROM platform_guides WHERE platform_id = ? AND version = ?"
  ).bind(canonicalPlatformId, version).first<PlatformGuideRow>();

  if (existing && !overwrite) {
    throw new Error(`platform '${canonicalPlatformId}' guide version '${version}' already exists`);
  }

  const ts = now();
  const id = existing?.id ?? uuid();
  const action: "created" | "updated" = existing ? "updated" : "created";

  if (existing) {
    await env.DB.prepare(`
      UPDATE platform_guides
      SET title_en = ?,
          title_zh = ?,
          content_en = ?,
          content_zh = ?,
          min_connector_version = ?,
          max_connector_version = ?,
          status = 'published',
          updated_by = ?,
          updated_at = ?,
          published_at = COALESCE(published_at, ?)
      WHERE id = ?
    `).bind(
      guide.title_en,
      guide.title_zh ?? null,
      guide.content_en ?? "",
      guide.content_zh ?? "",
      guide.min_connector_version ?? null,
      guide.max_connector_version ?? null,
      publisherId,
      ts,
      ts,
      id,
    ).run();
  } else {
    await env.DB.prepare(`
      INSERT INTO platform_guides (
        id, platform_id, version, is_latest, title_en, title_zh, content_en, content_zh,
        min_connector_version, max_connector_version, manifest_r2_key, status,
        created_by, updated_by, created_at, updated_at, published_at
      ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, NULL, 'published', ?, ?, ?, ?, ?)
    `).bind(
      id,
      canonicalPlatformId,
      version,
      guide.title_en,
      guide.title_zh ?? null,
      guide.content_en ?? "",
      guide.content_zh ?? "",
      guide.min_connector_version ?? null,
      guide.max_connector_version ?? null,
      publisherId,
      publisherId,
      ts,
      ts,
      ts,
    ).run();
  }

  await env.DB.prepare(
    "UPDATE platform_guides SET is_latest = 0 WHERE platform_id = ? AND id != ?"
  ).bind(canonicalPlatformId, id).run();
  await env.DB.prepare(
    "UPDATE platform_guides SET is_latest = 1, updated_by = ?, updated_at = ? WHERE id = ?"
  ).bind(publisherId, now(), id).run();

  const published = await getPlatformGuideById(env, id);
  if (!published) {
    throw new Error(`platform guide '${canonicalPlatformId}@${version}' was not found after upsert`);
  }

  const manifestKey = await publishPlatformGuideAssets(published, env);
  await env.DB.prepare(
    "UPDATE platform_guides SET manifest_r2_key = ?, updated_by = ?, updated_at = ? WHERE id = ?"
  ).bind(manifestKey, publisherId, now(), id).run();

  return {
    id,
    platform_id: canonicalPlatformId,
    version,
    action,
    manifest_r2_key: manifestKey,
    connector_version: connectorVersion,
  };
}

export async function handleInternalPublishRoutes(path: string, request: Request, env: Env): Promise<Response | null> {
  if (request.method !== "POST") return null;

  if (path === "/v1/internal/publish/docs") {
    const authError = await requireInternalPublisher(request, env);
    if (authError) return authError;

    let body: any;
    try {
      body = await request.json();
    } catch {
      return badRequest("Invalid JSON");
    }

    const section_key = typeof body?.section_key === "string" ? body.section_key.trim() : "";
    const section_title_en = typeof body?.section_title_en === "string" ? body.section_title_en.trim() : "";
    const section_title_zh = typeof body?.section_title_zh === "string" ? body.section_title_zh.trim() || null : null;
    const section_sort_order =
      typeof body?.section_sort_order === "number" && Number.isFinite(body.section_sort_order)
        ? body.section_sort_order
        : 0;
    const overwrite = typeof body?.overwrite === "boolean" ? body.overwrite : true;
    const dry_run = typeof body?.dry_run === "boolean" ? body.dry_run : false;
    const docs = Array.isArray(body?.docs)
      ? body.docs
          .map((item: any) => normalizeInternalDocInput(item))
          .filter((item: InternalDocInput | null): item is InternalDocInput => Boolean(item))
      : [];

    if (!section_key) return badRequest("section_key is required");
    if (!section_title_en) return badRequest("section_title_en is required");
    if (!docs.length) return badRequest("docs must contain at least one valid item");

    const existingSection = await env.DB.prepare(
      "SELECT id FROM doc_sections WHERE key = ?"
    ).bind(section_key).first<{ id: string }>();

    const existingDocs = await Promise.all(
      docs.map((doc: InternalDocInput) =>
        env.DB.prepare(
          "SELECT id, section_id FROM doc_items WHERE slug = ?"
        ).bind(doc.slug).first<{ id: string; section_id: string }>()
      )
    );

    if (!overwrite) {
      const duplicate = existingDocs.find((row) => row?.id);
      if (duplicate) return badRequest("one or more doc slugs already exist; set overwrite=true to replace them");
    }

    if (dry_run) {
      return jsonResponse({
        ok: true,
        mode: "dry_run",
        section_key,
        section_exists: Boolean(existingSection),
        docs: docs.map((doc: InternalDocInput, index: number) => ({
          slug: doc.slug,
          title_en: doc.title_en,
          action: existingDocs[index]?.id ? "update" : "create",
        })),
      });
    }

    const ts = now();
    const publisherId = "internal_publish_api";
    const sectionId = existingSection?.id ?? uuid();

    if (existingSection?.id) {
      await env.DB.prepare(
        "UPDATE doc_sections SET title_en = ?, title_zh = ?, sort_order = ? WHERE id = ?"
      ).bind(section_title_en, section_title_zh, section_sort_order, sectionId).run();
    } else {
      await env.DB.prepare(
        "INSERT INTO doc_sections (id, key, title_en, title_zh, sort_order) VALUES (?, ?, ?, ?, ?)"
      ).bind(sectionId, section_key, section_title_en, section_title_zh, section_sort_order).run();
    }

    const results: Array<{ slug: string; id: string; action: "created" | "updated" }> = [];

    for (let i = 0; i < docs.length; i += 1) {
      const doc = docs[i];
      const existing = existingDocs[i];
      const sortOrder = doc.sort_order != null ? doc.sort_order : i + 1;
      const status = doc.status || "published";

      if (existing?.id) {
        await env.DB.prepare(
          "UPDATE doc_items SET section_id = ?, title_en = ?, title_zh = ?, content_en = ?, content_zh = ?, sort_order = ?, status = ?, updated_by = ?, updated_at = ? WHERE id = ?"
        ).bind(
          sectionId,
          doc.title_en,
          doc.title_zh,
          doc.content_en ?? "",
          doc.content_zh ?? "",
          sortOrder,
          status,
          publisherId,
          ts,
          existing.id
        ).run();
        results.push({ slug: doc.slug, id: existing.id, action: "updated" });
      } else {
        const id = uuid();
        await env.DB.prepare(
          "INSERT INTO doc_items (id, section_id, slug, title_en, title_zh, content_en, content_zh, sort_order, status, updated_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ).bind(
          id,
          sectionId,
          doc.slug,
          doc.title_en,
          doc.title_zh,
          doc.content_en ?? "",
          doc.content_zh ?? "",
          sortOrder,
          status,
          publisherId,
          ts,
          ts
        ).run();
        results.push({ slug: doc.slug, id, action: "created" });
      }
    }

    return jsonResponse({
      ok: true,
      mode: "publish",
      section: {
        id: sectionId,
        key: section_key,
        created: !existingSection,
      },
      docs: results,
    }, existingSection ? 200 : 201);
  }

  if (path === "/v1/internal/publish/platform-guides") {
    const authError = await requireInternalPublisher(request, env);
    if (authError) return authError;

    let body: any;
    try {
      body = await request.json();
    } catch {
      return badRequest("Invalid JSON");
    }

    const overwrite = typeof body?.overwrite === "boolean" ? body.overwrite : true;
    const dry_run = typeof body?.dry_run === "boolean" ? body.dry_run : false;
    const guides = Array.isArray(body?.guides)
      ? body.guides
          .map((item: any) => normalizeInternalPlatformGuideInput(item))
          .filter((item: InternalPlatformGuideInput | null): item is InternalPlatformGuideInput => Boolean(item))
      : [];

    if (!guides.length) return badRequest("guides must contain at least one valid item");

    const planned = [];
    for (const guide of guides) {
      const canonicalPlatformId = await resolveCanonicalPlatformId(guide.platform_id, env);
      if (!canonicalPlatformId) {
        return badRequest(`platform_id '${guide.platform_id}' is not registered`);
      }

      const connectorVersion = await getCurrentPlatformConnectorVersion(canonicalPlatformId, env);
      const version = guide.version?.trim() || connectorVersion || "";
      if (!version) {
        return badRequest(`version is required for platform '${canonicalPlatformId}' because no connector version is published yet`);
      }

      if (!guide.content_en?.trim() && !guide.content_zh?.trim()) {
        return badRequest(`platform '${canonicalPlatformId}' guide requires at least one locale content`);
      }

      const existing = await env.DB.prepare(
        "SELECT id FROM platform_guides WHERE platform_id = ? AND version = ?"
      ).bind(canonicalPlatformId, version).first<{ id: string }>();

      if (existing && !overwrite) {
        return badRequest(`platform '${canonicalPlatformId}' guide version '${version}' already exists; set overwrite=true to replace it`);
      }

      planned.push({
        platform_id: canonicalPlatformId,
        requested_platform_id: guide.platform_id,
        version,
        connector_version: connectorVersion,
        action: existing ? "update" : "create",
        locales: [
          ...(guide.content_en?.trim() ? ["en"] : []),
          ...(guide.content_zh?.trim() ? ["zh"] : []),
        ],
      });
    }

    if (dry_run) {
      return jsonResponse({
        ok: true,
        mode: "dry_run",
        overwrite,
        guides: planned,
      });
    }

    const publisherId = "internal_publish_api";
    const results = [];
    for (const guide of guides) {
      const result = await upsertPublishedPlatformGuide(env, guide, publisherId, overwrite);
      results.push(result);
    }

    return jsonResponse({
      ok: true,
      mode: "publish",
      overwrite,
      guides: results,
    }, 201);
  }

  if (path === "/v1/internal/publish/platform") {
    const authError = await requireInternalPublisher(request, env);
    if (authError) return authError;

    const formData = await request.formData();
    const file = formData.get("file") as File | null;
    const platform_id = (formData.get("platform_id") as string | null)?.trim() || "";
    const version = (formData.get("version") as string | null)?.trim() || "";
    const dry_run = parseBooleanFormValue(formData.get("dry_run"), false);
    const overwrite = parseBooleanFormValue(formData.get("overwrite"), true);

    if (!file) return badRequest("file is required");
    if (!platform_id) return badRequest("platform_id is required");
    if (!version) return badRequest("version is required");

    const platform = await env.DB.prepare(
      "SELECT id FROM hardware_platforms WHERE id = ?"
    ).bind(platform_id).first<{ id: string }>();
    if (!platform) return badRequest("platform_id is not registered");

    const bytes = await file.arrayBuffer();
    let inspected: { hasClientPy: boolean; hasEmbeddedDeviceList: boolean };
    try {
      inspected = await inspectPlatformZip(bytes);
    } catch (error) {
      return badRequest(error instanceof Error ? error.message : "Invalid platform ZIP");
    }

    if (dry_run) {
      return jsonResponse({
        ok: true,
        mode: "dry_run",
        platform_id,
        version,
        has_client_py: inspected.hasClientPy,
        has_embedded_device_list: inspected.hasEmbeddedDeviceList,
      });
    }

    const zipKey = `platforms/${platform_id}/v${version}.zip`;
    const existingZip = await env.ASSETS.get(zipKey);
    if (existingZip && !overwrite) {
      return badRequest("platform version already exists; set overwrite=true to replace it");
    }

    await env.ASSETS.put(zipKey, bytes, {
      httpMetadata: { contentType: file.type || "application/zip" },
    });

    await env.ASSETS.put(
      `platforms/${platform_id}/latest.json`,
      JSON.stringify({ version }),
      {
        httpMetadata: { contentType: "application/json" },
      }
    );

    await syncDeviceList(platform_id, env);

    return jsonResponse({
      ok: true,
      mode: "publish",
      overwritten_version: Boolean(existingZip),
      platform_id,
      version,
      zip_r2_key: zipKey,
      has_client_py: inspected.hasClientPy,
      has_embedded_device_list: inspected.hasEmbeddedDeviceList,
    }, existingZip ? 200 : 201);
  }

  if (path !== "/v1/internal/publish/device") return null;

  const authError = await requireInternalPublisher(request, env);
  if (authError) return authError;

  const formData = await request.formData();
  const file = formData.get("file") as File | null;
  const platform_id = (formData.get("platform_id") as string | null)?.trim() || "";
  const product_id = (formData.get("product_id") as string | null)?.trim() || "";
  const version = (formData.get("version") as string | null)?.trim() || "";
  const name_en = (formData.get("name_en") as string | null)?.trim() || "";
  const name_zh = (formData.get("name_zh") as string | null)?.trim() || null;
  const github_url = (formData.get("github_url") as string | null)?.trim() || null;
  const detail_image_url = (formData.get("detail_image_url") as string | null)?.trim() || null;
  const status = (formData.get("status") as string | null)?.trim() || "published";
  const is_featured = parseBooleanFormValue(formData.get("is_featured"), false);
  const is_latest = parseBooleanFormValue(formData.get("is_latest"), true);
  const overwrite = parseBooleanFormValue(formData.get("overwrite"), true);
  const dry_run = parseBooleanFormValue(formData.get("dry_run"), false);

  if (!file) return badRequest("file is required");
  if (!platform_id) return badRequest("platform_id is required");
  if (!product_id) return badRequest("product_id is required");
  if (!version) return badRequest("version is required");
  if (!name_en) return badRequest("name_en is required");

  const platform = await env.DB.prepare(
    "SELECT id FROM hardware_platforms WHERE id = ?"
  ).bind(platform_id).first<{ id: string }>();
  if (!platform) return badRequest("platform_id is not registered");

  const bytes = await file.arrayBuffer();
  let inspected: { actionSpecsMarkdown: string; readmeContent: string | null };
  try {
    inspected = await inspectDeviceZip(bytes);
  } catch (error) {
    return badRequest(error instanceof Error ? error.message : "Invalid device ZIP");
  }

  if (dry_run) {
    return jsonResponse({
      ok: true,
      mode: "dry_run",
      platform_id,
      product_id,
      version,
      generated_action_specs: inspected.actionSpecsMarkdown,
      has_readme: Boolean(inspected.readmeContent),
    });
  }

  const ts = now();
  const publisherId = "internal_publish_api";

  let device = await env.DB.prepare(
    "SELECT id FROM devices WHERE product_id = ? AND platform_id = ?"
  ).bind(product_id, platform_id).first<{ id: string }>();

  let created_device = false;
  if (!device) {
    const deviceId = uuid();
    await env.DB.prepare(
      "INSERT INTO devices (id, product_id, name_en, name_zh, platform_id, detail_image_url, github_url, is_featured, status, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ).bind(
      deviceId,
      product_id,
      name_en,
      name_zh,
      platform_id,
      detail_image_url,
      github_url,
      is_featured ? 1 : 0,
      status,
      publisherId,
      ts,
      ts,
    ).run();
    device = { id: deviceId };
    created_device = true;
  } else {
    await env.DB.prepare(
      "UPDATE devices SET name_en=?, name_zh=?, detail_image_url=?, github_url=?, is_featured=?, status=?, updated_at=? WHERE id=?"
    ).bind(
      name_en,
      name_zh,
      detail_image_url,
      github_url,
      is_featured ? 1 : 0,
      status,
      ts,
      device.id,
    ).run();
  }

  const existingVersion = await env.DB.prepare(
    "SELECT id FROM device_versions WHERE device_id = ? AND version = ?"
  ).bind(device.id, version).first<{ id: string }>();

  let overwritten_version = false;
  if (existingVersion && !overwrite) {
    return badRequest("device version already exists; set overwrite=true to replace it");
  }

  const upload = await uploadDeviceZipBundle(bytes, file.name, file.type, env);

  if (is_latest) {
    await env.DB.prepare("UPDATE device_versions SET is_latest = 0 WHERE device_id = ?").bind(device.id).run();
  }

  let versionId = existingVersion?.id ?? uuid();
  if (existingVersion) {
    overwritten_version = true;
    await env.DB.prepare(
      "UPDATE device_versions SET zip_r2_key=?, action_specs_r2_key=?, readme_r2_key=?, is_latest=?, published_at=?, created_by=? WHERE id=? AND device_id=?"
    ).bind(
      upload.zip_r2_key,
      upload.action_specs_r2_key,
      upload.readme_r2_key,
      is_latest ? 1 : 0,
      ts,
      publisherId,
      versionId,
      device.id,
    ).run();
  } else {
    await env.DB.prepare(
      "INSERT INTO device_versions (id, device_id, version, is_latest, zip_r2_key, action_specs_r2_key, readme_r2_key, published_at, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    ).bind(
      versionId,
      device.id,
      version,
      is_latest ? 1 : 0,
      upload.zip_r2_key,
      upload.action_specs_r2_key,
      upload.readme_r2_key,
      ts,
      publisherId,
      ts,
    ).run();
  }

  await syncDeviceVersionAssets(device.id, versionId, env);
  await syncDeviceList(platform_id, env);

  return jsonResponse({
    ok: true,
    mode: "publish",
    created_device,
    overwritten_version,
    device_id: device.id,
    version_id: versionId,
    product_id,
    platform_id,
    version,
    zip_r2_key: upload.zip_r2_key,
    action_specs_r2_key: upload.action_specs_r2_key,
    readme_r2_key: upload.readme_r2_key,
    has_readme: upload.has_readme,
  }, existingVersion ? 200 : 201);
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
  await ensurePlatformGuideTables(env);

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
        env.DB.prepare(`SELECT * FROM hardware_platforms WHERE ${where} ORDER BY sort_order ASC, created_at DESC LIMIT ? OFFSET ?`).bind(...bindings, limit, offset).all(),
        env.DB.prepare(`SELECT COUNT(*) as c FROM hardware_platforms WHERE ${where}`).bind(...bindings).first<{ c: number }>(),
      ]);
      const normalizedItems = await Promise.all(items.results.map(async (item: any) => {
        const connectorVersion = await getCurrentPlatformConnectorVersion(item.id, env);
        const latestGuide = await getLatestPublishedPlatformGuide(env, item.id);
        return {
          ...item,
          aliases: normalizeAliases(item.aliases),
          connector_version: connectorVersion,
          ...summarizePlatformGuide(latestGuide, connectorVersion),
        };
      }));
      return jsonResponse({ items: normalizedItems, total: count?.c ?? 0, page, limit });
    }

    if (request.method === "POST") {
      let body: any;
      try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
      const { id, name_en, name_zh, sort_order = 0, aliases, description_en, description_zh, logo_url, website_url, status = "draft" } = body;
      if (!id?.trim()) return badRequest("id is required");
      if (!name_en?.trim()) return badRequest("name_en is required");

      // aliases can be array or comma-separated string — normalize to JSON array string
      const aliasesJson = aliases ? JSON.stringify(normalizeAliases(aliases)) : null;

      const ts = now();
      await env.DB.prepare(
        "INSERT INTO hardware_platforms (id, name_en, name_zh, sort_order, aliases, description_en, description_zh, logo_url, website_url, status, created_by, updated_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
      ).bind(id.trim(), name_en.trim(), name_zh || null, Number(sort_order) || 0, aliasesJson, description_en || null, description_zh || null, logo_url || null, website_url || null, status, admin.id, admin.id, ts, ts).run();
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
      const { name_en, name_zh, sort_order, aliases, description_en, description_zh, logo_url, website_url, status } = body;
      const aliasesJson = aliases !== undefined
        ? JSON.stringify(normalizeAliases(aliases))
        : null;
      await env.DB.prepare(
        "UPDATE hardware_platforms SET name_en=COALESCE(?,name_en), name_zh=COALESCE(?,name_zh), sort_order=COALESCE(?,sort_order), aliases=COALESCE(?,aliases), description_en=COALESCE(?,description_en), description_zh=COALESCE(?,description_zh), logo_url=COALESCE(?,logo_url), website_url=COALESCE(?,website_url), status=COALESCE(?,status), updated_by=?, updated_at=? WHERE id=?"
      ).bind(name_en||null, name_zh||null, sort_order!=null ? Number(sort_order) : null, aliasesJson, description_en||null, description_zh||null, logo_url||null, website_url||null, status||null, admin.id, now(), id).run();
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

  const platformGuides = path.match(/^\/v1\/admin\/platforms\/([^/]+)\/guides$/);
  if (platformGuides) {
    const platformId = platformGuides[1];

    if (request.method === "GET") {
      const platform = await env.DB.prepare("SELECT id FROM hardware_platforms WHERE id = ?").bind(platformId).first<{ id: string }>();
      if (!platform) return notFound(`Platform '${platformId}' not found`);

      const connectorVersion = await getCurrentPlatformConnectorVersion(platformId, env);
      const { results } = await env.DB.prepare(`
        SELECT *
        FROM platform_guides
        WHERE platform_id = ?
        ORDER BY is_latest DESC, published_at DESC, updated_at DESC
      `).bind(platformId).all();

      return jsonResponse({
        connector_version: connectorVersion,
        items: (results as PlatformGuideRow[]).map((row: PlatformGuideRow) => ({
          ...row,
          locales: getPlatformGuideLocales(row),
          connector_compatible: isConnectorVersionSupported(
            connectorVersion,
            row.min_connector_version,
            row.max_connector_version,
          ),
        })),
      });
    }

    if (request.method === "POST") {
      let body: any;
      try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }

      const platform = await env.DB.prepare("SELECT id FROM hardware_platforms WHERE id = ?").bind(platformId).first<{ id: string }>();
      if (!platform) return notFound(`Platform '${platformId}' not found`);

      const version = typeof body?.version === "string" ? body.version.trim() : "";
      const title_en = typeof body?.title_en === "string" ? body.title_en.trim() : "";
      const title_zh = typeof body?.title_zh === "string" ? body.title_zh.trim() || null : null;
      const content_en = typeof body?.content_en === "string" ? body.content_en : "";
      const content_zh = typeof body?.content_zh === "string" ? body.content_zh : "";
      const min_connector_version = typeof body?.min_connector_version === "string" ? body.min_connector_version.trim() || null : null;
      const max_connector_version = typeof body?.max_connector_version === "string" ? body.max_connector_version.trim() || null : null;
      const status = typeof body?.status === "string" && body.status.trim() ? body.status.trim() : "draft";

      if (!version) return badRequest("version is required");
      if (!title_en) return badRequest("title_en is required");
      if (status === "published") return badRequest("Use the publish endpoint to publish a platform guide");

      const existing = await env.DB.prepare(
        "SELECT id FROM platform_guides WHERE platform_id = ? AND version = ?"
      ).bind(platformId, version).first<{ id: string }>();
      if (existing) return badRequest("Guide version already exists for this platform");

      const id = uuid();
      const ts = now();
      await env.DB.prepare(`
        INSERT INTO platform_guides (
          id, platform_id, version, is_latest, title_en, title_zh, content_en, content_zh,
          min_connector_version, max_connector_version, manifest_r2_key, status,
          created_by, updated_by, created_at, updated_at, published_at
        ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL)
      `).bind(
        id,
        platformId,
        version,
        title_en,
        title_zh,
        content_en,
        content_zh,
        min_connector_version,
        max_connector_version,
        status,
        admin.id,
        admin.id,
        ts,
        ts,
      ).run();

      return jsonResponse({ id }, 201);
    }
  }

  const platformGuideById = path.match(/^\/v1\/admin\/platform-guides\/([^/]+)$/);
  if (platformGuideById) {
    const guideId = platformGuideById[1];

    if (request.method === "PUT") {
      let body: any;
      try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }

      const current = await getPlatformGuideById(env, guideId);
      if (!current) return notFound(`Platform guide '${guideId}' not found`);

      const title_en = typeof body?.title_en === "string" ? body.title_en.trim() : null;
      const title_zh = typeof body?.title_zh === "string" ? body.title_zh.trim() || null : undefined;
      const content_en = typeof body?.content_en === "string" ? body.content_en : undefined;
      const content_zh = typeof body?.content_zh === "string" ? body.content_zh : undefined;
      const min_connector_version = typeof body?.min_connector_version === "string" ? body.min_connector_version.trim() || null : undefined;
      const max_connector_version = typeof body?.max_connector_version === "string" ? body.max_connector_version.trim() || null : undefined;
      const status = typeof body?.status === "string" && body.status.trim() ? body.status.trim() : undefined;

      if (status === "published" && current.status !== "published") {
        return badRequest("Use the publish endpoint to publish a platform guide");
      }

      await env.DB.prepare(`
        UPDATE platform_guides
        SET title_en = COALESCE(?, title_en),
            title_zh = COALESCE(?, title_zh),
            content_en = COALESCE(?, content_en),
            content_zh = COALESCE(?, content_zh),
            min_connector_version = COALESCE(?, min_connector_version),
            max_connector_version = COALESCE(?, max_connector_version),
            status = COALESCE(?, status),
            updated_by = ?,
            updated_at = ?
        WHERE id = ?
      `).bind(
        title_en,
        title_zh === undefined ? null : title_zh,
        content_en ?? null,
        content_zh ?? null,
        min_connector_version === undefined ? null : min_connector_version,
        max_connector_version === undefined ? null : max_connector_version,
        status ?? null,
        admin.id,
        now(),
        guideId,
      ).run();

      return jsonResponse({ success: true });
    }

    if (request.method === "DELETE") {
      const current = await getPlatformGuideById(env, guideId);
      if (!current) return notFound(`Platform guide '${guideId}' not found`);
      if (current.is_latest) return badRequest("Unpublish or replace the latest guide before deleting it");
      await env.DB.prepare("DELETE FROM platform_guides WHERE id = ?").bind(guideId).run();
      return jsonResponse({ success: true });
    }
  }

  const publishPlatformGuide = path.match(/^\/v1\/admin\/platform-guides\/([^/]+)\/publish$/);
  if (publishPlatformGuide && request.method === "POST") {
    const guideId = publishPlatformGuide[1];
    const current = await getPlatformGuideById(env, guideId);
    if (!current) return notFound(`Platform guide '${guideId}' not found`);
    if (!current.content_en.trim() && !current.content_zh.trim()) {
      return badRequest("At least one guide content locale is required");
    }

    const ts = now();
    await env.DB.prepare(
      "UPDATE platform_guides SET is_latest = 0 WHERE platform_id = ?"
    ).bind(current.platform_id).run();
    await env.DB.prepare(`
      UPDATE platform_guides
      SET status = 'published',
          is_latest = 1,
          updated_by = ?,
          updated_at = ?,
          published_at = COALESCE(published_at, ?)
      WHERE id = ?
    `).bind(admin.id, ts, ts, guideId).run();

    const published = await getPlatformGuideById(env, guideId);
    if (!published) return notFound(`Platform guide '${guideId}' not found after publish`);
    const manifestKey = await publishPlatformGuideAssets(published, env);
    await env.DB.prepare(
      "UPDATE platform_guides SET manifest_r2_key = ?, updated_by = ?, updated_at = ? WHERE id = ?"
    ).bind(manifestKey, admin.id, now(), guideId).run();

    const connectorVersion = await getCurrentPlatformConnectorVersion(published.platform_id, env);
    return jsonResponse({
      success: true,
      id: guideId,
      manifest_r2_key: manifestKey,
      connector_version: connectorVersion,
      connector_compatible: isConnectorVersionSupported(
        connectorVersion,
        published.min_connector_version,
        published.max_connector_version,
      ),
    });
  }

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
      await syncDeviceList(platform_id.trim(), env);
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
      const before = await env.DB.prepare("SELECT platform_id FROM devices WHERE id = ?").bind(id).first<{ platform_id: string }>();
      await env.DB.prepare(
        "UPDATE devices SET name_en=COALESCE(?,name_en), name_zh=COALESCE(?,name_zh), platform_id=COALESCE(?,platform_id), detail_image_url=COALESCE(?,detail_image_url), github_url=COALESCE(?,github_url), is_featured=COALESCE(?,is_featured), status=COALESCE(?,status), updated_at=? WHERE id=?"
      ).bind(name_en||null, name_zh||null, platform_id||null, detail_image_url||null, github_url||null, is_featured!=null?is_featured:null, status||null, now(), id).run();
      const after = await env.DB.prepare("SELECT platform_id FROM devices WHERE id = ?").bind(id).first<{ platform_id: string }>();
      if (before?.platform_id) await syncDeviceList(before.platform_id, env);
      if (after?.platform_id && after.platform_id !== before?.platform_id) await syncDeviceList(after.platform_id, env);
      return jsonResponse({ success: true });
    }
    if (request.method === "DELETE") {
      if (admin.role !== "super") return forbidden("Super admin required");
      const device = await env.DB.prepare("SELECT platform_id FROM devices WHERE id = ?").bind(id).first<{ platform_id: string }>();
      await env.DB.prepare("DELETE FROM device_versions WHERE device_id = ?").bind(id).run();
      await env.DB.prepare("DELETE FROM devices WHERE id = ?").bind(id).run();
      if (device?.platform_id) await syncDeviceList(device.platform_id, env);
      return jsonResponse({ success: true });
    }
  }

  // ── Platform Connector Upload ─────────────────────────────────────────────

  // GET /v1/admin/platforms/:id/connector — get current connector version
  const platformConnector = path.match(/^\/v1\/admin\/platforms\/([^/]+)\/connector$/);
  if (platformConnector) {
    const platformId = platformConnector[1];
    if (request.method === "GET") {
      const version = await getCurrentPlatformConnectorVersion(platformId, env);
      const latestGuide = await getLatestPublishedPlatformGuide(env, platformId);
      return jsonResponse({
        version,
        ...summarizePlatformGuide(latestGuide, version),
      });
    }
    if (request.method === "POST") {
      const formData = await request.formData();
      const file = formData.get("file") as File | null;
      const version = (formData.get("version") as string || "").trim();
      if (!file) return badRequest("file is required");
      if (!version) return badRequest("version is required");

      // Upload zip to R2
      const zipKey = `platforms/${platformId}/v${version}.zip`;
      await env.ASSETS.put(zipKey, file.stream(), {
        httpMetadata: { contentType: "application/zip" },
      });

      // Update latest.json
      await env.ASSETS.put(`platforms/${platformId}/latest.json`,
        JSON.stringify({ version }), {
          httpMetadata: { contentType: "application/json" },
        }
      );

      // Sync device list
      await syncDeviceList(platformId, env);

      const latestGuide = await getLatestPublishedPlatformGuide(env, platformId);
      return jsonResponse({
        success: true,
        version,
        r2_key: zipKey,
        ...summarizePlatformGuide(latestGuide, version),
      }, 201);
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

      await syncDeviceVersionAssets(deviceId, id, env);

      // Sync device list for the platform
      const device = await env.DB.prepare("SELECT platform_id FROM devices WHERE id = ?").bind(deviceId).first<{ platform_id: string }>();
      if (device) await syncDeviceList(device.platform_id, env);

      return jsonResponse({ id }, 201);
    }
  }

  const deviceVersionById = path.match(/^\/v1\/admin\/devices\/([^/]+)\/versions\/([^/]+)$/);
  if (deviceVersionById) {
    const [, deviceId, versionId] = deviceVersionById;
    if (request.method === "PUT") {
      let body: any;
      try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
      const { zip_r2_key, action_specs_r2_key, readme_r2_key, is_latest } = body;

      if (is_latest) {
        await env.DB.prepare("UPDATE device_versions SET is_latest = 0 WHERE device_id = ?").bind(deviceId).run();
      }

      await env.DB.prepare(
        "UPDATE device_versions SET zip_r2_key=COALESCE(?,zip_r2_key), action_specs_r2_key=COALESCE(?,action_specs_r2_key), readme_r2_key=COALESCE(?,readme_r2_key), is_latest=COALESCE(?,is_latest) WHERE id=? AND device_id=?"
      ).bind(
        zip_r2_key || null,
        action_specs_r2_key || null,
        readme_r2_key || null,
        is_latest != null ? (is_latest ? 1 : 0) : null,
        versionId,
        deviceId
      ).run();

      await syncDeviceVersionAssets(deviceId, versionId, env);

      const device = await env.DB.prepare("SELECT platform_id FROM devices WHERE id = ?").bind(deviceId).first<{ platform_id: string }>();
      if (device) await syncDeviceList(device.platform_id, env);

      return jsonResponse({ success: true });
    }
  }

  // ── File Upload ──────────────────────────────────────────────────────────

  if (path === "/v1/admin/upload" && request.method === "POST") {
    const formData = await request.formData();
    const file = formData.get("file") as File | null;
    const type = formData.get("type") as string | null;
    if (!file) return badRequest("file is required");
    if (!type) return badRequest("type is required");

    const bytes = await file.arrayBuffer();
    let action_specs_r2_key: string | null = null;
    let readme_r2_key: string | null = null;

    if (type === "device_zip") {
      try {
        const upload = await uploadDeviceZipBundle(bytes, file.name, file.type, env);
        return jsonResponse({
          url: upload.url,
          r2_key: upload.zip_r2_key,
          action_specs_r2_key: upload.action_specs_r2_key,
          readme_r2_key: upload.readme_r2_key,
        }, 201);
      } catch (error) {
        return badRequest(error instanceof Error ? error.message : "Invalid device ZIP");
      }
    }

    const ext = file.name.split(".").pop() || "bin";
    const key = `uploads/${type}/${uuid()}.${ext}`;
    await env.ASSETS.put(key, bytes, {
      httpMetadata: { contentType: file.type || "application/octet-stream" },
    });

    const url = `https://api.entroflow.ai/api/uploads/${key}`;
    return jsonResponse({ url, r2_key: key, action_specs_r2_key, readme_r2_key }, 201);
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

  // PUT /v1/admin/docs/sections/:id
  const docSectionById = path.match(/^\/v1\/admin\/docs\/sections\/([^/]+)$/);
  if (docSectionById) {
    const id = docSectionById[1];
    if (request.method === "PUT") {
      let body: any;
      try { body = await request.json(); } catch { return badRequest("Invalid JSON"); }
      const { title_en, title_zh, sort_order } = body;
      await env.DB.prepare(
        "UPDATE doc_sections SET title_en=COALESCE(?,title_en), title_zh=COALESCE(?,title_zh), sort_order=COALESCE(?,sort_order) WHERE id=?"
      ).bind(title_en||null, title_zh||null, sort_order!=null?sort_order:null, id).run();
      return jsonResponse({ success: true });
    }
    if (request.method === "DELETE") {
      // Delete all items in section first
      await env.DB.prepare("DELETE FROM doc_items WHERE section_id = ?").bind(id).run();
      await env.DB.prepare("DELETE FROM doc_sections WHERE id = ?").bind(id).run();
      return jsonResponse({ success: true });
    }
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
