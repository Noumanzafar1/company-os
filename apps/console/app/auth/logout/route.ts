import { cookies } from 'next/headers';
import { NextRequest,NextResponse } from 'next/server';
import { apiUrl,CSRF_COOKIE,origin,SESSION_COOKIE } from '@/lib/api';
import { validCsrf } from '@/lib/security';

export async function POST(request:NextRequest) {
  const body=await request.formData();
  const jar=await cookies();
  const csrf=body.get('csrf');
  if(!validCsrf(request.headers.get('origin'),origin(),jar.get(CSRF_COOKIE)?.value,csrf))return new NextResponse(null,{status:403});
  const token=jar.get(SESSION_COOKIE)?.value;
  if(token) {
    try {
      const result=await fetch(apiUrl()+'/v1/auth/logout',{method:'POST',headers:{Authorization:`Bearer ${token}`,Origin:origin(),'X-CSRF-Token':String(csrf)},cache:'no-store',signal:AbortSignal.timeout(8000)});
      if(result.status!==204)return new NextResponse('Sign-out unavailable. Try again.',{status:503});
    } catch {return new NextResponse('Sign-out unavailable. Try again.',{status:503});}
  }
  const response=NextResponse.redirect(new URL('/login',origin()),303);
  response.cookies.delete(SESSION_COOKIE); response.cookies.delete(CSRF_COOKIE);
  response.headers.set('Cache-Control','no-store');
  return response;
}
