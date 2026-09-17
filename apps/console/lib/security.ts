import { timingSafeEqual } from 'node:crypto';

export function validCsrf(origin: string | null, expectedOrigin: string, cookie: string | undefined, token: unknown): boolean {
  return origin===expectedOrigin && typeof token==='string' && /^[a-f0-9]{64}$/.test(token)
    && typeof cookie==='string' && cookie.length===token.length
    && timingSafeEqual(Buffer.from(cookie),Buffer.from(token));
}

export function isLocalDevelopment(environment: string | undefined, mode: string | undefined, origin: string): boolean {
  return ['development','test'].includes(environment ?? '') && mode==='development'
    && ['localhost','127.0.0.1'].includes(new URL(origin).hostname);
}
