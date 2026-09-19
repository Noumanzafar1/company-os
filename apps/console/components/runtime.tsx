import Link from 'next/link';
import { cookies } from 'next/headers';
import { Shell } from '@/components/shell';
import { apiGet, CSRF_COOKIE, type Me, type Health } from '@/lib/api';
import type { components } from '../../../packages/contracts/api';

type Schema=components['schemas'];
type Envelope<T>={data:T};

export async function RuntimePage({workspace,kind='health',identifier,result}:{workspace?:string,kind?:'health'|'jobs'|'events'|'incidents',identifier?:string,result?:string}) {
  const profile=await apiGet<Me>('/v1/me');
  const selected=workspace || profile.data?.data.workspaces[0]?.id;
  if(!selected)return <Shell route="/system"/>;
  const prefix=`/v1/workspaces/${encodeURIComponent(selected)}`;
  const csrf=(await cookies()).get(CSRF_COOKIE)?.value || '';
  const unavailable=<p role="alert" className="notice error">Runtime records unavailable or access denied.</p>;
  const nav=<nav aria-label="Runtime navigation">{[['','Health'],['/jobs','Jobs and dead letters'],['/events','Event trace'],['/incidents','Incidents'],['/ai','AI gateway']].map(([path,label])=><Link className="outline-link" key={path} href={`/system${path}?workspace=${selected}`}>{label}</Link>)}</nav>;
  let content;
  if(kind==='health') {
    const foundation=await apiGet<Health>(`${prefix}/health`);
    const response=await apiGet<Envelope<Schema['RuntimeHealth']>>(`${prefix}/runtime-health`);
    const health=response.data?.data;
    content=health?<><p className="notice">Synthetic runtime only. Live sending is disabled. Real integrations: Not configured.</p>
      <h2>Platform status</h2>{foundation.data?.data.components.map(c=><div className="health-row" key={c.name}><span>{c.name}</span><span>{c.status==="healthy"?"Healthy":"Not configured"}</span></div>)}
      <h2>Runtime status: {health.status}</h2><p>Checked {health.as_of} · thresholds {health.threshold_version}</p>
      <section className="health-panel">{health.components.map(c=><div className="health-row" key={c.name}><span>{c.name.replaceAll('_',' ')}</span><strong>{c.status}{c.age_seconds!=null?` · ${Math.round(c.age_seconds)}s`:''}{c.count!=null?` · ${c.count}`:''}</strong></div>)}</section>
      <h2>Queues</h2>{health.queues.length?<table><thead><tr><th>State</th><th>Priority</th><th>Count</th></tr></thead><tbody>{health.queues.map(q=><tr key={q.state+q.priority}><td>{q.state}</td><td>{q.priority}</td><td>{q.count}</td></tr>)}</tbody></table>:<p>No durable jobs yet.</p>}
      <h2>Synthetic budgets</h2>{health.budgets.map(b=><p key={b.id}>{b.category}: spent {b.spent_usd} + reserved {b.reserved_usd} / {b.limit_usd} simulated USD · {b.status}</p>)}
      <h2>Uncertain effects</h2>{health.uncertain_effects.length?health.uncertain_effects.map(e=><p key={e.id}><Link href={`/system/jobs/${e.job_id}?workspace=${selected}`}>{e.id}</Link> · {e.state} · reconciliation {e.reconcile_after??'pending'}</p>):<p>No unresolved effects recorded.</p>}
      <h2>Long execution safety demo</h2><form method="post" action="/system/command" className="core-card"><input type="hidden" name="workspace" value={selected}/><input type="hidden" name="csrf" value={csrf}/><input type="hidden" name="action" value="long"/><label htmlFor="long-handler">Local synthetic handler</label><select id="long-handler" name="handler">{['sleep_success','infinite_cpu','cooperative_cancel','ignore_cancel','child_crash','fake_remote_accept_then_hang'].map(h=><option key={h}>{h}</option>)}</select><button type="submit">Create long synthetic work</button></form><p>Open the newest job to inspect execution history or request cancellation. No real provider is connected.</p>
      <h2>Trigger a synthetic scenario</h2><form method="post" action="/system/command" className="core-card"><input type="hidden" name="workspace" value={selected}/><input type="hidden" name="csrf" value={csrf}/><input type="hidden" name="action" value="synthetic"/>
      <label htmlFor="scenario">Scenario</label><select id="scenario" name="scenario">{['success','transient','invalid','exhausted','wait','effect_success','effect_rejected','effect_lost','effect_unknown','safety'].map(s=><option key={s}>{s}</option>)}</select><button type="submit">Create synthetic work</button></form>
      <p>Refresh to inspect durable progress. Lost-response scenarios retain the reservation and reconcile from the fake receipt after its delayed visibility.</p></>:unavailable;
  } else if(kind==='jobs' && identifier) {
    const response=await apiGet<Envelope<Schema['JobDetail']>>(`${prefix}/jobs/${encodeURIComponent(identifier)}`);
    const detail=response.data?.data;
    content=detail?<><h2>{detail.job.job_type} · {detail.job.state}</h2><p>Job {detail.job.id}</p><p>Correlation {detail.job.correlation_id} · workflow {detail.job.workflow_run_id??'None'}</p><p>Origin event {detail.job.origin_event_id??'Schedule/internal command'}</p><p>Fence {detail.job.fence} · attempt {detail.job.attempt_count}/{detail.job.max_attempts} · error {detail.job.last_error_code??'None'}</p>
      <h3>Attempts</h3><table><thead><tr><th>Attempt</th><th>Record</th><th>Outcome</th><th>Fence / worker</th></tr></thead><tbody>{detail.attempts.map(a=><tr key={a.id}><td>{a.attempt_no}</td><td>{a.phase}</td><td>{a.outcome} {a.error_code}</td><td>{a.fence} / {a.worker_id}</td></tr>)}</tbody></table>
      {detail.effect&&<section className="core-card"><h3>Fake effect: {detail.effect.state}</h3>{detail.job.coalesced_effect_id&&<p>This job follows the result of <Link href={`/system/jobs/${detail.effect.job_id}?workspace=${selected}`}>the canonical job</Link>; it has no dispatch or reservation authority.</p>}<p>Effect {detail.effect.id} · key {detail.effect.effect_key}</p><p>Provider receipt {detail.effect.provider_request_id??'Unknown'}</p><p>Reservation {detail.effect.reservation_id}</p><p>Request hash {detail.effect.request_hash}</p><p>Receipt hash {detail.effect.receipt_hash??'Unknown'}</p></section>}
      {detail.long_executions.length>0&&<><h3>Long executions</h3><table><thead><tr><th>Execution / fence</th><th>State / outcome</th><th>Elapsed</th><th>Termination</th></tr></thead><tbody>{detail.long_executions.map(x=><tr key={x.id}><td>{x.id} / {x.fence}</td><td>{x.state} · {x.outcome??'Pending'}</td><td>{x.elapsed_ms==null?'Unknown':`${Math.round(x.elapsed_ms)} ms`}</td><td>{x.forced==null?'Not yet recorded':x.forced?'Forced':'No force required'}</td></tr>)}</tbody></table></>}
      <h3>Event trace</h3>{detail.events.map(e=><p key={e.id}>{e.occurred_at} · {e.event_type} · {e.id}</p>)}
      <form method="post" action="/system/command" className="core-card"><input type="hidden" name="workspace" value={selected}/><input type="hidden" name="csrf" value={csrf}/><input type="hidden" name="job" value={identifier}/><input type="hidden" name="version" value={detail.job.record_version}/><label htmlFor="reason">Recovery or cancellation reason</label><input id="reason" name="reason" required minLength={5} maxLength={500}/><label><input type="checkbox" name="cause_changed"/> The transient cause has changed</label><button name="action" value="retry" disabled={detail.job.state!=='dead_letter'}>Retry eligible work</button><button name="action" value="cancel" disabled={['succeeded','cancelled','dead_letter'].includes(detail.job.state)}>Request cancellation</button></form></>:unavailable;
  } else if(kind==='jobs') {
    const response=await apiGet<Envelope<Schema['JobView'][]>>(`${prefix}/jobs`);
    content=response.data?<><h2>Jobs and dead letters</h2><table><thead><tr><th>Job</th><th>State</th><th>Attempts</th><th>Last error</th></tr></thead><tbody>{response.data.data.map(j=><tr key={j.id}><td><Link href={`/system/jobs/${j.id}?workspace=${selected}`}>{j.job_type} · {j.id.slice(0,8)}</Link></td><td>{j.state}</td><td>{j.attempt_count}</td><td>{j.last_error_code??'None'}</td></tr>)}</tbody></table><p>Most recent 50 jobs.</p></>:unavailable;
  } else if(kind==='events') {
    const response=await apiGet<Envelope<Schema['EventView'][]>>(`${prefix}/events`);
    content=response.data?<><h2>Event trace</h2>{response.data.data.map(e=><section className="core-card" key={e.id}><strong>{e.event_type}</strong><p>{e.occurred_at} · {e.id}</p><p>Correlation {e.correlation_id} · causation {e.causation_id??'Root command'}</p></section>)}</>:unavailable;
  } else {
    const response=await apiGet<Envelope<Schema['IncidentView'][]>>(`${prefix}/incidents`);
    content=response.data?<><h2>Technical incidents</h2>{response.data.data.length?response.data.data.map(i=><section className="core-card" key={i.id}><strong>{i.severity} · {i.kind} · {i.state}</strong><p>{i.id} · opened {i.opened_at}</p><p>Owner {i.owner_id}</p></section>):<p>No incidents recorded.</p>}</>:unavailable;
  }
  return <Shell route="/system" requestedWorkspace={selected}>{nav}{result&&<p role="status">{result==='ok'?'Command accepted.':'Command denied or unavailable; refresh current state before retrying.'}</p>}{content}</Shell>;
}
