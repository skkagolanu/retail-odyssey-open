# Security

Use GitHub private vulnerability reporting for sensitive disclosures; do not post credentials in issues. If it is unavailable, contact the repository owner privately. This repository is a demonstration, not an authenticated commerce service.

Public deployment requires TLS, exact origins and trusted hosts, secure cookies, proxy request/concurrency limits and restricted metrics. Browser sessions are bearer-cookie sessions, not user accounts. SQLite history is plaintext on disk; restrict access and encrypt storage/backups if needed. No payment/account credentials are collected. Uploaded images are not retained by this app, but the configured local provider may retain logs/history; review that provider's policy. ComfyUI/Ollama must not be exposed directly to the internet.

The upstream repository had historical credential findings; the derivative does not publish that history. Removing a token from a file does not revoke it. The upstream owner must revoke/rotate any credentials still valid; their validity was not tested.
