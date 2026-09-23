import type { Calculation, RecalculateResponse } from './api';
/** Display model mapped exclusively from the public API. */
export type DemoStatus = 'Дефицит' | 'Пограничный остаток' | 'В норме';
export interface DemoProduct {
  sku: string; name: string; subtitle: string;
  kind: 'cable' | 'breaker' | 'socket' | 'light' | 'panel';
  unit: 'м' | 'шт.' | 'ед.'; supplier: string; supplierId: string; category: string;
  calculation: Calculation;
  onHand: number; inTransit: number; recommended: number;
  expectedDate: string | null; status: DemoStatus;
  explanation: string; anomalyNote: string | null; stockoutNote: string | null;
}
export interface DemoSnapshot {
  updatedAt: string; products: DemoProduct[]; response: RecalculateResponse;
}
