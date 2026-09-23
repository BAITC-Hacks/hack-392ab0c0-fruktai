import type { RecalculateResponse, ImportMetadata } from '../types/api';
import type { DemoSnapshot, DemoStatus } from '../types/demo';

const statuses: Record<string, DemoStatus> = {
  high: 'Дефицит',
  medium: 'Пограничный остаток',
  low: 'В норме',
};
/** A display adapter; it never calculates a procurement quantity. */
export function toDashboard(
  response: RecalculateResponse,
  dataset = 'demo',
  metadata?: ImportMetadata,
): DemoSnapshot {
  return {
    updatedAt: response.generated_at,
    response,
    dataset,
    metadata,
    products: response.recommendations.map((item) => ({
      sku: item.sku,
      name: item.name,
      subtitle: item.sku,
      kind: 'panel',
      unit: metadata?.products.find((p) => p.sku === item.sku)?.unit || 'ед.',
      category: metadata?.products.find((p) => p.sku === item.sku)?.category || 'Не указана',
      supplier: item.supplier_name,
      supplierId: item.supplier_id,
      onHand: item.on_hand,
      inTransit: item.in_transit,
      recommended: item.recommended_qty,
      expectedDate: null,
      status: statuses[item.urgency],
      calculation: item,
      explanation: item.reasons.join(' '),
      anomalyNote:
        item.outlier_units_removed > 0
          ? 'Исключено из регулярного спроса: ' + item.outlier_units_removed + ' ед.'
          : null,
      stockoutNote:
        item.stockout_compensation > 0
          ? 'Компенсация упущенного спроса: ' + item.stockout_compensation + ' ед.'
          : null,
    })),
  };
}
