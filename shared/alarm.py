"""Alarm di lokasi (HP B di dalam lemari): getar, notifikasi, suara."""
import shutil
import subprocess
import time

_last = 0.0


def trigger_alarm(title: str, text: str, speak: str = "", cooldown: float = 5.0) -> None:
    global _last
    now = time.monotonic()
    if now - _last < cooldown:
        return
    _last = now
    print(f"[ALARM] {title}: {text}")
    if shutil.which("termux-vibrate"):
        subprocess.Popen(["termux-vibrate", "-d", "1500"])
        subprocess.Popen(["termux-notification", "--title", title, "--content", text])
        if speak and shutil.which("termux-tts-speak"):
            subprocess.Popen(["termux-tts-speak", speak])
