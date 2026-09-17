import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { SignJWT } from 'jose';
import { apiUrl,cookieOptions,CSRF_COOKIE,origin,SESSION_COOKIE,type SessionResponse,type SessionRequest } from '@/lib/api';
import { isLocalDevelopment, validCsrf } from '@/lib/security';

export async function POST(request:NextRequest) {
  if(!isLocalDevelopment(process.env.COMPANY_ENV,process.env.AUTH_MODE,origin()))return new NextResponse(null,{status:404});
  const body=await request.formData();
  const csrf=body.get('csrf');
  if(!validCsrf(request.headers.get('origin'),origin(),(await cookies()).get(CSRF_COOKIE)?.value,csrf))return new NextResponse(null,{status:403});
  const identity=body.get('identity');
  if(identity!=='a' && identity!=='b')return new NextResponse(null,{status:400});
  const secret=process.env.DEV_AUTH_SECRET;
  if(!secret || secret.length<32 || !process.env.CONSOLE_SECRET)return new NextResponse(null,{status:503});
  try {
    const token=await new SignJWT({aal:'aal1'}).setProtectedHeader({alg:'HS256'})
      .setSubject(`synthetic-user-${identity}`).setIssuer('company-os-local').setAudience('company-os-api')
      .setIssuedAt().setExpirationTime('15m').sign(new TextEncoder().encode(secret));
    const payload:SessionRequest={csrf_token:String(csrf)};
    const session=await fetch(apiUrl()+'/v1/auth/session',{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`,'X-Console-Secret':process.env.CONSOLE_SECRET},body:JSON.stringify(payload),cache:'no-store',signal:AbortSignal.timeout(8000)});
    if(!session.ok)throw new Error('Authentication unavailable');
    const data:SessionResponse=await session.json();
    const response=NextResponse.redirect(new URL('/attention',origin()),303);
    response.cookies.set(SESSION_COOKIE,data.session_token,cookieOptions());
    response.headers.set('Cache-Control','no-store');
    return response;
  } catch {return NextResponse.redirect(new URL('/login?error=unavailable',origin()),303);}
}
