import { test, expect } from '@playwright/test';
import { loadConfig } from '../../scripts/site/config.mjs';

const { t, site } = loadConfig();

test('home, search, direct links and mobile navigation', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('./');
  await expect(page.getByRole('heading', { name: site.title }).first()).toBeVisible();
  await page.getByRole('button', { name: t.search.button }).click();
  await page.locator('#localsearch-input').fill(site.searchQuery);
  await expect(page.locator('.VPLocalSearchBox .result').first()).toBeVisible();
  await page.locator('.VPLocalSearchBox .result').first().click();
  await expect(page.locator('h1')).toBeVisible();
  await page.reload();
  await expect(page.locator('h1')).toBeVisible();
  await expect(page.getByRole('link', { name: t.sourceInfo.link })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: t.menu }).click();
  await expect(page.locator('.VPSidebar')).toBeVisible();
  expect(errors).toEqual([]);
});

test('archive pages are excluded from search', async ({ page }) => {
  await page.goto('./');
  await page.getByRole('button', { name: t.search.button }).click();
  await page.locator('#localsearch-input').fill(site.searchQuery);
  await expect(page.locator('.VPLocalSearchBox .result').first()).toBeVisible();
  const links = await page.locator('.VPLocalSearchBox a').evaluateAll(items => items.map(a => a.getAttribute('href')));
  expect(links.filter(Boolean).some(url => url.includes('/archive/'))).toBe(false);
});
