import 'server-only';
import { cookies } from 'next/headers';
import type { paths } from '../../../packages/contracts/api';

// Generated API paths are the single source of request/response types.
export type Me = paths['/v1/me']['get']['responses'][200]['content']['application/json'];
export type WorkspaceResponse = paths['/v1/workspaces/{workspace_id}']['get']['responses'][200]['content']['application/json'];
export type Health = paths['/v1/workspaces/{workspace_id}/health']['get']['responses'][200]['content']['application/json'];
export type SessionResponse = paths['/v1/auth/session']['post']['responses'][200]['content']['application/json'];
export type SessionRequest = paths['/v1/auth/session']['post']['requestBody']['content']['application/json'];

export const SESSION_COOKIE = 'company_session';
export const CSRF_COOKIE = 'company_csrf';
export const origin = () => process.env.CONSOLE_ORIGIN || 'http://localhost:3000';
export const apiUrl = () => process.env.API_URL || 'http://127.0.0.1:8000';
export const cookieOptions = () => ({httpOnly:true,secure:['staging','production'].includes(process.env.COMPANY_ENV || ''),sameSite:'strict' as const,path:'/',maxAge:43200});

export async function apiGet<T>(path: string): Promise<{data?:T,status:number}> {
  const token=(await cookies()).get(SESSION_COOKIE)?.value;
  if(!token)return {status:401};
  try {
    const response=await fetch(apiUrl()+path,{headers:{Authorization:`Bearer ${token}`},cache:'no-store',signal:AbortSignal.timeout(8000)});
    return response.ok ? {data:await response.json() as T,status:response.status}:{status:response.status};
  } catch {return {status:503};}
}
