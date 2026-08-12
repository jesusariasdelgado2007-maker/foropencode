import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "crm.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS empresas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    valor REAL DEFAULT 0,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contenido TEXT NOT NULL,
    contacto_id INTEGER,
    empresa_id INTEGER,
    venta_id INTEGER,
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contacto_id) REFERENCES contactos(id) ON DELETE CASCADE,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
    FOREIGN KEY (venta_id) REFERENCES ventas(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ajustes (
    clave TEXT PRIMARY KEY,
    valor TEXT
);

CREATE TABLE IF NOT EXISTS plantillas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    canal TEXT NOT NULL,
    asunto TEXT DEFAULT '',
    cuerpo TEXT NOT NULL,
    activa INTEGER DEFAULT 1,
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS planes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    precio_mensual REAL DEFAULT 0,
    precio_anual REAL DEFAULT 0,
    limite_usuarios INTEGER DEFAULT 1,
    limite_contactos INTEGER DEFAULT 0,
    descripcion TEXT DEFAULT '',
    activo INTEGER DEFAULT 1,
    creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS suscripciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suscripcion_id INTEGER,
    monto REAL DEFAULT 0,
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canal TEXT NOT NULL,
    asunto TEXT DEFAULT '',
    cuerpo TEXT NOT NULL,
    contacto_id INTEGER,
    empresa_id INTEGER,
    venta_id INTEGER,
    para TEXT DEFAULT '',
    enviar_en DATETIME,
    estado TEXT DEFAULT 'pendiente',
    enviado_en DATETIME,
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


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    cur = conn.cursor()
    for clave, valor in DEFAULTS:
        cur.execute("INSERT OR IGNORE INTO ajustes (clave, valor) VALUES (?, ?)", (clave, valor))
    conn.commit()
    conn.close()
    print("Base de datos creada/verificada en:", DB_PATH)


if __name__ == "__main__":
    init_db()
