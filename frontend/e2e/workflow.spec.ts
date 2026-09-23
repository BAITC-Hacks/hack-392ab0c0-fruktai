import { test, expect } from '@playwright/test';

test('dashboard -> item history -> override -> persisted API -> CSV', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const responsePromise = page.waitForResponse(r => r.url().endsWith('/api/v1/recalculate') && r.status() === 200);
  await page.goto('/');
  const baseline = await (await responsePromise).json();
  const item = baseline.recommendations.find((r: { recommended_qty: number }) => r.recommended_qty > 0);
  await expect(page.getByRole('heading', { name: 'План закупок', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Открыть расчёт: ' + item.name, exact: true }).click();
  await expect(page.getByTestId('sales-history')).toBeVisible();
  await page.getByRole('textbox', { name: 'На складе', exact: true }).fill(String(item.on_hand + item.recommended_qty + 1));
  const changedPromise = page.waitForResponse(r => r.url().endsWith('/api/v1/recalculate') && r.status() === 200);
  await page.getByRole('button', { name: 'Пересчитать через API', exact: true }).click();
  const changed = await (await changedPromise).json();
  expect(changed.recommendations.find((r: { sku: string }) => r.sku === item.sku).recommended_qty).toBe(0);
  await expect(page.getByTestId('recommended-qty')).toHaveText('0 ед.');
  const detail = await request.get('/api/v1/items/' + encodeURIComponent(item.sku));
  expect((await detail.json()).calculation.recommended_qty).toBe(0);
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Проверить заказ', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Я проверил(а) позиции и объёмы' }).check();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Подтвердить и экспортировать CSV', exact: true }).click();
  expect((await download).suggestedFilename()).toBe('fruktai-recommendations.csv');
  expect(errors).toEqual([]);
});
