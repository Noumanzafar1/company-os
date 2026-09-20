import { AIPage } from '@/components/ai';
export default async function Page({searchParams,params}:{searchParams:Promise<{workspace?:string,result?:string}>,params:Promise<{identifier:string}>}) {
  return <AIPage {...await searchParams} {...await params}/>;
}
