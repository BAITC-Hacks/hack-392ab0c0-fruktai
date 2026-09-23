import type { AgentStep } from '../types/api';
export function AgentRunPanel({ open, onChange, steps, runId }: {
  open: boolean; onChange: (open: boolean) => void; steps: AgentStep[]; runId: string;
}) {
  return <details className="agent-panel" open={open} onToggle={e => onChange(e.currentTarget.open)} id="agent-run">
    <summary>Ход анализа · {steps.length} шагов</summary>
    <div className="agent-body"><p>Запуск: {runId}</p><ol className="agent-steps">
      {steps.map(step => <li key={step.step}><div><strong>{step.step}</strong><span>{step.status}</span><p>{step.message}</p></div></li>)}
    </ol><p className="helper">Статусы получены из API. Необязательные AI-пояснения видны в обоснованиях товара; число заказа рассчитано алгоритмом.</p></div>
  </details>;
}
