import { describe, it, expect } from 'vitest';
import { characterPayload, speechPayload, imagePayload } from './profile';
import { examples } from './examples';

describe('backend payload boundaries', () => {
  it('uses the backend age default for a blank field and rejects fractional or out-of-range ages', () => {
    expect(characterPayload({ ...examples[0], profile: { ...examples[0].profile, age: '' } }).profile.age).toBe(18);
    for (const age of ['2.5', '-1', '10001', 'NaN']) expect(() => characterPayload({ ...examples[0], profile: { ...examples[0].profile, age } })).toThrow('whole number');
    expect(characterPayload({ ...examples[0], profile: { ...examples[0].profile, age: '10000' } }).profile.age).toBe(10000);
  });
  it('keeps voice requests within the backend speech text and speed limits', () => {
    const payload = speechPayload('a'.repeat(2200), 'piper:de', 'de', 2);
    expect(payload.text).toHaveLength(2000);
    expect(payload.speed).toBe(1.3);
    expect(speechPayload('hello', '', 'en', 0).speed).toBe(0.7);
  });
  it('sends reproducible image settings and rejects invalid seeds before mutation', () => {
    expect(imagePayload('A portrait', 'balanced', 1024, '').options).toEqual({ width: 1024, height: 1024, steps: 25, seed: -1, preset: 'balanced' });
    expect(imagePayload('A portrait', 'fast', 512, '4294967295').options.seed).toBe(4294967295);
    for (const seed of ['2.5', '-2', '4294967296']) expect(() => imagePayload('A portrait', 'fast', 512, seed)).toThrow('whole number');
  });
});
