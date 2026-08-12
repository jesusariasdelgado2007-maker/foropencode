"""Vigilante del CRM.

Mantiene el servidor siempre activo:
  - Si el CRM se cae, lo relanza solo.
  - Si ya hay un CRM funcionando, esta instancia sale sin duplicar nada.
Se ejecuta en segundo plano con pythonw.
"""
import os
import socket
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
PUERTO = 5000


def puerto_ocupado(puerto=PUERTO):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", puerto))
        return False
    except OSError:
        return True
    finally:
        s.close()


def main():
    try:
        import msvcrt
    except ImportError:
        msvcrt = None

    os.makedirs(os.path.join(BASE, "data"), exist_ok=True)
    lock = open(os.path.join(BASE, "data", "crm.lock"), "a+")

    # Solo permitimos un vigilante a la vez (candado de archivo)
    if msvcrt is not None:
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return  # otro vigilante ya esta corriendo
    elif puerto_ocupado():
        return  # ya hay un CRM sirviendo

    while True:
        if puerto_ocupado():
            break  # otro proceso se hizo cargo; salimos
        proc = subprocess.Popen(
            [sys.executable, os.path.join(BASE, "app.py")],
            cwd=BASE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        while proc.poll() is None:
            time.sleep(2)
        time.sleep(3)  # pequena pausa antes de relanzar


if __name__ == "__main__":
    main()
