import type { StreamEvent, TokenResponse } from './types';
import type { paths } from './generated/api-schema';

type HttpMethod = 'get' | 'post' | 'put' | 'patch' | 'delete';
type Operation<P extends keyof paths, M extends HttpMethod> = M extends keyof paths[P] ? NonNullable<paths[P][M]> : never;
type JsonBody<P extends keyof paths, M extends HttpMethod> = Operation<P, M> extends { requestBody?: infer B } ? NonNullable<B> extends { content: { 'application/json': infer Body } } ? Body : never : never;
type Responses<P extends keyof paths, M extends HttpMethod> = Operation<P, M> extends { responses: infer R } ? R : never;
type JsonResponse<P extends keyof paths, M extends HttpMethod> = { [S in keyof Responses<P, M> & (200 | 201 | 202 | 204)]: Responses<P, M>[S] extends { content: { 'application/json': infer Body } } ? Body : undefined }[keyof Responses<P, M> & (200 | 201 | 202 | 204)];
type Endpoint<P extends keyof paths> = {
  [M in HttpMethod as Operation<P, M> extends never ? never : M]: M extends 'get' | 'delete' ? <T = JsonResponse<P, M>>(init?: RequestInit) => Promise<T> : <T = JsonResponse<P, M>>(body: JsonBody<P, M>, init?: RequestInit) => Promise<T>
};
/** Generated routes and bodies share the backend OpenAPI source; transport handles tokens and timeouts. */
export function endpoint<P extends keyof paths>(template: P, parameters: Record<string, string> = {}): Endpoint<P> {
  const path = template.replace(/\{([^}]+)\}/g, (_, name: string) => {
    if (!(name in parameters)) throw new Error('Missing API path parameter: ' + name);
    return encodeURIComponent(parameters[name]);
  });
  const read = (method: string) => <T>(init: RequestInit = {}) => api<T>(path, { ...init, method });
  const write = (method: string) => <T>(body: unknown, init: RequestInit = {}) => api<T>(path, { ...init, method, body: JSON.stringify(body) });
  return { get: read('GET'), delete: read('DELETE'), post: write('POST'), put: write('PUT'), patch: write('PATCH') } as unknown as Endpoint<P>;
}

export const API_URL = (import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? 'http://127.0.0.1:7810' : '')).replace(/\/$/, '');
let accessToken = '';
export function setTokens(tokens: TokenResponse | null) { accessToken = tokens?.access_token || ''; }
export function hasToken() { return Boolean(accessToken); }
export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!API_URL) throw new ApiError(503, 'The server connection has not been configured yet.');
  const headers = new Headers(init.headers);
  if (accessToken) headers.set('Authorization', 'Bearer ' + accessToken);
  if (init.body && typeof init.body === 'string') headers.set('Content-Type', 'application/json');
  const controller = new AbortController();
  const abort = () => controller.abort();
  init.signal?.addEventListener('abort', abort, { once: true });
  if (init.signal?.aborted) controller.abort();
  const timer = setTimeout(abort, 15000);
  try {
    const response = await fetch(API_URL + (path.startsWith('/api/') ? path : '/api/v1' + path), { ...init, headers, credentials: 'include', signal: controller.signal });
    if (!response.ok) {
      let detail = 'Request failed (' + response.status + ')';
      try { const data = await response.json(); detail = typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map((item: { msg?: string }) => String(item.msg || detail).replace(/^Value error, /, '')).join('; ') : data.error || detail; } catch { /* Proxies can return HTML. */ }
      if (response.status === 401 && accessToken) { setTokens(null); window.dispatchEvent(new Event('auth-expired')); }
      throw new ApiError(response.status, detail);
    }
    if (response.status === 204) return undefined as T;
    return await response.json() as T;
  } finally { clearTimeout(timer); init.signal?.removeEventListener('abort', abort); }
}
export async function refreshSession() {
  const tokens = await endpoint('/api/v1/auth/refresh').post<TokenResponse>({});
  setTokens(tokens); return tokens;
}
const toBase64Url = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
export function frontendRoot() { return window.location.origin + import.meta.env.BASE_URL; }
export async function beginAuth(mode = 'login') {
  if (!API_URL) throw new ApiError(503, 'The server connection has not been configured yet.');
  const verifier = toBase64Url(crypto.getRandomValues(new Uint8Array(32)));
  const state = toBase64Url(crypto.getRandomValues(new Uint8Array(24)));
  const challenge = toBase64Url(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))));
  sessionStorage.setItem('chatabae.pkce', JSON.stringify({ verifier, state, created: Date.now(), returnHash: window.location.hash }));
  const query = new URLSearchParams({ client_id: 'chatabae', redirect_uri: frontendRoot(), code_challenge: challenge, code_challenge_method: 'S256', state, mode });
  window.location.assign(API_URL + '/auth/authorize?' + query);
}
let authCompletion: Promise<TokenResponse | null> | undefined;
export function finishAuth(): Promise<TokenResponse | null> {
  if (authCompletion) return authCompletion;
  authCompletion = finishAuthOnce(); return authCompletion;
}
async function finishAuthOnce(): Promise<TokenResponse | null> {
  const query = new URLSearchParams(window.location.search);
  const code = query.get('code');
  if (!code) return null;
  const raw = sessionStorage.getItem('chatabae.pkce');
  sessionStorage.removeItem('chatabae.pkce');
  history.replaceState(null, '', window.location.pathname + window.location.hash);
  if (!raw) throw new Error('This sign-in request has expired. Please sign in again.');
  const saved = JSON.parse(raw) as { verifier: string; state: string; created: number; returnHash: string };
  if (query.get('state') !== saved.state || Date.now() - saved.created > 10 * 60 * 1000) throw new Error('The sign-in response could not be verified. Please try again.');
  const tokens = await endpoint('/api/v1/auth/exchange').post<TokenResponse>({ code, code_verifier: saved.verifier, redirect_uri: frontendRoot() });
  setTokens(tokens); window.location.hash = saved.returnHash || '#/library'; return tokens;
}
export function parseSseBlock(block: string): StreamEvent | null {
  let id = 0, event = 'message'; const data: string[] = [];
  for (const line of block.split('\n')) {
    if (line.startsWith('id:')) id = Number(line.slice(3).trim());
    if (line.startsWith('event:')) event = line.slice(6).trim();
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
  }
  if (!data.length) return null;
  return { id, event, data: JSON.parse(data.join('\n')) as Record<string, unknown> };
}
export async function watchJob(jobId: string, onEvent: (event: StreamEvent) => void, signal: AbortSignal) {
  let lastId = 0, attempts = 0;
  while (!signal.aborted) {
    let reportedLost = false;
    const reportLost = () => { if (!signal.aborted && !reportedLost) { reportedLost = true; window.dispatchEvent(new Event('connection-lost')); } };
    try {
      const controller = new AbortController();
      const abort = () => controller.abort();
      signal.addEventListener('abort', abort, { once: true });
      const stalled = () => { reportLost(); abort(); };
      let watchdog = setTimeout(stalled, 45000);
      let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
      try {
      const response = await fetch(API_URL + '/api/v1/jobs/' + encodeURIComponent(jobId) + '/events?after=' + lastId, { headers: { Authorization: 'Bearer ' + accessToken, Accept: 'text/event-stream', ...(lastId ? { 'Last-Event-ID': String(lastId) } : {}) }, signal: controller.signal });
      if (!response.ok || !response.body) throw new ApiError(response.status, 'The connection to this response was interrupted.');
      reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
      while (!signal.aborted) {
        const { done, value } = await reader.read();
        clearTimeout(watchdog); watchdog = setTimeout(stalled, 45000);
        buffer += decoder.decode(value, { stream: !done }); buffer = buffer.replace(/\r\n/g, '\n');
        let boundary;
        while ((boundary = buffer.indexOf('\n\n')) !== -1) {
          const event = parseSseBlock(buffer.slice(0, boundary)); buffer = buffer.slice(boundary + 2);
          if (!event || (event.id && event.id <= lastId)) continue;
          if (event.event === 'auth_expired') { setTokens(null); window.dispatchEvent(new Event('auth-expired')); throw new ApiError(401, String(event.data.reason || 'Please sign in again.')); }
          lastId = Math.max(lastId, event.id); onEvent(event);
          if (['completed', 'failed', 'cancelled'].includes(event.event)) { await reader.cancel().catch(() => {}); return; }
        }
        if (done) break;
      }
      if (!signal.aborted) throw new Error('The server stopped sending updates. Reopen the conversation to check its saved state.');
      } finally { clearTimeout(watchdog); signal.removeEventListener('abort', abort); await reader?.cancel().catch(() => {}); }
    } catch (error) { if (signal.aborted) return; if (!(error instanceof ApiError && error.status >= 400 && error.status < 500)) reportLost(); if (++attempts > 5 || error instanceof ApiError && [401, 403, 404, 429].includes(error.status)) throw error; }
    await new Promise<void>((resolve) => { const finish = () => { clearTimeout(timer); signal.removeEventListener('abort', finish); resolve(); }; const timer = setTimeout(finish, Math.min(1000 * 2 ** attempts, 15000)); signal.addEventListener('abort', finish, { once: true }); if (signal.aborted) finish(); });
  }
}
export async function assetBlob(id: string, signal?: AbortSignal) {
  if (!API_URL) throw new ApiError(503, 'The server connection has not been configured yet.');
  const timeout = AbortSignal.timeout(15000);
  const response = await fetch(API_URL + '/api/v1/assets/' + encodeURIComponent(id) + '/content', { headers: accessToken ? { Authorization: 'Bearer ' + accessToken } : {}, signal: signal ? AbortSignal.any([signal, timeout]) : timeout });
  if (!response.ok) throw new ApiError(response.status, 'This media could not be loaded.');
  return URL.createObjectURL(await response.blob());
}
