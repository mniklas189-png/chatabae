import type { Character, CharacterProfile, GenerationSettings } from './types';
import type { components } from './generated/api-schema';

export type CharacterDraft = Pick<Character, 'name' | 'description' | 'profile' | 'language' | 'voice' | 'visibility'>;
export const defaultGeneration: GenerationSettings = { temperature: 0.7, top_p: 0.8, max_tokens: 512 };
export function validateGeneration(value: GenerationSettings, invalid = 'Use temperature 0–2, top_p greater than 0 up to 1, and 32–1024 response tokens.') {
  if (!Number.isFinite(value.temperature) || value.temperature < 0 || value.temperature > 2 || !Number.isFinite(value.top_p) || value.top_p <= 0 || value.top_p > 1 || !Number.isInteger(value.max_tokens) || value.max_tokens < 32 || value.max_tokens > 1024) throw new Error(invalid);
  return { temperature: value.temperature, top_p: value.top_p, max_tokens: value.max_tokens } satisfies components['schemas']['Generation'];
}
export function generationDefaults(profile?: CharacterProfile): GenerationSettings {
  try { return profile?.generation_settings ? validateGeneration(profile.generation_settings) : { ...defaultGeneration }; } catch { return { ...defaultGeneration }; }
}
export function characterPayload(draft: CharacterDraft, invalidAge = 'Age must be a whole number between 0 and 10000.', invalidGeneration?: string) {
  const rawAge = String(draft.profile.age).trim();
  const age = rawAge === '' ? 18 : Number(rawAge);
  if (!Number.isInteger(age) || age < 0 || age > 10000) throw new Error(invalidAge);
  const profile = { ...draft.profile, age, fictional: true, generation_settings: validateGeneration(draft.profile.generation_settings || defaultGeneration, invalidGeneration) };
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
