import {loadEnv, python, run} from './local.mjs';

loadEnv();
run(python, ['-m', 'pytest', '-q', 'tests/unit/test_long_isolation.py',
  'tests/integration/test_long_runtime.py', ...process.argv.slice(2)]);
