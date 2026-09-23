import { AlertTriangle, ArrowUpRight, ShieldCheck } from 'lucide-react';
import type { WorkspaceController } from '../../hooks/useWorkspace';
import { ImportPanel } from '../ImportPanel';
import { KpiCards } from '../KpiCards';
import { Analytics, Comparison } from '../Analytics';
import { AgentRunPanel } from '../AgentRunPanel';
import { DataView } from '../DataView';
import { LoadingState } from '../LoadingState';
import { ProcurementQueue } from './ProcurementQueue';
import { initialFilters } from '../../utils/presentation';
import { SuppliersView } from './SuppliersView';

export function WorkspaceViews({ workspace }: { workspace: WorkspaceController }) {
  const {
    data,
    view,
    highRisk,
    chooseKpi,
    products,
    navigate,
    setFilters,
    agentOpen,
    setAgentOpen,
    loading,
    load,
    dataset,
  } = workspace;
  return (
    <>
      {' '}
      {loading && !data && <LoadingState />}
      {data && view === 'overview' && (
        <>
          {highRisk > 0 && (
            <div className="risk-banner">
              <span className="risk-banner-icon">
                <AlertTriangle size={19} />
              </span>
              <div>
                <strong>
                  Приоритет сегодня: {highRisk}{' '}
                  {highRisk === 1 ? 'позиция' : highRisk < 5 ? 'позиции' : 'позиций'} с риском
                  дефицита
                </strong>
                <p>Проверьте покрытие спроса на срок поставки и включите нужные позиции в заказ.</p>
              </div>
              <button onClick={() => chooseKpi('risk')}>
                Показать позиции
                <ArrowUpRight size={16} />
              </button>
            </div>
          )}
          <KpiCards products={products} summary={data.response.summary} onSelect={chooseKpi} />
          {
            <div className="overview-grid">
              <Analytics
                products={products}
                onStatus={(status) => {
                  navigate('table');
                  setFilters({ ...initialFilters, status });
                }}
              />
              <Comparison products={products} />
            </div>
          }
        </>
      )}
      {data && view === 'table' && <ProcurementQueue workspace={workspace} />}
      {data && view === 'suppliers' && <SuppliersView workspace={workspace} />}
      {view === 'data' && (
        <div className="sources-layout">
          <ImportPanel
            busy={loading}
            initiallyOpen
            onCalculate={async (id) => {
              const result = await load([], id);
              if (result) navigate('table');
              return result;
            }}
          />
          {data && <DataView data={data} />}
        </div>
      )}
      {view === 'activity' && data && (
        <section className="activity-view">
          <div className="section-heading">
            <ShieldCheck size={22} />
            <div>
              <h2>Прозрачный процесс</h2>
              <p>Статусы и детали последнего открытого расчёта из API.</p>
            </div>
          </div>
          <AgentRunPanel
            steps={data.response.agent_steps}
            runId={data.response.run_id}
            open={agentOpen}
            onChange={setAgentOpen}
          />
          <p className="helper">
            Журнал показывает завершённый запуск, а не трансляцию этапов в реальном времени.
          </p>
        </section>
      )}
      {!loading && !data && view !== 'data' && (
        <section className="empty-state">
          <h2>Для этого раздела нужен расчёт</h2>
          <p>Загрузите исходные данные или повторите запрос к API.</p>
          <button className="secondary-button" onClick={() => navigate('data')}>
            Открыть источники данных
          </button>
        </section>
      )}
      {dataset !== 'demo' && (
        <button className="text-button" disabled={loading} onClick={() => void load([], 'demo')}>
          Вернуться к учебному набору demo
        </button>
      )}
    </>
  );
}
