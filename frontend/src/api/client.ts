import fixture from '../mocks/demo.json';
import type { DemoProduct, DemoSnapshot } from '../types/demo';

/** Validate the presentation fixture. This schema does not describe a server API. */
function isDemoProduct(value: unknown): value is DemoProduct {
  if (typeof value !== 'object' || value === null) return false;
  const product = value as Record<string, unknown>;
  return ['sku', 'name', 'subtitle', 'supplier', 'category', 'explanation'].every(key => typeof product[key] === 'string') &&
    ['onHand', 'inTransit', 'recommended'].every(key => typeof product[key] === 'number' && Number.isFinite(product[key]) && product[key] >= 0) &&
    ['cable', 'breaker', 'socket', 'light', 'panel'].includes(String(product.kind)) &&
    ['шт.', 'м'].includes(String(product.unit)) &&
    ['Дефицит', 'Пограничный остаток', 'В норме'].includes(String(product.status)) &&
    ['anomalyNote', 'stockoutNote'].every(key => product[key] === null || typeof product[key] === 'string') &&
    (product.expectedDate === null || (typeof product.expectedDate === 'string' && Number.isFinite(Date.parse(product.expectedDate))));
}

export async function loadDashboard(): Promise<DemoSnapshot> {
  const mode = import.meta.env.VITE_API_MODE ?? 'mock';
  if (mode !== 'mock') {
    throw new Error('Источник API не подключён. Проверьте настройки подключения или вернитесь к демонстрационному режиму.');
  }
  const data: unknown = structuredClone(fixture);
  if (typeof data !== 'object' || data === null || !('products' in data) ||
      !Array.isArray(data.products) || !data.products.every(isDemoProduct) ||
      !('updatedAt' in data) || typeof data.updatedAt !== 'string' ||
      !Number.isFinite(Date.parse(data.updatedAt)) ||
      new Set(data.products.map(p => p.sku)).size !== data.products.length) {
    throw new Error('Демонстрационный набор повреждён: проверьте значения, даты и уникальность артикулов.');
  }
  return { updatedAt: data.updatedAt, products: data.products };
}
