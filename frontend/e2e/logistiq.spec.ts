import { test, expect } from '@playwright/test';

test('LOGISTIQ sample -> upload -> 12 calculated products -> XLSX', async ({ page }) => {
  const filename = process.env.E2E_LOGISTIQ_FILE;
  test.skip(!filename, 'Set E2E_LOGISTIQ_FILE to a local LOGISTIQ_test_dataset.xlsx');
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Обновить данные', exact: true })).toBeEnabled();
  await page.getByText('Загрузить данные / выгрузку 1С', { exact: true }).click();
  await page.getByLabel('Файлы источников', { exact: true }).setInputFiles(filename!);
  await page
    .getByRole('checkbox', {
      name: 'Клиентские данные обезличены, персональных данных нет',
    })
    .check();
  const imported = page.waitForResponse((r) => r.url().endsWith('/api/v1/datasets/import'));
  await page.getByRole('button', { name: 'Загрузить и проверить', exact: true }).click();
  const response = await imported;
  expect(response.status()).toBe(201);
  const metadata = await response.json();
  expect(metadata.counts.sales).toBe(720);
  expect(metadata.counts.products).toBe(12);
  await expect(page.getByTestId('import-panel')).toContainText('Current Snapshot');
  const calculated = page.waitForResponse((r) => r.url().endsWith('/api/v1/recalculate'));
  await page.getByRole('button', { name: 'Рассчитать загруженные данные', exact: true }).click();
  const resultResponse = await calculated;
  expect(resultResponse.status()).toBe(200);
  const result = await resultResponse.json();
  expect(result.summary.total_items).toBe(12);
  const bearing = result.recommendations.find((r: { sku: string }) => r.sku === 'SKF-6205');
  expect(bearing.on_hand).toBe(40);
  expect(bearing.in_transit).toBe(30);
  await page.getByRole('button', { name: 'Проверить заказ', exact: true }).click();
  await page.getByRole('combobox', { name: 'Формат экспорта', exact: true }).selectOption('xlsx');
  await page.getByRole('checkbox', { name: 'Я проверил(а) позиции и объёмы' }).check();
  const exported = page.waitForResponse((r) =>
    r.url().includes('/runs/' + result.run_id + '/export'),
  );
  const download = page.waitForEvent('download');
  await page
    .getByRole('button', { name: 'Подтвердить и экспортировать XLSX', exact: true })
    .click();
  expect((await exported).status()).toBe(200);
  expect((await download).suggestedFilename()).toBe('fruktai-recommendations.xlsx');
});

test('missing import route explains how to restart an old backend', async ({ page }) => {
  await page.route('**/api/v1/datasets/import', (route) =>
    route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Not Found' }),
    }),
  );
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Обновить данные', exact: true })).toBeEnabled();
  await page.getByText('Загрузить данные / выгрузку 1С', { exact: true }).click();
  await page.getByLabel('Файлы источников', { exact: true }).setInputFiles({
    name: 'input.xlsx',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('test'),
  });
  await page
    .getByRole('checkbox', {
      name: 'Клиентские данные обезличены, персональных данных нет',
    })
    .check();
  await page.getByRole('button', { name: 'Загрузить и проверить', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('scripts/run_local.py');
  await expect(page.getByRole('button', { name: 'Рассчитать загруженные данные' })).toHaveCount(0);
});
