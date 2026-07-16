"""Network mode strategies."""
from __future__ import annotations

from lib.network.access_point_service import ShellAccessPointService
from lib.network.adapters import StateFileAdapter
from lib.network.client_wifi_service import NmcliClientWifiService
from lib.network.interfaces import NetworkMode
from lib.network.models import NetworkConfig, NetworkState


class AccessPointMode(NetworkMode):
    def __init__(
        self,
        ap_service: ShellAccessPointService | None = None,
        client_service: NmcliClientWifiService | None = None,
        state_file: StateFileAdapter | None = None,
    ):
        self._ap = ap_service or ShellAccessPointService()
        self._client = client_service or NmcliClientWifiService()
        self._state = state_file or StateFileAdapter()

    def activate(self, config: NetworkConfig) -> bool:
        self._client.disconnect()
        ok = self._ap.start()
        if ok:
            self._state.write({"state": NetworkState.AP_ACTIVE.value, "mode": "ap"})
        return ok

    def deactivate(self) -> bool:
        return self._ap.stop()

    def is_active(self) -> bool:
        return self._ap.is_active()


class ClientWifiMode(NetworkMode):
    def __init__(
        self,
        client_service: NmcliClientWifiService | None = None,
        ap_service: ShellAccessPointService | None = None,
        state_file: StateFileAdapter | None = None,
    ):
        self._client = client_service or NmcliClientWifiService()
        self._ap = ap_service or ShellAccessPointService()
        self._state = state_file or StateFileAdapter()

    def activate(self, config: NetworkConfig) -> bool:
        self._state.write(
            {"state": NetworkState.CLIENT_WIFI_CONNECTING.value, "mode": "client"}
        )
        ok = self._client.connect(config, timeout_seconds=config.fallback_timeout_seconds)
        if ok:
            self._state.write(
                {"state": NetworkState.CLIENT_WIFI_ACTIVE.value, "mode": "client"}
            )
        else:
            self._state.write(
                {"state": NetworkState.CLIENT_WIFI_FAILED.value, "mode": "client"}
            )
        return ok

    def deactivate(self) -> bool:
        return self._client.disconnect()

    def is_active(self) -> bool:
        return self._client.is_connected()
