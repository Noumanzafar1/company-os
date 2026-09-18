// Synthetic acceptance demonstrations use the suite's disposable PostgreSQL DB.
import {loadEnv, python, run} from './local.mjs';

const demos = {
  all: null,
  events: 'atomic_event or replay_namespace or review_event',
  faults: 'process_crash or lease or fence or dependency or retry_history or review_recovery',
  webhooks: 'webhook or callback or completion_receipt',
  effects: 'effect_intent or replay_namespace or review_effect',
  budgets: 'reservations or ready_queue_load or prepared_non_use',
  schedules: 'schedule',
  isolation: 'tenant or role_boundaries or api_scope',
  load: 'initial_data or ready_queue_load',
};
const name=process.argv[2] || 'all';
if (!Object.hasOwn(demos,name)) throw new Error(`Choose: ${Object.keys(demos).join(', ')}`);
loadEnv();
run(python,['-m','pytest','-q','-s','tests/integration/test_runtime.py','tests/integration/test_phase4_review_fixes.py',
  ...(demos[name] ? ['-k',demos[name]] : [])]);
