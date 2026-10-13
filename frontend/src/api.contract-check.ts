import { endpoint } from './api';
import type { TokenResponse } from './types';

// Compile-only assertions: a schema drift must fail typecheck before a deployment.
export function assertGeneratedApiContract() {
  const renewed: Promise<TokenResponse> = endpoint('/api/v1/auth/refresh').post({});
  // @ts-expect-error Every exchange requires the PKCE verifier and redirect URI.
  endpoint('/api/v1/auth/exchange').post({ code: 'one-time-code' });
  // @ts-expect-error Status is a GET endpoint, not a POST endpoint.
  endpoint('/api/v1/status').post({});
  // @ts-expect-error Unknown routes cannot be requested through the generated adapter.
  endpoint('/api/v1/not-a-real-route');
  // @ts-expect-error Speech speed is numeric in the backend schema.
  endpoint('/api/v1/tts-jobs').post({ text: 'Hello', speed: 'fast' });
  return renewed;
}
