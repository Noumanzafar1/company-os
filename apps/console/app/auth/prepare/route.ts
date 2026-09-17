import { randomBytes } from 'node:crypto';
import { NextResponse } from 'next/server';
import { cookieOptions, CSRF_COOKIE, origin } from '@/lib/api';

export async function GET() {
  const response=NextResponse.redirect(new URL('/login',origin()));
  response.cookies.set(CSRF_COOKIE,randomBytes(32).toString('hex'),cookieOptions());
  response.headers.set('Cache-Control','no-store');
  return response;
}
