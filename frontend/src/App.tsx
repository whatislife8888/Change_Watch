import { useEffect, useState } from 'react';

/** Phase 0 placeholder: proves the Vite proxy reaches the backend. */
export default function App() {
  const [health, setHealth] = useState('checking...');
  useEffect(() => {
    fetch('/api/health').then((r) => r.json()).then((d) => setHealth(JSON.stringify(d))).catch((e) => setHealth(String(e)));
  }, []);
  return <p>Backend says: {health}</p>;
}
