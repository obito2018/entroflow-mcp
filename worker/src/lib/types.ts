export interface Env {
  ASSETS: R2Bucket;
  DB: D1Database;
  JWT_SECRET: string;
  ADMIN_JWT_SECRET: string;
}

export interface JwtPayload {
  sub: string;
  email: string;
  provider?: string;
  role?: string;
  iat: number;
  exp: number;
}
