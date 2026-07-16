"""Network service interfaces — Interface Segregation Principle."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from lib.network.models import NetworkConfig, NetworkStatus, WifiNetwork


class NetworkConfigRepository(ABC):
    @abstractmethod
    def load(self) -> NetworkConfig:
        ...

    @abstractmethod
    def save(self, config: NetworkConfig) -> None:
        ...

    @abstractmethod
    def merge_ap_defaults(self, config: NetworkConfig) -> NetworkConfig:
        ...


class WifiScanner(ABC):
    @abstractmethod
    def scan(self) -> List[WifiNetwork]:
        ...


class AccessPointService(ABC):
    @abstractmethod
    def start(self) -> bool:
        ...

    @abstractmethod
    def stop(self) -> bool:
        ...

    @abstractmethod
    def is_active(self) -> bool:
        ...


class ClientWifiService(ABC):
    @abstractmethod
    def connect(self, config: NetworkConfig, timeout_seconds: int = 90) -> bool:
        ...

    @abstractmethod
    def disconnect(self) -> bool:
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @abstractmethod
    def connected_ssid(self) -> str:
        ...

    @abstractmethod
    def signal_strength(self) -> Optional[int]:
        ...


class HostnameService(ABC):
    @abstractmethod
    def apply(self, hostname: str) -> bool:
        ...

    @abstractmethod
    def current_hostname(self) -> str:
        ...


class NetworkMode(ABC):
    """Strategy interface for AP vs client Wi-Fi modes."""

    @abstractmethod
    def activate(self, config: NetworkConfig) -> bool:
        ...

    @abstractmethod
    def deactivate(self) -> bool:
        ...

    @abstractmethod
    def is_active(self) -> bool:
        ...


class NetworkStatusProvider(ABC):
    @abstractmethod
    def get_status(self) -> NetworkStatus:
        ...


class FallbackService(ABC):
    @abstractmethod
    def watch_client_connection(
        self, config: NetworkConfig, on_fallback: callable
    ) -> bool:
        ...
