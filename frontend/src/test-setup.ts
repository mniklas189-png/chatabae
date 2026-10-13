import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
Object.defineProperty(globalThis, 'localStorage', { value: window.localStorage, configurable: true });
Object.defineProperty(globalThis, 'sessionStorage', { value: window.sessionStorage, configurable: true });
afterEach(cleanup);
