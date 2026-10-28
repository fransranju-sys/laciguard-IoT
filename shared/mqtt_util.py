"""Pembungkus kecil paho-mqtt (v2) untuk semua node."""
import json
import random

import paho.mqtt.client as mqtt

from shared import config


def make_client(role: str, subscriptions=None):
    """Buat client MQTT dan langsung terhubung.

    subscriptions: {topic_filter: handler(topic: str, payload: bytes)}
    Langganan dibuat di on_connect, jadi otomatis dipasang ulang saat reconnect.
    """
    subscriptions = subscriptions or {}
    client_id = f"laciguard-{config.PROJECT_ID}-{role}-{random.randint(0, 99999)}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    if config.MQTT_TLS:
        client.tls_set()  # memakai sertifikat CA bawaan sistem
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    def on_connect(c, userdata, flags, reason_code, properties=None):
        if reason_code.is_failure:
            print(f"[MQTT] gagal terhubung: {reason_code}")
            return
        print(f"[MQTT] terhubung ke {config.MQTT_HOST}:{config.MQTT_PORT}")
        for flt in subscriptions:
            c.subscribe(flt, qos=1)

    def on_message(c, userdata, msg):
        for flt, handler in subscriptions.items():
            if mqtt.topic_matches_sub(flt, msg.topic):
                try:
                    handler(msg.topic, msg.payload)
                except Exception as exc:  # jangan matikan thread MQTT
                    print(f"[MQTT] error di handler {msg.topic}: {exc!r}")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
    client.loop_start()
    return client


def publish_json(client, topic: str, obj: dict, qos: int = 1, retain: bool = False):
    client.publish(topic, json.dumps(obj, separators=(",", ":")), qos=qos, retain=retain)
