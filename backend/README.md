# Chatabae backend

Use `start.bat` from the repository root for normal operation. The launcher loads the saved private configuration and owns its child processes through a Windows Job Object. Running the backend directly is an advanced development option, requiring explicit data/config paths:

```powershell
$env:PYTHONPATH = 'backend'
$env:CHATABAE_CONFIG = 'C:\path\to\private\config.json'
$env:CHATABAE_DATA_DIR = 'C:\path\to\private\Chatabae'
.venv\Scripts\python.exe -m chatabae --host 127.0.0.1 --port 7810 --admin-port 7811
```

The single process owns two separate FastAPI listeners. Only port 7810 is forwarded by Funnel. Port 7811 requires the launcher-generated `CHATABAE_CONTROL_TOKEN`; admin routes never exist on the public application. Config comes from the external `CHATABAE_CONFIG` JSON and `CHATABAE_DATA_DIR`, `CHATABAE_MODE`, `CHATABAE_INSTANCE_ID`, `CHATABAE_CONTROL_TOKEN`. Default Windows data lives in `%USERPROFILE%\AppData\Local\Chatabae`, independent of virtualized app environment variables.

Dependencies are pinned in `requirements.txt`. SQLite is migrated through Alembic on startup, with WAL, foreign keys and bounded busy timeouts. There is no production AI mock: missing local model files produce unavailable capabilities and failed jobs. Tests explicitly inject providers and never launch models.

Password forms and recovery run on backend HTTPS. The Pages client uses an exact redirect URI, PKCE S256 and one-time 60-second codes. Access tokens stay in browser memory; refresh cookies use Secure, HttpOnly, SameSite=None and Partitioned over HTTPS. Refresh tokens never appear in JSON. If partitioned cookies are unavailable, top-level authorization uses the first-party backend login cookie. Registration shows eight recovery codes once; only their SHA-256 digests are stored. A reset consumes a code and revokes all previous sessions.

`/api/v1` provides characters, public library, favorites, conversations, messages, memories, private assets, reports, search, voices, settings/preferences and persistent jobs. `GET /jobs/{id}/events?after=<event-id>` uses fetch/SSE with Bearer authentication and persisted replay IDs. Streams revalidate expiry, revocation and bans, with three simultaneous streams per account. GPU jobs are serialized fairly; CPU TTS uses a separate worker. Public profile changes remain pending until local moderation passes, and only the approved snapshot/avatar is served publicly. Missing moderation holds publication. Online images require documented usage-right evidence; XTTS is separately gated.

## Backups and restore

Daily snapshots retain seven versions; weekly snapshots retain four. They contain a consistent SQLite backup plus exactly its referenced media and a SHA-256 manifest. Model files, tools and secrets are not copied. Keep snapshots private: they contain account password hashes and user chats. After 30 seconds of uptime the scheduler checks for an overdue snapshot, then hourly. Failed snapshots leave previous versions available.

```powershell
.\backup.bat create
.\backup.bat verify 'C:\path\to\snapshot'
# First stop Chatabae. Restore refuses a live backend PID.
.\backup.bat restore 'C:\path\to\snapshot'
```

Restore verifies the entire manifest and database, preserves the previous database/media under `pre-restore` names, retains models/tools/backups and revokes sessions/codes. Keep the preserved previous data until the restoration has been checked. Start the launcher and sign in again. No backup is sent to a cloud service.

The backup wrapper selects the same saved private data directory as the launcher, including installations created in the Codex environment. Avoid invoking the module with implicit paths against an existing installation.

Image requests select `fast` (15 steps) or `balanced` (25 steps). They store their effective random seed and actual saved dimensions, and use the character's canonical avatar as the reference when available. Standalone formats are square 512 or 1024 pixels. Automatic profile avatars share the image quota. Private XTTS output includes its CPML license URL in asset metadata and an HTTP `Link` header. Hardware status and active sessions are visible only through local control.

Tests: `cd backend; ..\.venv\Scripts\python.exe -m pytest -q`.
