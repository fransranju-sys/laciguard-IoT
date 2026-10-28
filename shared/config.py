"""Konfigurasi dari file .env (PROJECT_ID, broker MQTT, ukuran window)."""
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv opsional
    pass


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "y")


PROJECT_ID = os.getenv("PROJECT_ID", "laciguard_demo")
MQTT_HOST = os.getenv("MQTT_HOST", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_TLS = _bool("MQTT_TLS", True)
WINDOW_SIZE = int(os.getenv("WINDOW_SIZE", "10"))
SAMPLE_INTERVAL = float(os.getenv("SAMPLE_INTERVAL", "0.1"))


def topic(suffix: str) -> str:
    """Alamat topic MQTT, misal topic('alerts') -> laciguard/<PROJECT_ID>/alerts"""
    return f"laciguard/{PROJECT_ID}/{suffix}"
