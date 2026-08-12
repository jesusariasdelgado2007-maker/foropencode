"""Punto de entrada para servidores tipo gunicorn (Render).

Inicializa la base de datos (SQLite local o PostgreSQL si DATABASE_URL está
definida) y arranca el motor de automatización antes de servir la app.
"""
import threading

import app
import db

NEAR = True


def _init():
    if db.is_postgres():
        from pg_schema import init_pg

        init_pg()
    else:
        from init_db import init_db

        init_db()


_init()

# Arrancar el motor de automatización (scheduler) en un hilo de fondo
threading.Thread(target=app.scheduler_loop, daemon=True).start()

# app:app es lo que gunicorn busca
application = app.app
