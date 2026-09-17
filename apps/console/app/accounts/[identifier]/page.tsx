import { BusinessPage } from '@/components/business';
export default async function Page({params,searchParams}:{params:Promise<{identifier:string}>,searchParams:Promise<{workspace?:string,result?:string}>}) {
  return <BusinessPage kind="accounts" {...await params} {...await searchParams}/>;
}
