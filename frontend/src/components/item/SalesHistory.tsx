import { useEffect, useState } from 'react';
import {
  Line,
  LineChart,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceDot,
} from 'recharts';

import { TrendingUp } from 'lucide-react';
import type { DemoProduct } from '../../types/demo';
import type { ItemResponse } from '../../types/api';
import { loadItem } from '../../api/client';
import { formatNumber } from '../../utils/presentation';

export function SalesHistory({ product: p, runId }: { product: DemoProduct; runId: string }) {
  const [historyError, setHistoryError] = useState('');
  const [item, setItem] = useState<ItemResponse | null>(null);
  useEffect(() => {
    let active = true;
    setItem(null);
    setHistoryError('');
    loadItem(p.sku, runId)
      .then((value) => {
        if (active) setItem(value);
      })
      .catch((problem) => {
        if (active) setHistoryError(String(problem.message));
      });
    return () => {
      active = false;
    };
  }, [p, runId]);

  const c = p.calculation;
  const forecastPerDay = c.lead_time_days > 0 ? c.forecast_demand / c.lead_time_days : null;
  return (
    <section className="detail-section">
      <h3>
        <TrendingUp size={17} />
        Спрос и сигналы
      </h3>
      {historyError ? (
        <p role="alert" className="field-error">
          {historyError}
        </p>
      ) : !item ? (
        <p className="helper">Загрузка истории…</p>
      ) : (
        <>
          <div className="chart-key">
            <span>
              <i className="key-actual" />
              Продажи
            </span>
            <span>
              <i className="key-lost" />
              Упущенный спрос
            </span>
            <span>
              <i className="key-forecast" />
              Прогноз / день
            </span>
          </div>
          <div className="history-chart" data-testid="sales-history">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={item.history} margin={{ left: -22, right: 10, top: 12, bottom: 4 }}>
                <CartesianGrid vertical={false} stroke="#EAECF0" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(v) => String(v).slice(5).split('-').reverse().join('.')}
                  tick={{ fontSize: 10, fill: '#667085' }}
                  minTickGap={30}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis tick={{ fontSize: 10, fill: '#667085' }} axisLine={false} tickLine={false} />
                <Tooltip
                  formatter={(value, name) => [formatNumber(Number(value)) + ' ' + p.unit, name]}
                  contentStyle={{ borderRadius: 8, fontSize: 12, borderColor: '#D0D5DD' }}
                />
                <Line
                  dataKey="units"
                  name="Продажи"
                  stroke="#667085"
                  strokeWidth={1.7}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  dataKey="estimated_lost_units"
                  name="Упущенный спрос"
                  stroke="#175CD3"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
                {forecastPerDay !== null && (
                  <ReferenceLine
                    y={forecastPerDay}
                    stroke="#175CD3"
                    strokeDasharray="5 4"
                    ifOverflow="extendDomain"
                  />
                )}
                {item.history
                  .filter((d) => d.is_outlier)
                  .map((d) => (
                    <ReferenceDot
                      key={'outlier-' + d.date}
                      x={d.date}
                      y={d.units}
                      r={4}
                      fill="#B42318"
                      stroke="white"
                    />
                  ))}
                {item.history
                  .filter((d) => d.is_stockout)
                  .map((d) => (
                    <ReferenceDot
                      key={'stockout-' + d.date}
                      x={d.date}
                      y={0}
                      r={3}
                      fill="#B54708"
                      stroke="white"
                    />
                  ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-signals">
            <span>
              <i className="signal-dot anomaly" />
              Аномалии: {item.history.filter((d) => d.is_outlier).length} дн.
            </span>
            <span>
              <i className="signal-dot stockout" />
              Stockout: {item.history.filter((d) => d.is_stockout).length} дн.
            </span>
          </div>
          <p className="helper">
            Пунктир — средний прогноз на день срока поставки
            {forecastPerDay !== null
              ? ': ' + formatNumber(forecastPerDay) + ' ' + p.unit
              : ' (нет срока поставки)'}
            . Это ориентир, не ежедневная траектория прогноза. Скорректированный ряд API не
            передаёт.
          </p>
        </>
      )}
    </section>
  );
}
