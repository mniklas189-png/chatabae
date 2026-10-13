import type { components } from './generated/api-schema';
type Schemas = components['schemas'];
export type Language = Schemas['CharacterResponse']['language'];
export interface CharacterProfile {
  age: number | string; gender: string; appearance: string; personality: string;
  background: string; interests: string; communication_style: string;
  relationship: string; instructions: string;
}
export type Character = Omit<Schemas['CharacterResponse'], 'profile'> & { profile: CharacterProfile; example?: boolean; color?: string; tag?: string };
export type Conversation = Schemas['ConversationResponse'];
export type Asset = Schemas['AssetResponse'];
export type Message = Schemas['MessageResponse'];
export type Job = Schemas['JobResponse'];
export type Memory = Schemas['MemoryResponse'];
export type User = Schemas['UserResponse'];
export type TokenResponse = Schemas['TokenResponse'];
export interface Status { online?: boolean; models?: Record<string, unknown>; providers?: Record<string, unknown>; [key: string]: unknown }
export interface Preferences { theme: 'dark' | 'light'; autoplay: boolean; language: Language; voice: string; speed: number; volume: number }
export interface StreamEvent { id: number; event: string; data: Record<string, unknown> }
export interface Voice { id: string; name: string; language: string; gender?: string; engine?: string; available: boolean; reference_asset_id?: string }
