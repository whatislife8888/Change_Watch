/**
 * main.tsx — the entry point: loads the global styles and mounts <App /> into #root.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './design/global.css';
import { setupInstall } from './lib/install';

// Service worker + "Install app" support (see lib/install.ts). Runs before React so no install event is missed.
setupInstall();

// Apply the saved theme before React renders, so the page never flashes the wrong colours.
try {
  document.documentElement.dataset.theme = localStorage.getItem('cw-theme') === 'opaline' ? 'opaline' : 'fume';
} catch {
  document.documentElement.dataset.theme = 'fume';
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
