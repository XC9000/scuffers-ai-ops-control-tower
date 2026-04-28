"""Shipping Status API integration for Scuffers AI Ops Control Tower.

Modulo aislado y testable que encapsula la interaccion con la API logistica
externa del reto UDIA. El resto del pipeline se mantiene desacoplado: si este
modulo falla o se desactiva, el sistema sigue priorizando con las senales
internas (CSV + scoring base).

Diseno:
- Stack stdlib (sin dependencias).
- Saneamiento defensivo: la respuesta se normaliza a un dict estable; los
  errores se devuelven con la clave reservada ``_api_error`` para que cualquier
  consumidor pueda hacer fallback inmediato.
- Politica de relevancia explicita: combina el ranking del modelo con
  criterios de negocio (VIP, ticket urgente, internacional, payment_review)
  para no malgastar llamadas.
- Trazabilidad: cada llamada deja una entrada de log con latencia, estado y
  error si lo hubo.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Iterable


SHIPPING_API_BASE = os.getenv(
    "SCF_SHIPPING_API_BASE",
    "https://lkuutmnykcnbfmbpopcu.functions.supabase.co/api/shipping-status",
)
DEFAULT_TIMEOUT_S = 8

ALLOWED_STATUSES: set[str] = {
    "label_created",
    "picked_up",
    "in_transit",
    "at_sorting_center",
    "out_for_delivery",
    "delivered",
    "delayed",
    "exception",
    "lost",
    "returned_to_sender",
}

ALLOWED_REASONS: set[str] = {
    "high_volume",
    "carrier_capacity_issue",
    "address_validation_error",
    "weather_disruption",
    "warehouse_delay",
    "customs_hold",
    "unknown",
}

SEVERE_SHIPPING_STATUSES: set[str] = {
    "exception",
    "lost",
    "returned_to_sender",
    "delayed",
}

RECOVERED_STATUSES: set[str] = {
    "delivered",
    "out_for_delivery",
}

DELAY_REASONS_HIGH: set[str] = {
    "address_validation_error",
    "warehouse_delay",
    "carrier_capacity_issue",
    "customs_hold",
}

EMPTY_API_SUMMARY: dict[str, Any] = {
    "called": 0,
    "ok": 0,
    "errors": 0,
    "manual_review": 0,
    "severe": 0,
    "recovered": 0,
    "lifted_decisions": 0,
}


# ---------------------------------------------------------------------------
# Saneamiento defensivo
# ---------------------------------------------------------------------------


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_shipping_payload(raw: Any) -> dict[str, Any]:
    """Convierte una respuesta cruda de la API en un dict con tipos estables.

    Si llega algo que no es un dict, devuelve ``{"_api_error": "non-dict response"}``
    para que el caller pueda decidir. Los campos desconocidos se conservan
    bajo la clave ``_extra`` para no perder informacion futura.
    """
    if not isinstance(raw, dict):
        return {"_api_error": "non-dict response"}

    out: dict[str, Any] = {}

    status = str(raw.get("shipping_status", "")).strip().lower()
    if status and status not in ALLOWED_STATUSES:
        out["_unexpected_status"] = status
    out["shipping_status"] = status if status in ALLOWED_STATUSES else (status or "unknown")

    reason = str(raw.get("delay_reason", "")).strip().lower()
    if reason and reason not in ALLOWED_REASONS:
        out["_unexpected_reason"] = reason
    out["delay_reason"] = reason if reason in ALLOWED_REASONS else (reason or "")

    risk = _coerce_float(raw.get("delay_risk"))
    if risk > 1.0:
        risk = risk / 100.0
    out["delay_risk"] = max(0.0, min(1.0, risk))

    eta = raw.get("estimated_delivery_date")
    out["estimated_delivery_date"] = str(eta).strip() if eta else ""

    out["requires_manual_review"] = bool(raw.get("requires_manual_review"))

    known = {
        "shipping_status",
        "delay_reason",
        "delay_risk",
        "estimated_delivery_date",
        "requires_manual_review",
    }
    extras = {k: v for k, v in raw.items() if k not in known}
    if extras:
        out["_extra"] = extras
    return out


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def fetch_shipping_status(
    order_id: str,
    candidate_id: str,
    timeout: int = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Consulta sincrona a la Shipping Status API. Nunca lanza excepciones.

    Devuelve un dict normalizado o, en caso de fallo, ``{"_api_error": "..."}``.
    Siempre incluye ``_latency_ms`` para trazabilidad.
    """
    started = time.perf_counter()
    if not order_id or not candidate_id:
        return {
            "_api_error": "missing_order_id_or_candidate_id",
            "_latency_ms": 0,
        }

    base = os.getenv("SCF_SHIPPING_API_BASE", SHIPPING_API_BASE).rstrip("/")
    url = f"{base}/{order_id}"
    req = urllib.request.Request(url, headers={"X-Candidate-Id": candidate_id})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        normalized = normalize_shipping_payload(payload)
        normalized["_latency_ms"] = int((time.perf_counter() - started) * 1000)
        return normalized
    except urllib.error.HTTPError as exc:
        return {
            "_api_error": f"http_{exc.code}",
            "_latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except urllib.error.URLError as exc:
        return {
            "_api_error": f"network: {exc.reason}",
            "_latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except TimeoutError:
        return {
            "_api_error": "timeout",
            "_latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            "_api_error": f"invalid_json: {exc}",
            "_latency_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:  # ultimo paracaidas: nunca rompemos el pipeline
        return {
            "_api_error": f"unexpected: {exc.__class__.__name__}: {exc}",
            "_latency_ms": int((time.perf_counter() - started) * 1000),
        }


# ---------------------------------------------------------------------------
# Politica de relevancia
# ---------------------------------------------------------------------------


_VIP_HINTS = {"true", "1", "yes", "si", "sí"}
_VIP_SEGMENTS = {"vip_customer", "vip", "loyal_customer", "loyal"}
_HIGH_TICKET = {"urgent", "urgente", "high", "alta", "critical", "critica", "crítica"}


def select_relevant_orders(
    cases: list[Any],
    *,
    top_n: int = 25,
    must_include: Iterable[str] = (),
) -> list[Any]:
    """Decide para que pedidos vale la pena gastar una llamada a la API.

    Combina:
    1. Top N por ``case.score`` (lo que el modelo ya ha priorizado).
    2. Cualquier ``order_id`` listado en ``must_include`` (override manual).
    3. Hasta ``top_n // 5`` extras por criterios de negocio:
       - cliente VIP / loyal (campo ``is_vip`` o ``customer_segment``)
       - ticket abierto urgente
       - pedido internacional (``shipping_country`` distinto a ES)
       - pedido en payment_review

    Garantiza que no se duplican llamadas para el mismo ``order_id``.
    """
    by_id = {c.order_id: c for c in cases}
    pool: dict[str, Any] = {}

    ranked = sorted(cases, key=lambda c: getattr(c, "score", 0.0), reverse=True)
    for case in ranked[:top_n]:
        pool[case.order_id] = case

    for oid in must_include:
        if oid in by_id and oid not in pool:
            pool[oid] = by_id[oid]

    extra_quota = max(5, top_n // 5)
    extras: list[Any] = []
    for case in ranked:
        if case.order_id in pool:
            continue
        row = getattr(case, "row", {}) or {}
        is_vip = (
            str(row.get("is_vip", "")).strip().lower() in _VIP_HINTS
            or str(row.get("customer_segment", "")).strip().lower() in _VIP_SEGMENTS
        )
        urgency = str(row.get("support_ticket_urgency", "")).strip().lower()
        has_urgent_ticket = urgency in _HIGH_TICKET
        country = str(row.get("shipping_country", "")).strip().lower()
        is_international = bool(country) and country not in {
            "es",
            "spain",
            "espana",
            "españa",
        }
        order_status = str(row.get("order_status", "")).strip().lower().replace("-", "_")
        in_payment_review = order_status in {"payment_review", "paymentreview"}

        if is_vip or has_urgent_ticket or is_international or in_payment_review:
            extras.append(case)
            if len(extras) >= extra_quota:
                break

    for case in extras:
        pool[case.order_id] = case

    return list(pool.values())


# ---------------------------------------------------------------------------
# Orquestacion
# ---------------------------------------------------------------------------


def enrich_with_shipping_api(
    cases: list[Any],
    candidate_id: str | None,
    api_top: int,
    *,
    recompute_features: Callable[[Any], None] | None = None,
    timeout: int = DEFAULT_TIMEOUT_S,
    sleep_between: float = 0.05,
) -> dict[str, Any]:
    """Enriquece los pedidos relevantes con la informacion de la API.

    - ``candidate_id`` vacio o ``None`` -> no se hace ninguna llamada (modo offline).
    - ``recompute_features``: callback opcional para recalcular el scoring del
      caso despues de pegar la respuesta. Se invoca solo si la API respondio
      sin error y permite medir el delta de prioridad pre/post API.
    - El ``log`` interno se devuelve dentro del ``summary`` para que el caller
      pueda volcarlo a disco.
    """
    summary: dict[str, Any] = dict(EMPTY_API_SUMMARY)
    summary["log"] = []

    if not candidate_id:
        return summary

    targets = select_relevant_orders(cases, top_n=api_top)
    for case in targets:
        score_before = float(getattr(case, "score", 0.0))
        result = fetch_shipping_status(case.order_id, candidate_id, timeout=timeout)
        case.shipping_api = result
        case.score_pre_api = score_before
        summary["called"] += 1

        if result.get("_api_error"):
            summary["errors"] += 1
        else:
            summary["ok"] += 1
            status = result.get("shipping_status", "")
            if status in SEVERE_SHIPPING_STATUSES:
                summary["severe"] += 1
            if status in RECOVERED_STATUSES:
                summary["recovered"] += 1
            if result.get("requires_manual_review") is True:
                summary["manual_review"] += 1
            if recompute_features is not None:
                recompute_features(case)

        score_after = float(getattr(case, "score", score_before))
        case.api_lifted_score = round(score_after - score_before, 2)
        if abs(case.api_lifted_score) >= 1.0:
            summary["lifted_decisions"] += 1

        summary["log"].append(
            {
                "order_id": case.order_id,
                "shipping_status": result.get("shipping_status"),
                "delay_reason": result.get("delay_reason"),
                "delay_risk": result.get("delay_risk"),
                "requires_manual_review": result.get("requires_manual_review"),
                "estimated_delivery_date": result.get("estimated_delivery_date"),
                "score_before": round(score_before, 2),
                "score_after": round(score_after, 2),
                "delta": case.api_lifted_score,
                "latency_ms": result.get("_latency_ms"),
                "error": result.get("_api_error"),
            }
        )

        if sleep_between:
            time.sleep(sleep_between)
    return summary


# ---------------------------------------------------------------------------
# Helpers de UI / texto
# ---------------------------------------------------------------------------


def shipping_clause(case: Any) -> str:
    """Construye una frase explicativa con la info de la API o queda vacia."""
    api = getattr(case, "shipping_api", None) or {}
    if not api:
        return ""
    if api.get("_api_error"):
        return (
            f" La Shipping Status API fallo ({api['_api_error']}); "
            "priorizamos por datos internos para no perder ventana."
        )
    parts: list[str] = []
    status = api.get("shipping_status")
    if status:
        parts.append(f"estado {status}")
    eta = api.get("estimated_delivery_date")
    if eta:
        parts.append(f"ETA {eta}")
    delay_risk = api.get("delay_risk")
    if delay_risk:
        parts.append(f"delay_risk {delay_risk:.2f}")
    reason = api.get("delay_reason")
    if reason and reason not in {"none", "unknown", ""}:
        parts.append(f"motivo {reason}")
    if api.get("requires_manual_review") is True:
        parts.append("requires_manual_review=True")
    if not parts:
        return ""
    return " La Shipping Status API confirma " + ", ".join(parts) + "."


def shipping_badge(api: dict[str, Any] | None) -> tuple[str, str]:
    """Etiqueta compacta + tono visual para mostrar en filas/cards.

    Tonos: ``severe``, ``recovered``, ``manual``, ``ok``, ``error``, ``neutral``.
    """
    if not api:
        return ("", "neutral")
    if api.get("_api_error"):
        return (str(api["_api_error"]), "error")
    status = str(api.get("shipping_status", "")).strip().lower()
    reason = str(api.get("delay_reason", "")).strip().lower()
    manual = api.get("requires_manual_review") is True

    if status in SEVERE_SHIPPING_STATUSES:
        suffix = f" · {reason}" if reason and reason != "unknown" else ""
        return (f"{status}{suffix}", "severe")
    if manual:
        return ("manual review", "manual")
    if status in RECOVERED_STATUSES:
        return (status.replace("_", " "), "recovered")
    if status:
        return (status.replace("_", " "), "ok")
    return ("", "neutral")


def is_severe(api: dict[str, Any] | None) -> bool:
    if not api or api.get("_api_error"):
        return False
    return str(api.get("shipping_status", "")).lower() in SEVERE_SHIPPING_STATUSES


def is_recovered(api: dict[str, Any] | None) -> bool:
    if not api or api.get("_api_error"):
        return False
    return str(api.get("shipping_status", "")).lower() in RECOVERED_STATUSES
