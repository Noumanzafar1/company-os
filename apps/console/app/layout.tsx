import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {title:'Company OS · Foundation',description:'Private Company OS workspace'};
export default function RootLayout({children}:{children:React.ReactNode}) {
  return <html lang="en"><body>{children}</body></html>;
}
