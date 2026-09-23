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

test('new workspace: navigation, sort, filters, focus and accessible drawers', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Обновить данные', exact: true })).toBeEnabled();
  await expect(page.getByRole('columnheader', { name: 'Покрытие' })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Прогноз' })).toBeVisible();
  await page.screenshot({ path: '../artifacts/design-desktop.png', fullPage: true, animations: 'disabled' });
  await page.getByRole('combobox', { name: 'Сортировка', exact: true }).selectOption('quantity');
  const amounts = await page.locator('.desktop-table td.order-number').allTextContents();
  const numbers = amounts.map(text => Number(text.replace(/[^0-9]/g, '')));
  expect(numbers).toEqual([...numbers].sort((a, b) => b - a));
  const search = page.getByRole('textbox', { name: 'Поиск по товару, артикулу или поставщику' });
  await search.fill('STABLE-001');
  const product = page.locator('.desktop-table .product-cell').first();
  await product.click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByTestId('sales-history')).toBeVisible();
  await page.screenshot({ path: '../artifacts/design-details.png', fullPage: true, animations: 'disabled' });
  await page.keyboard.press('Escape');
  await expect(product).toBeFocused();
  await expect(search).toHaveValue('STABLE-001');
  await search.fill('no-such-sku');
  await expect(page.getByRole('heading', { name: 'Подходящих позиций нет' })).toBeVisible();
  await page.getByRole('button', { name: 'Сбросить фильтры', exact: true }).click();
  const nav = page.getByRole('navigation', { name: 'Основная навигация' });
  await nav.getByRole('button', { name: 'Обзор запасов', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Как изменится доступный запас' })).toBeVisible();
  await page.screenshot({ path: '../artifacts/design-overview.png', fullPage: true, animations: 'disabled' });
  await nav.getByRole('button', { name: 'Поставщики', exact: true }).click();
  await expect(page.locator('.supplier-row').first()).toBeVisible();
  await nav.getByRole('button', { name: 'Ход анализа', exact: true }).click();
  await expect(page.getByText('Данные загружены', { exact: false })).toBeVisible();
  await nav.getByRole('button', { name: 'Источники данных', exact: true }).click();
  await expect(page.getByTestId('import-panel')).toBeVisible();
  await page.screenshot({ path: '../artifacts/design-sources.png', fullPage: true, animations: 'disabled' });
});

test('mobile workspace fits viewport and preserves working item actions', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Обновить данные', exact: true })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await expect(page.locator('.mobile-product').first()).toBeVisible();
  await page.screenshot({ path: '../artifacts/design-mobile.png', fullPage: true, animations: 'disabled' });
  await page.locator('.mobile-product').first().getByRole('button', { name: /Открыть расчёт/ }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  const input = page.getByRole('textbox', { name: 'На складе', exact: true });
  await input.fill('123');
  await page.keyboard.press('Escape');
  await page.locator('.mobile-product').first().getByRole('button', { name: /Открыть расчёт/ }).click();
  await expect(page.getByRole('textbox', { name: 'На складе', exact: true })).toHaveValue('123');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Открыть навигацию', exact: true }).click();
  await page.getByRole('navigation', { name: 'Основная навигация' }).getByRole('button', { name: 'Обзор запасов', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Обзор запасов', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test('API error is actionable and does not claim a successful calculation', async ({ page }) => {
  let fail = true;
  await page.route('**/api/v1/recalculate', route => fail
    ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Тест: сервер временно недоступен' }) })
    : route.continue());
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Не удалось обновить рекомендации');
  await expect(page.getByText('Ошибка обновления', { exact: true })).toBeVisible();
  fail = false;
  await page.getByRole('button', { name: 'Повторить загрузку', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Обновить данные', exact: true })).toBeEnabled();
  await expect(page.getByRole('alert')).toHaveCount(0);
});
