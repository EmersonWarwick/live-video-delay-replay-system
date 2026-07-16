"""Network commands — Command pattern."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from lib.network.factory import NetworkModeFactory
from lib.network.hostname_service import AvahiHostnameService
from lib.network.interfaces import NetworkConfigRepository
from lib.network.models import NetworkConfig, NetworkState
from lib.network.adapters import StateFileAdapter
from lib.network.access_point_service import ShellAccessPointService
from lib.network.validation import validate_config, validate_hostname


class NetworkCommand(ABC):
    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        ...


class SaveNetworkSettingsCommand(NetworkCommand):
    def __init__(self, repo: NetworkConfigRepository, config: NetworkConfig):
        self._repo = repo
        self._config = config

    def execute(self) -> Dict[str, Any]:
        errors = validate_config(
            self._config,
            require_client_credentials=not self._config.use_local_access_point,
        )
        if errors:
            return {"ok": False, "errors": errors}
        self._repo.save(self._config)
        return {"ok": True, "config": self._config.public_dict()}


class SetDeviceHostnameCommand(NetworkCommand):
    def __init__(
        self,
        repo: NetworkConfigRepository,
        hostname_service: AvahiHostnameService,
        hostname: str,
    ):
        self._repo = repo
        self._hostname = hostname_service
        self._hostname_value = (hostname or "").strip()

    def execute(self) -> Dict[str, Any]:
        err = validate_hostname(self._hostname_value)
        if err:
            return {"ok": False, "errors": [err]}
        config = self._repo.load()
        config.device_hostname = self._hostname_value
        self._repo.save(config)
        if not self._hostname.apply(config.device_hostname):
            return {"ok": False, "error": "hostname_apply_failed"}
        return {"ok": True, "hostname": config.device_hostname}


class ApplyNetworkSettingsCommand(NetworkCommand):
    def __init__(
        self,
        repo: NetworkConfigRepository,
        hostname_service: AvahiHostnameService,
        state_file: StateFileAdapter,
        fallback_service: Optional["FallbackService"] = None,
    ):
        self._repo = repo
        self._hostname = hostname_service
        self._state = state_file
        self._fallback = fallback_service

    def execute(self) -> Dict[str, Any]:
        config = self._repo.load()
        errors = validate_config(
            config,
            require_client_credentials=not config.use_local_access_point,
        )
        if errors:
            return {"ok": False, "errors": errors}
        self._hostname.apply(config.device_hostname, restart_avahi=False)
        mode = NetworkModeFactory.create(config)
        if config.use_local_access_point:
            ok = mode.activate(config)
            return {"ok": ok, "mode": "ap", "state": NetworkState.AP_ACTIVE.value}
        ok = mode.activate(config)
        if not ok and self._fallback:
            fb = self._fallback.fallback_to_ap(config)
            err = getattr(getattr(mode, "_client", None), "last_error", "")
            return {
                "ok": False,
                "mode": "ap",
                "state": NetworkState.FALLBACK_TO_AP.value,
                "error": err or "client_wifi_failed",
                "fallback": fb,
            }
        return {
            "ok": ok,
            "mode": "client" if ok else "client",
            "state": (
                NetworkState.CLIENT_WIFI_ACTIVE.value
                if ok
                else NetworkState.CLIENT_WIFI_FAILED.value
            ),
            "error": getattr(getattr(mode, "_client", None), "last_error", "") or None,
        }


class SwitchToApModeCommand(NetworkCommand):
    def __init__(self, repo: NetworkConfigRepository, hostname_service: AvahiHostnameService):
        self._repo = repo
        self._hostname = hostname_service

    def execute(self) -> Dict[str, Any]:
        config = self._repo.load()
        config.use_local_access_point = True
        self._repo.save(config)
        self._hostname.apply(config.device_hostname)
        mode = NetworkModeFactory.create(config)
        ok = mode.activate(config)
        return {"ok": ok, "mode": "ap", "state": NetworkState.AP_ACTIVE.value}


class SwitchToClientWifiCommand(NetworkCommand):
    def __init__(
        self,
        repo: NetworkConfigRepository,
        hostname_service: AvahiHostnameService,
        fallback_service: Optional["FallbackService"] = None,
    ):
        self._repo = repo
        self._hostname = hostname_service
        self._fallback = fallback_service

    def execute(self) -> Dict[str, Any]:
        config = self._repo.load()
        errors = validate_config(config, require_client_credentials=True)
        if errors:
            return {"ok": False, "errors": errors}
        config.use_local_access_point = False
        self._repo.save(config)
        self._hostname.apply(config.device_hostname, restart_avahi=False)
        mode = NetworkModeFactory.create(config)
        ok = mode.activate(config)
        if not ok and self._fallback:
            fb = self._fallback.fallback_to_ap(config)
            err = getattr(getattr(mode, "_client", None), "last_error", "")
            return {
                "ok": False,
                "mode": "ap",
                "state": NetworkState.FALLBACK_TO_AP.value,
                "error": err or "client_wifi_failed",
                "fallback": fb,
            }
        return {
            "ok": ok,
            "mode": "client" if ok else "client",
            "state": (
                NetworkState.CLIENT_WIFI_ACTIVE.value
                if ok
                else NetworkState.CLIENT_WIFI_FAILED.value
            ),
            "error": getattr(getattr(mode, "_client", None), "last_error", "") or None,
        }


class ForgetWifiCredentialsCommand(NetworkCommand):
    def __init__(self, repo: NetworkConfigRepository, ap_service: ShellAccessPointService):
        self._repo = repo
        self._ap = ap_service

    def execute(self) -> Dict[str, Any]:
        config = self._repo.load()
        config.client_wifi_ssid = ""
        config.client_wifi_username = ""
        config.client_wifi_password = ""
        config.use_local_access_point = True
        self._repo.save(config)
        mode = NetworkModeFactory.create(config)
        ok = mode.activate(config)
        return {"ok": ok, "mode": "ap", "forgotten": True}


class FallbackService:
    """Return to AP mode when client Wi-Fi fails."""

    def __init__(
        self,
        repo: NetworkConfigRepository,
        ap_service: ShellAccessPointService,
        state_file: StateFileAdapter,
    ):
        self._repo = repo
        self._ap = ap_service
        self._state = state_file

    def fallback_to_ap(self, config: NetworkConfig) -> Dict[str, Any]:
        config.use_local_access_point = True
        self._repo.save(config)
        ok = self._ap.start()
        self._state.write({"state": NetworkState.FALLBACK_TO_AP.value, "mode": "ap"})
        return {"ok": ok, "state": NetworkState.FALLBACK_TO_AP.value}

    def watch_client_connection(
        self, config: NetworkConfig, on_fallback: callable
    ) -> bool:
        mode = NetworkModeFactory.create(config)
        ok = mode.activate(config)
        if not ok:
            on_fallback()
            return False
        return True
