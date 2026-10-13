import { describe, it, expect } from 'vitest';
import { characterPayload, defaultGeneration, generationDefaults, validateGeneration, speechPayload, imagePayload } from './profile';
import { examples } from './examples';
import type { CharacterProfile, GenerationSettings } from './types';

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

describe('saved character generation options', () => {
  const defaults = { temperature: 0.7, top_p: 0.8, max_tokens: 512 };
  const invalidOptions: [string, Partial<Record<keyof GenerationSettings, unknown>>][] = [
    ['negative temperature', { temperature: -0.01 }],
    ['temperature above two', { temperature: 2.01 }],
    ['NaN temperature', { temperature: Number.NaN }],
    ['infinite temperature', { temperature: Number.POSITIVE_INFINITY }],
    ['zero top_p', { top_p: 0 }],
    ['negative top_p', { top_p: -0.01 }],
    ['top_p above one', { top_p: 1.01 }],
    ['NaN top_p', { top_p: Number.NaN }],
    ['infinite top_p', { top_p: Number.POSITIVE_INFINITY }],
    ['token count below 32', { max_tokens: 31 }],
    ['token count above 1024', { max_tokens: 1025 }],
    ['fractional token count', { max_tokens: 128.5 }],
    ['infinite token count', { max_tokens: Number.POSITIVE_INFINITY }],
    ['NaN token count', { max_tokens: Number.NaN }],
    ['legacy token count string', { max_tokens: '128' }],
  ];

  it.each([
    { temperature: 0, top_p: 0.0001, max_tokens: 32 },
    { temperature: 2, top_p: 1, max_tokens: 1024 },
  ])('accepts valid boundary settings without silently changing them: %j', options => {
    expect(validateGeneration(options)).toEqual(options);
  });

  it.each(invalidOptions)('rejects %s before creating a backend payload', (_, invalid) => {
    const settings = { ...defaults, ...invalid } as GenerationSettings;
    const profile = { ...examples[0].profile, generation_settings: settings };
    expect(() => validateGeneration(settings, 'Invalid saved response options')).toThrow('Invalid saved response options');
    expect(() => characterPayload({ ...examples[0], profile }, undefined, 'Invalid saved response options')).toThrow('Invalid saved response options');
  });

  it('recovers safe defaults from missing, partial or corrupt legacy settings', () => {
    expect(generationDefaults()).toEqual(defaults);
    expect(generationDefaults(examples[0].profile)).toEqual(defaults);
    const corrupt = [null, {}, { temperature: 0.25 }, { temperature: '0.25', top_p: 0.8, max_tokens: 128 }, ...invalidOptions.map(([, invalid]) => ({ ...defaults, ...invalid }))];
    for (const generation_settings of corrupt) {
      const profile = { ...examples[0].profile, generation_settings } as unknown as CharacterProfile;
      expect(generationDefaults(profile)).toEqual(defaults);
    }
  });

  it('keeps recovered defaults independent between characters and preserves valid saved options', () => {
    const first = generationDefaults();
    first.temperature = 2;
    first.max_tokens = 1024;
    expect(generationDefaults()).toEqual(defaults);
    expect(defaultGeneration).toEqual(defaults);
    const saved = { temperature: 0.25, top_p: 0.95, max_tokens: 256 };
    const profile = { ...examples[0].profile, generation_settings: saved };
    const recovered = generationDefaults(profile);
    expect(recovered).toEqual(saved);
    recovered.max_tokens = 64;
    expect(profile.generation_settings.max_tokens).toBe(256);
  });

  it('persists only the three supported generation fields while retaining age and persona', () => {
    const saved = { temperature: 0.25, top_p: 0.95, max_tokens: 256, private_extra: 'Never send this as a generation parameter' };
    const profile = Object.freeze({ ...examples[0].profile, age: '42', personality: 'Thoughtful botanist', background: 'Studies mountain plants', relationship: 'An old fictional friend', instructions: 'Speak quietly and preserve the character history.', generation_settings: Object.freeze(saved) });
    const draft = Object.freeze({ ...examples[0], name: '  Botanist  ', description: '  Mountain stories  ', profile });
    const payload = characterPayload(draft);
    expect(payload.profile.generation_settings).toEqual({ temperature: 0.25, top_p: 0.95, max_tokens: 256 });
    expect(payload.profile).toMatchObject({ age: 42, gender: profile.gender, appearance: profile.appearance, personality: profile.personality, background: profile.background, interests: profile.interests, communication_style: profile.communication_style, relationship: profile.relationship, instructions: profile.instructions });
    expect(payload).toMatchObject({ name: 'Botanist', description: 'Mountain stories', language: draft.language, voice: draft.voice, visibility: draft.visibility });
    expect(payload).not.toHaveProperty('id');
    expect(profile.age).toBe('42');
    expect(profile.generation_settings).toHaveProperty('private_extra');
  });

  it('includes safe generation defaults when saving a character without older stored options', () => {
    const payload = characterPayload(examples[0]);
    expect(payload.profile.generation_settings).toEqual(defaults);
    expect(payload.profile.personality).toBe(examples[0].profile.personality);
    payload.profile.generation_settings.temperature = 2;
    expect(characterPayload(examples[0]).profile.generation_settings).toEqual(defaults);
  });
});
