import { spawn, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync, unlinkSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { resolve } from 'node:path';
import EmbeddedPostgres from 'embedded-postgres';

const root = process.cwd();
const win = process.platform === 'win32';
export const python = resolve('.venv', win ? 'Scripts/python.exe' : 'bin/python');
const local = resolve('.local');
mkdirSync(local, {recursive:true});
const secret = () => randomBytes(32).toString('hex');
export function loadEnv() {
  if (!existsSync('.env')) throw new Error('Run npm run setup first.');
  for (const line of readFileSync('.env','utf8').split(/\r?\n/)) {
    const match = line.match(/^([A-Z_]+)=(.*)$/);
    if (match && !process.env[match[1]]) process.env[match[1]]=match[2];
  }
  process.env.PYTHONPATH = `${root}${win?';':':'}${resolve('packages')}`;
}
export function run(command, args, options={}) {
  const result=spawnSync(command,args,{stdio:'inherit',windowsHide:true,...options});
  if(result.error) throw result.error;
  if(result.status!==0) throw new Error(`${command} failed (${result.status})`);
}
export function serviceEnvironments() {
  const runtimeEnv={...process.env};
  delete runtimeEnv.MIGRATION_DATABASE_URL;
  const apiEnv={...runtimeEnv}; delete apiEnv.WORKER_DATABASE_URL;
  const consoleEnv={...runtimeEnv}; delete consoleEnv.DATABASE_URL; delete consoleEnv.WORKER_DATABASE_URL;
  const workerEnv={...runtimeEnv};
  delete workerEnv.DATABASE_URL; delete workerEnv.DEV_AUTH_SECRET; delete workerEnv.CONSOLE_SECRET;
  return {apiEnv,consoleEnv,workerEnv};
}
const action=process.argv[2];
if(action==='setup') {
  if(!existsSync('.env')) {
    const owner=secret(), api=secret(), worker=secret();
    writeFileSync('.env',[
      'COMPANY_ENV=development','AUTH_MODE=development','CONSOLE_ORIGIN=http://localhost:3000',
      'API_URL=http://127.0.0.1:8000',
      `MIGRATION_DATABASE_URL=postgresql+psycopg://postgres:${owner}@127.0.0.1:55432/company_os`,
      `DATABASE_URL=postgresql+psycopg://company_api:${api}@127.0.0.1:55432/company_os`,
      `WORKER_DATABASE_URL=postgresql+psycopg://company_worker:${worker}@127.0.0.1:55432/company_os`,
      `DEV_AUTH_SECRET=${secret()}`,`CONSOLE_SECRET=${secret()}`,'LIVE_SENDING_ENABLED=false','LIVE_BUDGET_USD=0',''
    ].join('\n'),{mode:0o600,flag:'wx'});
  }
  if(!existsSync(python)) run(process.env.COMPANY_PYTHON || (win?'python':'python3'),['-m','venv','.venv']);
  run(python,['-m','pip','install','--require-hashes','-r','requirements.lock']);
  run(python,['-m','pip','install','--no-deps','--no-build-isolation','-e','.']);
  console.log('Local dependencies and random secrets ready. Run npm run dev.');
} else if(action==='stop') {
  writeFileSync(resolve('.local/services.stop'),'stop');
  writeFileSync(resolve('.local/worker.stop'),'stop');
  writeFileSync(resolve('.local/api.stop'),'stop');
  console.log('Requested clean shutdown of local services.');
} else if(['db','start','stop-db','migrate','seed'].includes(action)) {
  loadEnv();
  const admin=new URL(process.env.MIGRATION_DATABASE_URL.replace('postgresql+psycopg:','postgresql:'));
  const pg=new EmbeddedPostgres({databaseDir:resolve('.local/pgdata'),user:'postgres',password:admin.password,
    port:55432,persistent:true,authMethod:'scram-sha-256',initdbFlags:['--encoding=UTF8','--locale=C'],
    postgresFlags:['-c','listen_addresses=127.0.0.1','-c','max_connections=40'],
    onLog:()=>{},onError:()=>{}});
  const platform=win?'windows':process.platform;
  const {pg_ctl:pgCtl}=await import(`@embedded-postgres/${platform}-${process.arch}`);
  const dataDir=resolve('.local/pgdata');
  function databaseRunning() {
    return spawnSync(pgCtl,['status','-D',dataDir],{stdio:'ignore',windowsHide:true}).status===0;
  }
  function stopDatabase() {
    if(databaseRunning())run(pgCtl,['stop','-D',dataDir,'-m','fast','-w']);
  }
  if(action==='stop-db') { stopDatabase(); }
  else if(action==='migrate') run(python,['-m','alembic','upgrade','head']);
  else if(action==='seed') run(python,['-m','database.seeds.synthetic']);
  else {
    if(!existsSync(resolve('.local/pgdata/PG_VERSION'))) await pg.initialise();
    if(!databaseRunning())run(pgCtl,['start','-D',dataDir,'-l',resolve('.local/postgres.log'),'-o','-p 55432 -h 127.0.0.1 -c max_connections=40','-w']);
    run(python,['scripts/bootstrap_db.py']);
    if(action==='start') {
      for(const name of ['services.stop','worker.stop','api.stop']) {
        const path=resolve('.local',name); if(existsSync(path))unlinkSync(path);
      }
      run(python,['-m','alembic','upgrade','head']);
      run(python,['-m','database.seeds.synthetic']);
      const {apiEnv,consoleEnv,workerEnv}=serviceEnvironments();
      const children=[
        spawn(python,['-m','apps.api.run'],{stdio:'inherit',env:apiEnv,windowsHide:true}),
        spawn(python,['-m','apps.worker.main'],{stdio:'inherit',env:workerEnv,windowsHide:true}),
        spawn(process.execPath,[resolve('node_modules/next/dist/bin/next'),'dev','apps/console','--hostname','127.0.0.1'],{stdio:'inherit',env:consoleEnv,windowsHide:true})
      ];
      let stopping=false;
      async function stop() {
        if(stopping)return; stopping=true;
        clearInterval(stopWatcher);
        writeFileSync(resolve('.local/worker.stop'),'stop');
        writeFileSync(resolve('.local/api.stop'),'stop');
        children[2].kill('SIGTERM');
        const timeout=setTimeout(()=>children.forEach(child=>child.kill('SIGTERM')),10000);
        await Promise.all(children.map(child=>new Promise(r=>child.exitCode!==null?r():child.once('exit',r))));
        clearTimeout(timeout);
        stopDatabase();
        console.log('Services stopped cleanly; database files and sessions retained.');
      }
      const stopWatcher=setInterval(()=>{if(existsSync(resolve('.local/services.stop')))void stop();},250);
      process.on('SIGINT',stop); process.on('SIGTERM',stop);
      children.forEach(child=>child.on('exit',()=>{if(!stopping)void stop();}));
      console.log('Company OS: http://localhost:3000 (synthetic local identities only)');
    }
  }
}
