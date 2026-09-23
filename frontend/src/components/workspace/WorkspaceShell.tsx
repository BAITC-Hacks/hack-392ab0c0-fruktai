import type { ReactNode } from 'react';
import {
  BarChart3,
  Database,
  ChevronRight,
  ShoppingCart,
  Users,
  ShieldCheck,
  Layers3,
  Warehouse,
  Menu,
  Activity,
} from 'lucide-react';
import type { View, WorkspaceController } from '../../hooks/useWorkspace';

export function WorkspaceShell({
  workspace,
  children,
}: {
  workspace: WorkspaceController;
  children: ReactNode;
}) {
  const {
    view,
    grouped,
    products,
    navigate,
    mobileNav,
    compactNav,
    setMobileNav,
    data,
    loading,
    error,
    title,
  } = workspace;
  const navItems = [
    { id: 'overview' as View, label: 'Обзор запасов', Icon: BarChart3 },
    {
      id: 'table' as View,
      label: 'Рекомендации',
      Icon: ShoppingCart,
      count: products.filter((p) => p.recommended > 0).length,
    },
    { id: 'table' as View, label: 'Поставщики', Icon: Users, suppliers: true },
    { id: 'data' as View, label: 'Источники данных', Icon: Database },
    { id: 'activity' as View, label: 'Ход анализа', Icon: Activity },
  ];

  return (
    <>
      {' '}
      <a className="skip-link" href="#main-content">
        Перейти к рекомендациям
      </a>
      {compactNav && mobileNav && (
        <button
          className="nav-scrim"
          aria-label="Закрыть навигацию"
          onClick={() => setMobileNav(false)}
        />
      )}
      <aside
        className={'app-sidebar' + (mobileNav ? ' is-open' : '')}
        inert={compactNav && !mobileNav}
      >
        <a
          className="brand"
          href="#main-content"
          onClick={() => navigate('table')}
          aria-label="FruktAI — план закупок"
        >
          <span className="brand-symbol">
            <Layers3 size={23} strokeWidth={1.8} />
          </span>
          <strong>
            frukt<span>ai</span>
          </strong>
          <span className="workspace-badge">WORKSPACE</span>
        </a>
        <div className="workspace-identity">
          <span className="workspace-avatar">ЭК</span>
          <div>
            <strong>Электрокомплект</strong>
            <small>Планирование закупок</small>
          </div>
        </div>
        <span className="nav-section-label">Рабочее пространство</span>
        <nav aria-label="Основная навигация">
          {navItems.map(({ id, label, Icon, count, suppliers }) => {
            const active = view === id && (id !== 'table' || grouped === !!suppliers);
            return (
              <button
                key={label}
                className={active ? 'is-active' : ''}
                aria-current={active ? 'page' : undefined}
                onClick={() => navigate(id, suppliers)}
              >
                <Icon size={18} />
                <span>{label}</span>
                {count !== undefined && data && <b>{count}</b>}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="workflow-note">
            <ShieldCheck size={19} />
            <strong>Проверяемый расчёт</strong>
            <p>
              Алгоритм определяет количество.
              <br />
              AI помогает объяснить решение.
            </p>
          </div>
          <div className="sidebar-version">
            <span>HackAlem AI</span>
            <span>MVP</span>
          </div>
        </div>
      </aside>
      <div className="app-shell" inert={compactNav && mobileNav}>
        <header className="app-topbar">
          <button
            className="icon-button mobile-nav-toggle"
            aria-label="Открыть навигацию"
            onClick={() => setMobileNav(true)}
          >
            <Menu size={20} />
          </button>
          <div className="breadcrumbs">
            <span>Закупки</span>
            <ChevronRight size={14} />
            <strong>{title}</strong>
          </div>
          <div className="topbar-context">
            <span className="warehouse-label">
              <Warehouse size={15} />
              {data?.metadata?.warehouse_id || 'Склад не указан'}
            </span>
            <span className={'connection-status' + (error ? ' has-error' : '')}>
              <i />
              {loading
                ? 'Расчёт…'
                : error
                  ? 'Ошибка обновления'
                  : data
                    ? 'Расчёт получен'
                    : 'Нет данных'}
            </span>
            <button
              className="avatar"
              title="Профиль рабочего места"
              aria-label="Открыть профиль"
              aria-haspopup="dialog"
              onClick={() => workspace.setProfileOpen(true)}
            >
              МЗ
            </button>
          </div>
        </header>

        <main id="main-content">
          {children}
          <footer className="app-footer">
            <span>
              FruktAI <span> / </span> Рабочее место закупок
            </span>
            <span>Расчёт → проверка → экспорт</span>
          </footer>
        </main>
      </div>
    </>
  );
}
