import { test,expect } from '@playwright/test';

test('synthetic AI inspector, accounting, revocation and tenant isolation',async({page})=>{
  test.setTimeout(120000);
  await page.goto('/login');
  await page.getByRole('button',{name:/Sign in as Synthetic User A/}).click();
  const workspace=await page.locator('#workspace').inputValue();
  await page.goto(`/system/ai?workspace=${workspace}`);
  await expect(page.getByRole('heading',{name:'Governed AI gateway'})).toBeVisible();
  await expect(page.getByText('openai: unconfigured',{exact:true})).toBeVisible();
  await page.getByLabel('Scenario',{exact:true}).selectOption('repair');
  await page.getByRole('button',{name:'Create AI task'}).click();
  await page.waitForURL(/\/system\/ai\/[a-f0-9-]+\?/);
  await expect(async()=>{
    await page.reload();
    await expect(page.getByRole('heading',{name:'AI task · accepted',exact:true})).toBeVisible();
  }).toPass({timeout:45000});
  await expect(page.getByText('Call 2',{exact:true})).toBeVisible();
  await expect(page.getByText('business facts unavailable',{exact:true})).toBeVisible();
  const taskUrl=page.url();
  await page.getByRole('button',{name:'Revoke this synthetic context'}).click();
  await expect(page.getByText('Context: Invalid or expired; content and results withheld',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Sign out'}).click();
  await page.getByRole('button',{name:/Sign in as Synthetic User B/}).click();
  await page.goto(taskUrl);
  await expect(page.getByRole('heading',{name:'Workspace unavailable'})).toBeVisible();
});
