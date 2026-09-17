import { Shell } from '@/components/shell';
export default async function Page({searchParams}:{searchParams:Promise<{workspace?:string}>}) {
  return <Shell route="/attention" requestedWorkspace={(await searchParams).workspace}/>;
}
