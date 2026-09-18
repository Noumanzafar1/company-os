import { ApprovalsPage } from '@/components/approvals';
export default async function Page({searchParams}:{searchParams:Promise<{workspace?:string,result?:string}>}) {
  return <ApprovalsPage {...await searchParams}/>;
}
