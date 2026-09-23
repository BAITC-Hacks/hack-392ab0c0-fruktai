import type { ItemResponse, Override, RecalculateResponse, ImportMetadata } from '../types/api';
import { toDashboard } from './presentation';

const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
async function request(path: string, options?: RequestInit): Promise<unknown> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 100_000);
  try {
    const response = await fetch(base + path, { ...options, signal: controller.signal });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const detail = typeof body.detail === 'string' ? body.detail : 'Проверьте входные данные.';
      throw new Error('API ' + response.status + ': ' + detail);
    }
    return await response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError')
      throw new Error('Сервис не ответил за 100 секунд. Повторите запрос.');
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
export async function loadDashboard(overrides: Override[] = [], dataset = 'demo') {
  const metadata = dataset.startsWith('upload_')
    ? ((await request('/api/v1/datasets/' + encodeURIComponent(dataset))) as ImportMetadata)
    : undefined;
  const data = await request('/api/v1/recalculate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset, overrides }),
  });
  assertResponse(data);
  return toDashboard(data, dataset, metadata);
}
export async function loadItem(sku: string, runId: string): Promise<ItemResponse> {
  const data = (await request(
    '/api/v1/items/' + encodeURIComponent(sku) + '?run_id=' + encodeURIComponent(runId),
  )) as ItemResponse;
  if (!data || data.sku !== sku || !Array.isArray(data.history) || !data.calculation)
    throw new Error('API вернул некорректную историю товара.');
  return data;
}
export const templateUrl = base + '/api/v1/datasets/template.xlsx';
export async function importFiles(
  files: File[],
  warehouse: string,
  anonymized: boolean,
): Promise<ImportMetadata> {
  const body = new FormData();
  files.forEach((file) => body.append('files', file));
  body.append('warehouse_id', warehouse);
  body.append('anonymized', String(anonymized));
  return (await request('/api/v1/datasets/import', { method: 'POST', body })) as ImportMetadata;
}
export async function exportRun(runId: string, skus: string[], format: 'csv' | 'xlsx') {
  const params = new URLSearchParams({ format });
  skus.forEach((sku) => params.append('sku', sku));
  const response = await fetch(
    base + '/api/v1/runs/' + encodeURIComponent(runId) + '/export?' + params,
  );
  if (!response.ok)
    throw new Error('Не удалось экспортировать сохранённый расчёт: HTTP ' + response.status);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = 'fruktai-recommendations.' + format;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function assertResponse(data: unknown): asserts data is RecalculateResponse {
  const value = data as RecalculateResponse;
  if (
    !value ||
    typeof value.run_id !== 'string' ||
    !Number.isFinite(Date.parse(value.generated_at)) ||
    !value.summary ||
    !Array.isArray(value.recommendations) ||
    !Array.isArray(value.agent_steps)
  )
    throw new Error('Ответ API не соответствует контракту.');
  const numeric = [
    'recommended_qty',
    'on_hand',
    'in_transit',
    'lead_time_days',
    'avg_daily_demand',
    'forecast_demand',
    'safety_stock',
    'seasonality_factor',
    'growth_factor',
    'stockout_compensation',
    'outlier_units_removed',
    'days_of_cover',
  ] as const;
  for (const item of value.recommendations) {
    if (
      !item ||
      !['sku', 'name', 'supplier_id', 'supplier_name'].every(
        (k) => typeof (item as unknown as Record<string, unknown>)[k] === 'string',
      ) ||
      !numeric.every((k) => Number.isFinite(item[k]) && item[k] >= 0) ||
      !Number.isInteger(item.recommended_qty) ||
      !['high', 'medium', 'low'].includes(item.urgency) ||
      !Array.isArray(item.reasons) ||
      !item.reasons.every((r) => typeof r === 'string')
    )
      throw new Error('API вернул некорректную рекомендацию.');
  }
  if (new Set(value.recommendations.map((r) => r.sku)).size !== value.recommendations.length)
    throw new Error('API вернул повторяющиеся артикулы.');
}
