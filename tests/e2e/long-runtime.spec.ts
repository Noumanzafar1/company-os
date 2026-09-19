import {test,expect} from '@playwright/test';

test('synthetic long execution exposes durable execution history',async({page})=>{
  test.setTimeout(90000);
  await page.goto('/login');
  await page.getByRole('button',{name:/Sign in as Synthetic User A/}).click();
  const workspace=await page.locator('#workspace').inputValue();
  await page.goto(`/system/jobs?workspace=${workspace}`);
  const previous=await page.getByRole('link',{name:/synthetic ·/}).first().getAttribute('href').catch(()=>null);
  await page.goto(`/system?workspace=${workspace}`);
  await page.getByLabel('Local synthetic handler').selectOption('sleep_success');
  await page.getByRole('button',{name:'Create long synthetic work',exact:true}).click();
  await expect(page.getByRole('status')).toHaveText('Command accepted.');
  await page.getByRole('link',{name:'Jobs and dead letters'}).click();
  await page.waitForURL(/\/system\/jobs\?/);
  await expect(async()=>{
    await page.reload();
    await expect(page.getByRole('link',{name:/synthetic ·/}).first()).toBeVisible();
    if(previous)await expect(page.getByRole('link',{name:/synthetic ·/}).first()).not.toHaveAttribute('href',previous);
  }).toPass({timeout:30000});
  await page.getByRole('link',{name:/synthetic ·/}).first().click();
  await page.waitForURL(/\/system\/jobs\/[a-f0-9-]+\?/);
  await expect(async()=>{
    await page.reload();
    await expect(page.getByRole('heading',{name:'synthetic · succeeded',exact:true})).toBeVisible();
    await expect(page.getByRole('heading',{name:'Long executions',exact:true})).toBeVisible();
  }).toPass({timeout:30000});
  await expect(page.getByText('No force required',{exact:true})).toBeVisible();
});
