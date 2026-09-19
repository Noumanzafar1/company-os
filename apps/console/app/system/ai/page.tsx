import { AIPage } from '@/components/ai';
export default async function Page({searchParams}:{searchParams:Promise<{workspace?:string,result?:string}>}) {
  return <AIPage {...await searchParams}/>;
}
