import { ApprovalsPage } from '@/components/approvals';
export default async function Page({params,searchParams}:{params:Promise<{identifier:string}>,searchParams:Promise<{workspace?:string,result?:string}>}) {
  return <ApprovalsPage {...await searchParams} identifier={(await params).identifier}/>;
}
