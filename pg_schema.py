"""Esquema PostgreSQL para el CRM (usado cuando se despliega con DATABASE_URL)."""

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS empresas (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    sector TEXT DEFAULT '',
    telefono TEXT DEFAULT '',
    email TEXT DEFAULT '',
    web TEXT DEFAULT '',
    direccion TEXT DEFAULT '',
    notas TEXT DEFAULT '',
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contactos (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    email TEXT DEFAULT '',
    telefono TEXT DEFAULT '',
    cargo TEXT DEFAULT '',
    empresa_id INTEGER,
    notas TEXT DEFAULT '',
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ventas (
    id SERIAL PRIMARY KEY,
    titulo TEXT NOT NULL,
    valor DOUBLE PRECISION DEFAULT 0,
    etapa TEXT DEFAULT 'Prospeccion',
    empresa_id INTEGER,
    contacto_id INTEGER,
    descripcion TEXT DEFAULT '',
    fecha_cierre DATE,
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tareas (
    id SERIAL PRIMARY KEY,
    titulo TEXT NOT NULL,
    descripcion TEXT DEFAULT '',
    vencimiento DATE,
    completada INTEGER DEFAULT 0,
    contacto_id INTEGER,
    empresa_id INTEGER,
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS citas (
    id SERIAL PRIMARY KEY,
    titulo TEXT NOT NULL,
    fecha DATE NOT NULL,
    hora TEXT DEFAULT '',
    descripcion TEXT DEFAULT '',
    contacto_id INTEGER,
    empresa_id INTEGER,
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notas (
    id SERIAL PRIMARY KEY,
    contenido TEXT NOT NULL,
    contacto_id INTEGER,
    empresa_id INTEGER,
    venta_id INTEGER,
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plantillas (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    canal TEXT NOT NULL,
    asunto TEXT DEFAULT '',
    cuerpo TEXT NOT NULL,
    activa INTEGER DEFAULT 1,
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mensajes (
    id SERIAL PRIMARY KEY,
    canal TEXT NOT NULL,
    asunto TEXT DEFAULT '',
    cuerpo TEXT NOT NULL,
    contacto_id INTEGER,
    empresa_id INTEGER,
    venta_id INTEGER,
    para TEXT DEFAULT '',
    enviar_en TIMESTAMP,
    estado TEXT DEFAULT 'pendiente',
    enviado_en TIMESTAMP,
    respondido INTEGER DEFAULT 0,
    origen TEXT DEFAULT 'manual',
    reenvio_de INTEGER,
    message_id TEXT DEFAULT '',
    error TEXT DEFAULT '',
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ajustes (
    clave TEXT PRIMARY KEY,
    valor TEXT
);

CREATE INDEX IF NOT EXISTS idx_contactos_empresa ON contactos(empresa_id);
CREATE INDEX IF NOT EXISTS idx_ventas_contacto ON ventas(contacto_id);
CREATE INDEX IF NOT EXISTS idx_ventas_empresa ON ventas(empresa_id);
CREATE INDEX IF NOT EXISTS idx_mensajes_envio ON mensajes(enviar_en, estado);
"""

DEFAULTS = [
    ("smtp_host", ""),
    ("smtp_port", "587"),
    ("smtp_usuario", ""),
    ("smtp_password", ""),
    ("smtp_desde", ""),
    ("idle_dias", "3"),
    ("resend_dias", "3"),
    ("imap_host", "imap.gmail.com"),
    ("imap_activo", ""),
]


def init_pg():
    import psycopg2

    url = __import__("db").DATABASE_URL
    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(PG_SCHEMA)
    for clave, valor in DEFAULTS:
        cur.execute(
            "INSERT INTO ajustes (clave, valor) VALUES (%s, %s) "
            "ON CONFLICT (clave) DO NOTHING",
            (clave, valor),
        )
    conn.commit()
    cur.close()
    conn.close()
    print("Base de datos PostgreSQL creada/verificada.")


if __name__ == "__main__":
    if not __import__("db").DATABASE_URL:
        print("Define DATABASE_URL para inicializar Postgres.")
    else:
        init_pg()
