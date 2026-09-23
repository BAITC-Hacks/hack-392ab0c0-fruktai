import { useState } from 'react';
import { importFiles, templateUrl } from '../api/client';
import type { ImportMetadata } from '../types/api';

export function ImportPanel({ onCalculate, busy }: { onCalculate: (dataset: string) => Promise<unknown>; busy: boolean }) {
  const [files, setFiles] = useState<File[]>([]);
  const [warehouse, setWarehouse] = useState('');
  const [anonymized, setAnonymized] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [metadata, setMetadata] = useState<ImportMetadata | null>(null);
  const [error, setError] = useState('');
  async function upload() {
    setUploading(true); setError(''); setMetadata(null);
    try { setMetadata(await importFiles(files, warehouse, anonymized)); }
    catch (problem) { setError(problem instanceof Error ? problem.message : 'Ошибка импорта'); }
    finally { setUploading(false); }
  }
  return <details className="agent-panel" data-testid="import-panel">
    <summary><strong>Загрузить данные / выгрузку 1С</strong></summary>
    <div className="agent-body">
      <p>Продажи, товары, поставщики, остатки или материальная ведомость, stockout и товары в пути.
        Форматы: CSV, TSV, XLSX, XLS, JSON, текстовые PDF.</p>
      <a className="text-button" href={templateUrl} download>Скачать Excel-шаблон с учебными данными</a>
      <p className="helper">Для PDF нужны текстовые таблицы с границами; сканы требуют OCR.
        Для 1С пока используется обмен файлами, прямое подключение не настроено.</p>
      <form onSubmit={e => { e.preventDefault(); void upload(); }}>
        <label>Файлы источников<input aria-label="Файлы источников" type="file" multiple
          accept=".csv,.tsv,.xlsx,.xls,.json,.pdf" disabled={uploading || busy}
          onChange={e => { setFiles(Array.from(e.target.files ?? [])); setMetadata(null); }}/></label>
        <label>Код склада (если складов несколько)<input aria-label="Код склада" value={warehouse}
          disabled={uploading || busy} onChange={e => { setWarehouse(e.target.value); setMetadata(null); }}/></label>
        <label className="checkbox-label"><input type="checkbox" checked={anonymized}
          onChange={e => setAnonymized(e.target.checked)}/>Клиентские данные обезличены, персональных данных нет</label>
        <button className="secondary-button" disabled={busy || uploading || !files.length || !anonymized}>
          {uploading ? 'Проверка файлов…' : 'Загрузить и проверить'}
        </button>
      </form>
      {error && <p role="alert" className="field-error">{error}</p>}
      {metadata && <section>
        <h3>Вход проверен — проверьте полноту перед расчётом</h3>
        <p>Набор: {metadata.dataset} · Склад: {metadata.warehouse_id || 'не указан'}
          · Источник: {metadata.source === '1c_file_exchange' ? 'Ведомость 1С' : 'Загрузка файлов'}</p>
        <ul>{Object.entries(metadata.counts).map(([table, count]) => <li key={table}>{table}: {count} строк</li>)}</ul>
        {metadata.warnings.length > 0 && <div role="status"><strong>Предупреждения</strong><ul>
          {metadata.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></div>}
        <details><summary>Предпросмотр нормализованных данных</summary>
          {Object.entries(metadata.preview).map(([table, rows]) => <div key={table}>
            <h4>{table}</h4><pre style={{ overflowX: 'auto' }}>{JSON.stringify(rows, null, 2)}</pre></div>)}
        </details>
        <button className="primary-button" disabled={busy} onClick={() => void onCalculate(metadata.dataset)}>
          {busy ? 'Расчёт…' : 'Рассчитать загруженные данные'}
        </button>
      </section>}
    </div>
  </details>;
}
