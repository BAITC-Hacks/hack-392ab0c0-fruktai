import { Database, CheckCircle2, ShieldCheck, Calculator, ClipboardCheck, Flag, Circle, Info } from 'lucide-react';
const steps = [
  { title: 'Получение данных', Icon: Database, detail: 'Для реального запуска: история продаж, остатки, товары в пути и периоды отсутствия товара.' },
  { title: 'Проверка', Icon: CheckCircle2, detail: 'Проверка схемы, обязательных полей и допустимых значений на стороне сервиса.' },
  { title: 'Очистка', Icon: ShieldCheck, detail: 'Выявление разовых крупных продаж и аномалий по обезличенному клиенту.' },
  { title: 'Расчёт', Icon: Calculator, detail: 'Восстановление упущенного спроса, сезонность, рост, прогноз и потребность.' },
  { title: 'Валидация', Icon: ClipboardCheck, detail: 'Проверка рекомендаций и формирование объяснения для каждой позиции.' },
  { title: 'Завершение', Icon: Flag, detail: 'Группировка результата по поставщикам и публикация времени расчёта.' },
];
export function AgentRunPanel({ open, onChange }: { open: boolean; onChange: (open: boolean) => void }) {
  return <details className="agent-panel" open={open} onToggle={event => onChange(event.currentTarget.open)} id="agent-run"><summary><span className="agent-icon"><ShieldCheck size={17}/></span><span><strong>Ход анализа</strong><small>Agent Run</small></span><span className="agent-pending">Не запускался</span></summary><div className="agent-body"><p className="helper"><Info size={14}/>Ниже — этапы обработки. Сервис расчёта не подключён; статусы и длительности запуска не получены.</p><ol className="agent-steps">{steps.map(({ title, Icon, detail }) => <li key={title}><Icon size={18}/><div><strong>{title}</strong><span><Circle size={8}/>Нет данных о выполнении</span><p>{detail}</p></div></li>)}</ol></div></details>;
}
