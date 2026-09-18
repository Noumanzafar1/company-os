import { RuntimePage } from '@/components/runtime';
export default async function Page({searchParams}:{searchParams:Promise<{workspace?:string,result?:string}>}) {
  return <RuntimePage kind="jobs" {...await searchParams}/>;
}
