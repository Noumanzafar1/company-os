import {test,expect} from '@playwright/test';

test('Phase 3 source provenance, missingness, shared domains, scores and knowledge',async({page})=>{
  await page.goto('/login');
  await page.getByRole('button',{name:/Sign in as Synthetic User A/}).click();
  await page.getByRole('link',{name:/04 Accounts/}).click();
  await expect(page.getByRole('heading',{name:'Accounts',exact:true})).toBeVisible();
  await expect(page.getByText('shared.synthetic.example',{exact:true})).toHaveCount(2);
  await page.getByRole('link',{name:'Synthetic A Missing Trigger',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Why Company OS believes this'})).toBeVisible();
  await expect(page.getByText(/Unknown: trigger, role/).first()).toBeVisible();
  await page.getByRole('button',{name:'Recalculate deterministic score'}).click();
  await expect(page.getByRole('status')).toHaveText('Rescoring completed. Identical inputs reuse the immutable score.');
  await page.getByRole('link',{name:'Synthetic approved source',exact:true}).click();
  await expect(page.getByText(/Purposes: research, knowledge/)).toBeVisible();
  await page.getByRole('link',{name:/05 Leads/}).click();
  await expect(page.getByText(/ICP version:/).first()).toBeVisible();
  await expect(page.getByText(/Offer version:/).first()).toBeVisible();
  await page.getByRole('link',{name:/06 Knowledge/}).click();
  await page.getByLabel('Search synthetic knowledge').fill('knowledge');
  await page.getByRole('button',{name:'Search',exact:true}).click();
  await expect(page.getByText(/Synthetic A workspace-only approved knowledge/)).toBeVisible();
  await expect(page.getByText(/Synthetic A workspace-only stale knowledge/)).toBeVisible();
  await expect(page.getByText(/Synthetic B workspace-only/)).toHaveCount(0);
  await expect(page.getByText(/Synthetic A workspace-only revoked knowledge/)).toHaveCount(0);
  await page.screenshot({path:'test-results/core-knowledge.png',fullPage:true});
});

test('Phase 3 rights and retractions are visible, User B cannot read User A',async({page})=>{
  await page.goto('/login');
  await page.getByRole('button',{name:/Sign in as Synthetic User A/}).click();
  await page.getByRole('link',{name:/04 Accounts/}).click();
  await page.getByRole('link',{name:'Synthetic A Retracted Fact',exact:true}).click();
  await expect(page.getByText(/observed · entity match: confirmed · retracted/)).toBeVisible();
  const accountUrl=page.url();
  await page.screenshot({path:'test-results/core-account.png',fullPage:true});
  await page.getByRole('button',{name:'Sign out'}).click();
  await page.getByRole('button',{name:/Sign in as Synthetic User B/}).click();
  await page.goto(accountUrl);
  await expect(page.getByRole('heading',{name:'Workspace unavailable'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Synthetic A Retracted Fact'})).toHaveCount(0);
  await page.getByRole('link',{name:/04 Accounts/}).click();
  await expect(page.getByText('Business records unavailable or you do not have permission.',{exact:true})).toBeVisible();
});
