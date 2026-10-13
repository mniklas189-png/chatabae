import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from './App';
import { setTokens } from './api';
import { examples } from './examples';
import { stopAllSpeech } from './speech';
import type { Asset, Character, Job, Message } from './types';

const timestamp = '2026-10-12T12:00:00Z';
const token = { access_token: 'speech-test-access', token_type: 'bearer' as const, expires_in: 900, user: { id: 'speech-user', username: 'alice' } };
const character: Character = { ...examples[0], id: 'speech-character', name: 'Speech character', example: false, voice: 'kokoro:af_heart', language: 'en', profile: { ...examples[0].profile, age: 25 } };
const conversation = { id: 'speech-conversation', character_id: character.id, title: 'Current conversation', created_at: timestamp, updated_at: timestamp };
const otherConversation = { ...conversation, id: 'another-conversation', title: 'Another conversation' };
const oldReply: Message = { id: 'old-reply', conversation_id: conversation.id, role: 'assistant', content: 'An old saved answer.', created_at: timestamp, edited_at: null, assets: [] };
const newReply: Message = { ...oldReply, id: 'new-reply', content: 'A complete new answer.' };
const userMessage: Message = { ...oldReply, id: 'user-message', role: 'user', content: 'Hello' };
const job = (id: string, kind: string): Job => ({ id, kind, status: 'queued', created_at: timestamp, output: {}, error: null });
const jsonResponse = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const completedResponse = (output: unknown) => new Response('id: 1\nevent: completed\ndata: ' + JSON.stringify({ output }) + '\n\n', { headers: { 'Content-Type': 'text/event-stream' } });

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(accept => { resolve = accept; });
  return { promise, resolve };
}

function openChatEvents(signal?: AbortSignal | null) {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  let eventId = 0, closed = false;
  const abort = () => { if (!closed) { closed = true; controller.error(new DOMException('Stopped', 'AbortError')); } };
  const stream = new ReadableStream<Uint8Array>({
    start(value) { controller = value; },
    cancel() { closed = true; signal?.removeEventListener('abort', abort); },
  });
  signal?.addEventListener('abort', abort, { once: true });
  const send = (event: string, data: unknown) => {
    if (!closed) controller.enqueue(new TextEncoder().encode(`id: ${++eventId}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
  };
  return {
    response: new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } }),
    token: (text: string) => send('token', { text }),
    complete(output: unknown) { send('completed', { output }); if (!closed) { closed = true; controller.close(); signal?.removeEventListener('abort', abort); } },
    close() { if (!closed) { closed = true; controller.close(); signal?.removeEventListener('abort', abort); } },
  };
}

type SpeechRequest = { payload: Record<string, unknown>; signal?: AbortSignal | null };
interface SpeechHarness {
  fetcher: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
  speechRequests: SpeechRequest[];
  cancellations: string[];
  readonly chatSignal?: AbortSignal | null;
  readonly creationSignal?: AbortSignal | null;
  readonly chatCompleted: boolean;
  readonly pendingReloads: number;
  readonly speechWatches: number;
  readonly preferences: { autoplay: boolean; speed: number; volume: number; language: string; voice: string };
  token(text: string): void;
  completeChat(): void;
  acknowledgeSpeech(): void;
  releaseReload(): Promise<void>;
  cleanup(): void;
}
const harnesses: SpeechHarness[] = [];

function speechServer({ hq = false, delayedCreation = false, delayedReload = false } = {}): SpeechHarness {
  const person = { ...character, voice: hq ? 'xtts:Ana Florence' : character.voice };
  const creation = deferred<Response>(), reloadGate = deferred<Response>(), reloadRead = deferred<void>();
  const speechRequests: SpeechRequest[] = [], cancellations: string[] = [];
  let chatEvents: ReturnType<typeof openChatEvents> | undefined;
  let chatSignal: AbortSignal | null | undefined, creationSignal: AbortSignal | null | undefined;
  let sent = false, chatCompleted = false, pendingReloads = 0, speechWatches = 0;
  let preferences = { autoplay: true, speed: 1.2, volume: 0.5, language: 'en', voice: person.voice };
  const audio: Asset = { id: 'speech-audio', conversation_id: conversation.id, kind: 'audio', mime_type: 'audio/wav', size_bytes: 100, created_at: timestamp, url: '/api/v1/assets/speech-audio/content' };
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes('/auth/refresh')) return jsonResponse(token);
    if (url.endsWith('/auth/logout')) return jsonResponse({ ok: true });
    if (url.endsWith('/status')) return jsonResponse({ state: 'ready', online: true, instance_id: 'speech-test' });
    if (url.includes('/jobs/chat-job/events')) { chatSignal = init?.signal; chatEvents = openChatEvents(chatSignal); return chatEvents.response; }
    if (url.includes('/jobs/speech-job/events')) { speechWatches++; return completedResponse({ assets: [audio] }); }
    if (url.endsWith('/cancel')) {
      cancellations.push(url.split('/').at(-2)!);
      return jsonResponse({ ok: true });
    }
    if (url.endsWith('/speech') && init?.method === 'POST') {
      creationSignal = init.signal;
      speechRequests.push({ payload: JSON.parse(String(init.body)), signal: init.signal });
      return delayedCreation ? creation.promise : jsonResponse(job('speech-job', 'speech'), 202);
    }
    if (url.endsWith('/messages') && init?.method === 'POST') { sent = true; return jsonResponse({ message: userMessage, job: job('chat-job', 'chat') }, 202); }
    if (url.endsWith('/messages')) return jsonResponse(url.includes(otherConversation.id) ? [] : chatCompleted ? [oldReply, userMessage, newReply] : sent ? [oldReply, userMessage] : [oldReply]);
    if (url.endsWith('/memories') || url.endsWith('/assets') || url.endsWith('/library')) return jsonResponse([]);
    if (url.endsWith('/content')) return new Response(new Blob(['test-audio'], { type: 'audio/wav' }));
    if (url.endsWith('/characters')) {
      if (delayedReload && chatCompleted) { pendingReloads++; return reloadGate.promise; }
      return jsonResponse([person]);
    }
    if (url.endsWith('/conversations')) return jsonResponse([conversation, otherConversation]);
    if (url.endsWith('/preferences')) {
      if (init?.method === 'PUT') preferences = JSON.parse(String(init.body));
      return jsonResponse(preferences);
    }
    if (url.endsWith('/voices')) return jsonResponse([{ id: person.voice, engine: hq ? 'xtts' : 'kokoro', name: 'Selected voice', language: 'en', available: true }]);
    return jsonResponse([]);
  });
  const harness: SpeechHarness = {
    fetcher, speechRequests, cancellations,
    get chatSignal() { return chatSignal; },
    get creationSignal() { return creationSignal; },
    get chatCompleted() { return chatCompleted; },
    get pendingReloads() { return pendingReloads; },
    get speechWatches() { return speechWatches; },
    get preferences() { return preferences; },
    token(text: string) { if (!chatEvents) throw new Error('Chat SSE has not opened'); chatEvents.token(text); },
    completeChat() { chatCompleted = true; if (!chatEvents) throw new Error('Chat SSE has not opened'); chatEvents.complete({ message: newReply }); },
    acknowledgeSpeech() { creation.resolve(jsonResponse(job('speech-job', 'speech'), 202)); },
    releaseReload() {
      const response = jsonResponse([person]);
      const parse = response.json.bind(response);
      response.json = async () => { const result = await parse(); reloadRead.resolve(); return result; };
      reloadGate.resolve(response);
      // Assert after the old request has actually been consumed, not while it is still pending.
      return reloadRead.promise;
    },
    cleanup() { creation.resolve(jsonResponse(job('speech-job', 'speech'), 202)); reloadGate.resolve(jsonResponse([person])); chatEvents?.close(); },
  };
  harnesses.push(harness);
  vi.stubGlobal('fetch', fetcher);
  return harness;
}

beforeEach(() => {
  setTokens(null); localStorage.clear(); sessionStorage.clear(); history.replaceState(null, '', '/');
  Element.prototype.scrollIntoView = vi.fn();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  if (!URL.createObjectURL) Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:speech-test', configurable: true, writable: true });
  if (!URL.revokeObjectURL) Object.defineProperty(URL, 'revokeObjectURL', { value: () => {}, configurable: true, writable: true });
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:speech-test');
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
});

afterEach(async () => {
  cleanup();
  await act(async () => { for (const harness of harnesses.splice(0)) harness.cleanup(); await stopAllSpeech(); });
  vi.restoreAllMocks(); vi.unstubAllGlobals(); setTokens(null);
});

async function startChat(harness: SpeechHarness) {
  render(<MemoryRouter initialEntries={['/conversations/' + conversation.id]}><App/></MemoryRouter>);
  await screen.findByText(oldReply.content);
  await screen.findByRole('button', { name: /alice/ });
  await act(async () => { await Promise.resolve(); });
  expect(harness.speechRequests).toHaveLength(0);
  fireEvent.change(screen.getByRole('textbox', { name: 'Write a message…' }), { target: { value: 'Hello' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
  await waitFor(() => expect(harness.chatSignal).toBeDefined());
}

describe('automatic speech and the live conversation', () => {
  it('starts Fast speech while chat SSE remains open with an independent cancellation signal', async () => {
    const harness = speechServer();
    await startChat(harness);
    await act(async () => { harness.token('The first sentence is ready. Still generating'); });
    await waitFor(() => expect(harness.speechRequests).toHaveLength(1));
    expect(harness.chatCompleted).toBe(false);
    expect(harness.speechRequests[0].payload).toEqual({ text: 'The first sentence is ready.', voice: 'kokoro:af_heart', language: 'en', speed: 1.2 });
    expect(harness.chatSignal?.aborted).toBe(false);
    expect(harness.speechRequests[0].signal?.aborted).toBe(false);
    expect(harness.speechRequests[0].signal).not.toBe(harness.chatSignal);
    const player = await screen.findByRole('region', { name: 'Automatic speech' });
    expect(player.querySelector('audio')?.src).toContain('blob:speech-test');
    await act(async () => { harness.token(' the rest of the answer. '); });
    expect(await screen.findByText(/Still generating the rest of the answer/)).toBeTruthy();
    expect(harness.chatSignal?.aborted).toBe(false);
    expect(harness.cancellations).not.toContain('chat-job');
  });

  it('retains a delayed admission acknowledgement after Stop and cancels the owned speech ID without watching it', async () => {
    const harness = speechServer({ delayedCreation: true });
    await startChat(harness);
    await act(async () => { harness.token('A sentence ready for speech. More text'); });
    await waitFor(() => expect(harness.speechRequests).toHaveLength(1));
    fireEvent.click(screen.getByRole('button', { name: 'Stop response' }));
    await waitFor(() => expect(harness.cancellations).toContain('chat-job'));
    expect(harness.creationSignal?.aborted).toBe(false);
    expect(harness.cancellations).not.toContain('speech-job');
    await act(async () => { harness.acknowledgeSpeech(); });
    await waitFor(() => expect(harness.cancellations.filter(id => id === 'speech-job')).toHaveLength(1));
    expect(harness.speechWatches).toBe(0);
    expect(harness.cancellations.every(id => ['chat-job', 'speech-job'].includes(id))).toBe(true);
  });

  it('keeps a manual player after NotAllowedError and resumes it without interrupting the chat', async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, 'play')
      .mockRejectedValueOnce(new DOMException('Browser requires a gesture', 'NotAllowedError'))
      .mockImplementation(function (this: HTMLMediaElement) { this.dispatchEvent(new Event('play')); return Promise.resolve(); });
    const harness = speechServer();
    await startChat(harness);
    await act(async () => { harness.token('A playable first sentence. Still generating'); });
    const region = await screen.findByRole('region', { name: 'Automatic speech' });
    await screen.findByText('Press play to start the audio.');
    expect(region.querySelector('audio')?.getAttribute('src')).toBe('blob:speech-test');
    expect(harness.chatSignal?.aborted).toBe(false);
    expect(harness.chatCompleted).toBe(false);
    fireEvent.click(within(region).getByRole('button', { name: 'Resume audio' }));
    await waitFor(() => expect(play).toHaveBeenCalledTimes(2));
    expect(within(region).getByRole('button', { name: 'Pause audio' })).toBeTruthy();
    expect(harness.chatSignal?.aborted).toBe(false);
    expect(harness.cancellations).not.toContain('chat-job');
    expect(URL.revokeObjectURL).not.toHaveBeenCalledWith('blob:speech-test');
  });

  it('starts HQ speech only after the complete reply and its post-chat reload', async () => {
    const harness = speechServer({ hq: true, delayedReload: true });
    await startChat(harness);
    await act(async () => { harness.token('A complete sentence. More text'); });
    expect(harness.speechRequests).toHaveLength(0);
    await act(async () => { harness.completeChat(); });
    await waitFor(() => expect(harness.pendingReloads).toBeGreaterThan(0));
    expect(harness.speechRequests).toHaveLength(0);
    await act(async () => { await harness.releaseReload(); });
    await waitFor(() => expect(harness.speechRequests).toHaveLength(1));
    expect(harness.speechRequests[0].payload).toEqual({ text: newReply.content, voice: 'xtts:Ana Florence', language: 'en', speed: 1.2 });
  });

  it.each(['navigate', 'autoplay off', 'logout'] as const)('does not start stale HQ speech after %s during a pending reload', async action => {
    const harness = speechServer({ hq: true, delayedReload: true });
    await startChat(harness);
    await act(async () => { harness.completeChat(); });
    await waitFor(() => expect(harness.pendingReloads).toBeGreaterThan(0));
    if (action === 'navigate') {
      fireEvent.click(screen.getByRole('link', { name: /Another conversation/ }));
      await screen.findByText('Every conversation begins somewhere.');
    } else if (action === 'autoplay off') {
      fireEvent.click(screen.getByRole('link', { name: 'Settings' }));
      const autoplay = await screen.findByRole('switch', { name: 'Automatic audio playback' });
      expect(autoplay.getAttribute('aria-checked')).toBe('true');
      fireEvent.click(autoplay);
      await waitFor(() => expect(harness.preferences.autoplay).toBe(false));
      expect(autoplay.getAttribute('aria-checked')).toBe('false');
    } else {
      fireEvent.click(screen.getByRole('button', { name: /alice/ }));
      fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Sign out' }));
      await waitFor(() => expect(screen.queryByRole('button', { name: /alice/ })).toBeNull());
    }
    await act(async () => { await harness.releaseReload(); });
    await waitFor(() => expect(harness.speechRequests).toHaveLength(0));
    expect(harness.speechWatches).toBe(0);
  });
});
