import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'tests/e2e',fullyParallel:false,workers:1,retries:0,
  reporter:[['list'],['json',{outputFile:'test-results/e2e-results.json'}]],
  use:{baseURL:'http://localhost:3000',channel:process.env.PLAYWRIGHT_CHANNEL || undefined,headless:true,viewport:{width:1440,height:1000},screenshot:'only-on-failure',trace:'retain-on-failure'},
});
