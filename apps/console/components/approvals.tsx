import Link from 'next/link';
import { cookies } from 'next/headers';
import { randomUUID } from 'node:crypto';
import { Shell } from '@/components/shell';
import { apiGet, CSRF_COOKIE, type Me } from '@/lib/api';

type Approval=import('../../../packages/contracts/api').components['schemas']['ApprovalView'];
type Detail=import('../../../packages/contracts/api').components['schemas']['ApprovalDetail'];
type Envelope<T>={data:T};

export async function ApprovalsPage({workspace,identifier,result}:{workspace?:string,identifier?:string,result?:string}) {
  const profile=await apiGet<Me>('/v1/me');
  const selected=workspace || profile.data?.data.workspaces[0]?.id;
  if(!selected)return <Shell route="/approvals"/>;
  const prefix=`/v1/workspaces/${encodeURIComponent(selected)}`;
  const csrf=(await cookies()).get(CSRF_COOKIE)?.value || '';
  const hidden=<><input type="hidden" name="workspace" value={selected}/><input type="hidden" name="csrf" value={csrf}/><input type="hidden" name="idempotency" value={randomUUID()}/></>;
  const unavailable=<p role="alert" className="notice error">Approvals unavailable or access denied.</p>;
  let content;
  if(identifier) {
    const response=await apiGet<Envelope<Detail>>(`${prefix}/approvals/${encodeURIComponent(identifier)}`);
    const d=response.data?.data;
    if(d) {
      const a=d.request;
      const expired=a.effective_state==='expired';
      const policyChange='rules' in a.payload ? a.payload : null;
      const canApprove=a.state==='pending'&&!expired;
      content=<><Link href={`/approvals?workspace=${selected}`}>All approvals</Link><h2>{a.payload.label}</h2>
        <p className="notice">Synthetic action only · {a.action} · {expired?'expired':a.state}</p>
        <p>{a.rationale}</p><p>Requested by {a.created_by}</p>
        <h3>Exactly what this authorizes</h3><p>{d.targets.length} exact targets · up to {a.maximum_uses} uses · {a.maximum_volume} aggregate target operations · {a.maximum_spend} simulated USD maximum</p>
        <p>Expires {a.expires_at} · remaining uses {d.remaining_uses}</p>
        <p>Policy version {a.policy_version_id}. The current policy, object versions, safety holds and budget are checked again before execution.</p>
        <table><thead><tr><th>Target ID</th><th>Approved version</th></tr></thead><tbody>{d.targets.map(t=><tr key={t.id}><td>{t.id}</td><td>{t.version}</td></tr>)}</tbody></table>
        {policyChange?<><h3>Exact proposed policy</h3><p>Review the current pointer, candidate, typed rules and validity bounds before granting one activation.</p><pre>{JSON.stringify(policyChange,null,2)}</pre></>:<p>Scenario: {'scenario' in a.payload?a.payload.scenario:''}. Every listed target is part of the frozen set. Dependencies: current policy, fake endpoint, available runtime budget and quota.</p>}
        <details><summary>Immutable scope and hashes</summary><p>Scope {a.scope_hash}</p><p>Payload {a.payload_hash}</p><p>Target set {a.target_set_hash}</p>{d.manifest&&<><p>Manifest {d.manifest.id} · SHA-256 {d.manifest.manifest_hash}</p><pre>{JSON.stringify(d.manifest.scope,null,2)}</pre></>}</details>
        <p role="status">Authority validation: {d.validation_reason??'Current; spending and use capacity are checked on reservation'}</p>
        {canApprove&&<form method="post" action="/approvals/command" className="core-card">{hidden}<input type="hidden" name="identifier" value={identifier}/><input type="hidden" name="version" value={a.record_version}/><input type="hidden" name="scope_hash" value={a.scope_hash}/>
          <h3>Founder decision</h3><p>Granting authority requires verified MFA within the last ten minutes. Ordinary synthetic sign-in has no MFA.</p>
          <label htmlFor="rationale">Decision reason</label><input id="rationale" name="rationale" minLength={5} maxLength={500} required/>
          <label><input type="checkbox" name="confirmed" required/> I reviewed {a.action}, {d.targets.length} targets, {a.maximum_spend} simulated USD and the expiry above.</label>
          <button name="action" value="approve">Approve this exact scope</button><button name="action" value="reject">Reject</button><button name="action" value="revise">Request revision</button></form>}
        {a.state==='approved'&&<>{policyChange&&d.manifest?<form method="post" action="/approvals/command" className="core-card">{hidden}<input type="hidden" name="identifier" value={identifier}/><input type="hidden" name="version" value={policyChange.policy_record_version}/><input type="hidden" name="policy_version_id" value={policyChange.candidate_version_id}/><input type="hidden" name="decision_id" value={d.manifest.decision_id}/><input type="hidden" name="manifest_id" value={d.manifest.id}/><button name="action" value="policy_activate" disabled={expired||Boolean(d.validation_reason)||d.remaining_uses===0}>Activate this approved policy version</button></form>:<form method="post" action="/approvals/command" className="core-card">{hidden}<input type="hidden" name="identifier" value={identifier}/><input type="hidden" name="payload" value={JSON.stringify(a.payload)}/><input type="hidden" name="targets" value={JSON.stringify(d.targets)}/><input type="hidden" name="logical_key" value={randomUUID()}/><button name="action" value="execute" disabled={expired||Boolean(d.validation_reason)||d.remaining_uses===0}>Queue approved synthetic action</button></form>}
        <form method="post" action="/approvals/command" className="core-card">{hidden}<input type="hidden" name="identifier" value={identifier}/><input type="hidden" name="version" value={a.record_version}/><label htmlFor="revocation">Revocation reason</label><input id="revocation" name="rationale" minLength={5} maxLength={500} required/><button name="action" value="revoke">Revoke unused authority</button><p>Dispatched or uncertain effects retain their reconciliation history.</p></form></>}
        <h3>Decision history</h3>{d.history.map(h=><p key={h.id}>{h.created_at} · {h.decision} · {h.rationale}</p>)}
        <h3>Uses and runtime trace</h3>{d.uses.length?d.uses.map(u=><p key={u.id}>Use {u.use_number}: {u.state} · {u.spend_reserved} simulated USD · {u.volume} target operations · {u.job_id?<Link href={`/system/jobs/${u.job_id}?workspace=${selected}`}>Job / effect {u.effect_id}</Link>:<>Policy activation {u.activation_policy_id}</>}</p>):<p>No authority has been consumed.</p>}</>;
    } else content=unavailable;
  } else {
    const [response,targetResponse]=await Promise.all([apiGet<Envelope<Approval[]>>(`${prefix}/approvals`),apiGet<Envelope<{id:string,record_version:number,label:string,suppressed:boolean,rights_valid:boolean}[]>>(`${prefix}/authority/targets`)]);
    const target=targetResponse.data?.data.find(t=>!t.suppressed&&t.rights_valid);
    content=response.data?<><p className="page-intro">Review exact authority, expiry and remaining uses. No response ever grants approval.</p><h2>Review queue</h2>
      {response.data.data.length?<table><thead><tr><th>Action</th><th>Status</th><th>Expires</th><th>Limits</th></tr></thead><tbody>{response.data.data.map(a=><tr key={a.id}><td><Link href={`/approvals/${a.id}?workspace=${selected}`}>{a.payload.label}</Link></td><td>{a.effective_state}</td><td>{a.expires_at}</td><td>{a.maximum_uses} uses · {a.maximum_spend} simulated USD</td></tr>)}</tbody></table>:<h3>No approvals pending.</h3>}
      {target&&<form method="post" action="/approvals/command" className="core-card">{hidden}<h3>Create a synthetic L3 request</h3><p>Target: {target.label} · {target.id} · version {target.record_version}</p><input type="hidden" name="targets" value={JSON.stringify([{id:target.id,version:target.record_version}])}/><label htmlFor="label">Action summary</label><input id="label" name="label" required maxLength={100} defaultValue="Synthetic authority demonstration"/><label htmlFor="uses">Maximum uses (each reserves one simulated USD)</label><input id="uses" name="uses" type="number" min={1} max={10} defaultValue={1} required/><label htmlFor="why">Why this action is needed</label><input id="why" name="rationale" minLength={5} maxLength={500} required defaultValue="Inspect exact synthetic authority before execution"/><button name="action" value="request">Request founder review</button></form>}
      <form method="post" action="/approvals/command" className="core-card">{hidden}<h3>Emergency stop</h3><p>Freeze new governed actions in this workspace. Reconciliation continues. This phase has no automatic unfreeze.</p><label htmlFor="freeze">Protective reason</label><input id="freeze" name="rationale" required minLength={5} maxLength={500}/><button name="action" value="freeze">Freeze new actions</button></form></>:unavailable;
  }
  return <Shell route="/approvals" requestedWorkspace={selected}>{result&&<p role="status">{result==='ok'?'Command recorded. Execution, if queued, is still subject to runtime checks.':`Command denied: ${result}. Refresh and review the current scope.`}</p>}<div className="core-state authority-page">{content}</div></Shell>;
}
