import { test,expect } from '@playwright/test';

test('founder inspects exact scope, grants with offline MFA and sees immutable manifest',async({browser})=>{
  test.setTimeout(60000);
  const context=await browser.newContext({storageState:'.local/phase5-browser.json'});
  const page=await context.newPage();
  try {
    await page.goto('/approvals');
    await page.getByRole('textbox',{name:'Action summary'}).fill('Browser synthetic authority case');
    await page.getByRole('button',{name:'Request founder review'}).click();
    await expect(page.getByRole('heading',{name:'Exactly what this authorizes'})).toBeVisible();
    await expect(page.getByText(/1 exact targets/)).toBeVisible();
    await page.getByRole('textbox',{name:'Decision reason'}).fill('Inspected exact browser fixture');
    await page.getByRole('checkbox').check();
    await page.getByRole('button',{name:'Approve this exact scope'}).click();
    await expect(page.getByRole('button',{name:'Queue approved synthetic action'})).toBeEnabled();
    await page.getByText('Immutable scope and hashes',{exact:true}).click();
    await expect(page.getByText(/Manifest .*SHA-256/)).toBeVisible();
    await page.screenshot({path:'test-results/phase5-manifest.png',fullPage:true});
    await page.getByRole('button',{name:'Queue approved synthetic action'}).click();
    await expect(page.getByRole('status').first()).toContainText('Command recorded');
    await expect(async()=>{
      await page.reload();
      await expect(page.getByText(/Use 1: consumed/)).toBeVisible();
    }).toPass({timeout:30000});
    await page.screenshot({path:'test-results/phase5-consumed.png',fullPage:true});
    await page.getByRole('textbox',{name:'Revocation reason'}).fill('End bounded browser demonstration');
    await page.getByRole('button',{name:'Revoke unused authority'}).click();
    await expect(page.getByText(/Authority validation: AUTHORITY_REVOKED/)).toBeVisible();
    await expect(page.getByRole('button',{name:'Queue approved synthetic action'})).toHaveCount(0);
  } finally {await context.close();}
});
