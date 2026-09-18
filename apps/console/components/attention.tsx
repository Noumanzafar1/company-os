import Link from 'next/link';
import { Shell } from '@/components/shell';
import { apiGet,type Me } from '@/lib/api';

export async function AttentionPage({workspace}:{workspace?:string}) {
  const profile=await apiGet<Me>('/v1/me');
  const selected=workspace||profile.data?.data.workspaces[0]?.id;
  if(!selected)return <Shell route="/attention"/>;
  const prefix=`/v1/workspaces/${encodeURIComponent(selected)}`;
  const [technical,approvals]=await Promise.all([
    apiGet<{data:{id:string,kind:string,severity:string,state:string}[]}>(`${prefix}/incidents`),
    apiGet<{data:{id:string,effective_state:string,expires_at:string,maximum_spend:string,maximum_volume:number,payload:{label:string}}[]}>(`${prefix}/approvals`),
  ]);
  const incidents=(technical.data?.data||[]).filter(i=>i.state!=='resolved').map(i=>({id:i.id,title:i.kind.replaceAll('_',' '),priority:i.severity,url:`/system/incidents?workspace=${selected}`,expiry:'',impact:0}));
  const requests=(approvals.data?.data||[]).filter(a=>a.effective_state==='pending').map(a=>({id:a.id,title:a.payload.label,priority:'P2',url:`/approvals/${a.id}?workspace=${selected}`,expiry:a.expires_at,impact:Number(a.maximum_spend)+a.maximum_volume}));
  const ranked=[...incidents,...requests].sort((a,b)=>a.priority.localeCompare(b.priority)||(a.expiry||'9999').localeCompare(b.expiry||'9999')||b.impact-a.impact||a.id.localeCompare(b.id));
  const primary=ranked.slice(0,5),critical=ranked.slice(5).filter(i=>['P0','P1'].includes(i.priority));
  return <Shell route="/attention" requestedWorkspace={selected}>
    <p className="page-intro">Current decisions, with technical safety first.</p>
    {!technical.data&&<p role="alert">Technical attention is unavailable; safety cannot be confirmed.</p>}
    {!approvals.data&&<p role="alert">Business approvals are unavailable or outside your role.</p>}
    {ranked.length?primary.map(i=><section key={i.id} className="core-card"><strong>{i.priority}</strong> · <Link href={i.url}>{i.title}</Link>{i.expiry&&<p>Authority request expires {i.expiry}</p>}</section>):technical.data&&approvals.data?<h2>No decisions currently require action.</h2>:<p>Current decisions cannot be confirmed.</p>}
    {critical.length>0&&<section role="alert"><h2>{critical.length} further critical incidents</h2>{critical.map(i=><p key={i.id}><Link href={i.url}>{i.priority} · {i.title}</Link></p>)}</section>}
    {ranked.length>5&&<Link href={`/approvals?workspace=${selected}`}>Inspect the full approval queue</Link>}
  </Shell>;
}
