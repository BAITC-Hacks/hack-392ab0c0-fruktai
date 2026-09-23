import type { DemoProduct } from '../types/demo';

/** Quote every field and prevent spreadsheet formula execution, including leading whitespace. */
export const escapeCsvCell = (value: string | number): string => {
  const text = String(value);
  const safe = /^[\s\uFEFF]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text) ? "'" + text : text;
  return '"' + safe.replaceAll('"', '""') + '"';
};
export function createCsv(products: DemoProduct[]): string {
  const sorted = [...products].sort((a, b) => a.supplier.localeCompare(b.supplier, 'ru'));
  const rows: (string | number)[][] = [
    ['Артикул', 'Товар', 'Поставщик', 'Остаток', 'В пути', 'Рекомендованный заказ', 'Единица', 'Статус', 'Обоснование', 'Источник'],
    ...sorted.map(p => [p.sku, p.name, p.supplier, p.onHand, p.inTransit, p.recommended, p.unit, p.status, p.explanation, 'Демонстрационные данные']),
  ];
  return '\uFEFF' + rows.map(row => row.map(escapeCsvCell).join(';')).join('\r\n');
}
export function exportCsv(products: DemoProduct[]): void {
  const url = URL.createObjectURL(new Blob([createCsv(products)], { type: 'text/csv;charset=utf-8;' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'ekt-recommendations-demo.csv';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
