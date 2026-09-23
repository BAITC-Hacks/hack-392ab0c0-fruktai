import type { DemoProduct } from '../types/demo';
const escapeCell = (value: string | number): string => {
  const text = String(value);
  return '"' + (/^[=+@\-\t\r]/.test(text) ? "'" + text : text).replaceAll('"', '""') + '"';
};
export function exportCsv(products: DemoProduct[]): void {
  const rows: (string | number)[][] = [
    ['Артикул', 'Товар', 'Поставщик', 'Остаток', 'В пути', 'Рекомендованный заказ', 'Единица', 'Статус', 'Источник'],
    ...products.map(p => [p.sku, p.name, p.supplier, p.onHand, p.inTransit, p.recommended, p.unit, p.status, 'Демонстрационные данные'])
  ];
  const url = URL.createObjectURL(new Blob(['\uFEFF' + rows.map(row => row.map(escapeCell).join(';')).join('\r\n')], { type: 'text/csv;charset=utf-8;' }));
  const link = document.createElement('a');
  link.href = url; link.download = 'ekt-recommendations-demo.csv'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
