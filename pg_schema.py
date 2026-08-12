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
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE SET NULL
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
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE SET NULL,
    FOREIGN KEY (contacto_id) REFERENCES contactos(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tareas (
    id SERIAL PRIMARY KEY,
    titulo TEXT NOT NULL,
    descripcion TEXT DEFAULT '',
    vencimiento DATE,
    completada INTEGER DEFAULT 0,
    contacto_id INTEGER,
    empresa_id INTEGER,
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contacto_id) REFERENCES contactos(id) ON DELETE SET NULL,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS citas (
    id SERIAL PRIMARY KEY,
    titulo TEXT NOT NULL,
    fecha DATE NOT NULL,
    hora TEXT DEFAULT '',
    descripcion TEXT DEFAULT '',
    contacto_id INTEGER,
    empresa_id INTEGER,
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contacto_id) REFERENCES contactos(id) ON DELETE SET NULL,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS notas (
    id SERIAL PRIMARY KEY,
    contenido TEXT NOT NULL,
    contacto_id INTEGER,
    empresa_id INTEGER,
    venta_id INTEGER,
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contacto_id) REFERENCES contactos(id) ON DELETE CASCADE,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
    FOREIGN KEY (venta_id) REFERENCES ventas(id) ON DELETE CASCADE
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

CREATE TABLE IF NOT EXISTS planes (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    precio_mensual DOUBLE PRECISION DEFAULT 0,
    precio_anual DOUBLE PRECISION DEFAULT 0,
    limite_usuarios INTEGER DEFAULT 1,
    limite_contactos INTEGER DEFAULT 0,
    descripcion TEXT DEFAULT '',
    activo INTEGER DEFAULT 1,
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS suscripciones (
    id SERIAL PRIMARY KEY,
    empresa_id INTEGER,
    plan_id INTEGER,
    estado TEXT DEFAULT 'pendiente',
    ciclo TEXT DEFAULT 'mensual',
    inicio DATE,
    proximo_pago DATE,
    ultimo_pago DATE,
    notas TEXT DEFAULT '',
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE SET NULL,
    FOREIGN KEY (plan_id) REFERENCES planes(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS pagos (
    id SERIAL PRIMARY KEY,
    suscripcion_id INTEGER,
    monto DOUBLE PRECISION DEFAULT 0,
    moneda TEXT DEFAULT 'EUR',
    metodo TEXT DEFAULT 'manual',
    transaction_id TEXT DEFAULT '',
    url_pago TEXT DEFAULT '',
    estado TEXT DEFAULT 'pendiente',
    detalle TEXT DEFAULT '',
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    pagado_en TIMESTAMP,
    FOREIGN KEY (suscripcion_id) REFERENCES suscripciones(id) ON DELETE CASCADE
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
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contacto_id) REFERENCES contactos(id) ON DELETE SET NULL,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE SET NULL,
    FOREIGN KEY (venta_id) REFERENCES ventas(id) ON DELETE SET NULL
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
    ("pasarela", ""),
    ("moneda", "EUR"),
    ("mp_access_token", ""),
    ("stripe_secret_key", ""),
    ("stripe_webhook_secret", ""),
    ("paypal_client_id", ""),
    ("paypal_secret", ""),
    ("paypal_sandbox", "1"),
    ("public_url", "http://127.0.0.1:5000"),
    ("nequi_client_id", ""),
    ("nequi_secret", ""),
    ("nequi_api_key", ""),
    ("nequi_codigo_comercio", ""),
    ("nequi_sandbox", "1"),
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
