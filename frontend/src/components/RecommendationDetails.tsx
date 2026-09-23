import { Info, ShieldCheck, TrendingUp } from 'lucide-react';
import type { DemoProduct } from '../types/demo';
export function RecommendationDetails({ product:p }: { product: DemoProduct }) {
  return <div className="details">
    <div><h3><Info size={16}/> Почему рекомендован заказ</h3><p>{p.explanation}</p><div className="formula">Заказ = max(0, прогноз + страховой запас − остаток − поступления)</div><p className="detail-note">Формула для объяснения. Расчёт выполняется на backend; коэффициенты сезонности и роста ещё не получены.</p></div>
    <div className="explanation-notes">
      {p.anomalyNote && <div className="insight"><ShieldCheck size={18}/><div><strong>Исключение аномалии · пример</strong><p>{p.anomalyNote}</p></div></div>}
      {p.stockoutNote && <div className="insight"><TrendingUp size={18}/><div><strong>Упущенный спрос · пример</strong><p>{p.stockoutNote}</p></div></div>}
      {!p.anomalyNote && !p.stockoutNote && <p className="detail-note">В демонстрационных данных нет отдельного объяснения аномалии или stockout для этой позиции.</p>}
      <p className="detail-note">What-if пересчёт будет доступен после подключения POST /api/v1/recalculate.</p>
    </div>
  </div>;
}
