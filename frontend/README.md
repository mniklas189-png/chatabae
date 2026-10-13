# chatabae frontend

React, TypeScript, Vite and hash routing. The frontend is a static GitHub Pages app; account data, model jobs and media are served by the local backend.

Backend OpenAPI is the contract source. Run npm run generate:api after exporting backend/openapi.json; pinned openapi-typescript generates src/generated/api-schema.ts. Core response types come from this file, while endpoint() validates known paths, available methods, and JSON request bodies and infers schema response types. Editor and speech serialization satisfy generated input schemas. api.contract-check.ts contains compile-only negative assertions that fail if these guarantees drift.

Use Node.js 24. Run npm ci, npm run dev, npm run typecheck, npm test and npm run build. Build output is dist/. The schema contract test needs Python 3.12 and Pydantic 2; it uses the repository .venv if present, otherwise python on PATH (or CHATABAE_TEST_PYTHON).

VITE_API_BASE_URL is a public origin, such as your fixed Tailscale Funnel HTTPS URL. Development defaults to http://127.0.0.1:7810. Production with no configured URL performs no backend requests. VITE_BASE_PATH defaults to /chatabae/ for production and / for development.

The backend FRONTEND_URL must match the exact page root, for example https://mniklas189-png.github.io/chatabae/. PKCE returns its one-use code to this root via query parameters; the app removes them, exchanges the code, and restores its hash route. Passwords are entered only on backend HTML. Access tokens stay in memory; persistent refresh uses an HttpOnly partitioned cookie and first-party reauthorization fallback.

Tests cover offline behavior, editor validation against the actual backend CharacterInput schema, separate-origin sign-in, PKCE state, cookie-only refresh, unconfigured production, SSE chunk boundaries and event replay, automatic speech for new answers, account deletion confirmation, preservation of unsaved fields during AI improvement, and consent before private WAV reference upload.

Profile age is an integer from 0 to 10000 (blank defaults to 18). Form limits match the API: name 80, description 1000, character idea 4000, image prompt and memory 2000, message 12000 characters, and 1024 maximum response tokens. Image quality uses Fast 15 or Balanced 25 steps with an optional seed (-1/blank means fresh); without a reference, square 512/1024 sizes are available. A stable character avatar locks the format to its portrait proportions scaled to about 1 MP. Generated media displays the effective saved seed, quality and dimensions. Speech uses up to 2000 characters at speed 0.7–1.3; volume is a playback preference from 0–1. Private references need an enabled XTTS model and a permitted 6–30 second, 16-bit PCM WAV at 8–48 kHz. Browsers may require an initial play gesture before allowing automatic audio.
