import { randomUUID } from 'node:crypto';
import { cookies } from 'next/headers';
import { NextRequest,NextResponse } from 'next/server';
import { apiGet,apiUrl,CSRF_COOKIE,origin,SESSION_COOKIE } from '@/lib/api';
import { validCsrf } from '@/lib/security';
import type { components } from '../../../../../packages/contracts/api';

export async function POST(request:NextRequest) {
  const body=await request.formData();
  const jar=await cookies();
  const csrf=body.get('csrf');
  if(!validCsrf(request.headers.get('origin'),origin(),jar.get(CSRF_COOKIE)?.value,csrf))return new NextResponse(null,{status:403});
  const workspace=String(body.get('workspace'));
  const account=String(body.get('account'));
  const icp=String(body.get('icp'));
  if(![workspace,account,icp].every(value=>/^[a-f0-9-]{36}$/.test(value)))return new NextResponse(null,{status:400});
  const detail=await apiGet<{data:components['schemas']['AccountDetail']}>(`/v1/workspaces/${workspace}/accounts/${account}`);
  if(!detail.data)return new NextResponse('Account unavailable.',{status:detail.status});
  const payload:components['schemas']['ScoreInput']={subject_id:account,icp_version_id:icp,evidence_ids:detail.data.data.evidence.map(item=>item.id)};
  let ok=false;
  try {
    const response=await fetch(`${apiUrl()}/v1/workspaces/${workspace}/scores/calculate`,{method:'POST',headers:{Authorization:`Bearer ${jar.get(SESSION_COOKIE)?.value}`,Origin:origin(),'X-CSRF-Token':String(csrf),'Content-Type':'application/json','Idempotency-Key':randomUUID()},body:JSON.stringify(payload),cache:'no-store',signal:AbortSignal.timeout(8000)});
    ok=response.ok;
  } catch { ok=false; }
  return NextResponse.redirect(new URL(`/accounts/${account}?workspace=${workspace}&result=${ok?'ok':'failed'}`,origin()),303);
}
