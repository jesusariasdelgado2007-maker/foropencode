"""Integración con pasarelas de pago para cobrar las suscripciones del CRM.

Soporta tres pasarelas: Mercado Pago, Stripe y PayPal.
  - generar_link(): crea un checkout/orden y devuelve la URL de pago.
  - confirmar_evento(): procesa el webhook de la pasarela y devuelve
    (trans_id, aprobado, monto, moneda) o None si no es válido.

Las claves se configuran en la app (Suscripciones → Configuración de cobros).
"""
import base64
import hashlib
import hmac
import json
import uuid
import urllib.parse
import urllib.request

from datetime import datetime, timezone

PAYPAL_SANDBOX = "https://api-m.sandbox.paypal.com"
PAYPAL_LIVE = "https://api-m.paypal.com"


def _post_json(url, headers, payload, timeout=25):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post_form(url, headers, fields, timeout=25):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_json(url, headers, timeout=25):
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _mp_link(cfg, monto, moneda, concepto, ref, retorno_url):
    token = (cfg.get("mp_access_token") or "").strip()
    if not token:
        return None, "", "Configura el Access Token de Mercado Pago (Suscripciones → Configuración de cobros)."
    public = (cfg.get("public_url") or "").strip().rstrip("/")
    notif = (public + "/webhook/mercadopago") if public else None
    body = {
        "items": [{
            "id": str(ref), "title": concepto[:250],
            "quantity": 1, "unit_price": float(monto),
            "currency_id": (moneda or "EUR").upper(),
        }],
        "external_reference": str(ref),
        "back_urls": {
            "success": retorno_url, "pending": retorno_url, "failure": retorno_url,
        },
        "auto_return": "approved",
    }
    if notif:
        body["notification_url"] = notif
    je = _post_json(
        "https://api.mercadopago.com/checkout/preferences",
        {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        body,
    )
    url = je.get("init_point") or je.get("sandbox_init_point")
    if not url:
        raise RuntimeError("Mercado Pago no devolvió enlace: " + json.dumps(je)[:200])
    return url, je.get("id", ""), ""


def _stripe_link(cfg, monto, moneda, concepto, ref, retorno_url):
    sk = (cfg.get("stripe_secret_key") or "").strip()
    if not sk:
        return None, "", "Configura la Secret Key de Stripe (Suscripciones → Configuración de cobros)."
    try:
        import urllib.request as _ur
    except ImportError:
        pass
    auth = "Basic " + base64.b64encode((sk + ":").encode("utf-8")).decode("ascii")
    campos = {
        "mode": "payment",
        "success_url": retorno_url,
        "cancel_url": retorno_url,
        "client_reference_id": str(ref),
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": (moneda or "EUR").lower(),
        "line_items[0][price_data][unit_amount]": str(int(round(float(monto) * 100))),
        "line_items[0][price_data][product_data][name]": concepto[:250],
        "metadata[pago_id]": str(ref),
    }
    je = _post_form(
        "https://api.stripe.com/v1/checkout/sessions",
        {"Authorization": auth, "Content-Type": "application/x-www-form-urlencoded"},
        campos,
    )
    url = je.get("url")
    if not url:
        raise RuntimeError("Stripe no devolvió sesión: " + json.dumps(je)[:200])
    return url, je.get("id", ""), ""


def _pp_base(cfg):
    return PAYPAL_LIVE if (cfg.get("paypal_sandbox") or "").upper() != "1" else PAYPAL_SANDBOX


def _pp_token(cfg):
    client = (cfg.get("paypal_client_id") or "").strip()
    secret = (cfg.get("paypal_secret") or "").strip()
    if not (client and secret):
        return None, "Configura el Client ID y Secret de PayPal (Suscripciones → Configuración de cobros)."
    auth = "Basic " + base64.b64encode((client + ":" + secret).encode("utf-8")).decode("ascii")
    je = _post_form(
        _pp_base(cfg) + "/v1/oauth2/token",
        {
            "Authorization": auth,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        {"grant_type": "client_credentials"},
    )
    return je.get("access_token") or "", ""


def _pp_link(cfg, monto, moneda, concepto, ref, retorno_url, retorno_cancel):
    token, err = _pp_token(cfg)
    if err:
        return None, "", err
    if not token:
        return None, "", "PayPal no devolvió token de acceso."
    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": str(ref),
            "custom_id": str(ref),
            "description": concepto[:120],
            "amount": {
                "currency_code": (moneda or "EUR").upper(),
                "value": f"{float(monto):.2f}",
            },
        }],
        "application_context": {
            "brand_name": "CRM",
            "return_url": retorno_url,
            "cancel_url": retorno_cancel,
            "user_action": "PAY_NOW",
        },
    }
    je = _post_json(
        _pp_base(cfg) + "/v2/checkout/orders",
        {"Authorization": "Bearer " + token},
        body,
    )
    url = ""
    for link in je.get("links", []):
        if link.get("rel") == "approve":
            url = link.get("href", "")
    if not url:
        raise RuntimeError("PayPal no devolvió enlace: " + json.dumps(je)[:200])
    return url, je.get("id", ""), ""


def generar_link(cfg, gateway, monto, moneda, concepto, ref, retorno_url, retorno_cancel=""):
    """Crea el checkout en la pasarela. Devuelve (url, transaction_id, error)."""
    gateway = (gateway or "").lower()
    try:
        if gateway == "mercadopago":
            return _mp_link(cfg, monto, moneda, concepto, ref, retorno_url)
        if gateway == "stripe":
            return _stripe_link(cfg, monto, moneda, concepto, ref, retorno_url)
        if gateway == "paypal":
            return _pp_link(cfg, monto, moneda, concepto, ref, retorno_url, retorno_cancel or retorno_url)
        if gateway == "nequi":
            return _nequi_link(cfg, monto, concepto, ref)
        return None, "", "No hay una pasarela seleccionada (elige en Suscripciones → Configuración de cobros)."
    except Exception as e:
        return None, "", "Error de la pasarela: " + str(e)[:200]


def _strip_body(body):
    if isinstance(body, bytes):
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError:
            return body.decode("latin-1")
    return body or ""


def _mp_confirm(cfg, raw):
    try:
        body = json.loads(_strip_body(raw)) if not isinstance(raw, dict) else raw
    except (ValueError, TypeError):
        return None
    data = body.get("data") or {}
    pay_id = data.get("id")
    if not pay_id:
        return None
    token = (cfg.get("mp_access_token") or "").strip()
    if not token:
        return None
    try:
        je = _get_json(
            f"https://api.mercadopago.com/v1/payments/{pay_id}",
            {"Authorization": "Bearer " + token},
        )
    except Exception:
        return None
    if str(je.get("status")) != "approved":
        return None
    ref = je.get("external_reference") or je.get("payer", {}).get("id")
    monto = je.get("transaction_amount") or je.get("transaction_details", {}).get("total_paid_amount")
    return str(pay_id), True, float(monto or 0), str(ref or "")


def confirmar_evento(cfg, gateway, raw, headers=None):
    """Procesa un webhook. Devuelve (trans_id, aprobado, monto, ref) o None."""
    gateway = (gateway or "").lower()
    if gateway == "mercadopago":
        return _mp_confirm(cfg, raw)
    if gateway == "stripe":
        res = _stripe_confirm(cfg, raw, headers)
        return res
    if gateway == "paypal":
        res = _paypal_confirm(cfg, raw)
        return res
    if gateway == "nequi":
        res = _nequi_confirm(cfg, raw)
        return res
    return None


def _stripe_confirm(cfg, raw, headers):
    # Verificar firma HMAC-SHA256 de Stripe
    secret = (cfg.get("stripe_webhook_secret") or "").strip()
    sig_header = (headers or {}).get("Stripe-Signature") or (headers or {}).get("stripe-signature")
    if not secret or not sig_header:
        return None
    raw_s = _strip_body(raw)
    parts = {}
    for item in sig_header.split(","):
        k, _, v = item.strip().partition("=")
        parts[k] = v
    t, sig = parts.get("t"), parts.get("v1")
    if not (t and sig):
        return None
    signed = f"{t}.{raw_s}".encode("utf-8")
    esperado = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(esperado, sig):
        return None
    try:
        body = json.loads(raw_s)
    except ValueError:
        return None
    ev_type = body.get("type") or ""
    obj = body.get("data", {}).get("object", {}) or {}
    if ev_type == "checkout.session.completed" and obj.get("payment_status") == "paid":
        ref = obj.get("metadata", {}).get("pago_id") or obj.get("client_reference_id")
        return str(obj.get("id") or ""), True, float((obj.get("amount_total") or 0)) / 100.0, str(ref or "")
    return None


def _paypal_confirm(cfg, raw):
    try:
        body = json.loads(_strip_body(raw)) if not isinstance(raw, dict) else raw
    except (ValueError, TypeError):
        return None
    ev_type = (body.get("event_type") or "").upper()
    if "PAYMENT.CAPTURE.COMPLETED" not in ev_type and ev_type != "CHECKOUT.ORDER.APPROVED":
        return None
    resource = body.get("resource") or {}
    if ev_type == "CHECKOUT.ORDER.APPROVED":
        # requiere captura manual; no lo confirmamos aquí
        return None
    cap_id = resource.get("id")
    ref = resource.get("custom_id") or resource.get("reference_id") or ""
    if not cap_id:
        return None
    # Verificar contra la API de PayPal (consulta el capture)
    token, err = _pp_token(cfg)
    if err or not token:
        return None
    try:
        cap = _get_json(
            _pp_base(cfg) + f"/v2/payments/captures/{cap_id}",
            {"Authorization": "Bearer " + token},
        )
    except Exception:
        return None
    if str(cap.get("status")) != "COMPLETED":
        return None
    amount = cap.get("amount", {}) or {}
    return cap_id, True, float(amount.get("value") or 0), str(ref or "")


# ---------------------------------------------------------------------------
# Nequi (Colombia): pago por QR dinámico desde la app Nequi
# ---------------------------------------------------------------------------
NEQUI_BASE_SANDBOX = "https://api.sandbox.nequi.com"
NEQUI_BASE_LIVE = "https://api.nequi.com"
NEQUI_AUTH_SANDBOX = "https://oauth.sandbox.nequi.com/oauth2/token"
NEQUI_AUTH_LIVE = "https://oauth.nequi.com/oauth2/token"
NEQUI_QR_GENERATE = "/payments/v2/-services-paymentservice-generatecodeqr"
NEQUI_QR_STATUS = "/payments/v2/-services-paymentservice-getstatuspayment"
NEQUI_CHANNEL_QR = "PQR03-C001"


def _nequi_env(cfg):
    sandbox = (cfg.get("nequi_sandbox") or "").strip() == "1"
    base = NEQUI_BASE_SANDBOX if sandbox else NEQUI_BASE_LIVE
    auth = NEQUI_AUTH_SANDBOX if sandbox else NEQUI_AUTH_LIVE
    return base, auth


def _nequi_token(cfg):
    client = (cfg.get("nequi_client_id") or "").strip()
    secret = (cfg.get("nequi_secret") or "").strip()
    if not (client and secret):
        return None, "Configura el Client ID y Secret de Nequi (Suscripciones → Configuración de cobros)."
    _, auth_uri = _nequi_env(cfg)
    auth = "Basic " + base64.b64encode((client + ":" + secret).encode("utf-8")).decode("ascii")
    try:
        je = _post_form(
            auth_uri + "?grant_type=client_credentials",
            {"Authorization": auth, "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            {},
        )
    except Exception as e:
        return None, "Autenticación con Nequi falló: " + str(e)[:160]
    token = je.get("access_token") if isinstance(je, dict) else None
    if not token:
        return None, "Nequi no devolvió token de acceso (" + json.dumps(je)[:120] + ")"
    ttype = je.get("token_type") or "Bearer"
    return f"{ttype} {token}", ""


def _nequi_envelope(cfg, op, ver, any_body):
    return {
        "RequestMessage": {
            "RequestHeader": {
                "Channel": NEQUI_CHANNEL_QR,
                "RequestDate": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S."),
                "MessageID": uuid.uuid4().hex[:10],
                "ClientID": (cfg.get("nequi_client_id") or "").strip(),
                "Destination": {
                    "ServiceName": "PaymentsService",
                    "ServiceOperation": op,
                    "ServiceRegion": "C001",
                    "ServiceVersion": ver,
                },
            },
            "RequestBody": {"any": any_body},
        }
    }


def _nequi_post(cfg, path, op, ver, any_body):
    api_key = (cfg.get("nequi_api_key") or "").strip()
    if not api_key:
        raise RuntimeError("Configura la API Key de Nequi (Suscripciones → Configuración de cobros).")
    token, err = _nequi_token(cfg)
    if err:
        raise RuntimeError(err)
    base, _ = _nequi_env(cfg)
    payload = _nequi_envelope(cfg, op, ver, any_body)
    # Fechas ISO con milisegundos
    payload["RequestMessage"]["RequestHeader"]["RequestDate"] = (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
    )
    je = _post_json(
        base + path,
        {"Authorization": token, "x-api-key": api_key},
        payload,
    )
    status = je.get("ResponseMessage", {}).get("ResponseHeader", {}).get("Status", {}) or {}
    if str(status.get("StatusCode")) != "0":
        raise RuntimeError(
            "Nequi error " + str(status.get("StatusCode")) + ": " + str(status.get("StatusDesc"))
        )
    return je


def _nequi_link(cfg, monto, concepto, ref):
    codigo = (cfg.get("nequi_codigo_comercio") or "").strip()
    if not codigo:
        return None, "", "Configura el Código de comercio (NIT) de Nequi (Suscripciones → Configuración de cobros)."
    je = _nequi_post(
        cfg,
        NEQUI_QR_GENERATE,
        "generateCodeQR",
        "1.2.0",
        {
            "generateCodeQRRQ": {
                "code": codigo,
                "value": str(int(round(float(monto)))),
                "reference1": str(ref),
                "reference2": "Suscripcion CRM",
            }
        },
    )
    rs = je.get("ResponseMessage", {}).get("ResponseBody", {}).get("any", {}).get("generateCodeQRRS", {}) or {}
    qr = rs.get("qrValue") or rs.get("codeQR")
    trn = rs.get("transactionId") or rs.get("trnId") or ""
    if not qr:
        raise RuntimeError("Nequi no devolvió QR: " + json.dumps(rs)[:160])
    return qr, trn, ""


def _nequi_confirm(cfg, raw):
    qr = raw.get("qr") if isinstance(raw, dict) else (raw or "")
    if not qr:
        return None
    try:
        je = _nequi_post(
            cfg,
            NEQUI_QR_STATUS,
            "getStatusPayment",
            "1.0.0",
            {"getStatusPaymentRQ": {"qrValue": qr}},
        )
    except Exception:
        return None
    rs = je.get("ResponseMessage", {}).get("ResponseBody", {}).get("any", {}).get("getStatusPaymentRS", {}) or {}
    if str(rs.get("status")) != "35":  # 35 = COMPLETED
        return None
    try:
        monto = float(rs.get("value") or 0)
    except (TypeError, ValueError):
        monto = 0
    return str(rs.get("trnId") or ""), True, monto, str(qr)