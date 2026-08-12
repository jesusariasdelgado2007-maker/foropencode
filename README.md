# CRM - Gestor de Clientes

CRM con Flask + SQLite (local) o PostgreSQL (nube). Incluye contactos, empresas,
ventas, tareas, citas, mensajes y automatización (plantillas, WhatsApp, email,
alertas de venta estancada, recordatorios).

## Modo local
- Ejecuta `python app.py` o `iniciar_crm.bat`.
- Usa SQLite en `data/crm.db`. Sin configuración extra.

## Modo nube (Render + Neon.tech)
1. Crea una base PostgreSQL gratuita en **Neon.tech** y copia su connection string.
2. Define la variable de entorno `DATABASE_URL` con ese string.
3. En Render, crea un Web Service apuntando a tu repositorio:
   - Runtime: Python
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 4`
   - Define `DATABASE_URL` en Environment.
   - Deploy.

El módulo `wsgi.py` inicializa la BD (Postgres si hay `DATABASE_URL`, si no SQLite)
y arranca el motor de automatización.
