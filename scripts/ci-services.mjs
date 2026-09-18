import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { writeFileSync } from 'node:fs';
import { loadEnv,python,run,serviceEnvironments } from './local.mjs';
loadEnv();
if(process.argv[2]==='prepare') {
  run(python,['scripts/bootstrap_db.py']);
  run(python,['-m','alembic','upgrade','head']);
  run(python,['-m','database.seeds.synthetic']);
} else if(process.argv[2]==='e2e') {
  const {apiEnv,consoleEnv,workerEnv}=serviceEnvironments();
  const api=spawn(python,['-m','apps.api.run','--stop-file','.local/ci-api.stop'],{stdio:'inherit',windowsHide:true,env:apiEnv});
  const worker=spawn(python,['-m','apps.worker.main','--stop-file','.local/ci-worker.stop'],{stdio:'inherit',windowsHide:true,env:workerEnv});
  const consoleProcess=spawn(process.execPath,['node_modules/next/dist/bin/next','start','apps/console','--hostname','127.0.0.1'],{stdio:'inherit',windowsHide:true,env:consoleEnv});
  try {
    let ready=false;
    for(let i=0;i<60;i++) {
      try {
        const apiReady=await fetch('http://127.0.0.1:8000/health/ready',{signal:AbortSignal.timeout(1000)});
        const consoleReady=await fetch('http://localhost:3000/login',{redirect:'manual',signal:AbortSignal.timeout(1000)});
        if(apiReady.ok && [200,307].includes(consoleReady.status)){ready=true;break;}
      }catch{}
      await new Promise(r=>setTimeout(r,1000));
    }
    if(!ready)throw new Error('Services did not become ready');
    run(process.execPath,[resolve('node_modules/@playwright/test/cli.js'),'test']);
  } finally {
    writeFileSync('.local/ci-worker.stop','stop');
    writeFileSync('.local/ci-api.stop','stop'); consoleProcess.kill('SIGTERM');
    const timeout=setTimeout(()=>api.kill('SIGTERM'),10000);
    await new Promise(r=>api.exitCode!==null?r():api.once('exit',r));
    clearTimeout(timeout);
    const workerTimeout=setTimeout(()=>worker.kill('SIGTERM'),10000);
    await new Promise(r=>worker.exitCode!==null?r():worker.once('exit',r));
    clearTimeout(workerTimeout);
  }
}
