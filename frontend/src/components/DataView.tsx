import { Database, FileText, Info, CircleCheck, Clock3 } from 'lucide-react';
import type { DemoSnapshot } from '../types/demo';
import { formatDate } from '../utils/presentation';

export function DataView({ data }: { data: DemoSnapshot }) {
  return <section className="data-view"><div className="view-heading"><span className="eyebrow">Источник и полнота</span><h2>Данные для принятия решения</h2><p>Все значения этого экрана взяты из одного подготовленного набора.</p></div>
    <div className="data-source"><Database size={23}/><div><h3>Демонстрационный набор</h3><p>{data.products.length} позиций · дата среза {formatDate(data.updatedAt)}</p></div><span className="mini-tag">Демо</span></div>
    <div className="data-notice"><Info size={18}/><p>Это пример интерфейса. Набор не синхронизирован с 1С и не отражает актуальный склад. Не используйте его для реальной закупки.</p></div>
    <h3 className="section-title">Полнота входных данных</h3><div className="data-checklist">
      {[
        ['Номенклатура и поставщики', true, 'Артикулы, категории и единицы измерения'],
        ['Остатки и товары в пути', true, 'Значения из примера; без истории движения'],
        ['Рекомендации и причины', true, 'Готовые демонстрационные значения'],
        ['История продаж', false, 'Нужна для среднего спроса, тренда и графика'],
        ['Сезонность и устойчивый рост', false, 'Коэффициенты должен вернуть сервис расчёта'],
        ['Периоды stockout и аномалии', false, 'Есть текстовые примеры, но нет исходных событий'],
        ['Сроки поставки и страховой запас', false, 'Нужны для раскрытия численной формулы'],
      ].map(([name, ready, note]) => <div key={String(name)}>{ready ? <CircleCheck size={17} className="teal-text"/> : <Clock3 size={17} className="muted"/>}<span><strong>{name}</strong><small>{note}</small></span><b className={ready ? 'teal-text' : 'muted'}>{ready ? 'Есть в примере' : 'Не получено'}</b></div>)}
    </div><div className="data-footnote"><FileText size={18}/><p>Склад и период анализа не переданы отдельными полями, поэтому переключатели для них не имитируются. Клиентские идентификаторы и персональные данные на экран не выводятся.</p></div>
  </section>;
}
