# Security policy

## Reporting a vulnerability

Report security issues privately to **tournelalexandre@gmail.com**, or through GitHub's
[private vulnerability reporting](https://docs.github.com/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
on this repository. Please do **not** open a public issue for a vulnerability.

**Response time:** acknowledgement within **7 days**, and an assessment within **30 days**.
This is a single-maintainer project — that is the honest figure, not a service-level agreement.

Please include what you did, what happened, what you expected, and the version
(`python run.py --version`).

## Supported versions

Only the latest release is supported. There are no maintained back-branches.

## Threat model — what is and is not in scope

Angelith runs locally, processes files the user supplies, and talks to a language-model
endpoint the user configures. It exposes no network service of its own.

**In scope:**

- Path traversal or arbitrary file writes from a crafted source archive (`.cbz`, `.cbr`,
  `.epub` — all of them are zip files with attacker-controlled member names).
- Code execution via a malformed `.docx`, `.pdf`, `.epub` or image.
- Unsafe deserialisation of `config.yaml` or of a glossary.
- Any path by which text is sent somewhere the user did not configure. **The core promise of
  this project is that content stays on the machine**; a leak of document content is a security
  bug here, not a privacy nicety.
- Command injection through file names or configuration values reaching Pandoc or WeasyPrint.

**Out of scope:**

- What the language model generates. A bad translation is a quality issue.
- Vulnerabilities in Ollama, Pandoc, WeasyPrint or model weights — report those upstream.
- Attacks requiring an attacker who already has local access to the machine.
