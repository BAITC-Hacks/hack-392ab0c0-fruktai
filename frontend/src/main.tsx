import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';
// A mount starts a persisted recalculation; do not double-submit it in dev StrictMode.
ReactDOM.createRoot(document.getElementById('root')!).render(<App />);
