import { BusinessPage } from '@/components/business';
export default async function Page({searchParams}:{searchParams:Promise<{workspace?:string,q?:string}>}) {
  const search=await searchParams;
  return <BusinessPage kind="knowledge" workspace={search.workspace} query={search.q}/>;
}
