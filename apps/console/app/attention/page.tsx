import { AttentionPage } from '@/components/attention';
export default async function Page({searchParams}:{searchParams:Promise<{workspace?:string}>}) {
  return <AttentionPage workspace={(await searchParams).workspace}/>;
}
