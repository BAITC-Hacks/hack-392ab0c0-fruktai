import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

async function importTs(path) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  const result = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
  return import('data:text/javascript;base64,' + Buffer.from(result.outputText).toString('base64'));
}
const ui = await importTs('../src/utils/presentation.ts');
const csv = await importTs('../src/utils/csv.ts');
const { products } = JSON.parse(await readFile(new URL('../src/mocks/demo.json', import.meta.url), 'utf8'));
assert.equal(ui.quantitySummary(products), '500 м · 300 шт.');
assert.equal(ui.filterProducts(products, { ...ui.initialFilters, search: '  a9F74132 ' }).length, 1);
assert.equal(ui.filterProducts(products, { ...ui.initialFilters, signal: 'anomaly' })[0].sku, 'ВВГнг-3x2.5');
assert.equal(ui.filterProducts(products, { ...ui.initialFilters, signal: 'stockout' })[0].sku, 'A9F74132');
assert.equal(ui.filterProducts(products, { ...ui.initialFilters, supplier: 'IEK', status: 'Дефицит' }).length, 0);
assert.equal(ui.filterProducts(products, ui.initialFilters)[0].onHand, 0);
assert.equal(ui.validateScenario({ onHand: '0', inTransit: '12,5' }), null);
for (const input of ['', '-1', 'Infinity', '1e999', '1e2', '0x10', '2a', '1000000001']) {
  assert.ok(ui.validateScenario({ onHand: input, inTransit: '0' }), 'Reject invalid input: ' + input);
}
const before = JSON.stringify(products);
ui.filterProducts(products, { ...ui.initialFilters, sort: 'supplier' });
csv.createCsv(products);
assert.equal(JSON.stringify(products), before, 'Sorting/export must never mutate recommendations');
assert.equal(csv.escapeCsvCell('  =1+1'), '"\'  =1+1"');
assert.equal(csv.escapeCsvCell('Кабель "A"; Б'), '"Кабель ""A""; Б"');
const exported = csv.createCsv([products[1]]);
assert.ok(exported.startsWith('\uFEFF'));
assert.ok(exported.includes('"100";"шт."'));
assert.ok(exported.includes('Демонстрационные данные'));
assert.equal(exported.split('\r\n').length, 2);
console.log('PASS: filters, risk ordering, mixed units, draft validation, CSV and immutable source data.');
