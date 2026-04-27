# Source Policy

This project should remain transparent and conservative about collection.

Accepted sources:

- Public official pages
- Public news and media pages
- RSS/Atom feeds
- Public pages that permit ordinary browser access and reasonable automated fetching

Rejected sources:

- Login-only pages
- CAPTCHA-gated pages
- Paywalled pages
- Private groups, chats, DMs, or personal accounts
- Endpoints that require reverse engineering private APIs
- Sources whose terms disallow automated collection

Publishing rule:

- Commit aggregated outputs in `docs/`.
- Do not commit raw collected text by default.
- If a raw excerpt is needed for debugging, keep it local and remove it before publishing.
