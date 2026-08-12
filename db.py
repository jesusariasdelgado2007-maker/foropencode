"""Capa de datos con soporte doble: SQLite (local) y PostgreSQL (nube).

Uso:
  - Local (sin cambios): usa SQLite en data/crm.db.
  - Nube: define la variable de entorno DATABASE_URL con la conexión Postgres
    (ej. de Neon.tech o Supabase) y el CRM usará PostgreSQL.

Todas las consultas del app usan marcadores '?' (sqlite). Este módulo los
traduce a '%s' cuando el backend es PostgreSQL.
"""
import os
import re

import psycopg2.extensions as ext

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "crm.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

_Q = re.compile(r"\?")

# Identificadores OID de timestamp en PostgreSQL (1114: sin tz, 1184: con tz)
_TS_OIDS = (1114, 1184)


def _ts_tostr(value, cursor):
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _date_tostr(value, cursor):
    if value is None:
        return None
    return value.isoformat()


_TS_TYPE = ext.new_type(_TS_OIDS, "CRM_TIMESTAMP_STR", _ts_tostr)
_DATE_TYPE = ext.new_type(ext.DATE.values, "CRM_DATE_STR", _date_tostr)
ext.register_type(_TS_TYPE)
ext.register_type(_DATE_TYPE)


def is_postgres():
    return bool(DATABASE_URL)


def connect():
    if is_postgres():
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def translate(sql):
    """Convierte '?' a '%s' para Postgres."""
    if not is_postgres():
        return sql
    return _Q.sub("%s", sql)


def execute(conn, sql, args=()):
    cur = conn.cursor()
    if is_postgres():
        tsql = translate(sql)
        if re.match(r"^\s*insert\b", tsql, re.I) and "ajustes" not in tsql:
            tsql = tsql.rstrip(";") + " RETURNING id"
            cur.execute(tsql, tuple(args) if args else ())
            row = cur.fetchone()
            lid = row[0] if row else None
        else:
            cur.execute(tsql, tuple(args) if args else ())
            lid = None
    else:
        cur.execute(sql, tuple(args) if args else ())
        lid = getattr(cur, "lastrowid", None)
    conn.commit()
    cur.close()
    return lid


def queryall(conn, sql, args=()):
    cur = conn.cursor()
    cur.execute(translate(sql), tuple(args) if args else ())
    if is_postgres():
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    else:
        rows = cur.fetchall()
    cur.close()
    return rows


def queryone(conn, sql, args=()):
    rows = queryall(conn, sql, args)
    return rows[0] if rows else None
