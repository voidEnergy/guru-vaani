\# Guru-Vaani Hackathon Engineering Rules



1\. ZERO-KEY BOOT: The entire app MUST start via `docker compose up --build` with zero environment variables or API keys set. Never crash on missing keys. When no LLM/STT key is provided, run the built-in Local Deterministic Voice Engine and display a clear UI badge: "Cloud API key not set — running Local Voice Engine".

2\. NO LAZY STUBS: Implement full, deterministic Python parsing logic for Hinglish numerals, Indian fractions, self-corrections, self-talk filtering, bounds checking, undo stack, and bulk grace confirmation. Write unit tests proving every case passes.

3\. STRICT LOCAL PII VAULT: Student names and parent phone numbers must stay strictly in browser `localStorage`. Never send student names to backend endpoints—only send `roll\_no`, schema, and transcripts.

4\. DOCKER NETWORKING: Frontend Nginx must reverse-proxy `/api/\*` to `http://backend:8000` so browser requests use relative `/api/...` URLs with zero CORS or container-DNS bugs.

5\. MOBILE-FIRST UX: Design for a smartphone screen first (single-column, large thumb Mic button pinned at bottom) scaling cleanly to desktop split-screen.

