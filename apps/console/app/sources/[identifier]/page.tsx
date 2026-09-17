import { BusinessPage } from '@/components/business';
export default async function Page({params,searchParams}:{params:Promise<{identifier:string}>,searchParams:Promise<{workspace?:string}>}) {
  return <BusinessPage kind="sources" {...await params} {...await searchParams}/>;
}
