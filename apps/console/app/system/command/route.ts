import { randomUUID } from 'node:crypto';
import { cookies } from 'next/headers';
import { NextRequest,NextResponse } from 'next/server';
import { apiUrl,CSRF_COOKIE,origin,SESSION_COOKIE } from '@/lib/api';
import { validCsrf } from '@/lib/security';

export async function POST(request:NextRequest) {
  const body=await request.formData();
  const jar=await cookies();
  const csrf=body.get('csrf');
  if(!validCsrf(request.headers.get('origin'),origin(),jar.get(CSRF_COOKIE)?.value,csrf))return new NextResponse(null,{status:403});
  const workspace=String(body.get('workspace'));
  const action=String(body.get('action'));
  const job=String(body.get('job')||'');
  if(!/^[a-f0-9-]{36}$/.test(workspace) || !['synthetic','retry','cancel'].includes(action) || (action!=='synthetic'&&!/^[a-f0-9-]{36}$/.test(job)))return new NextResponse(null,{status:400});
  const path=action==='synthetic'?'runtime/synthetic':`jobs/${job}/${action}`;
  const payload=action==='synthetic'?{scenario:String(body.get('scenario')),logical_key:randomUUID()}:{reason:String(body.get('reason')),cause_changed:body.get('cause_changed')==='on'};
  let ok=false;
  try {
    const response=await fetch(`${apiUrl()}/v1/workspaces/${workspace}/${path}`,{method:'POST',headers:{Authorization:`Bearer ${jar.get(SESSION_COOKIE)?.value}`,Origin:origin(),'X-CSRF-Token':String(csrf),'Content-Type':'application/json','Idempotency-Key':randomUUID(),...(action!=='synthetic'?{'If-Match':String(body.get('version'))}:{})},body:JSON.stringify(payload),cache:'no-store',signal:AbortSignal.timeout(8000)});
    ok=response.ok;
  } catch {ok=false;}
  return NextResponse.redirect(new URL(`/system${job?`/jobs/${job}`:''}?workspace=${workspace}&result=${ok?'ok':'failed'}`,origin()),303);
}
