import Link from 'next/link';
import { cookies } from 'next/headers';
import { Shell } from '@/components/shell';
import { apiGet, CSRF_COOKIE, type Me } from '@/lib/api';
import type { components } from '../../../packages/contracts/api';

type Schema=components['schemas'];
type Account=Schema['AccountView'];
type AccountDetail=Schema['AccountDetail'];
type Lead=Schema['LeadView'];
type Evidence=Schema['EvidenceView'];
type Source=Schema['SourceView'];
type Score=Schema['ScoreView'];
type Knowledge=Schema['KnowledgeHit'];
type ICP=Schema['ICPVersionView'];
type Offer=Schema['OfferVersionView'];
type Envelope<T>={data:T};
type Page<T>={data:T[],next_cursor?:string|null};

function ScoreCard({score}:{score:Score}) {
  return <section className="core-card"><h3>Score {score.known_points} / 100 · {score.priority}</h3>
    <p>{score.current_support?'Supporting evidence is current.':'Historical score — supporting evidence or identity is no longer current.'}</p>
    <p>Unknown: {score.missing_keys.join(', ') || 'None'} · Exclusions: {score.hard_exclusions.join(', ') || 'None'}</p>
    <table><thead><tr><th>Component</th><th>Points</th><th>Support / reason</th></tr></thead><tbody>
      {score.components.map(c=><tr key={c.component}><td>{c.component}</td><td>{c.points??'Unknown'} / {c.max_points}</td><td>{c.evidence_ids.length} evidence references {c.reason_codes.join(', ')}</td></tr>)}
    </tbody></table><details><summary>Reproducibility</summary><p>ICP version: {score.icp_version_id}</p><p>Policy hash: {score.policy_hash}</p><p>Input hash: {score.input_hash}</p></details>
    <p className="small">Deterministic synthetic prioritization. No qualification or outreach permission.</p>
  </section>;
}

function EvidenceCard({item,workspace}:{item:Evidence,workspace:string}) {
  return <article className="core-card"><h3>{item.fact_key}: {item.fact_value.value===null?'Unknown':String(item.fact_value.value)}</h3>
    <p>{item.fact_kind} · entity match: {item.entity_match} · {item.current_support?'Current support':item.invalid_reasons.join(', ')}</p>
    <p>Observed {item.observed_at} · expires {item.expires_at}</p>
    <p><Link href={`/sources/${item.source_id}?workspace=${workspace}`}>Inspect source rights</Link> · Reference: {item.provider_record_id??item.source_url??'Document'}</p>
    <details><summary>Evidence identity and hash</summary><p>{item.id}</p><p>{item.content_sha256}</p></details>
  </article>;
}

export async function BusinessPage({kind,identifier,workspace,cursor,query,result}:{kind:'accounts'|'leads'|'evidence'|'sources'|'knowledge',identifier?:string,workspace?:string,cursor?:string,query?:string,result?:string}) {
  const profile=await apiGet<Me>('/v1/me');
  const selected=workspace || profile.data?.data.workspaces[0]?.id;
  const route=kind==='evidence'||kind==='sources'?'/accounts':`/${kind}`;
  if(!selected)return <Shell route={route} requestedWorkspace={workspace}/>;
  const prefix=`/v1/workspaces/${encodeURIComponent(selected)}`;
  const csrf=(await cookies()).get(CSRF_COOKIE)?.value || '';
  let content;
  const unavailable=<section role="alert" className="notice error">Business records unavailable or you do not have permission.</section>;
  if(kind==='accounts' && identifier) {
    const response=await apiGet<Envelope<AccountDetail>>(`${prefix}/accounts/${encodeURIComponent(identifier)}`);
    const detail=response.data?.data;
    content=detail?<>
      <p><Link href={`/accounts?workspace=${selected}`}>← All accounts</Link></p><h2>{detail.account.display_name}</h2>
      <p>{detail.account.primary_domain??'Domain unknown'} · discriminator: {detail.account.identity_discriminator} · {detail.account.status}</p>
      {detail.account.merged_into_id&&<p>Retired identity redirects to <Link href={`/accounts/${detail.account.merged_into_id}?workspace=${selected}`}>surviving account</Link>.</p>}
      <p>Unknown fields: {detail.account.unknown_fields.join(', ') || 'None'}</p>
      <p><Link href={`/sources/${detail.source.id}?workspace=${selected}`}>{detail.source.name}</Link> · {detail.source.rights_status} · {detail.source.current_use_allowed?'Research use allowed':'New factual use blocked'}</p>
      <h2>Score explanation</h2>{result&&<p role="status">{result==='ok'?'Rescoring completed. Identical inputs reuse the immutable score.':'Rescoring could not be completed.'}</p>}
      {detail.scores.length>0&&<form action="/business/rescore" method="post"><input type="hidden" name="csrf" value={csrf}/><input type="hidden" name="workspace" value={selected}/><input type="hidden" name="account" value={detail.account.id}/><input type="hidden" name="icp" value={detail.scores[0].icp_version_id}/><button type="submit" className="outline-link">Recalculate deterministic score</button></form>}
      {detail.scores.length?detail.scores.map(s=><ScoreCard key={s.id} score={s}/>):<p>No score recorded.</p>}
      <h2>Why Company OS believes this</h2>{detail.evidence.map(e=><EvidenceCard key={e.id} item={e} workspace={selected}/>)}
      <h2>Observed signals</h2>{detail.signals.length?detail.signals.map(s=><section className="core-card" key={s.id}><h3>{s.kind} · {s.status}</h3><p>{s.relevance_summary}</p><p>{s.current_support?'Current support':'Expired or unsupported'}</p></section>):<p>Signals unknown.</p>}
      <h2>Employment relationships</h2>{detail.employments.length?detail.employments.map(e=><p key={e.id}>{e.title} · {e.status} · person {e.person_id} · {e.current_support?'Current supporting evidence':'Stale evidence'}</p>):<p>No employment facts recorded.</p>}
    </>:unavailable;
  } else if(kind==='accounts') {
    const response=await apiGet<Page<Account>>(`${prefix}/accounts${cursor?`?cursor=${encodeURIComponent(cursor)}`:''}`);
    content=response.data?<><p className="page-intro">Synthetic business identities with source provenance. Shared domains remain distinct.</p><div className="core-grid">{response.data.data.map(a=><article className="core-card" key={a.id}><h2><Link href={`/accounts/${a.id}?workspace=${selected}`}>{a.display_name}</Link></h2><p>{a.primary_domain??'Domain unknown'}</p><p>{a.identity_discriminator} · {a.status}</p><p>Unknown: {a.unknown_fields.join(', ') || 'None'}</p><p>{a.current_fact_count} current facts; source {a.source_status}</p><p>Signals: {a.signals.join(', ') || 'Unknown'}</p><p>Score: {a.score_summary?.known_points??'Unknown'}; {a.score_summary?.priority??'Unscored'}; {a.score_summary?.current_support?'current support':'review freshness'}</p><Link href={`/sources/${a.source_id}?workspace=${selected}`}>Source and rights</Link></article>)}</div>{response.data.next_cursor&&<Link href={`/accounts?workspace=${selected}&cursor=${encodeURIComponent(response.data.next_cursor)}`}>Next page</Link>}</>:unavailable;
  } else if(kind==='leads') {
    const response=await apiGet<Page<Lead>>(`${prefix}/leads${cursor?`?cursor=${encodeURIComponent(cursor)}`:''}`);
    const leads=response.data?.data;
    const scores=leads?await Promise.all(leads.map(l=>l.latest_score_id?apiGet<Envelope<Score>>(`${prefix}/scores/${l.latest_score_id}`):Promise.resolve(null))):[];
    const icpIds=[...new Set(leads?.map(lead=>lead.icp_version_id)??[])];
    const offerIds=[...new Set(leads?.map(lead=>lead.offer_version_id)??[])];
    const icps=new Map(await Promise.all(icpIds.map(async id=>[id,(await apiGet<Envelope<ICP>>(`${prefix}/icp-versions/${id}`)).data?.data] as const)));
    const offers=new Map(await Promise.all(offerIds.map(async id=>[id,(await apiGet<Envelope<Offer>>(`${prefix}/offer-versions/${id}`)).data?.data] as const)));
    content=leads?<><p className="page-intro">Prospecting relationships. ICP and Offer definitions are draft versions; eligibility and sending are unavailable.</p>{leads.map((lead,index)=><article className="core-card" key={lead.id}><h2><Link href={`/accounts/${lead.account_id}?workspace=${selected}`}>{lead.account_name}</Link></h2><p>State: {lead.state} · person: {lead.person_name??'Unknown'}</p><p>ICP version: {lead.icp_name} v{lead.icp_version} ({lead.icp_version_id})</p><p>Offer version: {lead.offer_name} v{lead.offer_version} ({lead.offer_version_id})</p><details><summary>Inspect draft ICP and Offer definitions</summary><p>Industry criteria: {icps.get(lead.icp_version_id)?.criteria.industries.join(', ')??'Unavailable'}</p><p>Required problem evidence: {icps.get(lead.icp_version_id)?.criteria.required_problem_fact_keys.join(', ')??'Unavailable'}</p><p>Excluded industries: {icps.get(lead.icp_version_id)?.exclusions.industry_codes?.join(', ')||'None'}</p><p>Rubric: {icps.get(lead.icp_version_id)?.score_policy.version??'Unavailable'}</p><p>Offer scope: {offers.get(lead.offer_version_id)?.scope??'Unavailable'}</p><p>Offer exclusions: {offers.get(lead.offer_version_id)?.exclusions??'Unavailable'}</p><p>Capacity: {offers.get(lead.offer_version_id)?.capacity_limit??'Unknown'}</p></details>{scores[index]?.data&&<ScoreCard score={scores[index]!.data!.data}/>}</article>)}{response.data?.next_cursor&&<Link href={`/leads?workspace=${selected}&cursor=${encodeURIComponent(response.data.next_cursor)}`}>Next page</Link>}</>:unavailable;
  } else if(kind==='sources' && identifier) {
    const response=await apiGet<Envelope<Source>>(`${prefix}/sources/${encodeURIComponent(identifier)}`);
    const source=response.data?.data;
    content=source?<section className="core-card"><h2>{source.name}</h2><p>Rights: {source.rights_status} · {source.current_use_allowed?'Current research use allowed':'New factual use blocked'}</p><p>Purposes: {source.permitted_purposes.join(', ')}</p><p>Permitted fields: {source.allowed_fields.join(', ')}</p><p>Expiry: {source.expires_at??'Unknown'} · retention: {source.retention_days??'Unknown'} days</p><p>Rights evidence version: {source.rights_document_version_id??'Missing'}</p><p>Source approval never grants outreach permission.</p></section>:unavailable;
  } else if(kind==='evidence' && identifier) {
    const response=await apiGet<Envelope<Evidence>>(`${prefix}/evidence/${encodeURIComponent(identifier)}`);
    content=response.data?<EvidenceCard item={response.data.data} workspace={selected}/>:unavailable;
  } else {
    const response=query?await apiGet<Envelope<Knowledge[]>>(`${prefix}/knowledge/search?q=${encodeURIComponent(query)}`):null;
    content=<><form method="get" action="/knowledge"><input type="hidden" name="workspace" value={selected}/><label htmlFor="knowledge-query">Search synthetic knowledge</label><input id="knowledge-query" name="q" defaultValue={query??''} maxLength={200} required/><button type="submit">Search</button></form>{response?(response.data?response.data.data.map(hit=><article className="core-card" key={hit.knowledge_id}><h2>{hit.title}</h2><p>{hit.status} · review due {hit.review_due_at}</p><p>{hit.excerpt}</p><p>Document version {hit.document_version_id}</p></article>):unavailable):<p>Search is scoped by workspace membership and document permissions.</p>}</>;
  }
  return <Shell route={route} requestedWorkspace={selected}><div className="core-state">{content}</div></Shell>;
}
