import { CheckCircle2, AlertTriangle, Workflow, ChevronDown } from 'lucide-react';
import type { AgentStep } from '../types/api';

const labels: Record<string, string> = {
  load_data: 'Данные загружены', validate_data: 'Структура проверена',
  detect_outliers: 'Аномалии обработаны', estimate_lost_demand: 'Упущенный спрос оценён',
  calculate_recommendations: 'Рекомендации рассчитаны', validate_result: 'Результат проверен',
  save_result: 'Расчёт сохранён',
};
export function AgentRunPanel({ open, onChange, steps, runId }: {
  open: boolean; onChange: (open: boolean) => void; steps: AgentStep[]; runId: string;
}) {
  const complete = steps.filter(s => s.status === 'completed').length;
  return <details className="agent-panel" open={open} onToggle={e => { if (e.currentTarget.open !== open) onChange(e.currentTarget.open); }} id="agent-run">
    <summary><span className="agent-icon"><Workflow size={19}/></span><strong>Ход анализа</strong><span className="agent-summary-note">Проверяемая цепочка расчёта</span><span className="agent-pending">{complete} / {steps.length} выполнено</span><ChevronDown size={16}/></summary>
    <div className="agent-body"><p className="run-id">Run ID <code>{runId}</code></p><ol className="agent-steps">
      {steps.map((step, index) => <li key={step.step}>{step.status === 'completed' ? <CheckCircle2 size={18}/> : <AlertTriangle size={18}/>}<div><strong><small>{String(index + 1).padStart(2, '0')}</small>{labels[step.step] || step.step}</strong><span>{step.status === 'completed' ? 'Выполнено' : step.status === 'warning' ? 'Предупреждение' : 'Ошибка'}</span><details><summary>Технические детали</summary><p>{step.message}</p></details></div></li>)}
    </ol><p className="helper">Журнал получен из API. Количество рассчитано алгоритмом; AI-пояснения, если доступны, находятся в карточке товара.</p></div>
  </details>;
}
