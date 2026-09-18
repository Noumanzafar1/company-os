import { RuntimePage } from '@/components/runtime';
export default async function Page({searchParams}:{searchParams:Promise<{workspace?:string}>}) {
  return <RuntimePage kind="incidents" {...await searchParams}/>;
}
