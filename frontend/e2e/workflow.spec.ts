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

test('upload Excel -> preview -> calculate -> persisted history -> Excel export', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Обновить данные', exact: true })).toBeEnabled();
  const template = await request.get('/api/v1/datasets/template.xlsx');
  expect(template.ok()).toBeTruthy();
  await page.getByText('Загрузить данные / выгрузку 1С', { exact: true }).click();
  await page.getByLabel('Файлы источников', { exact: true }).setInputFiles({
    name: 'input.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: await template.body(),
  });
  await page.getByRole('checkbox', { name: 'Клиентские данные обезличены, персональных данных нет' }).check();
  const imported = page.waitForResponse(r => r.url().endsWith('/api/v1/datasets/import'));
  await page.getByRole('button', { name: 'Загрузить и проверить', exact: true }).click();
  const response = await imported;
  expect(response.status()).toBe(201);
  const metadata = await response.json();
  await expect(page.getByRole('heading', { name: 'Вход проверен — проверьте полноту перед расчётом' })).toBeVisible();
  await expect(page.getByTestId('import-panel')).toContainText('sales: 336 строк');
  await page.getByText('Предпросмотр нормализованных данных', { exact: true }).click();
  await expect(page.getByTestId('import-panel')).toContainText('WH-01');
  const computed = page.waitForResponse(r => r.url().endsWith('/api/v1/recalculate'));
  await page.getByRole('button', { name: 'Рассчитать загруженные данные', exact: true }).click();
  const result = await (await computed).json();
  expect(await page.evaluate(() => localStorage.getItem('fruktai-dataset'))).toBe(metadata.dataset);
  const item = result.recommendations[0];
  const history = page.waitForResponse(r => r.url().includes('/api/v1/items/') && r.url().includes(result.run_id));
  await page.getByRole('button', { name: 'Открыть расчёт: ' + item.name, exact: true }).click();
  expect((await (await history).json()).calculation.recommended_qty).toBe(item.recommended_qty);
  await expect(page.getByTestId('sales-history')).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Проверить заказ', exact: true }).click();
  await page.getByRole('combobox', { name: 'Формат экспорта', exact: true }).selectOption('xlsx');
  await page.getByRole('checkbox', { name: 'Я проверил(а) позиции и объёмы' }).check();
  const exported = page.waitForResponse(r => r.url().includes('/runs/' + result.run_id + '/export'));
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Подтвердить и экспортировать XLSX', exact: true }).click();
  expect((await exported).status()).toBe(200);
  expect((await download).suggestedFilename()).toBe('fruktai-recommendations.xlsx');
  await page.reload();
  await expect(page.getByRole('button', { name: 'Вернуться к учебному набору demo' })).toBeVisible();
  expect(errors).toEqual([]);
});
