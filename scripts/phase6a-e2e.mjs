import {randomBytes} from 'node:crypto';
import {loadEnv,python,run} from './local.mjs';

loadEnv();
const name='company_os_e2e_'+randomBytes(6).toString('hex');
run(python,['scripts/phase6a_e2e_database.py','create',name]);
try {
  for(const key of ['MIGRATION_DATABASE_URL','DATABASE_URL','WORKER_DATABASE_URL'])process.env[key]=process.env[key].replace(/\/[^/]+$/,'/'+name);
  run(python,['-m','alembic','upgrade','head']);
  run(python,['-m','database.seeds.synthetic']);
  run(process.execPath,['scripts/ci-services.mjs','e2e']);
} finally {run(python,['scripts/phase6a_e2e_database.py','drop',name]);}
