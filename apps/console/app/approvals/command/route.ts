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
  if(!uuid.test(workspace)||!['request','approve','reject','revise','execute','revoke','freeze','policy_activate'].includes(action)||(identifier&&!uuid.test(identifier)))return new NextResponse(null,{status:400});
  if(action==='approve'&&body.get('confirmed')!=='on')return new NextResponse(null,{status:400});
  let path='',payload:unknown;
  try {
    if(action==='request') {
      const uses=Number(body.get('uses'));
      path='approvals/request';
      payload={action:'runtime.synthetic_external_action',targets:JSON.parse(String(body.get('targets'))),payload:{label:String(body.get('label')),scenario:'effect_success'},maximum_uses:uses,maximum_spend:String(uses),maximum_volume:uses,expires_at:new Date(Date.now()+3600000).toISOString(),rationale:String(body.get('rationale'))};
    } else if(['approve','reject','revise'].includes(action)) {
      path=`approvals/${identifier}/decide`;payload={decision:action,expected_scope_hash:String(body.get('scope_hash')),rationale:String(body.get('rationale'))};
    } else if(action==='policy_activate') {
      path='policies/activate';payload={policy_version_id:String(body.get('policy_version_id')),decision_id:String(body.get('decision_id')),manifest_id:String(body.get('manifest_id'))};
    } else if(action==='execute') {
      path=`approvals/${identifier}/execute`;payload={targets:JSON.parse(String(body.get('targets'))),payload:JSON.parse(String(body.get('payload'))),logical_key:String(body.get('logical_key'))};
    } else {
      path=action==='freeze'?'authority/freeze':`approvals/${identifier}/revoke`;payload={rationale:String(body.get('rationale'))};
    }
  } catch {return new NextResponse(null,{status:400});}
  let result='UNAVAILABLE',destination=identifier;
  try {
    const response=await fetch(`${apiUrl()}/v1/workspaces/${workspace}/${path}`,{method:'POST',headers:{Authorization:`Bearer ${jar.get(SESSION_COOKIE)?.value}`,Origin:origin(),'X-CSRF-Token':String(csrf),'Content-Type':'application/json','Idempotency-Key':String(body.get('idempotency')),'If-Match':String(body.get('version')||1)},body:JSON.stringify(payload),cache:'no-store',signal:AbortSignal.timeout(8000)});
    const data=await response.json();
    result=response.ok?(data.data?.result==='DENY'?data.data.reasons[0]:'ok'):(data.error?.code||'DENIED');
    if(action==='request'&&data.data?.request_id)destination=data.data.request_id;
  } catch {result='UNAVAILABLE';}
  return NextResponse.redirect(new URL(`/approvals${destination?`/${destination}`:''}?workspace=${workspace}&result=${encodeURIComponent(result)}`,origin()),303);
}
