import { describe, it, expect, vi } from 'vitest';
import { SentenceBuffer, SpeechQueue, SpeechJobTracker, registerSpeechStop, stopAllSpeech } from './speech';

const turn = () => new Promise(resolve => setTimeout(resolve, 0));
describe('streaming sentence speech', () => {
  it('waits for sentence boundaries across deltas and preserves abbreviations and final tails', () => {
    const text = new SentenceBuffer();
    expect(text.push('Hello')).toEqual([]);
    expect(text.push('. Dr. Mira is here. ')).toEqual(['Hello.', 'Dr. Mira is here.']);
    expect(text.push('One final thought')).toEqual([]);
    expect(text.finish()).toEqual(['One final thought']); expect(text.finish()).toEqual([]);
  });
  it('bounds punctuation-free clips rather than accumulating unlimited text', () => {
    const text = new SentenceBuffer(50); const chunks = [...text.push('a'.repeat(140)), ...text.finish()];
    expect(chunks.map(chunk => chunk.length)).toEqual([50, 50, 40]);
  });
  it('never splits a Unicode surrogate pair at the clip boundary', () => {
    const text = new SentenceBuffer(500); const original = 'a'.repeat(499) + '😀'; const clips = [...text.push(original), ...text.finish()];
    expect(clips.join('')).toBe(original); expect(clips.every(clip => clip.length <= 500)).toBe(true);
    expect(clips.every(clip => [...clip].every(point => point.length === 2 || point.charCodeAt(0) < 0xd800 || point.charCodeAt(0) > 0xdfff))).toBe(true);
  });
  it('generates and plays in order, releases clips, and never overlaps jobs or playback', async () => {
    const events: string[] = []; let finishFirst: (() => void) | undefined;
    const queue = new SpeechQueue({ generate: async text => { events.push('generate:' + text); return { url: text, release: () => events.push('release:' + text) }; }, play: async clip => { events.push('play:' + clip.url); if (clip.url === 'First.') await new Promise<void>(resolve => { finishFirst = resolve; }); }, onError: vi.fn() });
    queue.enqueue('First.'); queue.enqueue('Second.'); await turn();
    expect(events).toEqual(['generate:First.', 'play:First.']);
    finishFirst!(); await turn();
    expect(events).toEqual(['generate:First.', 'play:First.', 'release:First.', 'generate:Second.', 'play:Second.', 'release:Second.']); queue.stop();
  });
  it('aborts only its own queue, releases the current clip, and never starts queued speech after stop', async () => {
    const chat = new AbortController(); const release = vi.fn(); const generate = vi.fn(async () => ({ url: 'clip', release }));
    const queue = new SpeechQueue({ generate, play: (_clip, signal) => new Promise<void>((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Stopped', 'AbortError')), { once: true })), onError: vi.fn() });
    queue.enqueue('First.'); queue.enqueue('Second.'); await turn(); queue.stop(); await turn();
    expect(queue.signal.aborted).toBe(true); expect(chat.signal.aborted).toBe(false); expect(generate).toHaveBeenCalledOnce(); expect(release).toHaveBeenCalledOnce(); expect(queue.enqueue('More.')).toBe(false);
  });
  it('bounds pending text and total jobs, and stops without retrying a quota failure', async () => {
    const error = Object.assign(new Error('Speech quota reached'), { status: 429 }); const onError = vi.fn(); const generate = vi.fn().mockRejectedValue(error);
    const queue = new SpeechQueue({ generate, play: vi.fn(), onError, maxPending: 1, maxJobs: 2, maxCharacters: 10 });
    expect(queue.enqueue('First.')).toBe(true); expect(queue.enqueue('Second.')).toBe(true); expect(queue.enqueue('Too long.')).toBe(false);
    await turn(); expect(generate).toHaveBeenCalledOnce(); expect(onError).toHaveBeenCalledWith(error); expect(queue.enqueue('Again.')).toBe(false);
  });
  it('waits for a speech creation acknowledgement after Stop and cancels its committed job before logout', async () => {
    let acknowledge: ((job: { id: string }) => void) | undefined, cancelled: (() => void) | undefined;
    const cancel = vi.fn(() => new Promise<void>(resolve => { cancelled = resolve; })); const tracker = new SpeechJobTracker<{ id: string }>(cancel); const signal = new AbortController();
    const unregister = registerSpeechStop(() => tracker.stop());
    const creation = tracker.create('user:conversation', () => new Promise<{ id: string }>(resolve => { acknowledge = resolve; }), signal.signal);
    const abortedCreation = expect(creation).rejects.toMatchObject({ name: 'AbortError' });
    signal.abort(); let finished = false; const stopping = stopAllSpeech().then(() => { finished = true; }); await turn();
    expect(finished).toBe(false); acknowledge!({ id: 'committed-job' }); await turn();
    expect(cancel).toHaveBeenCalledExactlyOnceWith('committed-job'); expect(finished).toBe(false);
    cancelled!(); await stopping; await abortedCreation; expect(finished).toBe(true); unregister();
  });
  it('cancels an adopted resumed speech job in its owning conversation only', async () => {
    const cancel = vi.fn().mockResolvedValue(undefined); const tracker = new SpeechJobTracker<{ id: string }>(cancel);
    tracker.trackKnown('first', { id: 'resumed-speech' }); tracker.trackKnown('second', { id: 'other-speech' });
    await tracker.stop('first'); expect(cancel).toHaveBeenCalledExactlyOnceWith('resumed-speech');
    tracker.complete('other-speech'); await tracker.stop(); expect(cancel).toHaveBeenCalledOnce();
  });
});
