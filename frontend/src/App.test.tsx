import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from './App';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { setTokens } from './api';
import { examples } from './examples';
import type { Asset, Character, Job, Message } from './types';

beforeEach(() => {
  setTokens(null);
  localStorage.clear(); sessionStorage.clear(); history.replaceState(null, '', '/');
  Element.prototype.scrollIntoView = vi.fn();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  if (!URL.createObjectURL) Object.defineProperty(URL, 'createObjectURL', { value: () => 'blob:test', writable: true, configurable: true });
  if (!URL.revokeObjectURL) Object.defineProperty(URL, 'revokeObjectURL', { value: () => {}, writable: true, configurable: true });
});
const body = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const token = { access_token: 'test-access', token_type: 'bearer', expires_in: 900, user: { id: 'test-user', username: 'alice' } };
const character: Character = { ...examples[0], id: 'character-1', name: 'Schema character', example: false, profile: { ...examples[0].profile, age: 25 }, voice: 'piper:en', language: 'en' };
const conversation = { id: 'conversation-1', character_id: character.id, title: 'A conversation', created_at: '2026-10-12T12:00:00Z', updated_at: '2026-10-12T12:00:00Z' };
const job = (id: string, kind: string): Job => ({ id, kind, status: 'queued', created_at: '2026-10-12T12:00:00Z', output: {}, error: null });
const completed = (output: unknown) => new Response('id: 1\nevent: completed\ndata: ' + JSON.stringify({ output }) + '\n\n', { headers: { 'Content-Type': 'text/event-stream' } });
function signedInResponse(url: string, characters: Character[] = [character], preferences = {}) {
  if (url.includes('/auth/refresh')) return body(token);
  if (url.endsWith('/status')) return body({ state: 'ready', online: true, instance_id: 'test' });
  if (url.endsWith('/characters')) return body(characters);
  if (url.endsWith('/conversations')) return body([conversation]);
  if (url.endsWith('/preferences')) return body(preferences);
  return body([]);
}
function anonymousServer() {
  return vi.fn(async (url: string) => url.includes('/auth/refresh') ? body({ detail: 'Not signed in' }, 401) : url.includes('/status') ? body({ state: 'running', instance_id: 'test' }) : body([]));
}
describe('character space', () => {
  it.each([{ online: false, state: 'ready' }, { online: true, state: 'unavailable' }, { state: 'draining' }])('keeps a HTTP 200 unavailable server offline (%j)', async status => {
    const fetcher = vi.fn(async (url: string) => url.endsWith('/status') ? body(status) : url.includes('/auth/refresh') ? body({ detail: 'Not signed in' }, 401) : body([]));
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter initialEntries={['/library']}><App/></MemoryRouter>);
    await screen.findByRole('button', { name: 'Server offline' });
    expect(screen.queryByRole('button', { name: 'Server online' })).toBeNull();
    expect(fetcher.mock.calls.some(call => String(call[0]).endsWith('/library'))).toBe(false);
  });
  it('filters the explicitly labeled starter collection without inventing conversations', async () => {
    vi.stubGlobal('fetch', anonymousServer());
    render(<MemoryRouter initialEntries={['/library']}><App/></MemoryRouter>);
    expect(screen.getByRole('heading', { name: 'Mira' })).toBeTruthy();
    fireEvent.change(screen.getByRole('textbox', { name: 'Search characters…' }), { target: { value: 'atlas' } });
    expect(screen.getByRole('heading', { name: 'Atlas' })).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Mira' })).toBeNull();
    expect(screen.getByRole('tab', { name: 'Starter collection' }).getAttribute('aria-selected')).toBe('true');
  });
  it('keeps offline examples readable and refuses copy rather than showing a fake success', async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter initialEntries={['/character/example-mira']}><App/></MemoryRouter>);
    await screen.findByRole('button', { name: 'Server offline' });
    fireEvent.click(screen.getByRole('button', { name: 'Make it yours' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('server is unavailable'));
    expect(fetcher.mock.calls.every(call => !String(call[0]).endsWith('/characters'))).toBe(true);
  });
  it('validates an empty manual profile before sending a mutation', async () => {
    const fetcher = anonymousServer(); vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter initialEntries={['/editor']}><App/></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: 'Save character' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Give your character a name.');
    expect(fetcher.mock.calls.every(call => !String(call[0]).endsWith('/characters'))).toBe(true);
  });
  it('requires the separate server sign-in and never displays a password field on Pages', async () => {
    vi.stubGlobal('fetch', anonymousServer());
    render(<MemoryRouter initialEntries={['/editor']}><App/></MemoryRouter>);
    await screen.findByRole('button', { name: 'Server online' });
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'New person' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Short description' }), { target: { value: 'A thoughtful companion' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save character' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Passwords are never entered/)).toBeTruthy();
    expect(document.querySelector('input[type="password"]')).toBeNull();
  });
  it('sends a numeric age accepted by the actual backend CharacterInput schema', async () => {
    let saved: Record<string, unknown> | null = null;
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes('/auth/refresh')) return body(token);
      if (url.endsWith('/status')) return body({ state: 'ready', online: true, instance_id: 'test' });
      if (url.endsWith('/preferences')) return body({});
      if (url.endsWith('/characters') && init?.method === 'POST') {
        const request = JSON.parse(String(init.body));
        const candidates = [resolve(process.cwd(), '../.venv/Scripts/python.exe'), resolve(process.cwd(), '../.venv/bin/python')];
        const python = process.env.CHATABAE_TEST_PYTHON || candidates.find(existsSync) || 'python';
        const result = spawnSync(python, ['-c', 'import json,sys; from chatabae.schemas import CharacterInput; model=CharacterInput.model_validate(json.load(sys.stdin)); print(model.model_dump_json())'], { input: JSON.stringify(request), encoding: 'utf8', env: { ...process.env, PYTHONPATH: resolve(process.cwd(), '../backend') } });
        expect(result.status, result.stderr).toBe(0);
        saved = { ...JSON.parse(result.stdout), id: 'saved-character', revision: 1, moderation_status: 'pending', avatar_asset_id: null };
        return body(saved, 201);
      }
      if (url.endsWith('/characters')) return body(saved ? [saved] : []);
      return body([]);
    });
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter initialEntries={['/editor']}><App/></MemoryRouter>);
    await screen.findByRole('button', { name: 'Server online' });
    await screen.findByRole('button', { name: /alice/ });
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Numeric profile' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Short description' }), { target: { value: 'A schema-checked fictional character.' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Age' }), { target: { value: '25' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save character' }));
    await waitFor(() => { const error = screen.queryByRole('alert'); if (error) throw new Error(error.textContent || 'Save failed'); expect(saved).not.toBeNull(); }, { timeout: 10000 });
    expect((saved as unknown as { profile: { age: number } }).profile.age).toBe(25);
  }, 20000);
  it('generates speech for a new assistant response with the selected speed, without reading old history', async () => {
    const oldMessage: Message = { id: 'old', conversation_id: conversation.id, role: 'assistant', content: 'A saved answer.', created_at: conversation.created_at, edited_at: null, assets: [] };
    const reply: Message = { ...oldMessage, id: 'new', content: 'A new answer.' };
    const userMessage: Message = { ...oldMessage, id: 'sent', role: 'user', content: 'Hello' };
    const audio: Asset = { id: 'new-audio', conversation_id: conversation.id, kind: 'audio', mime_type: 'audio/wav', size_bytes: 100, created_at: conversation.created_at, url: '/api/v1/assets/new-audio/content' };
    let sent = false, spoken = false;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes('/jobs/chat-job/events')) return completed({ message: reply });
      if (url.includes('/jobs/speech-job/events')) return completed({ assets: [audio] });
      if (url.endsWith('/messages') && init?.method === 'POST') { sent = true; return body({ message: userMessage, job: job('chat-job', 'chat') }, 202); }
      if (url.endsWith('/messages')) return body(sent ? [oldMessage, userMessage, reply] : [oldMessage]);
      if (url.endsWith('/speech')) {
        expect(JSON.parse(String(init?.body))).toEqual({ text: reply.content, voice: 'piper:en', language: 'en', speed: 1.2 });
        spoken = true; return body(job('speech-job', 'speech'), 202);
      }
      if (url.endsWith('/assets')) return body(spoken ? [audio] : []);
      if (url.endsWith('/content')) return new Response(new Blob(['audio'], { type: 'audio/wav' }));
      return signedInResponse(url, [character], { autoplay: true, speed: 1.2, volume: 0.5 });
    }));
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test-audio'); vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    render(<MemoryRouter initialEntries={['/conversations/' + conversation.id]}><App/></MemoryRouter>);
    await screen.findByText('A saved answer.');
    expect(spoken).toBe(false);
    fireEvent.change(screen.getByRole('textbox', { name: 'Write a message…' }), { target: { value: 'Hello' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
    await waitFor(() => expect(spoken).toBe(true));
    await waitFor(() => { const audioElement = document.querySelector('audio'); expect(audioElement?.getAttribute('autoplay')).not.toBeNull(); expect(audioElement?.volume).toBe(0.5); });
  });
  it('requires the exact username before deleting the account and clears private browser state', async () => {
    let deleted = false;
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/me') && init?.method === 'DELETE') { deleted = true; return body({ ok: true }); }
      return signedInResponse(url);
    });
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter initialEntries={['/settings']}><App/></MemoryRouter>);
    await screen.findByRole('button', { name: /alice/ });
    sessionStorage.setItem('chatabae.job.old', JSON.stringify({ userId: token.user.id, jobId: 'private-job' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete my account' }));
    const dialog = await screen.findByRole('dialog'); const deleteButton = within(dialog).getByRole('button', { name: 'Delete my account' });
    expect((deleteButton as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Your username' }), { target: { value: 'other' } });
    fireEvent.click(deleteButton); expect(deleted).toBe(false);
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Your username' }), { target: { value: 'alice' } });
    fireEvent.click(deleteButton);
    await waitFor(() => expect(deleted).toBe(true));
    await screen.findByText('Your account and private data have been deleted.');
    expect(localStorage.getItem('chatabae.returning')).toBeNull(); expect(sessionStorage.getItem('chatabae.job.old')).toBeNull();
    expect(screen.queryByRole('button', { name: /alice/ })).toBeNull();
  });
  it('applies a field improvement while preserving other unsaved profile edits', async () => {
    let current = character, requested: unknown;
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/improve')) { requested = JSON.parse(String(init?.body)); return body(job('improve-job', 'profile_improve'), 202); }
      if (url.includes('/jobs/improve-job/events')) { current = { ...character, revision: 2, profile: { ...character.profile, personality: 'A revised personality.' } }; return completed({ character: current }); }
      return signedInResponse(url, [current]);
    });
    vi.stubGlobal('fetch', fetcher);
    render(<MemoryRouter initialEntries={['/editor/' + character.id]}><App/></MemoryRouter>);
    await waitFor(() => expect((screen.getByRole('textbox', { name: 'Name' }) as HTMLInputElement).value).toBe(character.name));
    fireEvent.change(screen.getByRole('textbox', { name: 'Background' }), { target: { value: 'An unsaved background.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Improve with AI: Personality' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Describe your character' }), { target: { value: 'Make them calmer.' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Improve with AI' }));
    await waitFor(() => expect((screen.getByRole('textbox', { name: 'Personality' }) as HTMLTextAreaElement).value).toBe('A revised personality.'));
    expect(requested).toEqual({ field: 'personality', idea: 'Make them calmer.' });
    expect((screen.getByRole('textbox', { name: 'Background' }) as HTMLTextAreaElement).value).toBe('An unsaved background.');
  });
  it('uploads a private WAV reference only after explicit voice permission and stores only its voice ID', async () => {
    const reference = { id: 'xtts:ref:private-reference', name: 'My private voice', engine: 'xtts', language: 'en', available: true, reference_asset_id: 'private-reference' };
    const catalog = [{ id: 'xtts:stock', name: 'Stock voice', engine: 'xtts', language: 'en', available: true }];
    let uploaded = false, chosenVoice = '';
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/voices')) return body(uploaded ? [...catalog, reference] : catalog);
      if (url.endsWith('/voice-references')) {
        const data = init?.body as FormData;
        expect(data.get('consent')).toBe('true'); expect((data.get('file') as File).name).toBe('authorized.wav');
        expect(new Headers(init?.headers).has('Content-Type')).toBe(false);
        uploaded = true; return body(reference, 201);
      }
      if (url.endsWith('/preferences') && init?.method === 'PUT') { chosenVoice = JSON.parse(String(init.body)).voice; return body({}); }
      return signedInResponse(url);
    }));
    render(<MemoryRouter initialEntries={['/settings']}><App/></MemoryRouter>);
    await screen.findByRole('button', { name: /alice/ });
    await waitFor(() => expect((screen.getByLabelText('Upload voice reference') as HTMLInputElement).disabled).toBe(false));
    const wav = new Uint8Array(44 + 16000 * 2 * 6); const view = new DataView(wav.buffer);
    for (const [offset, value] of [[0, 'RIFF'], [8, 'WAVE'], [12, 'fmt '], [36, 'data']] as const) wav.set(new TextEncoder().encode(value), offset);
    view.setUint32(4, wav.length - 8, true); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true); view.setUint32(40, wav.length - 44, true);
    fireEvent.change(screen.getByLabelText('Upload voice reference'), { target: { files: [new File([wav], 'authorized.wav', { type: 'audio/wav' })] } });
    const uploadButton = screen.getByRole('button', { name: 'Upload voice reference' });
    expect((uploadButton as HTMLButtonElement).disabled).toBe(true); fireEvent.click(uploadButton); expect(uploaded).toBe(false);
    fireEvent.click(screen.getByRole('checkbox', { name: 'I have permission to use this voice.' })); fireEvent.click(uploadButton);
    await waitFor(() => expect(chosenVoice).toBe(reference.id));
    expect(await screen.findByText('Your private voice is ready to select.')).toBeTruthy();
    expect(document.body.textContent).not.toContain('C:\\');
  });
  it('shows saved private memories on the character profile', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/memories')) return body([{ id: 'memory-1', character_id: character.id, conversation_id: conversation.id, content: 'Remember our favorite café.', enabled: true, automatic: false, created_at: conversation.created_at }]);
      return signedInResponse(url);
    }));
    render(<MemoryRouter initialEntries={['/character/' + character.id]}><App/></MemoryRouter>);
    await screen.findByRole('heading', { name: character.name });
    fireEvent.click(screen.getByRole('button', { name: 'Memories' }));
    expect(await screen.findByText('Remember our favorite café.')).toBeTruthy();
    expect(screen.getByRole('link', { name: /A conversation.*Enabled/ }).getAttribute('href')).toBe('/conversations/' + conversation.id);
  });
  it('sends the selected image quality, square size and seed and renders the assistant image asset', async () => {
    const image: Asset = { id: 'image-result', kind: 'image', mime_type: 'image/png', size_bytes: 100, created_at: conversation.created_at, url: '/api/v1/assets/image-result/content', character_id: character.id, conversation_id: conversation.id, metadata: { seed: 123, preset: 'fast', steps: 15, width: 512, height: 512, reference: false } };
    const reply: Message = { id: 'image-message', conversation_id: conversation.id, role: 'assistant', content: '', assets: [image], created_at: conversation.created_at, edited_at: null };
    let requested: unknown, generated = false;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/images')) { requested = JSON.parse(String(init?.body)); return body(job('image-job', 'image'), 202); }
      if (url.includes('/jobs/image-job/events')) { generated = true; return completed({ message: reply, assets: [image] }); }
      if (url.endsWith('/messages')) return body(generated ? [reply] : []);
      if (url.endsWith('/assets')) return body(generated ? [image] : []);
      if (url.endsWith('/content')) return new Response(new Blob(['image'], { type: 'image/png' }));
      return signedInResponse(url);
    }));
    render(<MemoryRouter initialEntries={['/conversations/' + conversation.id]}><App/></MemoryRouter>);
    await screen.findByRole('button', { name: 'Create image' });
    await screen.findByRole('button', { name: /alice/ });
    fireEvent.click(screen.getByRole('button', { name: 'Create image' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByRole('textbox', { name: 'Describe the image you’d like to create' }), { target: { value: 'A quiet café.' } });
    fireEvent.change(within(dialog).getByRole('combobox', { name: 'Image quality' }), { target: { value: 'fast' } });
    fireEvent.change(within(dialog).getByRole('combobox', { name: 'Image format' }), { target: { value: '512' } });
    fireEvent.change(within(dialog).getByRole('spinbutton', { name: 'Seed (optional)' }), { target: { value: '123' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Create image' }));
    await waitFor(() => expect(requested).toEqual({ prompt: 'A quiet café.', options: { width: 512, height: 512, steps: 15, seed: 123, preset: 'fast' } }));
    expect(await screen.findByRole('img', { name: 'Image' })).toBeTruthy();
    expect(screen.getAllByRole('img', { name: 'Image' })).toHaveLength(1);
    expect(screen.getByText('123')).toBeTruthy();
    expect(screen.getByText('Fast · 15 steps · 512 × 512')).toBeTruthy();
  });
  it('locks image format to the stable character reference portrait', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/content') ? new Response(new Blob(['portrait'], { type: 'image/png' })) : signedInResponse(url, [{ ...character, avatar_asset_id: 'canonical-avatar' }])));
    render(<MemoryRouter initialEntries={['/conversations/' + conversation.id]}><App/></MemoryRouter>);
    await screen.findByRole('button', { name: 'Create image' });
    fireEvent.click(screen.getByRole('button', { name: 'Create image' }));
    const dialog = await screen.findByRole('dialog');
    expect((within(dialog).getByRole('combobox', { name: 'Image format' }) as HTMLSelectElement).disabled).toBe(true);
    expect(within(dialog).getByText(/reference portrait determines/)).toBeTruthy();
  });
  it('links the output license beside audio and stops playback at the beginning', async () => {
    const license = 'https://coqui.ai/cpml';
    const audio: Asset = { id: 'licensed-audio', kind: 'audio', mime_type: 'audio/wav', size_bytes: 100, created_at: conversation.created_at, url: '/api/v1/assets/licensed-audio/content', license_url: license };
    vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/assets') ? body([audio]) : url.endsWith('/content') ? new Response(new Blob(['audio'], { type: 'audio/wav' })) : signedInResponse(url)));
    const pause = vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
    render(<MemoryRouter initialEntries={['/gallery']}><App/></MemoryRouter>);
    const licenseLink = await screen.findByRole('link', { name: 'License for this output' });
    expect(licenseLink.getAttribute('href')).toBe(license);
    expect(licenseLink.getAttribute('rel')).toContain('license');
    const element = document.querySelector('audio')!; element.currentTime = 7;
    fireEvent.click(screen.getByRole('button', { name: 'Stop audio' }));
    expect(pause).toHaveBeenCalledOnce(); expect(element.currentTime).toBe(0);
    pause.mockRestore();
  });
  it('immediately shows a lost response connection and restores online status after a healthy poll', async () => {
    let interrupted = false;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/messages') && init?.method === 'POST') return body({ message: { id: 'sent', conversation_id: conversation.id, role: 'user', content: 'Hello', created_at: conversation.created_at, edited_at: null, assets: [] }, job: job('lost-job', 'chat') }, 202);
      if (url.includes('/jobs/lost-job/events')) { interrupted = true; throw new TypeError('Network disconnected'); }
      if (url.endsWith('/jobs/lost-job')) return body({ ...job('lost-job', 'chat'), status: 'completed' });
      return signedInResponse(url);
    }));
    render(<MemoryRouter initialEntries={['/conversations/' + conversation.id]}><App/></MemoryRouter>);
    await screen.findByRole('button', { name: 'Server online' });
    await screen.findByRole('textbox', { name: 'Write a message…' });
    fireEvent.change(screen.getByRole('textbox', { name: 'Write a message…' }), { target: { value: 'Hello' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
    await screen.findByText('Connection interrupted. The saved response will resume when the server reconnects.');
    expect(interrupted).toBe(true);
    const offline = screen.getByRole('button', { name: 'Server offline' });
    expect((screen.getByRole('textbox', { name: 'Write a message…' }) as HTMLTextAreaElement).disabled).toBe(true);
    fireEvent.click(offline);
    await screen.findByRole('button', { name: 'Server online' });
  });
});
