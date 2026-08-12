import imaplib
import os
import re
import smtplib
import sqlite3
import threading
import time
import urllib.parse
from datetime import date, datetime, timedelta
from email.header import Header
from email.mime.text import MIMEText

import calendar

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    g,
)

import db
import pasarela

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "crm.db")

app = Flask(__name__)
app.secret_key = "crm-local-simple-2026"

SIMBOLOS_MONEDA = {
    "EUR": "€", "USD": "$", "MXN": "$", "ARS": "$", "COP": "$",
    "CLP": "$", "PEN": "S/", "BRL": "R$", "GBP": "£",
}
CURRENCY = "EUR"


@app.template_filter("money")
def money_format(value):
    try:
        value = float(value or 0)
    except (TypeError, ValueError):
        value = 0
    mon = SIMBOLOS_MONEDA.get(CURRENCY, (CURRENCY + " ").upper())
    return f"{value:,.2f} {mon}".replace(",", "X").replace(".", ",").replace("X", ".")

ETAPAS = ["Prospeccion", "Calificado", "Propuesta", "Negociacion", "Ganado", "Perdido"]


def get_db():
    if "db" not in g:
        g.db = db.connect()
        if not db.is_postgres():
            g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    d = g.pop("db", None)
    if d is not None:
        try:
            d.close()
        except Exception:
            pass


def query(sql, args=(), one=False):
    rows = db.queryall(get_db(), sql, args)
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    return db.execute(get_db(), sql, args)


def form_val(*keys):
    return {k: request.form.get(k, "").strip() for k in keys}


def resolve_empresa(nombre):
    """Devuelve el id de una empresa por nombre; si no existe, la crea."""
    if not nombre:
        return None
    fila = query("SELECT id FROM empresas WHERE nombre=?", (nombre,), one=True)
    if fila:
        return fila["id"]
    return execute("INSERT INTO empresas (nombre) VALUES (?)", (nombre,))


@app.context_processor
def inject_globals():
    global CURRENCY
    try:
        CURRENCY = (get_ajustes().get("moneda") or "EUR").upper()
    except Exception:
        CURRENCY = "EUR"
    return {
        "etapas": ETAPAS,
        "hoy": date.today().isoformat(),
        "moneda_simbolo": SIMBOLOS_MONEDA.get(CURRENCY, CURRENCY + " "),
        "susc_estados": {
            "pendiente": "Pendiente de pago",
            "activa": "Activa",
            "vencida": "Vencida",
            "cancelada": "Cancelada",
        },
        "pago_estados": {
            "pendiente": "Pendiente",
            "aprobado": "Aprobado",
            "rechazado": "Rechazado",
            "fallo": "Fallo",
        },
    }


@app.route("/")
def index():
    db = get_db()
    resumen = {
        "empresas": query("SELECT COUNT(*) c FROM empresas", one=True)["c"],
        "contactos": query("SELECT COUNT(*) c FROM contactos", one=True)["c"],
        "ventas_activas": query(
            "SELECT COUNT(*) c FROM ventas WHERE etapa NOT IN ('Ganado','Perdido')",
            one=True,
        )["c"],
        "ventas_ganadas": query(
            "SELECT COUNT(*) c FROM ventas WHERE etapa='Ganado'", one=True
        )["c"],
        "valor_ganado": query(
            "SELECT COALESCE(SUM(valor),0) c FROM ventas WHERE etapa='Ganado'",
            one=True,
        )["c"],
        "valor_pipeline": query(
            "SELECT COALESCE(SUM(valor),0) c FROM ventas WHERE etapa NOT IN ('Ganado','Perdido')",
            one=True,
        )["c"],
        "tareas_pendientes": query(
            "SELECT COUNT(*) c FROM tareas WHERE completada=0", one=True
        )["c"],
        "citas_hoy": query(
            "SELECT COUNT(*) c FROM citas WHERE fecha=?", (date.today().isoformat(),),
            one=True,
        )["c"],
        "mensajes_pend": query(
            "SELECT COUNT(*) c FROM mensajes WHERE estado IN ('pendiente','preparado')",
            one=True,
        )["c"],
    }
    ultimas_ventas = query(
        """SELECT v.*, c.nombre contacto, e.nombre empresa
           FROM ventas v LEFT JOIN contactos c ON c.id=v.contacto_id
           LEFT JOIN empresas e ON e.id=v.empresa_id
           ORDER BY v.id DESC LIMIT 5"""
    )
    proximas_citas = query(
        """SELECT ci.*, c.nombre contacto, e.nombre empresa
           FROM citas ci LEFT JOIN contactos c ON c.id=ci.contacto_id
           LEFT JOIN empresas e ON e.id=ci.empresa_id
           WHERE ci.fecha >= ? ORDER BY ci.fecha ASC LIMIT 5""",
        (date.today().isoformat(),),
    )
    tareas_pend = query(
        """SELECT t.*, c.nombre contacto
           FROM tareas t LEFT JOIN contactos c ON c.id=t.contacto_id
           WHERE t.completada=0 ORDER BY COALESCE(CAST(t.vencimiento AS TEXT),'9999') ASC LIMIT 5"""
    )
    pipeline = query(
        "SELECT etapa, COUNT(*) c, COALESCE(SUM(valor),0) v FROM ventas GROUP BY etapa"
    )
    return render_template(
        "index.html",
        resumen=resumen,
        ultimas_ventas=ultimas_ventas,
        proximas_citas=proximas_citas,
        tareas_pend=tareas_pend,
        pipeline=pipeline,
    )


# ----------------------- EMPRESAS -----------------------
@app.route("/empresas")
def empresas():
    lista = query("SELECT * FROM empresas ORDER BY nombre")
    return render_template("empresas.html", lista=lista)


@app.route("/empresas/nueva", methods=["POST"])
def empresa_nueva():
    d = form_val("nombre", "sector", "telefono", "email", "web", "direccion", "notas")
    if not d["nombre"]:
        flash("El nombre es obligatorio", "error")
    else:
        execute(
            """INSERT INTO empresas (nombre, sector, telefono, email, web, direccion, notas)
               VALUES (?,?,?,?,?,?,?)""",
            tuple(d.values()),
        )
        flash("Empresa añadida", "ok")
    return redirect(url_for("empresas"))


@app.route("/empresas/<int:eid>/editar", methods=["POST"])
def empresa_editar(eid):
    d = form_val("nombre", "sector", "telefono", "email", "web", "direccion", "notas")
    if not d["nombre"]:
        flash("El nombre es obligatorio", "error")
    else:
        execute(
            """UPDATE empresas SET nombre=?, sector=?, telefono=?, email=?, web=?,
               direccion=?, notas=? WHERE id=?""",
            tuple(d.values()) + (eid,),
        )
        flash("Empresa actualizada", "ok")
    return redirect(url_for("empresas"))


@app.route("/empresas/<int:eid>/eliminar", methods=["POST"])
def empresa_eliminar(eid):
    execute("DELETE FROM empresas WHERE id=?", (eid,))
    flash("Empresa eliminada", "ok")
    return redirect(url_for("empresas"))


@app.route("/empresas/<int:eid>")
def empresa_detalle(eid):
    emp = query("SELECT * FROM empresas WHERE id=?", (eid,), one=True)
    if not emp:
        return redirect(url_for("empresas"))
    contactos_lista = query(
        "SELECT * FROM contactos WHERE empresa_id=? ORDER BY nombre", (eid,)
    )
    ventas_lista = query("SELECT * FROM ventas WHERE empresa_id=? ORDER BY id DESC", (eid,))
    notas_lista = query("SELECT * FROM notas WHERE empresa_id=? ORDER BY id DESC", (eid,))
    tareas_lista = query("SELECT * FROM tareas WHERE empresa_id=? ORDER BY id DESC", (eid,))
    return render_template(
        "empresa.html",
        emp=emp,
        contactos_lista=contactos_lista,
        ventas_lista=ventas_lista,
        notas_lista=notas_lista,
        tareas_lista=tareas_lista,
        plantillas=plantillas_activas(),
        contacto_sel=None,
        venta_sel=None,
        empresa_sel=emp["id"],
        enlaces_wa=enlaces_wa("empresa", emp, None, None),
    )


# ----------------------- CONTACTOS -----------------------
@app.route("/contactos")
def contactos():
    lista = query(
        """SELECT co.*, e.nombre empresa FROM contactos co
           LEFT JOIN empresas e ON e.id=co.empresa_id ORDER BY co.nombre"""
    )
    empresas_lista = query("SELECT id, nombre FROM empresas ORDER BY nombre")
    return render_template("contactos.html", lista=lista, empresas_lista=empresas_lista)


@app.route("/contactos/nuevo", methods=["POST"])
def contacto_nuevo():
    d = form_val("nombre", "email", "telefono", "cargo", "notas")
    empresa_id = resolve_empresa(request.form.get("empresa_nombre", "").strip())
    if not d["nombre"]:
        flash("El nombre es obligatorio", "error")
    else:
        execute(
            """INSERT INTO contactos (nombre, email, telefono, cargo, empresa_id, notas)
               VALUES (?,?,?,?,?,?)""",
            (d["nombre"], d["email"], d["telefono"], d["cargo"],
             empresa_id, d["notas"]),
        )
        flash("Contacto añadido", "ok")
    return redirect(url_for("contactos"))


@app.route("/contactos/<int:cid>/editar", methods=["POST"])
def contacto_editar(cid):
    d = form_val("nombre", "email", "telefono", "cargo", "notas")
    empresa_id = resolve_empresa(request.form.get("empresa_nombre", "").strip())
    if not d["nombre"]:
        flash("El nombre es obligatorio", "error")
    else:
        execute(
            """UPDATE contactos SET nombre=?, email=?, telefono=?, cargo=?, empresa_id=?, notas=?
               WHERE id=?""",
            (d["nombre"], d["email"], d["telefono"], d["cargo"],
             empresa_id, d["notas"], cid),
        )
        flash("Contacto actualizado", "ok")
    return redirect(url_for("contactos"))


@app.route("/contactos/<int:cid>/eliminar", methods=["POST"])
def contacto_eliminar(cid):
    execute("DELETE FROM contactos WHERE id=?", (cid,))
    flash("Contacto eliminado", "ok")
    return redirect(url_for("contactos"))


@app.route("/contactos/<int:cid>")
def contacto_detalle(cid):
    cont = query(
        """SELECT co.*, e.nombre empresa, e.id empresa_id FROM contactos co
           LEFT JOIN empresas e ON e.id=co.empresa_id WHERE co.id=?""",
        (cid,),
        one=True,
    )
    if not cont:
        return redirect(url_for("contactos"))
    ventas_lista = query("SELECT * FROM ventas WHERE contacto_id=? ORDER BY id DESC", (cid,))
    notas_lista = query("SELECT * FROM notas WHERE contacto_id=? ORDER BY id DESC", (cid,))
    tareas_lista = query("SELECT * FROM tareas WHERE contacto_id=? ORDER BY id DESC", (cid,))
    empresa_row = query("SELECT * FROM empresas WHERE id=?", (cont["empresa_id"],), one=True) if cont["empresa_id"] else None
    return render_template(
        "contacto.html",
        cont=cont,
        ventas_lista=ventas_lista,
        notas_lista=notas_lista,
        tareas_lista=tareas_lista,
        plantillas=plantillas_activas(),
        contacto_sel=cont["id"],
        venta_sel=None,
        empresa_sel=cont["empresa_id"],
        enlaces_wa=enlaces_wa("contacto", cont, None, empresa_row),
    )


# ----------------------- VENTAS -----------------------
@app.route("/ventas")
def ventas():
    lista = query(
        """SELECT v.*, c.nombre contacto, e.nombre empresa FROM ventas v
           LEFT JOIN contactos c ON c.id=v.contacto_id
           LEFT JOIN empresas e ON e.id=v.empresa_id
           ORDER BY v.id DESC"""
    )
    contactos_lista = query("SELECT id, nombre FROM contactos ORDER BY nombre")
    empresas_lista = query("SELECT id, nombre FROM empresas ORDER BY nombre")
    return render_template(
        "ventas.html",
        lista=lista,
        contactos_lista=contactos_lista,
        empresas_lista=empresas_lista,
        resumen=None,
    )


@app.route("/ventas/nueva", methods=["POST"])
def venta_nueva():
    d = form_val("titulo", "etapa", "fecha_cierre", "descripcion")
    valor = request.form.get("valor", "0")
    empresa_id = request.form.get("empresa_id", "")
    contacto_id = request.form.get("contacto_id", "")
    if not d["titulo"]:
        flash("El título es obligatorio", "error")
    else:
        try:
            valor = float(valor)
        except ValueError:
            valor = 0
        execute(
            """INSERT INTO ventas (titulo, valor, etapa, empresa_id, contacto_id,
               descripcion, fecha_cierre) VALUES (?,?,?,?,?,?,?)""",
            (d["titulo"], valor, d["etapa"],
             int(empresa_id) if empresa_id else None,
             int(contacto_id) if contacto_id else None,
             d["descripcion"], d["fecha_cierre"] or None),
        )
        flash("Venta añadida", "ok")
    return redirect(url_for("ventas"))


@app.route("/ventas/<int:vid>/editar", methods=["POST"])
def venta_editar(vid):
    d = form_val("titulo", "etapa", "fecha_cierre", "descripcion")
    valor = request.form.get("valor", "0")
    empresa_id = request.form.get("empresa_id", "")
    contacto_id = request.form.get("contacto_id", "")
    if not d["titulo"]:
        flash("El título es obligatorio", "error")
    else:
        try:
            valor = float(valor)
        except ValueError:
            valor = 0
        execute(
            """UPDATE ventas SET titulo=?, valor=?, etapa=?, empresa_id=?, contacto_id=?,
               descripcion=?, fecha_cierre=? WHERE id=?""",
            (d["titulo"], valor, d["etapa"],
             int(empresa_id) if empresa_id else None,
             int(contacto_id) if contacto_id else None,
             d["descripcion"], d["fecha_cierre"] or None, vid),
        )
        flash("Venta actualizada", "ok")
    return redirect(url_for("ventas"))


@app.route("/ventas/<int:vid>/etapa", methods=["POST"])
def venta_etapa(vid):
    etapa = request.form.get("etapa", "")
    if etapa in ETAPAS:
        execute("UPDATE ventas SET etapa=? WHERE id=?", (etapa, vid))
    return redirect(url_for("ventas"))


@app.route("/ventas/<int:vid>/eliminar", methods=["POST"])
def venta_eliminar(vid):
    execute("DELETE FROM ventas WHERE id=?", (vid,))
    flash("Venta eliminada", "ok")
    return redirect(url_for("ventas"))


@app.route("/ventas/<int:vid>")
def venta_detalle(vid):
    vent = query(
        """SELECT v.*, c.nombre contacto, e.nombre empresa FROM ventas v
           LEFT JOIN contactos c ON c.id=v.contacto_id
           LEFT JOIN empresas e ON e.id=v.empresa_id WHERE v.id=?""",
        (vid,),
        one=True,
    )
    if not vent:
        return redirect(url_for("ventas"))
    notas_lista = query("SELECT * FROM notas WHERE venta_id=? ORDER BY id DESC", (vid,))
    contacto_row = query("SELECT * FROM contactos WHERE id=?", (vent["contacto_id"],), one=True) if vent["contacto_id"] else None
    empresa_row = query("SELECT * FROM empresas WHERE id=?", (vent["empresa_id"],), one=True) if vent["empresa_id"] else None
    return render_template(
        "venta.html",
        vent=vent,
        notas_lista=notas_lista,
        plantillas=plantillas_activas(),
        contacto_sel=vent["contacto_id"],
        venta_sel=vent["id"],
        empresa_sel=vent["empresa_id"],
        enlaces_wa=enlaces_wa("venta", contacto_row, vent, empresa_row),
    )


# ----------------------- TAREAS -----------------------
@app.route("/tareas")
def tareas():
    filtro = request.args.get("f", "pendientes")
    if filtro == "todas":
        lista = query(
            """SELECT t.*, c.nombre contacto, e.nombre empresa FROM tareas t
               LEFT JOIN contactos c ON c.id=t.contacto_id
               LEFT JOIN empresas e ON e.id=t.empresa_id ORDER BY t.id DESC"""
        )
    else:
        lista = query(
            """SELECT t.*, c.nombre contacto, e.nombre empresa FROM tareas t
               LEFT JOIN contactos c ON c.id=t.contacto_id
               LEFT JOIN empresas e ON e.id=t.empresa_id
               WHERE t.completada=0 ORDER BY COALESCE(CAST(t.vencimiento AS TEXT),'9999') ASC"""
        )
    contactos_lista = query("SELECT id, nombre FROM contactos ORDER BY nombre")
    empresas_lista = query("SELECT id, nombre FROM empresas ORDER BY nombre")
    return render_template(
        "tareas.html",
        lista=lista,
        filtro=filtro,
        contactos_lista=contactos_lista,
        empresas_lista=empresas_lista,
    )


@app.route("/tareas/nueva", methods=["POST"])
def tarea_nueva():
    d = form_val("titulo", "vencimiento", "descripcion")
    contacto_id = request.form.get("contacto_id", "")
    empresa_id = request.form.get("empresa_id", "")
    if not d["titulo"]:
        flash("El título es obligatorio", "error")
    else:
        execute(
            """INSERT INTO tareas (titulo, descripcion, vencimiento, contacto_id, empresa_id)
               VALUES (?,?,?,?,?)""",
            (d["titulo"], d["descripcion"], d["vencimiento"] or None,
             int(contacto_id) if contacto_id else None,
             int(empresa_id) if empresa_id else None),
        )
        flash("Tarea añadida", "ok")
    return redirect(url_for("tareas"))


@app.route("/tareas/<int:tid>/completar", methods=["POST"])
def tarea_completar(tid):
    execute("UPDATE tareas SET completada = 1 - completada WHERE id=?", (tid,))
    return redirect(request.referrer or url_for("tareas"))


@app.route("/tareas/<int:tid>/eliminar", methods=["POST"])
def tarea_eliminar(tid):
    execute("DELETE FROM tareas WHERE id=?", (tid,))
    flash("Tarea eliminada", "ok")
    return redirect(request.referrer or url_for("tareas"))


# ----------------------- CITAS -----------------------
@app.route("/citas")
def citas():
    lista = query(
        """SELECT ci.*, c.nombre contacto, e.nombre empresa FROM citas ci
           LEFT JOIN contactos c ON c.id=ci.contacto_id
           LEFT JOIN empresas e ON e.id=ci.empresa_id
           ORDER BY ci.fecha DESC, ci.hora ASC"""
    )
    contactos_lista = query("SELECT id, nombre FROM contactos ORDER BY nombre")
    empresas_lista = query("SELECT id, nombre FROM empresas ORDER BY nombre")
    return render_template(
        "citas.html",
        lista=lista,
        contactos_lista=contactos_lista,
        empresas_lista=empresas_lista,
    )


@app.route("/citas/nueva", methods=["POST"])
def cita_nueva():
    d = form_val("titulo", "fecha", "hora", "descripcion")
    contacto_id = request.form.get("contacto_id", "")
    empresa_id = request.form.get("empresa_id", "")
    if not d["titulo"] or not d["fecha"]:
        flash("Título y fecha son obligatorios", "error")
    else:
        execute(
            """INSERT INTO citas (titulo, fecha, hora, descripcion, contacto_id, empresa_id)
               VALUES (?,?,?,?,?,?)""",
            (d["titulo"], d["fecha"], d["hora"], d["descripcion"],
             int(contacto_id) if contacto_id else None,
             int(empresa_id) if empresa_id else None),
        )
        flash("Cita añadida", "ok")
    return redirect(url_for("citas"))


@app.route("/citas/<int:cid>/editar", methods=["POST"])
def cita_editar(cid):
    d = form_val("titulo", "fecha", "hora", "descripcion")
    contacto_id = request.form.get("contacto_id", "")
    empresa_id = request.form.get("empresa_id", "")
    if not d["titulo"] or not d["fecha"]:
        flash("Título y fecha son obligatorios", "error")
    else:
        execute(
            """UPDATE citas SET titulo=?, fecha=?, hora=?, descripcion=?, contacto_id=?,
               empresa_id=? WHERE id=?""",
            (d["titulo"], d["fecha"], d["hora"], d["descripcion"],
             int(contacto_id) if contacto_id else None,
             int(empresa_id) if empresa_id else None, cid),
        )
        flash("Cita actualizada", "ok")
    return redirect(url_for("citas"))


@app.route("/citas/<int:cid>/eliminar", methods=["POST"])
def cita_eliminar(cid):
    execute("DELETE FROM citas WHERE id=?", (cid,))
    flash("Cita eliminada", "ok")
    return redirect(url_for("citas"))


# ----------------------- NOTAS -----------------------
@app.route("/notas/nueva", methods=["POST"])
def nota_nueva():
    contenido = request.form.get("contenido", "").strip()
    contacto_id = request.form.get("contacto_id", "")
    empresa_id = request.form.get("empresa_id", "")
    venta_id = request.form.get("venta_id", "")
    if contenido:
        execute(
            """INSERT INTO notas (contenido, contacto_id, empresa_id, venta_id)
               VALUES (?,?,?,?)""",
            (contenido,
             int(contacto_id) if contacto_id else None,
             int(empresa_id) if empresa_id else None,
             int(venta_id) if venta_id else None),
        )
        flash("Nota añadida", "ok")
    return redirect(request.referrer or url_for("index"))


@app.route("/notas/<int:nid>/eliminar", methods=["POST"])
def nota_eliminar(nid):
    execute("DELETE FROM notas WHERE id=?", (nid,))
    flash("Nota eliminada", "ok")
    return redirect(request.referrer or url_for("index"))


# ----------------------- MENSAJES Y AUTOMATIZACIÓN -----------------------
def get_ajustes():
    return {r["clave"]: r["valor"] for r in query("SELECT clave, valor FROM ajustes")}


def set_ajuste(clave, valor):
    execute(
        "INSERT INTO ajustes (clave, valor) VALUES (?, ?) "
        "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
        (clave, valor),
    )


# ---------------------------------------------------------------------------
# Suscripciones (SaaS)
# ---------------------------------------------------------------------------
@app.template_filter("qr")
def qr_svg(value):
    """Genera un QR en SVG (data URI) para mostrar con la app Nequi."""
    if not value:
        return ""
    try:
        import base64
        import io
        import xml.etree.ElementTree as ET

        import qrcode
        from qrcode.image.svg import SvgPathImage

        img = qrcode.make(str(value), image_factory=SvgPathImage, box_size=6)
        buf = io.BytesIO()
        ET.ElementTree(img.get_image()).write(buf, encoding="utf-8")
        return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


def _sumar_ciclo(fecha, ciclo):
    """Suma un periodo (1 mes o 1 año) a una fecha ISO; devuelve fecha ISO."""
    if fecha is None:
        d = date.today()
    elif isinstance(fecha, str):
        try:
            d = datetime.strptime(fecha[:10], "%Y-%m-%d").date()
        except ValueError:
            d = date.today()
    else:
        d = fecha
    meses = 12 if (ciclo or "").lower() == "anual" else 1
    m = d.month - 1 + meses
    y = d.year + m // 12
    m = m % 12 + 1
    ultimo = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, ultimo)).isoformat()


def _precio_plan(plan, ciclo):
    if not plan:
        return 0
    return float(plan["precio_anual"] or 0) if (ciclo or "").lower() == "anual" else float(plan["precio_mensual"] or 0)


def _susc_detalle(sid):
    return query(
        """SELECT s.*, e.nombre empresa_c, e.telefono empresa_tel, e.email empresa_email,
                  p.nombre plan_c, p.precio_mensual, p.precio_anual,
                  p.limite_usuarios, p.limite_contactos
           FROM suscripciones s
           LEFT JOIN empresas e ON e.id=s.empresa_id
           LEFT JOIN planes p ON p.id=s.plan_id
           WHERE s.id=?""",
        (sid,),
        one=True,
    )


def _lista_susc():
    return query(
        """SELECT s.*, e.nombre empresa_c, p.nombre plan_c, p.precio_mensual,
                  p.precio_anual, p.limite_usuarios, p.limite_contactos
           FROM suscripciones s
           LEFT JOIN empresas e ON e.id=s.empresa_id
           LEFT JOIN planes p ON p.id=s.plan_id
           ORDER BY s.id DESC"""
    )


def _stats_susc():
    lista = _lista_susc()
    hoy = date.today()
    limite = (hoy + timedelta(days=30)).isoformat()
    activas = [s for s in lista if s["estado"] == "activa"]
    vencidas = [s for s in lista if s["estado"] == "vencida"]
    por_vencer = [s for s in activas if s["proximo_pago"] and s["proximo_pago"] <= limite]
    mrr = sum(
        (float(s["precio_anual"] or 0) / 12) if s["ciclo"] == "anual" else float(s["precio_mensual"] or 0)
        for s in activas
    )
    return {
        "lista": lista,
        "activas": len(activas),
        "vencidas": len(vencidas),
        "por_vencer": len(por_vencer),
        "mrr": mrr,
        "total": len(lista),
    }


def _certificar_pago(pago_id, trans_id="", pagado=True):
    """Marca un pago como aprobado/rechazado y actualiza la suscripción."""
    pago = query("SELECT * FROM pagos WHERE id=?", (pago_id,), one=True)
    if not pago:
        return
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hoy = date.today().isoformat()
    execute(
        "UPDATE pagos SET estado=?, transaction_id=COALESCE(NULLIF(?,''), transaction_id), "
        "pagado_en=? WHERE id=?",
        ("aprobado" if pagado else "rechazado", trans_id, ahora if pagado else None, pago_id),
    )
    if not pagado or not pago["suscripcion_id"]:
        return
    sub = query("SELECT * FROM suscripciones WHERE id=?", (pago["suscripcion_id"],), one=True)
    if not sub:
        return
    inicio = sub["inicio"] or (sub["ultimo_pago"] or hoy)
    prox = _sumar_ciclo(hoy, sub["ciclo"] or "mensual")
    execute(
        "UPDATE suscripciones SET estado='activa', ultimo_pago=?, proximo_pago=?, "
        "inicio=COALESCE(inicio, ?) WHERE id=?",
        (hoy, prox, hoy, sub["id"]),
    )


def _nuevo_pago(sid, gateway, base_url):
    """Crea un cargo pendiente y genera el enlace de pago. Devuelve (pago_id, error)."""
    sub = _susc_detalle(sid)
    if not sub:
        return None, "La suscripción no existe."
    plan = query("SELECT * FROM planes WHERE id=?", (sub["plan_id"],), one=True)
    if not plan:
        return None, "El plan de la suscripción ya no existe."
    monto = _precio_plan(plan, sub["ciclo"] or "mensual")
    if monto <= 0:
        return None, "El plan no tiene precio. Configúralo en Planes."
    gateway = (gateway or "").lower()
    # Nequi cobra en pesos colombianos (COP), sin decimales
    moneda = "COP" if gateway == "nequi" else (get_ajustes().get("moneda") or "EUR").upper()
    pid = execute(
        "INSERT INTO pagos (suscripcion_id, monto, moneda, metodo, estado) "
        "VALUES (?, ?, ?, ?, 'pendiente')",
        (sid, monto, moneda, gateway or "manual"),
    )
    if not gateway:
        return pid, ""
    retorno = base_url.rstrip("/") + url_for("suscripcion_detalle", sid=sid)
    concepto = f"Suscripción CRM — {sub['empresa_c'] or 'Cliente'} · {plan['nombre']}"
    url_pago, trans_id, err = pasarela.generar_link(
        get_ajustes(), gateway, monto, moneda, concepto, pid, retorno, retorno
    )
    if url_pago:
        execute("UPDATE pagos SET url_pago=?, transaction_id=? WHERE id=?", (url_pago, trans_id, pid))
    else:
        execute("UPDATE pagos SET detalle=? WHERE id=?", (err or "Sin pasarela configurada", pid))
    return pid, err


def rellenar(texto, contacto=None, venta=None, empresa=None):
    """Sustituye {variables} en una plantilla."""
    c = dict(contacto) if contacto else {}
    v = dict(venta) if venta else {}
    e = dict(empresa) if empresa else {}
    mapa = {
        "nombre_contacto": c.get("nombre", ""),
        "email_contacto": c.get("email", ""),
        "telefono_contacto": c.get("telefono", ""),
        "cargo": c.get("cargo", ""),
        "empresa": e.get("nombre", "") or v.get("empresa", "") or "",
        "titulo_venta": v.get("titulo", ""),
        "valor": money_format(v.get("valor")),
        "etapa": v.get("etapa", ""),
        "fecha_cierre": v.get("fecha_cierre") or "",
        "hoy": date.today().strftime("%d/%m/%Y"),
    }
    for k, val in mapa.items():
        texto = texto.replace("{" + k + "}", str(val))
    return texto


def wa_link(telefono, texto):
    """Genera enlace de WhatsApp con el mensaje pre-escrito."""
    num = re.sub(r"\D", "", str(telefono or ""))
    if not num:
        return None
    return f"https://wa.me/{num}?text={urllib.parse.quote(texto)}"


def enviar_email(dest, asunto, cuerpo):
    cfg = get_ajustes()
    host = cfg.get("smtp_host", "")
    usuario = cfg.get("smtp_usuario", "")
    password = cfg.get("smtp_password", "")
    if not (host and usuario):
        raise RuntimeError("SMTP no configurado")
    try:
        puerto = int(cfg.get("smtp_port", "587"))
    except ValueError:
        puerto = 587
    desde = cfg.get("smtp_desde") or usuario
    msg = MIMEText(cuerpo, "plain", "utf-8")
    msg["Subject"] = str(Header(asunto, "utf-8"))
    msg["From"] = desde
    msg["To"] = dest
    msg["Message-ID"] = f"<crm{int(time.time() * 1000)}@crm.local>"
    server = smtplib.SMTP(host, puerto, timeout=15)
    try:
        server.ehlo()
        if not cfg.get("smtp_ssl"):
            server.starttls()
        server.login(usuario, password)
        server.send_message(msg)
    finally:
        server.quit()
    return msg["Message-ID"]


def destinos_de(contacto, empresa):
    contacto = dict(contacto) if contacto else {}
    empresa = dict(empresa) if empresa else {}
    tel = contacto.get("telefono") or empresa.get("telefono") or ""
    mail = contacto.get("email") or empresa.get("email") or ""
    return tel, mail


def plantillas_activas():
    return query(
        "SELECT * FROM plantillas WHERE activa=1 ORDER BY canal, nombre"
    )


def enlaces_wa(tipo, contacto, venta, empresa):
    """Lista de enlaces wa.me ya pre-escritos para los botones de 1 clic."""
    plantillas = query(
        "SELECT * FROM plantillas WHERE activa=1 AND canal='whatsapp'"
    )
    if not plantillas:
        return []
    tel, _ = destinos_de(contacto, empresa)
    if not tel:
        return [(p["nombre"], None) for p in plantillas]
    links = []
    for p in plantillas:
        cuerpo = rellenar(p["cuerpo"], contacto, venta, empresa)
        links.append((p["nombre"], wa_link(tel, cuerpo)))
    return links


def detectar_respuestas():
    """Revisa IMAP y marca como respondidos los emails que el cliente contestó."""
    cfg = get_ajustes()
    if not cfg.get("imap_activo"):
        return
    usuario = cfg.get("smtp_usuario", "")
    password = cfg.get("smtp_password", "")
    host = cfg.get("imap_host") or "imap.gmail.com"
    if not (usuario and password):
        return
    enviados = query(
        "SELECT id, message_id, para FROM mensajes "
        "WHERE canal='email' AND estado='enviado' AND respondido=0 AND message_id!=''"
    )
    if not enviados:
        return
    ids_por_ref = {}
    for e in enviados:
        mid = e["message_id"]
        for ref in re.split(r">?\s*,?\s*<|,", mid):
            ref = ref.strip().strip("<").strip(">")
            if ref:
                ids_por_ref[ref] = e["id"]
    try:
        con = imaplib.IMAP4_SSL(host, timeout=20)
    except Exception:
        return
    try:
        con.login(usuario, password)
        con.select("INBOX")
        oraciones = " OR ".join(
            [f'(HEADER "In-Reply-To" "{ref}")' for ref in ids_por_ref][:30]
        )
        if not oraciones or not ids_por_ref:
            return
        _, data = con.search(None, oraciones)
        respondidos = set()
        for num_b in (data[0] or b"").split():
            try:
                _, msg_data = con.fetch(num_b, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO)])")
                raw = msg_data[0][1].decode("utf-8", "ignore")
                candidato = re.search(r"IN-Reply-To:\s*<([^>]+)>", raw, re.I)
                if candidato:
                    ref = candidato.group(1).strip()
                    if ref in ids_por_ref:
                        respondidos.add(ids_por_ref[ref])
            except Exception:
                continue
        for mid in respondidos:
            execute("UPDATE mensajes SET respondido=1 WHERE id=?", (mid,))
            execute("DELETE FROM mensajes WHERE reenvio_de=? AND estado='pendiente'", (mid,))
    except Exception:
        pass
    finally:
        try:
            con.logout()
        except Exception:
            pass


def run_automation():
    """Motor que se ejecuta en segundo plano cada minuto."""
    cfg = get_ajustes()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")

    detectar_respuestas()

    # 1) Enviar mensajes programados que ya vencen
    debidos = query(
        "SELECT * FROM mensajes WHERE estado='pendiente' "
        "AND substr(CAST(enviar_en AS TEXT),1,16) <= ?",
        (ahora,),
    )
    for m in debidos:
        if m["canal"] == "whatsapp":
            execute("UPDATE mensajes SET estado='preparado' WHERE id=?", (m["id"],))
            continue
        # email
        try:
            mensaje_id = enviar_email(m["para"], m["asunto"], m["cuerpo"])
            execute(
                "UPDATE mensajes SET estado='enviado', enviado_en=?, message_id=? WHERE id=?",
                (ahora, mensaje_id, m["id"]),
            )
            # 2) Recordatorio automático: reenvío si no hay respuesta en X días
            dias = int(cfg.get("resend_dias") or 3)
            ya = query(
                "SELECT id FROM mensajes WHERE reenvio_de=? AND estado IN ('pendiente','enviado')",
                (m["id"],),
                one=True,
            )
            if not ya:
                cuando = (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%d %H:%M")
                execute(
                    """INSERT INTO mensajes (canal, asunto, cuerpo, contacto_id, venta_id,
                       para, enviar_en, estado, origen, reenvio_de)
                       VALUES ('email', ?, ?, ?, ?, ?, ?, 'pendiente', 'reenvio', ?)""",
                    (
                        "[Recordatorio] " + m["asunto"],
                        "Le recordamos nuestro mensaje anterior:\n\n" + m["cuerpo"],
                        m["contacto_id"], m["venta_id"], m["para"], cuando, m["id"],
                    ),
                )
        except Exception as e:
            execute(
                "UPDATE mensajes SET estado='fallo', error=? WHERE id=?",
                (str(e)[:200], m["id"]),
            )

    # 3) Alertas de ventas estancadas -> crea tarea de seguimiento
    try:
        idle = int(cfg.get("idle_dias") or 3)
    except ValueError:
        idle = 3
    activas = query(
        """SELECT v.*, c.nombre contacto_c, c.id contacto_id,
                  e.nombre empresa_c, e.id empresa_id
           FROM ventas v
           LEFT JOIN contactos c ON c.id=v.contacto_id
           LEFT JOIN empresas e ON e.id=v.empresa_id
           WHERE v.etapa NOT IN ('Ganado','Perdido')"""
    )
    for v in activas:
        v = dict(v)
        ultima = v["creado"]
        fila = query(
            "SELECT MAX(creado) c FROM notas WHERE venta_id=?", (v["id"],), one=True
        )
        if fila and fila["c"] and fila["c"] > ultima:
            ultima = fila["c"]
        try:
            desde = datetime.strptime(ultima, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            desde = datetime.now()
        dias = (datetime.now() - desde).days
        if dias >= idle:
            titulo = f"Seguimiento: {v['titulo']} lleva {dias} días en {v['etapa']}"
            dup = query(
                "SELECT id FROM tareas WHERE titulo=? AND completada=0",
                (titulo,),
                one=True,
            )
            if not dup:
                execute(
                    """INSERT INTO tareas (titulo, descripcion, vencimiento, contacto_id, empresa_id)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        titulo,
                        f"Valor: {money_format(v['valor'])}. "
                        f"Cliente: {v.get('contacto_c') or v.get('empresa_c') or '—'}",
                        (date.today() + timedelta(days=1)).isoformat(),
                        v["contacto_id"], v["empresa_id"],
                    ),
                )

    # 4) Suscripciones: marcar vencidas y crear aviso de renovación
    try:
        hoy_s = date.today().isoformat()
        activas = query(
            """SELECT s.*, e.nombre empresa_c, p.nombre plan_c
               FROM suscripciones s
               LEFT JOIN empresas e ON e.id=s.empresa_id
               LEFT JOIN planes p ON p.id=s.plan_id
               WHERE s.estado='activa'"""
        )
        for s in activas:
            if s["proximo_pago"] and s["proximo_pago"] <= hoy_s:
                execute("UPDATE suscripciones SET estado='vencida' WHERE id=?", (s["id"],))
                titulo = f"Renovar suscripción de {s['empresa_c'] or 'cliente'} — {s['plan_c'] or 'sin plan'}"
                dup = query(
                    "SELECT id FROM tareas WHERE titulo=? AND completada=0", (titulo,), one=True
                )
                if not dup:
                    execute(
                        "INSERT INTO tareas (titulo, descripcion, vencimiento) VALUES (?, ?, ?)",
                        (
                            titulo,
                            f"La suscripción venció el {s['proximo_pago']}. Genera el cobro de renovación.",
                            hoy_s,
                        ),
                    )
    except Exception:
        pass

    # 5) Nequi: confirmar pagos por QR (consulta de estado cada minuto)
    try:
        if (get_ajustes().get("pasarela") or "").lower() == "nequi":
            pendientes = query(
                "SELECT * FROM pagos WHERE estado='pendiente' AND metodo='nequi'"
            )
            for pg in pendientes:
                if not pg["url_pago"]:
                    continue
                res = pasarela.confirmar_evento(get_ajustes(), "nequi", {"qr": pg["url_pago"]})
                if res:
                    trans_id, aprobado, monto, ref = res
                    _certificar_pago(pg["id"], trans_id, pagado=aprobado)
    except Exception:
        pass


def scheduler_loop():
    while True:
        try:
            with app.app_context():
                run_automation()
        except Exception:
            pass
        time.sleep(60)


@app.route("/mensajes")
def mensajes():
    plantillas_lista = query("SELECT * FROM plantillas ORDER BY canal, nombre")
    cola = query(
        """SELECT m.*, c.nombre contacto, e.nombre empresa, v.titulo venta
           FROM mensajes m
           LEFT JOIN contactos c ON c.id=m.contacto_id
           LEFT JOIN empresas e ON e.id=m.empresa_id
           LEFT JOIN ventas v ON v.id=m.venta_id
           ORDER BY (m.estado='enviado'), m.enviar_en ASC"""
    )
    contactos_lista = query("SELECT id, nombre, email, telefono FROM contactos ORDER BY nombre")
    ventas_lista = query(
        "SELECT id, titulo FROM ventas WHERE etapa NOT IN ('Ganado','Perdido') "
        "ORDER BY id DESC"
    )
    ajustes = get_ajustes()
    cola_final = []
    for m in cola:
        m_dic = dict(m)
        m_dic["link"] = (
            wa_link(m["para"], m["cuerpo"])
            if m["canal"] == "whatsapp" and m["estado"] == "preparado"
            else None
        )
        cola_final.append(m_dic)
    return render_template(
        "mensajes.html",
        plantillas_lista=plantillas_lista,
        cola=cola_final,
        contactos_lista=contactos_lista,
        ventas_lista=ventas_lista,
        ajustes=ajustes,
    )


@app.route("/plantillas/nueva", methods=["POST"])
def plantilla_nueva():
    nombre = request.form.get("nombre", "").strip()
    canal = request.form.get("canal", "whatsapp")
    asunto = request.form.get("asunto", "").strip()
    cuerpo = request.form.get("cuerpo", "").strip()
    if not nombre or not cuerpo:
        flash("Nombre y cuerpo son obligatorios", "error")
    else:
        execute(
            "INSERT INTO plantillas (nombre, canal, asunto, cuerpo) VALUES (?,?,?,?)",
            (nombre, canal, asunto, cuerpo),
        )
        flash("Plantilla creada", "ok")
    return redirect(url_for("mensajes"))


@app.route("/plantillas/<int:tid>/editar", methods=["POST"])
def plantilla_editar(tid):
    nombre = request.form.get("nombre", "").strip()
    canal = request.form.get("canal", "whatsapp")
    asunto = request.form.get("asunto", "").strip()
    cuerpo = request.form.get("cuerpo", "").strip()
    activa = 1 if request.form.get("activa") else 0
    if not nombre or not cuerpo:
        flash("Nombre y cuerpo son obligatorios", "error")
    else:
        execute(
            "UPDATE plantillas SET nombre=?, canal=?, asunto=?, cuerpo=?, activa=? WHERE id=?",
            (nombre, canal, asunto, cuerpo, activa, tid),
        )
        flash("Plantilla actualizada", "ok")
    return redirect(url_for("mensajes"))


@app.route("/plantillas/<int:tid>/eliminar", methods=["POST"])
def plantilla_eliminar(tid):
    execute("DELETE FROM plantillas WHERE id=?", (tid,))
    flash("Plantilla eliminada", "ok")
    return redirect(url_for("mensajes"))


@app.route("/mensajes/nueva", methods=["POST"])
def mensaje_nueva():
    plantilla_id = request.form.get("plantilla_id", "")
    contacto_id = request.form.get("contacto_id", "")
    empresa_id = request.form.get("empresa_id", "")
    venta_id = request.form.get("venta_id", "")
    fecha_hora = request.form.get("fecha_hora", "").strip()
    para = request.form.get("para", "").strip()

    contacto = query("SELECT * FROM contactos WHERE id=?", (int(contacto_id) if contacto_id else 0,), one=True)
    empresa = query("SELECT * FROM empresas WHERE id=?", (int(empresa_id) if empresa_id else 0,), one=True)
    venta = query("SELECT * FROM ventas WHERE id=?", (int(venta_id) if venta_id else 0,), one=True)
    plantilla = query("SELECT * FROM plantillas WHERE id=?", (int(plantilla_id) if plantilla_id else 0,), one=True)

    if not plantilla:
        flash("Elige una plantilla", "error")
    else:
        cuerpo = rellenar(plantilla["cuerpo"], contacto, venta, empresa)
        asunto = rellenar(plantilla["asunto"], contacto, venta, empresa)
        canal = plantilla["canal"]
        tel, mail = destinos_de(contacto, empresa)
        if para:
            dest = para
        elif canal == "whatsapp":
            dest = tel
        else:
            dest = mail
        if not dest:
            flash("Sin teléfono/email para el cliente. Añádelo en su ficha.", "error")
        else:
            cuando = fecha_hora.replace("T", " ") if fecha_hora else datetime.now().strftime("%Y-%m-%d %H:%M")
            execute(
                """INSERT INTO mensajes (canal, asunto, cuerpo, contacto_id, empresa_id,
                   venta_id, para, enviar_en, estado, origen)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (canal, asunto, cuerpo,
                 int(contacto_id) if contacto_id else None,
                 int(empresa_id) if empresa_id else None,
                 int(venta_id) if venta_id else None,
                 dest, cuando, "pendiente", "plantilla"),
            )
            flash("Mensaje programado", "ok")
            if not fecha_hora:
                run_automation()
    return redirect(request.referrer or url_for("mensajes"))


@app.route("/mensajes/<int:mid>/enviar", methods=["POST"])
def mensaje_enviar(mid):
    m = query("SELECT * FROM mensajes WHERE id=?", (mid,), one=True)
    if m:
        if not m["enviar_en"] or m["estado"] != "enviado":
            execute(
                "UPDATE mensajes SET enviar_en=? WHERE id=?",
                (datetime.now().strftime("%Y-%m-%d %H:%M"), mid),
            )
        run_automation()
        flash("Procesado", "ok")
    return redirect(request.referrer or url_for("mensajes"))


@app.route("/mensajes/<int:mid>/respondido", methods=["POST"])
def mensaje_respondido(mid):
    execute("UPDATE mensajes SET respondido=1 WHERE id=?", (mid,))
    execute("DELETE FROM mensajes WHERE reenvio_de=? AND estado='pendiente'", (mid,))
    flash("Marcado como respondido", "ok")
    return redirect(request.referrer or url_for("mensajes"))


@app.route("/mensajes/<int:mid>/eliminar", methods=["POST"])
def mensaje_eliminar(mid):
    execute("DELETE FROM mensajes WHERE id=?", (mid,))
    flash("Mensaje eliminado", "ok")
    return redirect(request.referrer or url_for("mensajes"))


# ---------------------------------------------------------------------------
# Suscripciones (SaaS): planes, licencias y cobros
# ---------------------------------------------------------------------------
@app.route("/planes")
def planes():
    lista = query("SELECT * FROM planes ORDER BY id DESC")
    return render_template("planes.html", lista=lista)


@app.route("/planes/nueva", methods=["POST"])
def plan_nueva():
    d = form_val("nombre", "descripcion")
    if not d["nombre"]:
        flash("El plan necesita un nombre", "error")
        return redirect(url_for("planes"))
    try:
        pm = float(request.form.get("precio_mensual") or 0)
        pa = float(request.form.get("precio_anual") or 0)
        lu = int(request.form.get("limite_usuarios") or 1)
        lc = int(request.form.get("limite_contactos") or 0)
    except ValueError:
        flash("Precios y límites deben ser números", "error")
        return redirect(url_for("planes"))
    execute(
        "INSERT INTO planes (nombre, precio_mensual, precio_anual, limite_usuarios, "
        "limite_contactos, descripcion, activo) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (d["nombre"], pm, pa, lu, lc, d["descripcion"], 1 if request.form.get("activo") else 0),
    )
    flash("Plan creado", "ok")
    return redirect(url_for("planes"))


@app.route("/planes/<int:pid>/editar", methods=["POST"])
def plan_editar(pid):
    d = form_val("nombre", "descripcion")
    try:
        pm = float(request.form.get("precio_mensual") or 0)
        pa = float(request.form.get("precio_anual") or 0)
        lu = int(request.form.get("limite_usuarios") or 1)
        lc = int(request.form.get("limite_contactos") or 0)
    except ValueError:
        flash("Precios y límites deben ser números", "error")
        return redirect(url_for("planes"))
    execute(
        "UPDATE planes SET nombre=?, precio_mensual=?, precio_anual=?, limite_usuarios=?, "
        "limite_contactos=?, descripcion=?, activo=? WHERE id=?",
        (d["nombre"], pm, pa, lu, lc, d["descripcion"], 1 if request.form.get("activo") else 0, pid),
    )
    flash("Plan actualizado", "ok")
    return redirect(url_for("planes"))


@app.route("/planes/<int:pid>/eliminar", methods=["POST"])
def plan_eliminar(pid):
    execute("DELETE FROM planes WHERE id=?", (pid,))
    flash("Plan eliminado", "ok")
    return redirect(url_for("planes"))


@app.route("/suscripciones")
def suscripciones():
    stats = _stats_susc()
    planes_act = query("SELECT * FROM planes WHERE activo=1 ORDER BY nombre")
    empresas = query("SELECT id, nombre FROM empresas ORDER BY nombre")
    return render_template(
        "suscripciones.html", stats=stats, planes=planes_act, empresas=empresas
    )


@app.route("/suscripciones/nueva", methods=["POST"])
def suscripcion_nueva():
    try:
        empresa_id = int(request.form.get("empresa_id") or 0)
        plan_id = int(request.form.get("plan_id") or 0)
    except ValueError:
        empresa_id = plan_id = 0
    ciclo = request.form.get("ciclo") or "mensual"
    notas = request.form.get("notas", "").strip()
    if not empresa_id or not plan_id:
        flash("Selecciona la empresa y el plan", "error")
        return redirect(url_for("suscripciones"))
    plan = query("SELECT * FROM planes WHERE id=? AND activo=1", (plan_id,), one=True)
    if not plan:
        flash("El plan no existe o está inactivo", "error")
        return redirect(url_for("suscripciones"))
    sid = execute(
        "INSERT INTO suscripciones (empresa_id, plan_id, estado, ciclo, notas) "
        "VALUES (?, ?, 'pendiente', ?, ?)",
        (empresa_id, plan_id, ciclo, notas),
    )
    gateway = (get_ajustes().get("pasarela") or "").strip()
    if gateway:
        _nuevo_pago(sid, gateway, get_ajustes().get("public_url") or "http://127.0.0.1:5000")
    flash("Suscripción creada. Genera el cobro desde su ficha.", "ok")
    return redirect(url_for("suscripcion_detalle", sid=sid))


@app.route("/suscripciones/<int:sid>")
def suscripcion_detalle(sid):
    s = _susc_detalle(sid)
    if not s:
        flash("Suscripción no encontrada", "error")
        return redirect(url_for("suscripciones"))
    pagos = query("SELECT * FROM pagos WHERE suscripcion_id=? ORDER BY id DESC", (sid,))
    return render_template("suscripcion.html", s=s, pagos=pagos)


@app.route("/suscripciones/<int:sid>/pagar", methods=["POST"])
def suscripcion_pagar(sid):
    gateway = (get_ajustes().get("pasarela") or "").strip()
    base = get_ajustes().get("public_url") or "http://127.0.0.1:5000"
    pago_id, err = _nuevo_pago(sid, gateway, base)
    if err:
        flash(err, "error")
    else:
        mensaje = "QR de Nequi generado. El cliente debe escanearlo con su app." if gateway.lower() == "nequi" else "Cobro generado. Revisa el enlace en la ficha."
        flash(mensaje, "ok")
    return redirect(url_for("suscripcion_detalle", sid=sid))


@app.route("/suscripciones/<int:sid>/nequi/estado", methods=["POST"])
def suscripcion_nequi_estado(sid):
    pago = query(
        "SELECT * FROM pagos WHERE suscripcion_id=? AND estado='pendiente' AND metodo='nequi' "
        "ORDER BY id DESC",
        (sid,),
        one=True,
    )
    if not pago or not pago["url_pago"]:
        flash("No hay un cobro Nequi pendiente", "error")
        return redirect(url_for("suscripcion_detalle", sid=sid))
    res = pasarela.confirmar_evento(get_ajustes(), "nequi", {"qr": pago["url_pago"]})
    if not res:
        flash("El pago aún no se ha completado (o no se encuentra aprobado en Nequi).", "error")
        return redirect(url_for("suscripcion_detalle", sid=sid))
    trans_id, aprobado, monto, ref = res
    _certificar_pago(pago["id"], trans_id, pagado=aprobado)
    flash("¡Pago confirmado con Nequi! La suscripción está activa." if aprobado else "El pago no fue aprobado.", "ok" if aprobado else "error")
    return redirect(url_for("suscripcion_detalle", sid=sid))


@app.route("/suscripciones/<int:sid>/pagado", methods=["POST"])
def suscripcion_pagado(sid):
    pago = query(
        "SELECT * FROM pagos WHERE suscripcion_id=? AND estado='pendiente' ORDER BY id DESC",
        (sid,),
        one=True,
    )
    if not pago:
        s = _susc_detalle(sid)
        plan = query("SELECT * FROM planes WHERE id=?", (s["plan_id"],), one=True) if s else None
        monto = _precio_plan(plan, s["ciclo"] or "mensual") if plan else 0
        pago_id = execute(
            "INSERT INTO pagos (suscripcion_id, monto, moneda, metodo, estado) "
            "VALUES (?, ?, ?, 'manual', 'pendiente')",
            (sid, monto, get_ajustes().get("moneda") or "EUR"),
        )
    else:
        pago_id = pago["id"]
    _certificar_pago(pago_id, "", pagado=True)
    flash("Suscripción marcada como pagada", "ok")
    return redirect(url_for("suscripcion_detalle", sid=sid))


@app.route("/suscripciones/<int:sid>/prorrogar", methods=["POST"])
def suscripcion_prorrogar(sid):
    s = _susc_detalle(sid)
    if not s:
        flash("Suscripción no encontrada", "error")
        return redirect(url_for("suscripciones"))
    plan = query("SELECT * FROM planes WHERE id=?", (s["plan_id"],), one=True)
    monto = _precio_plan(plan, s["ciclo"] or "mensual") if plan else 0
    pid = execute(
        "INSERT INTO pagos (suscripcion_id, monto, moneda, metodo, estado, pagado_en) "
        "VALUES (?, ?, ?, 'manual', 'aprobado', ?)",
        (sid, monto, get_ajustes().get("moneda") or "EUR", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    _certificar_pago(pid, "", pagado=True)
    flash("Periodo renovado un ciclo más", "ok")
    return redirect(url_for("suscripcion_detalle", sid=sid))


@app.route("/suscripciones/<int:sid>/cancelar", methods=["POST"])
def suscripcion_cancelar(sid):
    execute("UPDATE suscripciones SET estado='cancelada' WHERE id=?", (sid,))
    flash("Suscripción cancelada", "ok")
    return redirect(url_for("suscripcion_detalle", sid=sid))


@app.route("/suscripciones/<int:sid>/reactivar", methods=["POST"])
def suscripcion_reactivar(sid):
    execute("UPDATE suscripciones SET estado='pendiente' WHERE id=?", (sid,))
    flash("Suscripción reactivada (pendiente de cobro)", "ok")
    return redirect(url_for("suscripcion_detalle", sid=sid))


@app.route("/suscripciones/<int:sid>/eliminar", methods=["POST"])
def suscripcion_eliminar(sid):
    execute("UPDATE suscripciones SET estado='cancelada' WHERE id=?", (sid,))
    execute("DELETE FROM suscripciones WHERE id=?", (sid,))
    flash("Suscripción eliminada", "ok")
    return redirect(url_for("suscripciones"))


@app.route("/pasarela/config")
def pasarela_config():
    cfg = get_ajustes()
    return render_template("pasarela.html", cfg=cfg)


@app.route("/pasarela/guardar", methods=["POST"])
def pasarela_guardar():
    claves = (
        "pasarela", "moneda", "mp_access_token", "stripe_secret_key",
        "stripe_webhook_secret", "paypal_client_id", "paypal_secret",
        "paypal_sandbox", "public_url",
        "nequi_client_id", "nequi_secret", "nequi_api_key",
        "nequi_codigo_comercio", "nequi_sandbox",
    )
    for clave in claves:
        set_ajuste(clave, request.form.get(clave, ""))
    flash("Configuración de cobros guardada", "ok")
    return redirect(url_for("pasarela_config"))


def _webhook_aplicar(res):
    if not res:
        return
    trans_id, aprobado, monto, ref = res
    try:
        pago_id = int(ref)
    except (TypeError, ValueError):
        return
    pago = query("SELECT * FROM pagos WHERE id=?", (pago_id,), one=True)
    if not pago or pago["estado"] == "aprobado":
        return
    _certificar_pago(pago_id, trans_id, pagado=aprobado)
    print("Webhook procesado: pago", pago_id, "->", "aprobado" if aprobado else "rechazado")


@app.route("/webhook/mercadopago", methods=["POST"])
def webhook_mp():
    res = pasarela.confirmar_evento(get_ajustes(), "mercadopago", request.data)
    _webhook_aplicar(res)
    return "", 200


@app.route("/webhook/stripe", methods=["POST"])
def webhook_stripe():
    res = pasarela.confirmar_evento(get_ajustes(), "stripe", request.data, dict(request.headers))
    _webhook_aplicar(res)
    return "", 200


@app.route("/webhook/paypal", methods=["POST"])
def webhook_paypal():
    res = pasarela.confirmar_evento(get_ajustes(), "paypal", request.data)
    _webhook_aplicar(res)
    return "", 200


@app.route("/ajustes/guardar", methods=["POST"])
def ajustes_guardar():
    for clave in ("smtp_host", "smtp_port", "smtp_usuario", "smtp_password",
                  "smtp_desde", "idle_dias", "resend_dias", "imap_host"):
        set_ajuste(clave, request.form.get(clave, ""))
    set_ajuste("smtp_ssl", "1" if request.form.get("smtp_ssl") else "")
    set_ajuste("imap_activo", "1" if request.form.get("imap_activo") else "")
    flash("Configuración guardada", "ok")
    return redirect(url_for("mensajes"))


if __name__ == "__main__":
    import webbrowser

    if db.is_postgres():
        from pg_schema import init_pg
        init_pg()
    else:
        from init_db import init_db
        init_db()

    def salida(texto):
        try:
            print(texto)
        except Exception:
            pass

    port = int(os.environ.get("CRM_PORT", 5000))
    url = f"http://127.0.0.1:{port}"

    threading.Thread(target=scheduler_loop, daemon=True).start()
    if not os.environ.get("CRM_NO_BROWSER"):
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    backend = "PostgreSQL" if db.is_postgres() else "SQLite"
    salida("=" * 50)
    salida(f"  CRM abierto en:  {url}")
    salida(f"  Backend: {backend}")
    salida("  Cierra esta ventana para detener el CRM.")
    if not db.is_postgres():
        salida("  Tus datos se guardan en: data/crm.db")
    salida("=" * 50)
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
