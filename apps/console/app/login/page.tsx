import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { CSRF_COOKIE, origin } from '@/lib/api';
import { isLocalDevelopment } from '@/lib/security';

export default async function Login({searchParams}:{searchParams:Promise<{error?:string}>}) {
  const csrf=(await cookies()).get(CSRF_COOKIE)?.value;
  if(!csrf)redirect('/auth/prepare');
  const {error}=await searchParams;
  const local=isLocalDevelopment(process.env.COMPANY_ENV,process.env.AUTH_MODE,origin());
  return <main className="login-wrap"><section className="login-card">
    <div className="brand"><span className="brand-mark">C</span> COMPANY OS</div>
    <span className="eyebrow">PRIVATE WORKSPACE</span>
    <h1>A clear place<br/>to run the company.</h1>
    <p className="muted">Sign in to your assigned workspace.</p>
    {error && <p role="alert" className="notice error">Sign-in unavailable. Please try again.</p>}
    {local ? <><div className="notice">Local foundation demo · synthetic identities only</div>
      <form action="/auth/login" method="post">
        <input type="hidden" name="csrf" value={csrf}/>
        <button className="primary" name="identity" value="a">Sign in as Synthetic User A <span>→</span></button>
        <button className="secondary" name="identity" value="b">Sign in as Synthetic User B <span>→</span></button>
      </form><p className="small muted">Each identity has access to one separate workspace. No public signup.</p></>
      : <div className="notice">Invite-only managed sign-in is not configured for this environment. Contact the workspace owner.</div>}
    <footer>PHASE 02 <span>Repository & platform foundation</span></footer>
  </section></main>;
}
