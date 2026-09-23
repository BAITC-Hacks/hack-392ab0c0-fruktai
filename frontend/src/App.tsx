import { useWorkspace } from './hooks/useWorkspace';
import { WorkspaceShell } from './components/workspace/WorkspaceShell';
import { WorkspaceHeader } from './components/workspace/WorkspaceHeader';
import { WorkspaceViews } from './components/workspace/WorkspaceViews';
import { WorkspaceDialogs } from './components/workspace/WorkspaceDialogs';

/** Composition root: presentation delegates to the shared workspace controller. */
export default function App() {
  const workspace = useWorkspace();
  return (
    <>
      <WorkspaceShell workspace={workspace}>
        <WorkspaceHeader workspace={workspace} />
        <WorkspaceViews workspace={workspace} />
      </WorkspaceShell>
      <WorkspaceDialogs workspace={workspace} />
    </>
  );
}
