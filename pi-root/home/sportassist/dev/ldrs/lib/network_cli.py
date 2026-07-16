#!/usr/bin/env python3
"""CLI for privileged network operations — called from ldrs-network-*.sh."""
from __future__ import annotations

import json
import sys
from pathlib import Path

LDRS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LDRS_ROOT))

from lib.network.manager import NetworkManager  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: ldrs-network-cli.py <command> [json]", file=sys.stderr)
        return 2
    cmd = sys.argv[1]
    mgr = NetworkManager()
    payload = {}
    if len(sys.argv) > 2:
        try:
            payload = json.loads(sys.argv[2])
        except json.JSONDecodeError:
            print(json.dumps({"ok": False, "error": "invalid_json"}))
            return 1

    handlers = {
        "status": lambda: {"ok": True, **mgr.get_status()},
        "config": lambda: {"ok": True, "config": mgr.get_config()},
        "scan": mgr.scan_wifi,
        "save": lambda: mgr.save_settings(payload),
        "set-hostname": lambda: mgr.set_device_hostname(payload.get("hostname", "")),
        "apply": mgr.apply_settings,
        "switch-ap": mgr.switch_to_ap,
        "switch-client": mgr.switch_to_client_wifi,
        "forget": mgr.forget_credentials,
        "boot": mgr.boot_apply,
        "logs": lambda: {"ok": True, "logs": mgr.export_logs()},
    }
    fn = handlers.get(cmd)
    if not fn:
        print(json.dumps({"ok": False, "error": f"unknown_command:{cmd}"}))
        return 1
    result = fn()
    print(json.dumps(result))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
