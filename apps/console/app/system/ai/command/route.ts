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
  const identifier=String(body.get('identifier')||'');
  const action=String(body.get('action'));
  const uuid=/^[a-f0-9-]{36}$/;
  if(!uuid.test(workspace)||!['submit','evaluate','propose','revoke','promote'].includes(action)||(['revoke','promote'].includes(action)&&!uuid.test(identifier)))return new NextResponse(null,{status:400});
  const path=action==='submit'?'ai-tasks':action==='evaluate'?'ai-evaluations':action==='propose'?'ai-routes/propose':action==='promote'?`ai-routes/${identifier}/promote`:`ai-tasks/${identifier}/revoke-context`;
  const payload=action==='submit'?{scenario:String(body.get('scenario'))}:action==='evaluate'?{dataset:String(body.get('dataset'))}:action==='propose'?{route_id:String(body.get('route_id')),evaluation_id:String(body.get('evaluation_id')),rollback_route_id:String(body.get('rollback_route_id'))}:{rationale:action==='revoke'?'Protective synthetic context revocation':'Activate exact human-reviewed synthetic route'};
  let destination='/system/ai',result='failed';
  try {
    const response=await fetch(`${apiUrl()}/v1/workspaces/${workspace}/${path}`,{method:'POST',headers:{Authorization:`Bearer ${jar.get(SESSION_COOKIE)?.value}`,Origin:origin(),'X-CSRF-Token':String(csrf),'Content-Type':'application/json','Idempotency-Key':String(body.get('idempotency')),'If-Match':String(body.get('version')||1)},body:JSON.stringify(payload),cache:'no-store',signal:AbortSignal.timeout(15000)});
    const data=await response.json();
    if(response.ok&&data.data?.result!=='DENY'){result='ok';if(action==='submit')destination+=`/${data.data.id}`;if(action==='propose')destination=`/approvals/${data.data.request_id}`;}
    if(action==='revoke')destination+=`/${identifier}`;
  } catch {result='failed';}
  return NextResponse.redirect(new URL(`${destination}?workspace=${workspace}&result=${result}`,origin()),303);
}
