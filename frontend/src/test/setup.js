import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

function createStorage() {
  let store = {};
  return {
    getItem: (key) => store[key] ?? null,
    setItem: (key, value) => {
      store[key] = String(value);
    },
    removeItem: (key) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
}

if (typeof globalThis.localStorage === 'undefined') {
  const storage = createStorage();
  globalThis.localStorage = storage;
  if (typeof window !== 'undefined') {
    Object.defineProperty(window, 'localStorage', { value: storage });
  }
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
  document.documentElement.removeAttribute('lang');
});
