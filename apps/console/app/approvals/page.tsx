import { Shell } from '@/components/shell';
export default async function Page({searchParams}:{searchParams:Promise<{workspace?:string}>}) {
  return <Shell route="/approvals" requestedWorkspace={(await searchParams).workspace}/>;
}
