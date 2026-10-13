import { describe, it, expect, vi, afterEach } from 'vitest';
import { parseSseBlock, watchJob } from './api';
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.useRealTimers(); });
function eventStream(chunks: string[]) {
  return new Response(new ReadableStream({ start(controller) { for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk)); controller.close(); } }), { headers: { 'Content-Type': 'text/event-stream' } });
}
describe('persisted job streaming', () => {
  it('ignores SSE heartbeats and preserves multiline JSON framing', () => {
    expect(parseSseBlock(': heartbeat')).toBeNull();
    expect(parseSseBlock('id: 42\nevent: token\ndata: {"text":\ndata: "hello"}')).toEqual({ id: 42, event: 'token', data: { text: 'hello' } });
  });
  it('receives tokens with split CRLF/chunk boundaries and stops on completion', async () => {
    const lost = vi.fn(); window.addEventListener('connection-lost', lost);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(eventStream(['id: 1\r', '\nevent: token\r\ndata: {"text":"Hello"}\r\n', '\r\nid: 2\nevent: completed\ndata: {"output":{"message_id":"saved"}}\n\n'])));
    const received: string[] = [];
    await watchJob('job', event => received.push(event.event), new AbortController().signal);
    expect(received).toEqual(['token', 'completed']);
    expect(lost).not.toHaveBeenCalled(); window.removeEventListener('connection-lost', lost);
  });
  it('reconnects with its last saved event ID and discards replay duplicates', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn().mockResolvedValueOnce(eventStream(['id: 7\nevent: token\ndata: {"text":"First"}\n\n'])).mockResolvedValueOnce(eventStream(['id: 7\nevent: token\ndata: {"text":"First"}\n\nid: 8\nevent: completed\ndata: {"output":{}}\n\n']));
    vi.stubGlobal('fetch', fetcher); const received: number[] = [];
    const stream = watchJob('replay', event => received.push(event.id), new AbortController().signal);
    await vi.advanceTimersByTimeAsync(2200); await stream;
    expect(received).toEqual([7, 8]);
    expect(fetcher.mock.calls[1][0]).toContain('after=7');
    expect(fetcher.mock.calls[1][1].headers['Last-Event-ID']).toBe('7');
  });
  it.each(['network', 'premature EOF'])('reports %s connection loss immediately before retrying', async kind => {
    const controller = new AbortController(); const lost = vi.fn(() => controller.abort());
    window.addEventListener('connection-lost', lost);
    const fetcher = kind === 'network' ? vi.fn().mockRejectedValue(new TypeError('Network disconnected')) : vi.fn().mockResolvedValue(eventStream(['id: 1\nevent: token\ndata: {"text":"Partial"}\n\n']));
    vi.stubGlobal('fetch', fetcher);
    try { await watchJob('lost', () => {}, controller.signal); expect(lost).toHaveBeenCalledOnce(); expect(fetcher).toHaveBeenCalledOnce(); }
    finally { controller.abort(); window.removeEventListener('connection-lost', lost); }
  });
  it('reports a stalled stream when its heartbeat watchdog expires', async () => {
    vi.useFakeTimers(); const controller = new AbortController(); const lost = vi.fn(() => controller.abort());
    window.addEventListener('connection-lost', lost);
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init: RequestInit) => new Response(new ReadableStream({ start(stream) { init.signal?.addEventListener('abort', () => stream.error(new DOMException('Aborted', 'AbortError')), { once: true }); } }))));
    try { const pending = watchJob('stalled', () => {}, controller.signal); await vi.advanceTimersByTimeAsync(44999); expect(lost).not.toHaveBeenCalled(); await vi.advanceTimersByTimeAsync(1); await pending; expect(lost).toHaveBeenCalledOnce(); }
    finally { controller.abort(); window.removeEventListener('connection-lost', lost); }
  });
  it.each([401, 403, 404, 429])('does not report authentication, ownership or quota status %i as a lost connection', async status => {
    const lost = vi.fn(); window.addEventListener('connection-lost', lost);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status })));
    try { await expect(watchJob('private', () => {}, new AbortController().signal)).rejects.toMatchObject({ status }); expect(lost).not.toHaveBeenCalled(); }
    finally { window.removeEventListener('connection-lost', lost); }
  });
});
describe('authorization response', () => {
  it('rejects a mismatched PKCE state before exchanging the code, then removes URL credentials', async () => {
    vi.resetModules(); const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    history.replaceState(null, '', '/?code=one-time&state=wrong');
    sessionStorage.setItem('chatabae.pkce', JSON.stringify({ verifier: 'secret-verifier', state: 'expected', created: Date.now(), returnHash: '#/library' }));
    const { finishAuth } = await import('./api');
    await expect(finishAuth()).rejects.toThrow('could not be verified');
    expect(fetcher).not.toHaveBeenCalled();
    expect(window.location.search).toBe('');
    expect(sessionStorage.getItem('chatabae.pkce')).toBeNull();
  });
  it('refreshes only through the cookie endpoint and sends no JavaScript refresh credential', async () => {
    vi.resetModules(); const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ access_token: 'short-token', token_type: 'bearer', expires_in: 900, user: { id: 'u', username: 'alice' } })));
    vi.stubGlobal('fetch', fetcher);
    const { refreshSession } = await import('./api');
    await refreshSession();
    expect(fetcher.mock.calls[0][0]).toContain('/api/v1/auth/refresh');
    expect(fetcher.mock.calls[0][1].credentials).toBe('include');
    expect(fetcher.mock.calls[0][1].body).toBe('{}');
    expect(localStorage.getItem('access_token')).toBeNull();
  });
  it('makes no network requests from an unconfigured production build', async () => {
    vi.resetModules(); vi.stubEnv('DEV', false); vi.stubEnv('VITE_API_BASE_URL', '');
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    const { api, API_URL } = await import('./api');
    expect(API_URL).toBe('');
    await expect(api('/status')).rejects.toThrow('not been configured');
    expect(fetcher).not.toHaveBeenCalled();
  });
});
