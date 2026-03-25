export interface Env {
  ASSETS: R2Bucket;
  DB: D1Database;
  JWT_SECRET: string;
  ADMIN_JWT_SECRET: string;
  INIT_SECRET: string;
  GOOGLE_CLIENT_ID: string;
  GOOGLE_CLIENT_SECRET: string;
  GITHUB_CLIENT_ID: string;
  GITHUB_CLIENT_SECRET: string;
}

export interface JwtPayload {
  sub: string;
  email: string;
  provider?: string;
  role?: string;
  iat: number;
  exp: number;
}
