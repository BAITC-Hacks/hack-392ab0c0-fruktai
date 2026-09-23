import { AlertTriangle, CircleCheck, Clock3 } from 'lucide-react';
import type { DemoStatus } from '../types/demo';

export function StatusBadge({ status }: { status: DemoStatus }) {
  const kind = status === 'Дефицит' ? 'danger' : status === 'В норме' ? 'neutral' : 'warning';
  const Icon = status === 'Дефицит' ? AlertTriangle : status === 'В норме' ? CircleCheck : Clock3;
  return <span className={`status-badge ${kind}`}><Icon size={13} aria-hidden="true"/>{status}</span>;
}
