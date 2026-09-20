import Link from 'next/link';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import type { ReactNode } from 'react';
import { apiGet,CSRF_COOKIE,type Me,type Health,type WorkspaceResponse } from '@/lib/api';

const routes=[['/attention','Attention','01'],['/approvals','Approvals','02'],['/system','System Health','03'],['/accounts','Accounts','04'],['/leads','Leads','05'],['/knowledge','Knowledge','06']];

export async function Shell({route,requestedWorkspace,children}:{route:string,requestedWorkspace?:string,children?:ReactNode}) {
  const profile=await apiGet<Me>('/v1/me');
  if(profile.status===401)redirect('/login');
  if(!profile.data)return <main className="failure"><h1>Company OS is temporarily unavailable</h1><p>Your workspace could not be loaded. Please retry shortly.</p></main>;
  const user=profile.data.data;
  const selected=requestedWorkspace || user.workspaces[0]?.id;
  const workspace=selected ? await apiGet<WorkspaceResponse>(`/v1/workspaces/${encodeURIComponent(selected)}`):undefined;
  const scope=workspace?.data?.data;
  const csrf=(await cookies()).get(CSRF_COOKIE)?.value;
  const health=scope && route==='/system' ? await apiGet<Health>(`/v1/workspaces/${scope.id}/health`):undefined;
  const title=routes.find(([path])=>path===route)?.[1];
  return <div className="app-frame">
    <aside className="sidebar"><Link className="brand" href="/attention"><span className="brand-mark">C</span> COMPANY OS</Link>
      <div className="workspace-box"><label htmlFor="workspace">WORKSPACE</label>
        <form method="get" action={route}><select id="workspace" name="workspace" defaultValue={scope?.id || ''} aria-label="Workspace">
          {!scope && <option value="">Select workspace</option>}
          {user.workspaces.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}
        </select><button className="switch" type="submit">Open workspace â†’</button></form>
        <span className="small muted">{scope?.kind.replace('_',' ') || 'No workspace selected'}</span>
      </div>
      <span className="nav-label">OVERVIEW</span><nav aria-label="Application navigation">
        {routes.map(([path,label,number])=><Link key={path} href={path+(scope?`?workspace=${scope.id}`:'')} aria-current={path===route?'page':undefined}><span>{number}</span>{label}{path===route&&<i/>}</Link>)}
      </nav>
      <div className="sidebar-bottom"><div className="local-indicator"><i/> Local foundation</div><p>External integrations are not configured.</p></div>
    </aside>
    <div className="main-column"><header className="topbar"><span>{scope?.name || 'Workspace unavailable'} <span className="slash">/</span> {title}</span>
      <div className="user-menu"><div><strong>{user.display_name}</strong><span>{scope?.roles.join(', ').replaceAll('_',' ') || 'No active membership'}</span></div>
        <form action="/auth/logout" method="post"><input type="hidden" name="csrf" value={csrf || ''}/><button className="text-button">Sign out</button></form></div>
    </header>
    <main className="content"><div className="page-heading"><div><span className="eyebrow">YOUR OPERATING SPACE</span><h1>{title}</h1></div><span className="phase-tag">PHASE 6B</span></div>
      {!scope ? <section className="empty-state" role="alert"><div className="empty-symbol">âŠ˜</div><h2>Workspace unavailable</h2><p>This workspace is unavailable or you do not have access.</p><Link href={route}>Return to your workspace</Link></section>
      : children ? children : route==='/system' ? <><p className="page-intro">Connection status for this foundation. Unconfigured services have no active connections.</p>
        {health?.data ? <section className="health-panel"><div className="panel-heading"><h2>Platform status</h2><span className="small muted">Checked {new Date(health.data.meta.as_of).toISOString().slice(11,19)} UTC</span></div>
          {health.data.data.components.map(component=><div className="health-row" key={component.name}><span>{component.name}</span><span className={component.status==='healthy'?'status healthy':'status'}>{component.status==='healthy'?'Healthy':'Not configured'}</span></div>)}
        </section>:<section className="notice error" role="alert">System status unavailable. Health could not be confirmed.</section>}
        <div className="notice">Live sending is disabled. The worker currently performs connectivity checks only.</div></>
      : <><p className="page-intro">{route==='/attention'?'A focused place for decisions that need your attention.':'A dedicated place to review and authorize future work.'}</p>
        <section className="empty-state"><div className="empty-symbol">{route==='/attention'?'âœ“':'â—‡'}</div><span className="eyebrow">{route==='/attention'?'A CLEAR START':'NOTHING AWAITING REVIEW'}</span>
          <h2>{route==='/attention'?'No decisions currently require action.':'No approvals pending.'}</h2>
          <p>{route==='/attention'?'Your workspace foundation is ready. Business workflows will appear here as they are introduced.':'Approval workflows are not enabled in this foundation. No business actions can be approved or executed yet.'}</p>
          <Link href={`/system?workspace=${scope.id}`} className="outline-link">View system health <span>â†—</span></Link>
        </section></>}
      <footer className="page-footer"><span>Company OS Â· Platform foundation</span><span>Private by design. Scoped to your workspace.</span></footer>
    </main></div>
  </div>;
}
