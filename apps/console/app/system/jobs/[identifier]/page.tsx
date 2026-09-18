import { RuntimePage } from '@/components/runtime';
export default async function Page({searchParams,params}:{searchParams:Promise<{workspace?:string,result?:string}>,params:Promise<{identifier:string}>}) {
  return <RuntimePage kind="jobs" {...await searchParams} {...await params}/>;
}
