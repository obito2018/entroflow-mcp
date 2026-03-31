-- EntroFlow Database Schema

-- 用户表
CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY,
  email         TEXT UNIQUE NOT NULL,
  name          TEXT,
  avatar_url    TEXT,
  provider      TEXT NOT NULL,
  provider_id   TEXT,
  password_hash TEXT,
  email_verified INTEGER NOT NULL DEFAULT 0,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_provider ON users(provider, provider_id);

-- 管理员表
CREATE TABLE IF NOT EXISTS admins (
  id            TEXT PRIMARY KEY,
  email         TEXT UNIQUE NOT NULL,
  name          TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'editor',
  created_at    INTEGER NOT NULL,
  last_login_at INTEGER
);

-- AI 平台表
CREATE TABLE IF NOT EXISTS ai_platforms (
  id          TEXT PRIMARY KEY,
  name_en     TEXT NOT NULL,
  name_zh     TEXT,
  logo_url    TEXT,
  sort_order  INTEGER NOT NULL DEFAULT 0,
  is_active   INTEGER NOT NULL DEFAULT 1,
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);

-- 硬件平台表
CREATE TABLE IF NOT EXISTS hardware_platforms (
  id             TEXT PRIMARY KEY,
  name_en        TEXT NOT NULL,
  name_zh        TEXT,
  sort_order     INTEGER NOT NULL DEFAULT 0,
  aliases        TEXT,
  description_en TEXT,
  description_zh TEXT,
  logo_url       TEXT,
  website_url    TEXT,
  status         TEXT NOT NULL DEFAULT 'draft',
  created_by     TEXT NOT NULL,
  updated_by     TEXT,
  created_at     INTEGER NOT NULL,
  updated_at     INTEGER NOT NULL
);

-- 设备表
CREATE TABLE IF NOT EXISTS devices (
  id               TEXT PRIMARY KEY,
  product_id       TEXT UNIQUE NOT NULL,
  name_en          TEXT NOT NULL,
  name_zh          TEXT,
  platform_id      TEXT NOT NULL REFERENCES hardware_platforms(id),
  downloads_count  INTEGER NOT NULL DEFAULT 0,
  detail_image_url TEXT,
  github_url       TEXT,
  is_featured      INTEGER NOT NULL DEFAULT 0,
  status           TEXT NOT NULL DEFAULT 'draft',
  created_by       TEXT NOT NULL,
  created_at       INTEGER NOT NULL,
  updated_at       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_devices_platform ON devices(platform_id);
CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status);
CREATE INDEX IF NOT EXISTS idx_devices_featured ON devices(is_featured);

-- 设备版本表
CREATE TABLE IF NOT EXISTS device_versions (
  id                  TEXT PRIMARY KEY,
  device_id           TEXT NOT NULL REFERENCES devices(id),
  version             TEXT NOT NULL,
  is_latest           INTEGER NOT NULL DEFAULT 0,
  zip_r2_key          TEXT,
  action_specs_r2_key TEXT,
  readme_r2_key       TEXT,
  published_at        INTEGER,
  created_by          TEXT NOT NULL,
  created_at          INTEGER NOT NULL,
  UNIQUE(device_id, version)
);
CREATE INDEX IF NOT EXISTS idx_device_versions_device ON device_versions(device_id);

-- 下载记录表
CREATE TABLE IF NOT EXISTS download_logs (
  id          TEXT PRIMARY KEY,
  device_id   TEXT NOT NULL REFERENCES devices(id),
  version     TEXT NOT NULL,
  channel     TEXT NOT NULL,
  install_id  TEXT,
  user_id     TEXT,
  ip          TEXT,
  created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_download_logs_device ON download_logs(device_id);
CREATE INDEX IF NOT EXISTS idx_download_logs_channel ON download_logs(channel);

-- Agent 安装平台统计表
CREATE TABLE IF NOT EXISTS agent_install_platforms (
  id             TEXT PRIMARY KEY,
  install_id     TEXT NOT NULL,
  platform_key   TEXT NOT NULL,
  platform_label TEXT NOT NULL,
  created_at     INTEGER NOT NULL,
  updated_at     INTEGER NOT NULL,
  UNIQUE(install_id, platform_key)
);
CREATE INDEX IF NOT EXISTS idx_agent_install_platforms_install ON agent_install_platforms(install_id);
CREATE INDEX IF NOT EXISTS idx_agent_install_platforms_platform ON agent_install_platforms(platform_key);

-- 文档分区表
CREATE TABLE IF NOT EXISTS doc_sections (
  id         TEXT PRIMARY KEY,
  key        TEXT UNIQUE NOT NULL,
  title_en   TEXT NOT NULL,
  title_zh   TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
);

-- 文档条目表
CREATE TABLE IF NOT EXISTS doc_items (
  id          TEXT PRIMARY KEY,
  section_id  TEXT NOT NULL REFERENCES doc_sections(id),
  slug        TEXT UNIQUE NOT NULL,
  title_en    TEXT NOT NULL,
  title_zh    TEXT,
  content_en  TEXT NOT NULL DEFAULT '',
  content_zh  TEXT NOT NULL DEFAULT '',
  sort_order  INTEGER NOT NULL DEFAULT 0,
  status      TEXT NOT NULL DEFAULT 'draft',
  updated_by  TEXT,
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_doc_items_section ON doc_items(section_id);
CREATE INDEX IF NOT EXISTS idx_doc_items_status ON doc_items(status);

-- 反馈表
CREATE TABLE IF NOT EXISTS feedback (
  id          TEXT PRIMARY KEY,
  email       TEXT,
  user_id     TEXT,
  login_type  TEXT NOT NULL,
  content     TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'new',
  assignee_id TEXT,
  note        TEXT,
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status);

-- 商务合作表
CREATE TABLE IF NOT EXISTS business_inquiries (
  id          TEXT PRIMARY KEY,
  company     TEXT NOT NULL,
  email       TEXT NOT NULL,
  content     TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'new',
  assignee_id TEXT,
  note        TEXT,
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_business_status ON business_inquiries(status);
