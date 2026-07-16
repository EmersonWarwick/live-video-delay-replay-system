"""Factory for network mode strategies."""
from __future__ import annotations

from lib.network.interfaces import NetworkMode
from lib.network.models import NetworkConfig
from lib.network.modes import AccessPointMode, ClientWifiMode


class NetworkModeFactory:
    @staticmethod
    def create(config: NetworkConfig) -> NetworkMode:
        if config.use_local_access_point:
            return AccessPointMode()
        return ClientWifiMode()
