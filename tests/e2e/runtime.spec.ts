import { test,expect } from '@playwright/test';

test('durable synthetic job, trace, health and workspace isolation',async({page})=>{
  test.setTimeout(90000);
  await page.goto('/login');
  await page.getByRole('button',{name:/Sign in as Synthetic User A/}).click();
  const workspace=await page.locator('#workspace').inputValue();
  await page.goto(`/system?workspace=${workspace}`);
  await expect(page.getByRole('heading',{name:/Runtime status/})).toBeVisible();
  await page.getByLabel('Scenario',{exact:true}).selectOption('success');
  await page.getByRole('button',{name:'Create synthetic work'}).click();
  await expect(page.getByRole('status')).toHaveText('Command accepted.');
  await page.getByRole('link',{name:'Jobs and dead letters'}).click();
  await page.waitForURL(/\/system\/jobs\?/);
  await expect(async()=>{
    await page.reload();
    await expect(page.getByRole('link',{name:/synthetic ·/}).first()).toBeVisible();
  }).toPass({timeout:30000});
  await page.getByRole('link',{name:/synthetic ·/}).first().click();
  await page.waitForURL(/\/system\/jobs\/[a-f0-9-]+\?/);
  await expect(async()=>{
    await page.reload();
    await expect(page.getByRole('heading',{name:'synthetic · succeeded',exact:true})).toBeVisible();
  }).toPass({timeout:30000});
  await expect(page.getByRole('heading',{name:'Attempts',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Event trace',exact:true})).toBeVisible();
  await page.screenshot({path:'test-results/phase4-job.png',fullPage:true});
  const jobUrl=page.url();
  await page.getByRole('button',{name:'Sign out'}).click();
  await page.getByRole('button',{name:/Sign in as Synthetic User B/}).click();
  await page.goto(jobUrl);
  await expect(page.getByRole('heading',{name:'Workspace unavailable'})).toBeVisible();
});
