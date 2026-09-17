import { BusinessPage } from '@/components/business';
export default async function Page({searchParams}:{searchParams:Promise<{workspace?:string,cursor?:string}>}) {
  return <BusinessPage kind="leads" {...await searchParams}/>;
}
