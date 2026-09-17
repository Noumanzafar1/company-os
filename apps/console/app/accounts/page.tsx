import { BusinessPage } from '@/components/business';
export default async function Page({searchParams}:{searchParams:Promise<{workspace?:string,cursor?:string}>}) {
  return <BusinessPage kind="accounts" {...await searchParams}/>;
}
