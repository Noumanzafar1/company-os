import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { loadEnv,python,run } from './local.mjs';

loadEnv();
const generate=process.argv[2]==='contracts';
run(python,['scripts/contracts.py',...(generate?[]:['--check'])]);
const output=generate?'packages/contracts/api.d.ts':'.local/api.check.d.ts';
run(process.execPath,['node_modules/openapi-typescript/bin/cli.js','packages/contracts/openapi.json','-o',output]);
if(!generate) {
  if(readFileSync(output,'utf8').replaceAll('\r\n','\n')!==readFileSync('packages/contracts/api.d.ts','utf8').replaceAll('\r\n','\n'))throw new Error('Generated TypeScript contract drift');
  run(python,['-m','ruff','check','.']);
  run(python,['-m','ruff','format','--check','.']);
  run(python,['-m','mypy','packages/company_os','apps/api','apps/worker']);
  run(python,['scripts/boundaries.py']);
  run(python,['-m','pytest','-q']);
  const cwd=resolve('apps/console');
  run(process.execPath,[resolve('node_modules/eslint/bin/eslint.js'),'.'],{cwd});
  run(process.execPath,[resolve('node_modules/typescript/bin/tsc'),'--noEmit'],{cwd});
  run(process.execPath,[resolve('node_modules/vitest/vitest.mjs'),'run'],{cwd});
  console.log('All foundation checks passed. Browser E2E and production build are separate gates.');
}
