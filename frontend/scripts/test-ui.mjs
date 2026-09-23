import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

async function importTs(path) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  const result = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  });
  return import('data:text/javascript;base64,' + Buffer.from(result.outputText).toString('base64'));
}
const ui = await importTs('../src/utils/presentation.ts');
const csv = await importTs('../src/utils/csv.ts');
const { toDashboard } = await importTs('../src/api/presentation.ts');
const response = JSON.parse(
  await readFile(new URL('../src/mocks/demo.json', import.meta.url), 'utf8'),
);
const { products } = toDashboard(response);
assert.equal(products.length, response.summary.total_items);
for (const product of products) {
  const source = response.recommendations.find((r) => r.sku === product.sku);
  assert.equal(product.recommended, source.recommended_qty);
  assert.equal(product.onHand, source.on_hand);
  assert.equal(product.supplierId, source.supplier_id);
}
assert.equal(
  ui.filterProducts(products, { ...ui.initialFilters, search: ' stable-001 ' }).length,
  1,
);
assert.ok(ui.filterProducts(products, { ...ui.initialFilters, signal: 'anomaly' }).length > 0);
assert.ok(ui.filterProducts(products, { ...ui.initialFilters, signal: 'stockout' }).length > 0);
assert.equal(ui.validateScenario({ onHand: '0', inTransit: '12' }), null);
for (const input of ['', '-1', '12,5', '1.5', 'Infinity', '1e2', '0x10', '2a', '1000000001']) {
  assert.ok(ui.validateScenario({ onHand: input, inTransit: '0' }), 'Reject: ' + input);
}
const byQuantity = ui.filterProducts(products, { ...ui.initialFilters, sort: 'quantity' });
assert.deepEqual(
  byQuantity.map((p) => p.recommended),
  products.map((p) => p.recommended).sort((a, b) => b - a),
);
const byCover = ui.filterProducts(products, { ...ui.initialFilters, sort: 'cover' });
assert.deepEqual(
  byCover.map((p) => p.calculation.days_of_cover),
  products.map((p) => p.calculation.days_of_cover).sort((a, b) => a - b),
);
assert.equal(
  ui.shortReason({ ...products[0], recommended: 0 }),
  'Пополнение по расчёту не требуется',
);
const before = JSON.stringify(products);
ui.filterProducts(products, { ...ui.initialFilters, sort: 'supplier' });
csv.createCsv(products);
assert.equal(JSON.stringify(products), before);
assert.equal(csv.escapeCsvCell('  =1+1'), '"\'  =1+1"');
const exported = csv.createCsv([products[0]]);
assert.ok(exported.startsWith('\uFEFF'));
assert.ok(exported.includes('FruktAI API / demo'));
assert.equal(exported.split('\r\n').length, 2);
console.log('PASS: real contract adapter, filters, integer overrides, safe CSV, immutable source.');
