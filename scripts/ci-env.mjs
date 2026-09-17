import { readFileSync,writeFileSync } from 'node:fs';
const password=process.env.CI_PG_PASSWORD;
if(!process.env.CI || !password)throw new Error('Ephemeral CI only');
const text=readFileSync('.env','utf8').replace(/^MIGRATION_DATABASE_URL=.*$/m,`MIGRATION_DATABASE_URL=postgresql+psycopg://postgres:${password}@127.0.0.1:55432/company_os`).replace('COMPANY_ENV=development','COMPANY_ENV=test');
writeFileSync('.env',text,{mode:0o600});
