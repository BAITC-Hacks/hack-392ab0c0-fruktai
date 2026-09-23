import type { DemoProduct } from '../types/demo';
export function ProductArt({ kind }: { kind: DemoProduct['kind'] }) {
  return (
    <div className={'product-art ' + kind} aria-hidden="true">
      <i />
      <b />
      <span />
    </div>
  );
}
