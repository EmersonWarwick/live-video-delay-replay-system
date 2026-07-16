# Live Video Delay Replay System — Build Instructions (index)

Choose the guide for your build machine:

| Platform | Document |
|----------|----------|
| **macOS** | [`build-instructions-mac.md`](build-instructions-mac.md) — canonical long form |
| **Windows** | [`build-instructions-pc.md`](build-instructions-pc.md) — mirrors manufacturing flow; defers detail to Mac guide |

**Specs:** `.cursor/architecture-and-technical-spec.md`  
**Runtime tree:** `pi-root/README.md`  
**Python pip deps:** `requirements-pip.txt` (install per build guide §4.1 or `scripts/install-pi-python-deps.sh`)

**Per-unit secrets** (`config/appliance-*.env`, `config/web-*.env`): copy from `*.env.example` at construction — **do not commit real passwords to git**.
