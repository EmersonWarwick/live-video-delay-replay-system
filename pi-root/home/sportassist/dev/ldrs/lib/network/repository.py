"""Persist network configuration."""
from __future__ import annotations

from pathlib import Path

from lib.env_util import load_env, save_env
from lib.network.interfaces import NetworkConfigRepository
from lib.network.models import NetworkConfig

WIFI_NETWORK_ENV = Path("/etc/sportassist/wifi-network.env")
WIFI_AP_ENV = Path("/etc/sportassist/wifi-ap.env")

_DEFAULT_HEADER = """# Sport Assist Wi-Fi network mode — AP vs client building Wi-Fi
# Managed by Network Settings (ldrs-network-cli.py)
"""


class FileNetworkConfigRepository(NetworkConfigRepository):
    def __init__(
        self,
        path: Path = WIFI_NETWORK_ENV,
        ap_env_path: Path = WIFI_AP_ENV,
    ):
        self._path = path
        self._ap_env_path = ap_env_path

    def load(self) -> NetworkConfig:
        values = load_env(self._path)
        if not values:
            values = {
                "USE_LOCAL_ACCESS_POINT": "1",
                "DEVICE_HOSTNAME": "sport-assist.local",
                "CLIENT_WIFI_SECURITY_TYPE": "wpa2-psk",
                "FALLBACK_TIMEOUT_SECONDS": "90",
            }
        config = NetworkConfig.from_env(values)
        return self.merge_ap_defaults(config)

    def save(self, config: NetworkConfig) -> None:
        merged = self.merge_ap_defaults(config)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        save_env(self._path, merged.to_env(), header=_DEFAULT_HEADER.strip())
        try:
            import grp
            import os
            import pwd

            self._path.chmod(0o640)
            os.chown(
                self._path,
                pwd.getpwnam("root").pw_uid,
                grp.getgrnam("sportassist").gr_gid,
            )
        except OSError:
            pass

    def merge_ap_defaults(self, config: NetworkConfig) -> NetworkConfig:
        ap = load_env(self._ap_env_path)
        if ap.get("AP_SSID") and not config.local_ap_ssid:
            config.local_ap_ssid = ap["AP_SSID"]
        if ap.get("AP_PSK") and not config.local_ap_password:
            config.local_ap_password = ap["AP_PSK"]
        return config
