import { useEffect, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';

interface Props {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}
export function Drawer({ title, children, onClose, wide = false }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element?.showModal();
    document.body.classList.add('dialog-open');
    return () => {
      element?.close();
      document.body.classList.remove('dialog-open');
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className={'drawer ' + (wide ? 'wide-drawer' : '')}
      aria-labelledby="drawer-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          const rect = event.currentTarget.getBoundingClientRect();
          if (
            event.clientX < rect.left ||
            event.clientX > rect.right ||
            event.clientY < rect.top ||
            event.clientY > rect.bottom
          )
            onClose();
        }
      }}
    >
      <header className="drawer-header">
        <span id="drawer-title">{title}</span>
        <button className="icon-button" onClick={onClose} aria-label="Закрыть панель" autoFocus>
          <X size={20} />
        </button>
      </header>
      <div className="drawer-body">{children}</div>
    </dialog>
  );
}
