/** Split live deltas into bounded, complete sentences without re-reading old text. */
export class SentenceBuffer {
  private pending = '';
  receivedCharacters = 0;
  constructor(private maxCharacters = 500) { if (!Number.isInteger(maxCharacters) || maxCharacters < 2) throw new RangeError('Speech clips need at least two characters.'); }
  push(text: string): string[] { this.receivedCharacters += text.length; this.pending += text; return this.take(false); }
  finish(): string[] { return this.take(true); }
  private take(flush: boolean) {
    const output: string[] = [];
    while (this.pending.trim()) {
      let boundary = -1;
      const endings = /[.!?…]["'»”’\])]*(?=\s)/g;
      let match: RegExpExecArray | null;
      while ((match = endings.exec(this.pending))) {
        const end = match.index + match[0].length;
        if (/\b(?:dr|mr|mrs|ms|prof|sr|jr|bzw|usw)\.$|\b[A-Z]\.$|\bz\.B\.$|\bu\.a\.$/i.test(this.pending.slice(0, end))) continue;
        boundary = end; break;
      }
      if (boundary < 0 && this.pending.length <= this.maxCharacters && !flush) break;
      if (boundary < 0) boundary = this.pending.length;
      if (boundary > this.maxCharacters) { const space = this.pending.lastIndexOf(' ', this.maxCharacters); boundary = space > this.maxCharacters / 2 ? space : this.maxCharacters; }
      const before = this.pending.charCodeAt(boundary - 1), after = this.pending.charCodeAt(boundary);
      if (before >= 0xd800 && before <= 0xdbff && after >= 0xdc00 && after <= 0xdfff) boundary--;
      const sentence = this.pending.slice(0, boundary).trim(); this.pending = this.pending.slice(boundary).trimStart();
      if (sentence) output.push(sentence);
    }
    if (!this.pending.trim()) this.pending = '';
    return output;
  }
}

const speechStops = new Set<() => Promise<void>>();
const pendingSpeechStops = new Set<Promise<void>>();
export function registerSpeechStop(stop: () => Promise<void>) { speechStops.add(stop); return () => speechStops.delete(stop); }
export function trackSpeechStop(task: Promise<void>) { pendingSpeechStops.add(task); void task.finally(() => pendingSpeechStops.delete(task)).catch(() => {}); return task; }
export async function stopAllSpeech() { await Promise.allSettled([...speechStops].map(stop => stop()).concat([...pendingSpeechStops])); }

type SpeechTicket<T> = { scope: string; stopped: boolean; id?: string; creation?: Promise<T>; cancellation?: Promise<void>; detach: () => void };
/** Retain admission acknowledgements after Stop so committed speech jobs can still be cancelled. */
export class SpeechJobTracker<T extends { id: string }> {
  private creating = new Set<SpeechTicket<T>>(); private known = new Map<string, SpeechTicket<T>>();
  constructor(private cancel: (id: string) => Promise<void>) {}
  trackKnown(scope: string, value: T) { if (!this.known.has(value.id)) this.known.set(value.id, { scope, id: value.id, stopped: false, detach: () => {} }); }
  async create(scope: string, factory: () => Promise<T>, signal?: AbortSignal): Promise<T> {
    if (signal?.aborted) throw new DOMException('Stopped', 'AbortError');
    const ticket: SpeechTicket<T> = { scope, stopped: false, detach: () => {} };
    const aborted = () => { ticket.stopped = true; void this.cancelTicket(ticket); };
    signal?.addEventListener('abort', aborted, { once: true }); ticket.detach = () => signal?.removeEventListener('abort', aborted);
    ticket.creation = factory().then(async value => { ticket.id = value.id; this.known.set(value.id, ticket); if (ticket.stopped) { await this.cancelTicket(ticket); throw new DOMException('Stopped', 'AbortError'); } return value; });
    this.creating.add(ticket);
    try { return await ticket.creation; } finally { this.creating.delete(ticket); if (!ticket.id) ticket.detach(); }
  }
  complete(id: string) { const ticket = this.known.get(id); ticket?.detach(); this.known.delete(id); }
  private cancelTicket(ticket: SpeechTicket<T>): Promise<void> {
    if (!ticket.id) return Promise.resolve();
    if (!ticket.cancellation) ticket.cancellation = this.cancel(ticket.id).catch(() => {}).finally(() => this.complete(ticket.id!));
    return ticket.cancellation;
  }
  stop(scope?: string): Promise<void> {
    const tickets = [...new Set([...this.creating, ...this.known.values()])].filter(ticket => scope === undefined || ticket.scope === scope);
    for (const ticket of tickets) { ticket.stopped = true; void this.cancelTicket(ticket); }
    return trackSpeechStop((async () => { await Promise.allSettled(tickets.flatMap(ticket => ticket.creation ? [ticket.creation] : [])); await Promise.allSettled(tickets.map(ticket => this.cancelTicket(ticket))); })());
  }
}

export interface SpeechClip { url: string; licenseUrl?: string | null; release: () => void }
export interface SpeechQueueOptions {
  generate: (text: string, signal: AbortSignal) => Promise<SpeechClip>;
  play: (clip: SpeechClip, signal: AbortSignal) => Promise<void>;
  onError: (error: unknown) => void;
  onIdle?: () => void;
  maxPending?: number; maxJobs?: number; maxCharacters?: number;
}
/** One CPU speech job and one playing clip at a time, independently of the chat stream. */
export class SpeechQueue {
  private controller = new AbortController(); private pending: string[] = []; private draining = false; private stopped = false; private jobsStarted = 0;
  get signal() { return this.controller.signal; }
  constructor(private options: SpeechQueueOptions) {}
  enqueue(text: string): boolean {
    text = text.trim(); if (!text) return true;
    const maxCharacters = this.options.maxCharacters ?? 500;
    if (this.stopped || this.jobsStarted >= (this.options.maxJobs ?? 10) || text.length > maxCharacters) return false;
    const tail = this.pending.length - 1;
    if (tail >= 0 && this.pending[tail].length + text.length + 1 <= maxCharacters) { this.pending[tail] += ' ' + text; return true; }
    if (this.pending.length >= (this.options.maxPending ?? 6) || this.jobsStarted + this.pending.length >= (this.options.maxJobs ?? 10)) {
      const last = this.pending.length - 1;
      if (last >= 0 && this.pending[last].length + text.length + 1 <= maxCharacters) { this.pending[last] += ' ' + text; return true; }
      return false;
    }
    this.pending.push(text); void this.drain(); return true;
  }
  stop() { this.stopped = true; this.pending = []; this.controller.abort(); }
  private async drain() {
    if (this.draining || this.stopped) return;
    this.draining = true;
    try {
      while (this.pending.length && !this.stopped) {
        const text = this.pending.shift()!; this.jobsStarted++; let clip: SpeechClip | undefined;
        try { clip = await this.options.generate(text, this.signal); if (!this.signal.aborted) await this.options.play(clip, this.signal); }
        finally { clip?.release(); }
      }
    } catch (error) { if (!this.signal.aborted) { this.stop(); this.options.onError(error); } }
    finally { this.draining = false; this.options.onIdle?.(); }
  }
}
