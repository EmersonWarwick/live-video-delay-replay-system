# Contributing to Live Video Delay Replay System

Thank you for contributing. **Pull requests are welcome and encouraged** — this project improves faster when venue operators, coaches, and developers share real hardware feedback and code.

The workflow is **spec-driven**: specifications in `.cursor/` define behaviour; code implements them.

---

## How to contribute (short path)

1. Fork the repository (or branch from `main` if you have write access).
2. Open an Issue if the change is large or ambiguous — describe the **venue problem**, not only a preferred solution.
3. Update the owning **specification** in `.cursor/` first (see workflow below).
4. Implement the matching change under `pi-root/` (or docs/scripts).
5. **Open a pull request** with a clear description and links to the specs you changed.

Small PRs (one logical change, easy to test) are the most valuable. Documentation-only and testing-procedure PRs are just as welcome as firmware changes.

---

## Before you start

1. Read [README.md](README.md) for project scope and layout.
2. Read [`.cursor/constitution.md`](.cursor/constitution.md) — core invariants and anti-patterns.
3. Read [`.cursor/architecture-and-technical-spec.md`](.cursor/architecture-and-technical-spec.md) for appliance architecture.
4. Check [ROADMAP.md](ROADMAP.md) and open GitHub issues to avoid duplicate work.

---

## Spec-driven workflow

Every functional change should follow this order:

1. **Identify the owning spec** — use the document map in `constitution.md` §1.
2. **Update the specification** — describe the new or changed behaviour precisely (URLs, defaults, acceptance criteria).
3. **Implement** — change code in `pi-root/` (and mobile repos if applicable) to match the spec.
4. **Verify** — manual tests per `architecture-and-technical-spec.md` §10 (network → RTSP → buffer → HTTP → clients).

If behaviour differs from the spec today, **fix the spec to match shipped code first**, then implement improvements in a follow-up change with an updated spec.

Do not add behaviour in code without a corresponding spec update in the same pull request (unless the change is a pure bug fix restoring spec-compliant behaviour).

---

## What to contribute

| Area                   | Location                             | Notes                                                   |
| ---------------------- | ------------------------------------ | ------------------------------------------------------- |
| Pi firmware & services | `pi-root/`                           | systemd units, shell helpers, Flask app, Python libs    |
| Specifications         | `.cursor/*.md`                       | Primary source of truth                                 |
| Build & manufacturing  | `build-instructions*.md`, `scripts/` | Keep Mac guide canonical; PC guide mirrors              |
| Tests & validation     | `testing/`                           | Manual procedures welcome; automated tests as they grow |
| Docs & roadmap         | `README.md`, `ROADMAP.md`, …         | Clarity and accuracy PRs are appreciated                |
| Mobile apps            | Separate repositories                | Align with `spec-mobile-clients.md`                     |

High-value topics for first-time contributors: camera model reports, build-guide fixes, AP/LAN edge cases, and documentation that matches real Pi behaviour.

---

## Runtime naming (`sportassist`)

**Runtime paths** (what systemd and helpers expect):

- Linux user / home: `sportassist` → `/home/sportassist/dev/ldrs/`
- Config and data: `/etc/sportassist/`, `/var/lib/sportassist/`
- Shared assets: `/usr/share/sportassist/` (logo and idle splash)
- Web unit: `User=sportassist` in `ldrs-web.service`

The `pi-root/` tree mirrors these names. Phase 2 may rebrand paths further (see [ROADMAP.md](ROADMAP.md)).

---

## Pull request guidelines

1. **One logical change per PR** — easier to review against specs.
2. **Link the spec** — cite which `.cursor/spec-*.md` sections your PR implements or amends.
3. **No secrets** — never commit `config/appliance-*.env`, `config/web-*.env`, real passwords, Wi‑Fi passphrases, camera admin credentials, or **Raspberry Pi Linux / sudo (super-user) passwords**. `.gitignore` blocks the usual env patterns; double-check before push. Keep Pi and camera super-user credentials in a private offline record only.
4. **European English** — spelling and tone in docs (colour, behaviour, …).
5. **Minimal scope** — match existing naming, paths, and patterns unless the spec explicitly calls for refactoring.
6. **Test on real hardware when possible** — Pi 5 + PoE camera for ingest/HDMI/AP changes.

### Commit messages

Use clear, imperative subjects:

```text
spec: document Wi-Fi client mode API responses
fix: restart hdmi-delay when PLAYBACK_OFFSET changes
docs: clarify web login defaults in build guide
```

---

## Development environment

### Pi appliance (primary)

Follow [build-instructions.md](build-instructions.md) to flash and deploy a development unit. Use `scripts/pack-pi-root.sh` and `scripts/push-to-pi.sh` for iterative sync.

Python dependencies:

- **Entry / install notes:** [requirements.txt](requirements.txt)
- **Pip package list:** [requirements-pip.txt](requirements-pip.txt) (`onvif-zeep`, `WSDiscovery`)
- **Apt packages** (do not pip-install these on Pi OS): `python3-flask`, `python3-zeep`

Preferred installer: `scripts/install-pi-python-deps.sh`.

### AI-assisted development

[Cursor](https://cursor.com) and other AI tools are encouraged. Point assistants at `.cursor/constitution.md` and the relevant spec before generating code. **Review all generated changes** against the specification before opening a PR.

---

## Code style

- **Shell**: POSIX where practical; match existing `ldrs-*.sh` patterns.
- **Python**: Match conventions under `pi-root/home/sportassist/dev/ldrs/lib/`; type hints where already used.
- **Flask templates**: Keep settings/replay pages consistent with `spec-settings-page.md` and `spec-frontend.md`.
- **Comments**: Explain non-obvious business logic only; prefer self-explanatory code.

---

## Reporting issues

Include:

- Hardware (Pi model, RAM, camera model)
- Network mode (AP vs LAN client)
- Relevant systemd unit status (`ldrs-replay-buffer`, `ldrs-web`, …)
- Spec section you believe is violated (if any)

Do not paste real passwords, AP passphrases, or camera credentials.

---

## Licensing

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).

---

## Community conduct

Be respectful and constructive. Focus on reliable, unattended venue hardware — changes that compromise stability or security will be scrutinised carefully.

Questions and ideas: open a GitHub Issue or Discussion. Ready to share code? **Open a pull request** — we will review it.
