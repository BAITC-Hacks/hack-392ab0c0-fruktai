import { test, expect } from '@playwright/test';

test('profile actions, navigation filters, journal and resized mobile menu', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Обновить данные', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Открыть профиль', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Профиль рабочего места' })).toBeVisible();
  await page.getByRole('button', { name: 'Открыть источники данных', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByTestId('import-panel')).toBeVisible();
  const nav = page.getByRole('navigation', { name: 'Основная навигация' });
  await nav.getByRole('button', { name: 'Рекомендации' }).click();
  await page
    .getByRole('textbox', { name: 'Поиск по товару, артикулу или поставщику' })
    .fill('missing-item');
  await nav.getByRole('button', { name: 'Поставщики', exact: true }).click();
  await expect(page.locator('.supplier-row').first()).toBeVisible();
  await nav.getByRole('button', { name: 'Ход анализа', exact: true }).click();
  const journal = page.locator('#agent-run');
  await expect(journal).toHaveAttribute('open', '');
  await journal.locator(':scope > summary').click();
  await expect(journal).not.toHaveAttribute('open', '');
  await journal.locator(':scope > summary').click();
  await expect(journal).toHaveAttribute('open', '');
  await page.getByRole('button', { name: 'Открыть профиль', exact: true }).click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Открыть профиль', exact: true })).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Открыть навигацию', exact: true }).click();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByRole('button', { name: 'Закрыть навигацию', exact: true })).toHaveCount(0);
  await nav.getByRole('button', { name: 'Обзор запасов', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Обзор запасов', exact: true })).toBeVisible();
});
