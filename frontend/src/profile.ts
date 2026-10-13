import type { Character } from './types';
import type { components } from './generated/api-schema';

export type CharacterDraft = Pick<Character, 'name' | 'description' | 'profile' | 'language' | 'voice' | 'visibility'>;
export function characterPayload(draft: CharacterDraft, invalidAge = 'Age must be a whole number between 0 and 10000.') {
  const rawAge = String(draft.profile.age).trim();
  const age = rawAge === '' ? 18 : Number(rawAge);
  if (!Number.isInteger(age) || age < 0 || age > 10000) throw new Error(invalidAge);
  const profile = { ...draft.profile, age, fictional: true };
  return { name: draft.name.trim(), description: draft.description.trim(), profile, language: draft.language, voice: draft.voice, visibility: draft.visibility } satisfies components['schemas']['CharacterInput'];
}
export function speechPayload(text: string, voice: string, language: 'de' | 'en', speed: number) {
  return { text: text.slice(0, 2000), voice: voice || undefined, language, speed: Math.min(1.3, Math.max(0.7, speed)) } satisfies components['schemas']['SpeechRequest'];
}
export function imagePayload(prompt: string, preset: 'fast' | 'balanced', size: 512 | 1024, seedText: string, invalidSeed = 'Seed must be a whole number from -1 to 4294967295.') {
  const seed = seedText.trim() === '' ? -1 : Number(seedText);
  if (!Number.isInteger(seed) || seed < -1 || seed > 4294967295) throw new Error(invalidSeed);
  return { prompt, options: { width: size, height: size, steps: preset === 'fast' ? 15 : 25, seed, preset } } satisfies components['schemas']['ImageRequest'];
}
