/** Presentation-only demo data. NOT a backend API contract. */
export type DemoStatus = 'Дефицит' | 'Пограничный остаток' | 'В норме';
export interface DemoProduct {
  sku: string; name: string; subtitle: string;
  kind: 'cable' | 'breaker' | 'socket' | 'light' | 'panel';
  unit: 'м' | 'шт.'; supplier: string; category: string;
  onHand: number; inTransit: number; recommended: number;
  expectedDate: string | null; status: DemoStatus;
  explanation: string; anomalyNote: string | null; stockoutNote: string | null;
}
export interface DemoSnapshot { updatedAt: string; products: DemoProduct[] }
