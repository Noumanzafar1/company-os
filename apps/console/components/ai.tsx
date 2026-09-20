import Link from 'next/link';
import { cookies } from 'next/headers';
import { randomUUID } from 'node:crypto';
import { Shell } from '@/components/shell';
import { apiGet, CSRF_COOKIE, type Me } from '@/lib/api';
import type { components } from '../../../packages/contracts/api';

type S=components['schemas'];
type Health={providers:{provider:string,status:string}[],tasks:{id:string,state:string,error_code:string|null}[],counts:{state:string,count:number}[],routes:{id:string,state:string,evaluation_id:string|null,evaluation_status:string,body:S['AIRoute']}[],evaluations:{id:string,route_id:string,body:S['AIEvaluation'],current_route_id:string,current_result:S['AIEvaluation']}[],budgets:{category:string,status:string,spent_usd:string,reserved_usd:string,limit_usd:string}[],warning:string};

export async function AIPage({workspace,identifier,result}:{workspace?:string,identifier?:string,result?:string}) {
  const profile=await apiGet<Me>('/v1/me');
  const selected=workspace||profile.data?.data.workspaces[0]?.id;
  if(!selected)return <Shell route="/system"/>;
  const csrf=(await cookies()).get(CSRF_COOKIE)?.value||'';
  const hidden=<><input type="hidden" name="workspace" value={selected}/><input type="hidden" name="csrf" value={csrf}/><input type="hidden" name="idempotency" value={randomUUID()}/></>;
  const prefix=`/v1/workspaces/${encodeURIComponent(selected)}`;
  let content;
  if(identifier) {
    const response=await apiGet<{data:S['AIInspection']}>(`${prefix}/ai-tasks/${encodeURIComponent(identifier)}`);
    const d=response.data?.data;
    content=d?<><h2>AI task · {d.state}</h2><p>{d.task.task_type} v{d.task.task_version} · proposal only</p>
      <p>Task {d.id} · <Link href={`/system/jobs/${d.job_id}?workspace=${selected}`}>Job and cancellation</Link></p>
      <p>Route {d.route.route_id} v{d.route.version} · {d.route.primary_provider} · {d.route.primary_model_id}</p>
      <p>Context: {d.context_current?'Current':'Invalid or expired; content and results withheld'}</p><p>Context hash {d.context?.content_hash??'Withheld'}</p>
      <p>Correlation {d.correlation_id}</p>
      <h3>Evidence and unknowns</h3>{d.context?.evidence.map(e=><p key={e.ref.id}>{e.ref.type} · {e.ref.id} v{e.ref.version} · observed {e.ref.observed_at}</p>)}
      <p>{d.result?.unknowns.join('; ')||'No accepted output'}</p><p>{d.result?.uncertainties.join('; ')}</p>
      <h3>Validation</h3><p>{d.result?.status??'No current result'} · {d.result?.validation.defects.join(', ')||'No defects recorded in an available result'}</p>
      {d.result?.result&&<pre>{JSON.stringify(d.result.result,null,2)}</pre>}
      <h3>Model calls and accounting</h3><p>Maximum {d.task.max_model_calls} calls · task cap {d.task.max_cost_usd} simulated USD · {d.task.max_input_tokens}/{d.task.max_output_tokens} input/output tokens</p>
      {d.model_runs.map((call,i)=><details key={i} open><summary>Call {i+1}</summary><pre>{JSON.stringify(call,null,2)}</pre></details>)}
      {d.context_current&&<form method="post" action="/system/ai/command" className="core-card">{hidden}<input type="hidden" name="identifier" value={d.id}/><input type="hidden" name="version" value={d.context?.evidence[0]?.ref.version||1}/><button name="action" value="revoke">Revoke this synthetic context</button><p>This protective action invalidates access and hides any result derived from the source.</p></form>}
      <p>Technical fixtures establish gateway behavior only. No business state or external action is approved by a model output.</p></>:<p role="alert">AI task unavailable or access denied.</p>;
  } else {
    const response=await apiGet<{data:Health}>(`${prefix}/ai-health`);
    const h=response.data?.data;
    content=h?<><h2>Governed AI gateway</h2><p className="notice">Synthetic engineering fixtures only. Live providers: not configured. Business quality: FOUNDER_LABELLED_DATASET_REQUIRED.</p>
      <h3>Provider status</h3>{h.providers.map(p=><p key={p.provider}>{p.provider}: {p.status}</p>)}<p>{h.warning}</p>
      <h3>AI budgets</h3>{h.budgets.map(b=><p key={b.category}>{b.category}: {b.spent_usd} spent + {b.reserved_usd} reserved / {b.limit_usd} simulated USD · {b.status}</p>)}
      <h3>Run a synthetic scenario</h3><form method="post" action="/system/ai/command" className="core-card">{hidden}<label htmlFor="ai-scenario">Scenario</label><select id="ai-scenario" name="scenario">{['success','refusal','repair','incomplete','timeout','forged_evidence','unsupported_claim','injection','secret','tool_url','cross_workspace','incorrect_usage','budget_exhausted','max_calls','fallback_denied','delayed'].map(s=><option key={s}>{s}</option>)}</select><button name="action" value="submit">Create AI task</button></form>
      <h3>Route and evaluation</h3>{h.routes.map(r=><p key={r.id}>{r.state} · {r.id} · {r.body.primary_provider} · evaluation {r.evaluation_status} {r.evaluation_id??'(synthetic bootstrap or draft)'}</p>)}
      <form method="post" action="/system/ai/command" className="core-card">{hidden}<label htmlFor="ai-dataset">Frozen comparison dataset</label><select id="ai-dataset" name="dataset">{['seed','development','holdout','adversarial'].map(s=><option key={s}>{s}</option>)}</select><button name="action" value="evaluate">Compare candidate and current route</button></form>
      {h.evaluations.map(e=><section className="core-card" key={e.id}><h4>{e.body.split} · {e.body.decision} · {e.body.sample_count} samples per route</h4><p>Evaluation {e.id}. Small synthetic sample; no business quality conclusion or confidence interval.</p><details><summary>Candidate and current metrics</summary><pre>{JSON.stringify({candidate:e.body,current:e.current_result},null,2)}</pre></details>{e.body.decision==='technical_pass'&&<form method="post" action="/system/ai/command">{hidden}<input type="hidden" name="route_id" value={e.route_id}/><input type="hidden" name="evaluation_id" value={e.id}/><input type="hidden" name="rollback_route_id" value={e.current_route_id}/><button name="action" value="propose">Request exact route promotion review</button></form>}</section>)}
      <h3>AI runs</h3><p>{h.counts.map(c=>`${c.state}: ${c.count}`).join(' · ')}</p><table><thead><tr><th>Task</th><th>Status</th><th>Reason</th></tr></thead><tbody>{h.tasks.map(t=><tr key={t.id}><td><Link href={`/system/ai/${t.id}?workspace=${selected}`}>{t.id}</Link></td><td>{t.state}</td><td>{t.error_code??'None'}</td></tr>)}</tbody></table><p>Refresh to inspect durable progress.</p></>:<p role="alert">AI gateway unavailable or access denied.</p>;
  }
  return <Shell route="/system" requestedWorkspace={selected}><nav><Link className="outline-link" href={`/system?workspace=${selected}`}>System health</Link><Link className="outline-link" href={`/system/ai?workspace=${selected}`}>AI gateway</Link></nav>{result&&<p role="status">{result==='ok'?'Command accepted.':'Command denied or unavailable. Refresh current state.'}</p>}{content}</Shell>;
}
