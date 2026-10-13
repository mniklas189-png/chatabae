import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
Object.defineProperty(globalThis, 'localStorage', { value: window.localStorage, configurable: true });
Object.defineProperty(globalThis, 'sessionStorage', { value: window.sessionStorage, configurable: true });
Object.defineProperty(HTMLMediaElement.prototype, 'play', { value: () => Promise.resolve(), configurable: true, writable: true });
Object.defineProperty(HTMLMediaElement.prototype, 'pause', { value: () => {}, configurable: true, writable: true });
Object.defineProperty(HTMLMediaElement.prototype, 'load', { value: () => {}, configurable: true, writable: true });
afterEach(cleanup);
