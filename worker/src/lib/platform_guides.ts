import { Env } from "./types";

export type PlatformGuideRow = {
  id: string;
  platform_id: string;
  version: string;
  is_latest: number;
  title_en: string;
  title_zh: string | null;
  content_en: string;
  content_zh: string;
  min_connector_version: string | null;
  max_connector_version: string | null;
  manifest_r2_key: string | null;
  status: string;
  created_by: string;
  updated_by: string | null;
  created_at: number;
  updated_at: number;
  published_at: number | null;
};

export async function ensurePlatformGuideTables(env: Env): Promise<void> {
  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS platform_guides (
      id                    TEXT PRIMARY KEY,
      platform_id           TEXT NOT NULL REFERENCES hardware_platforms(id),
      version               TEXT NOT NULL,
      is_latest             INTEGER NOT NULL DEFAULT 0,
      title_en              TEXT NOT NULL,
      title_zh              TEXT,
      content_en            TEXT NOT NULL DEFAULT '',
      content_zh            TEXT NOT NULL DEFAULT '',
      min_connector_version TEXT,
      max_connector_version TEXT,
      manifest_r2_key       TEXT,
      status                TEXT NOT NULL DEFAULT 'draft',
      created_by            TEXT NOT NULL,
      updated_by            TEXT,
      created_at            INTEGER NOT NULL,
      updated_at            INTEGER NOT NULL,
      published_at          INTEGER,
      UNIQUE(platform_id, version)
    )
  `).run();
  await env.DB.prepare(
    "CREATE INDEX IF NOT EXISTS idx_platform_guides_platform ON platform_guides(platform_id)"
  ).run();
  await env.DB.prepare(
    "CREATE INDEX IF NOT EXISTS idx_platform_guides_latest ON platform_guides(platform_id, is_latest)"
  ).run();
  await env.DB.prepare(
    "CREATE INDEX IF NOT EXISTS idx_platform_guides_status ON platform_guides(status)"
  ).run();
}

function normalizeVersionParts(version: string): string[] {
  return version
    .trim()
    .replace(/^v/i, "")
    .split(".")
    .map((part) => part.trim())
    .filter(Boolean);
}

export function compareLooseVersions(a: string, b: string): number {
  const aParts = normalizeVersionParts(a);
  const bParts = normalizeVersionParts(b);
  const maxLength = Math.max(aParts.length, bParts.length);

  for (let index = 0; index < maxLength; index += 1) {
    const aPart = aParts[index] ?? "0";
    const bPart = bParts[index] ?? "0";
    const aNum = Number(aPart);
    const bNum = Number(bPart);

    if (!Number.isNaN(aNum) && !Number.isNaN(bNum)) {
      if (aNum !== bNum) return aNum > bNum ? 1 : -1;
      continue;
    }

    if (aPart !== bPart) return aPart > bPart ? 1 : -1;
  }

  return 0;
}

export function isConnectorVersionSupported(
  connectorVersion: string | null | undefined,
  minConnectorVersion: string | null | undefined,
  maxConnectorVersion: string | null | undefined,
): boolean {
  const normalizedConnector = connectorVersion?.trim();
  if (!normalizedConnector) return true;

  if (minConnectorVersion?.trim() && compareLooseVersions(normalizedConnector, minConnectorVersion) < 0) {
    return false;
  }

  if (maxConnectorVersion?.trim() && compareLooseVersions(normalizedConnector, maxConnectorVersion) > 0) {
    return false;
  }

  return true;
}

export function getPlatformGuideBaseKey(platformId: string, version: string): string {
  return `platform-guides/${platformId}/v${version}`;
}

export function getPlatformGuideManifestKey(platformId: string): string {
  return `platform-guides/${platformId}/latest.json`;
}

export function getPlatformGuideLocaleKey(platformId: string, version: string, locale: "en" | "zh"): string {
  return `${getPlatformGuideBaseKey(platformId, version)}/guide.${locale}.md`;
}

export function buildPlatformGuideManifest(row: PlatformGuideRow) {
  const locales: string[] = [];
  const files: Record<string, string> = {};

  if (row.content_en?.trim()) {
    locales.push("en");
    files.en = getPlatformGuideLocaleKey(row.platform_id, row.version, "en");
  }

  if (row.content_zh?.trim()) {
    locales.push("zh");
    files.zh = getPlatformGuideLocaleKey(row.platform_id, row.version, "zh");
  }

  return {
    platform_id: row.platform_id,
    version: row.version,
    published_at: row.published_at,
    min_connector_version: row.min_connector_version,
    max_connector_version: row.max_connector_version,
    locales,
    files,
  };
}

export async function getLatestPublishedPlatformGuide(env: Env, platformId: string): Promise<PlatformGuideRow | null> {
  await ensurePlatformGuideTables(env);
  return env.DB.prepare(`
    SELECT *
    FROM platform_guides
    WHERE platform_id = ? AND status = 'published'
    ORDER BY is_latest DESC, published_at DESC, updated_at DESC
    LIMIT 1
  `).bind(platformId).first<PlatformGuideRow>();
}
