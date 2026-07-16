"""Network configuration and state models."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class NetworkState(str, Enum):
    AP_ACTIVE = "AP_ACTIVE"
    CLIENT_WIFI_CONNECTING = "CLIENT_WIFI_CONNECTING"
    CLIENT_WIFI_ACTIVE = "CLIENT_WIFI_ACTIVE"
    CLIENT_WIFI_FAILED = "CLIENT_WIFI_FAILED"
    FALLBACK_TO_AP = "FALLBACK_TO_AP"
    UNKNOWN = "UNKNOWN"


class WifiSecurityType(str, Enum):
    OPEN = "open"
    WPA2_PSK = "wpa2-psk"
    WPA_EAP = "wpa-eap"


@dataclass
class NetworkConfig:
    use_local_access_point: bool = True
    local_ap_ssid: str = ""
    local_ap_password: str = ""
    client_wifi_ssid: str = ""
    client_wifi_username: str = ""
    client_wifi_password: str = ""
    client_wifi_security_type: str = WifiSecurityType.WPA2_PSK.value
    device_hostname: str = "sport-assist.local"
    fallback_timeout_seconds: int = 90

    def to_env(self) -> Dict[str, str]:
        return {
            "USE_LOCAL_ACCESS_POINT": "1" if self.use_local_access_point else "0",
            "LOCAL_AP_SSID": self.local_ap_ssid,
            "LOCAL_AP_PASSWORD": self.local_ap_password,
            "CLIENT_WIFI_SSID": self.client_wifi_ssid,
            "CLIENT_WIFI_USERNAME": self.client_wifi_username,
            "CLIENT_WIFI_PASSWORD": self.client_wifi_password,
            "CLIENT_WIFI_SECURITY_TYPE": self.client_wifi_security_type,
            "DEVICE_HOSTNAME": self.device_hostname,
            "FALLBACK_TIMEOUT_SECONDS": str(self.fallback_timeout_seconds),
        }

    @classmethod
    def from_env(cls, values: Dict[str, str]) -> "NetworkConfig":
        return cls(
            use_local_access_point=values.get("USE_LOCAL_ACCESS_POINT", "1") == "1",
            local_ap_ssid=values.get("LOCAL_AP_SSID", ""),
            local_ap_password=values.get("LOCAL_AP_PASSWORD", ""),
            client_wifi_ssid=values.get("CLIENT_WIFI_SSID", ""),
            client_wifi_username=values.get("CLIENT_WIFI_USERNAME", ""),
            client_wifi_password=values.get("CLIENT_WIFI_PASSWORD", ""),
            client_wifi_security_type=values.get(
                "CLIENT_WIFI_SECURITY_TYPE", WifiSecurityType.WPA2_PSK.value
            ),
            device_hostname=values.get("DEVICE_HOSTNAME", "sport-assist.local"),
            fallback_timeout_seconds=int(values.get("FALLBACK_TIMEOUT_SECONDS", "90") or 90),
        )

    def public_dict(self) -> Dict[str, Any]:
        """Safe for API — never includes passwords."""
        return {
            "useLocalAccessPoint": self.use_local_access_point,
            "localApSsid": self.local_ap_ssid,
            "hasLocalApPassword": bool(self.local_ap_password),
            "clientWifiSsid": self.client_wifi_ssid,
            "clientWifiUsername": self.client_wifi_username,
            "hasClientWifiPassword": bool(self.client_wifi_password),
            "clientWifiSecurityType": self.client_wifi_security_type,
            "deviceHostname": self.device_hostname,
            "fallbackTimeoutSeconds": self.fallback_timeout_seconds,
        }


@dataclass
class WifiNetwork:
    ssid: str
    security_type: str
    signal_strength: int = 0
    in_use: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ssid": self.ssid,
            "securityType": self.security_type,
            "signalStrength": self.signal_strength,
            "inUse": self.in_use,
        }


@dataclass
class NetworkStatus:
    state: NetworkState = NetworkState.UNKNOWN
    mode: str = "unknown"
    connected_ssid: str = ""
    ip_address: str = ""
    signal_strength: Optional[int] = None
    hostname: str = "sport-assist.local"
    ap_active: bool = False
    client_wifi_active: bool = False
    client_wifi_status: str = ""
    camera_connected: bool = False
    replay_service_active: bool = False
    interface: str = ""
    ssh_endpoints: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "mode": self.mode,
            "connectedSsid": self.connected_ssid,
            "ipAddress": self.ip_address,
            "signalStrength": self.signal_strength,
            "hostname": self.hostname,
            "apActive": self.ap_active,
            "clientWifiActive": self.client_wifi_active,
            "clientWifiStatus": self.client_wifi_status,
            "cameraConnected": self.camera_connected,
            "replayServiceActive": self.replay_service_active,
            "interface": self.interface,
            "sshEndpoints": self.ssh_endpoints,
        }
