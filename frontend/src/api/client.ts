import fixture from '../mocks/demo.json';
import type { DemoSnapshot } from '../types/demo';

export async function loadDashboard(): Promise<DemoSnapshot> {
  const mode = import.meta.env.VITE_API_MODE ?? 'mock';
  if (mode !== 'mock') {
    throw new Error('Реальный API ещё не подключён: docs/API_CONTRACT.md пуст. Для демонстрации установите VITE_API_MODE=mock.');
  }
  return structuredClone(fixture) as DemoSnapshot;
}
