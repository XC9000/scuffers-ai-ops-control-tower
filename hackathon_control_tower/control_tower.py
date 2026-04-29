"""Scuffers AI Ops Control Tower.

Solucion del reto del hackathon UDIA (2026-04-28).

El programa carga los CSV simulados de un drop, los cruza, calcula riesgos
explicables y produce las 10 acciones prioritarias con el formato pedido en
el enunciado. Soporta enriquecimiento opcional con la Shipping Status API y
genera tres salidas: top_actions.json, report.md y dashboard.html.

Decisiones clave:
- Stack: Python stdlib unicamente (zero dependencias) para que arranque en
  cualquier portatil del hackathon sin instalar nada.
- Datos: tolerante a ruido. Acepta los 6 CSV partidos (orders, order_items,
  customers, inventory, support_tickets, campaigns) o un unico CSV
  denormalizado.
- IA: la priorizacion combina senales numericas explicables (no caja negra)
  con un detector de patrones por accion. Cada accion lleva motivo, impacto
  esperado, confianza y owner para que un humano pueda actuar al instante.
- Demo: salida JSON identica al formato del enunciado + reporte ejecutivo +
  dashboard HTML para presentar.

Uso:
    python control_tower.py --data ../scuffers_all_mock_data/candidate_csvs \
                            --out outputs_full \
                            --candidate-id '#SCF-2026-6594'
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shipping_api import (
    DELAY_REASONS_HIGH,
    EMPTY_API_SUMMARY,
    RECOVERED_STATUSES,
    SEVERE_SHIPPING_STATUSES,
    enrich_with_shipping_api,
    is_recovered,
    is_severe,
    shipping_badge,
    shipping_clause,
)


URGENT_TICKET_LEVELS = {"urgent", "urgente", "critical", "critica", "crítica"}
HIGH_TICKET_LEVELS = URGENT_TICKET_LEVELS | {"high", "alta"}
NEGATIVE_SENTIMENTS = {"negative", "negativo", "very_negative", "muy_negativo"}
VIP_SEGMENTS = {"vip_customer", "vip"}
LOYAL_SEGMENTS = {"loyal_customer", "loyal"}
AT_RISK_SEGMENTS = {"at_risk_customer", "at_risk"}

# Constantes de negocio centralizadas para evitar magic numbers dispersos.
SOFT_MAX_CLV_EUR = 1500.0  # CLV "alto" considerado tope a efectos de scoring
SOFT_MAX_ORDER_VALUE_EUR = 200.0  # Pedido grande sobre el cual el riesgo se satura
SOFT_MAX_VIEWS_PER_HOUR = 4000.0  # Vistas/h "muy altas" para el drop de Scuffers
DROP_DECAY_PER_HOUR = 0.75  # Modelo: la demanda decae 25%/h tras el peak
DROP_FORECAST_HORIZON_H = 4  # Ventana de pronostico de demanda
ACTION_VALIDITY_DEFAULT_MIN = 60
ACTION_VALIDITY_BY_TYPE = {
    "vip_rescue": 30,
    "pause_campaign": 30,
    "reduce_campaign_pressure": 45,
    "throttle_traffic": 30,
    "carrier_escalation": 30,
    "address_validation_fix": 45,
    "manual_shipping_review": 60,
    "express_priority_pack": 30,
    "payment_review_audit": 45,
    "proactive_customer_contact": 60,
    "stock_reallocation": 90,
    "demand_forecast_alert": 90,
    "demand_forecast_watch": 120,
    "demand_forecast_rebalance": 120,
    "support_macro_response": 120,
    "carrier_capacity_review": 90,
}
ACTION_VERB = {
    "vip_rescue": "Rescatar",
    "pause_campaign": "Pausar",
    "reduce_campaign_pressure": "Reducir",
    "throttle_traffic": "Frenar",
    "carrier_escalation": "Escalar",
    "address_validation_fix": "Corregir",
    "manual_shipping_review": "Revisar",
    "express_priority_pack": "Empaquetar",
    "payment_review_audit": "Validar",
    "proactive_customer_contact": "Contactar",
    "stock_reallocation": "Reasignar",
    "demand_forecast_alert": "Pronosticar",
    "demand_forecast_watch": "Vigilar",
    "demand_forecast_rebalance": "Rebalancear",
    "support_macro_response": "Crear macro",
    "carrier_capacity_review": "Revisar carrier",
}


# ---------------------------------------------------------------------------
# Helpers de normalizacion
# ---------------------------------------------------------------------------


def slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def canon_id(value: Any) -> str:
    """Identificador canonico (alfanumerico minusculas) para joins ruidosos."""

    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def display_sku(value: Any) -> str:
    return str(value).strip().upper().replace("_", "-")


def norm_row(row: dict[str, str]) -> dict[str, str]:
    return {slug(k): (v or "").strip() for k, v in row.items()}


def first_present(row: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    if not s:
        return default
    s = s.replace("%", "").replace("€", "").replace("$", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s or s in {"-", ".", "-."}:
        return default
    try:
        return float(s)
    except ValueError:
        return default


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "si", "sí", "vip"}


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def scaled(value: float, soft_max: float) -> float:
    if soft_max <= 0:
        return 0.0
    return clamp((value / soft_max) * 100)


def campaign_score(value: Any) -> float:
    raw = str(value).strip().lower()
    if raw in {"very_high", "very high", "muy_alta", "muy alta"}:
        return 100
    if raw in {"low", "baja", "light"}:
        return 30
    if raw in {"medium", "media", "mid"}:
        return 60
    if raw in {"high", "alta", "heavy"}:
        return 85
    return scaled(to_float(value), 100)


def sentiment_risk(value: Any) -> float:
    raw = str(value).strip().lower()
    if not raw:
        return 0
    numeric = to_float(raw, default=None)  # type: ignore[arg-type]
    if numeric is not None:
        if -1 <= numeric <= 1:
            return clamp((1 - numeric) * 50)
        return clamp(100 - numeric)
    if any(x in raw for x in ["very_negative", "muy_neg", "angry", "enfad", "fatal"]):
        return 95
    if any(x in raw for x in ["negative", "negativo", "bad", "malo", "queja"]):
        return 75
    if any(x in raw for x in ["neutral", "neutro"]):
        return 35
    if any(x in raw for x in ["positive", "positivo", "good", "bien"]):
        return 5
    return 30


def urgency_score(value: Any) -> float:
    raw = str(value).strip().lower()
    if raw in URGENT_TICKET_LEVELS:
        return 100
    if raw in {"high", "alta"}:
        return 80
    if raw in {"medium", "media", "mid"}:
        return 55
    if raw in {"low", "baja"}:
        return 25
    return scaled(to_float(value), 100)


def percent(value: Any) -> float:
    raw = str(value).strip()
    number = to_float(raw)
    if "%" in raw or number > 1:
        return clamp(number, 0, 100)
    return clamp(number * 100, 0, 100)


# ---------------------------------------------------------------------------
# Modelo de datos
# ---------------------------------------------------------------------------


@dataclass
class OrderCase:
    order_id: str
    rows: list[dict[str, str]] = field(default_factory=list)
    shipping_api: dict[str, Any] | None = None
    features: dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    confidence: float = 0.55
    score_pre_api: float | None = None  # priority score antes del enrich
    api_lifted_score: float = 0.0  # delta de score introducido por la API

    def add(self, row: dict[str, str]) -> None:
        self.rows.append(row)

    @property
    def row(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for row in self.rows:
            for key, value in row.items():
                if value and key not in merged:
                    merged[key] = value
        return merged


@dataclass
class SkuView:
    sku: str
    product: str
    category: str
    size: str
    unit_price: float
    available: float
    reserved: float
    incoming: float
    incoming_eta: str
    sell_through: float
    views: float
    conversion: float
    campaigns: list[dict[str, Any]] = field(default_factory=list)
    units_sold_observed: float = 0.0

    @property
    def net_stock(self) -> float:
        return self.available - self.reserved

    @property
    def effective_supply(self) -> float:
        return max(0.0, self.available + (self.incoming if self.incoming else 0.0))

    @property
    def units_per_hour(self) -> float:
        """Velocidad estimada en unidades/h.

        Combinamos sell_through (% del inventario activo vendido en la ultima
        hora) con el inventario total reservado+disponible. Si el sell_through
        es 0 caemos al numero de unidades realmente facturadas en los CSV.
        """

        rate = self.sell_through * (self.available + self.reserved)
        if rate <= 0:
            rate = self.units_sold_observed
        return max(rate, 0.0)

    @property
    def time_to_stockout_min(self) -> float | None:
        """Minutos hasta agotar el stock disponible al ritmo actual."""

        if self.available <= 0:
            return 0.0
        velocity = self.units_per_hour
        if velocity <= 0:
            return None
        return self.available * 60.0 / velocity

    def stockout_phrase(self) -> str:
        if self.available <= 0 and self.reserved > 0:
            return f"oversell ya consumado ({self.net_stock:.0f} unidades comprometidas sin stock)"
        eta = self.time_to_stockout_min
        if eta is None:
            return "sin sell-through observable, riesgo de rotura por demanda potencial"
        if eta <= 0:
            return "sin stock disponible ahora mismo"
        if eta < 60:
            return f"agotamiento estimado en ~{eta:.0f} min al ritmo actual"
        if eta < 240:
            return f"agotamiento estimado en ~{eta / 60:.1f} h al ritmo actual"
        return f"stock cubre ~{eta / 60:.0f} h al ritmo actual"

    def lost_revenue_eur(self, gap_units: float) -> float:
        """Coste estimado de no actuar = gap * precio unitario."""

        return max(0.0, gap_units) * max(0.0, self.unit_price)


# ---------------------------------------------------------------------------
# Carga y join
# ---------------------------------------------------------------------------


def load_csvs(data_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(data_dir.glob("*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                row = norm_row(raw)
                row["_source_file"] = path.name
                rows.append(row)
    return rows


def source_is(row: dict[str, str], name: str) -> bool:
    return row.get("_source_file", "").lower() == name.lower()


def assemble_order_cases(
    rows: list[dict[str, str]],
) -> tuple[
    dict[str, OrderCase],
    dict[str, dict[str, str]],
    dict[str, dict[str, str]],
    dict[str, list[dict[str, str]]],
    list[dict[str, str]],
    dict[str, list[dict[str, str]]],
]:
    order_rows = [r for r in rows if source_is(r, "orders.csv")]
    if not order_rows:
        order_rows = [
            r
            for r in rows
            if first_present(r, "order_id", "order", "id_pedido", "pedido_id")
        ]

    items_by_order: dict[str, list[dict[str, str]]] = defaultdict(list)
    tickets_by_order: dict[str, list[dict[str, str]]] = defaultdict(list)
    customers_by_id: dict[str, dict[str, str]] = {}
    inventory_by_sku: dict[str, dict[str, str]] = {}
    campaigns: list[dict[str, str]] = []

    for row in rows:
        order_id = str(
            first_present(row, "order_id", "order", "id_pedido", "pedido_id", default="")
        )
        customer_id = str(first_present(row, "customer_id", "client_id", default=""))
        sku = str(first_present(row, "sku", "product_sku", default=""))

        if source_is(row, "order_items.csv") and order_id:
            items_by_order[order_id].append(row)
        elif source_is(row, "support_tickets.csv") and order_id:
            tickets_by_order[order_id].append(row)
        elif source_is(row, "customers.csv") and customer_id:
            customers_by_id[customer_id] = row
        elif source_is(row, "inventory.csv") and sku:
            inventory_by_sku[canon_id(sku)] = row
        elif source_is(row, "campaigns.csv") or first_present(
            row, "campaign_id", "target_sku"
        ):
            campaigns.append(row)

    cases: dict[str, OrderCase] = {}
    for idx, order in enumerate(order_rows):
        order_id = str(
            first_present(
                order,
                "order_id",
                "order",
                "id_pedido",
                "pedido_id",
                default=f"ROW-{idx + 1}",
            )
        )
        case = cases.setdefault(order_id, OrderCase(order_id=order_id))
        case.add(order)

        customer_id = str(first_present(order, "customer_id", "client_id", default=""))
        if customer_id and customer_id in customers_by_id:
            case.add(customers_by_id[customer_id])

        related_items = items_by_order.get(order_id, [])
        if not related_items and str(
            first_present(order, "sku", "product_sku", default="")
        ):
            related_items = [order]

        for item in related_items:
            if item is not order:
                case.add(item)
            sku = str(first_present(item, "sku", "product_sku", default=""))
            if sku and canon_id(sku) in inventory_by_sku:
                case.add(inventory_by_sku[canon_id(sku)])

            shipping_city = str(first_present(order, "shipping_city", "city", default="")).lower()
            shipping_country = str(first_present(order, "shipping_country", "country", default="")).lower()
            campaign_source = str(first_present(order, "campaign_source", default="")).lower()
            for campaign in campaigns:
                target_sku = str(first_present(campaign, "target_sku", "sku", default="")).lower()
                target_city = str(first_present(campaign, "target_city", "city", default="")).lower()
                source = str(first_present(campaign, "campaign_source", default="")).lower()
                sku_match = not target_sku or canon_id(target_sku) == canon_id(sku)
                source_match = not source or not campaign_source or source == campaign_source
                city_match = not target_city or target_city in {
                    shipping_city,
                    shipping_country,
                    "es",
                    "all",
                    "global",
                }
                if sku_match and source_match and city_match:
                    case.add(campaign)

        for ticket in tickets_by_order.get(order_id, []):
            case.add(ticket)

    return (
        cases,
        customers_by_id,
        inventory_by_sku,
        items_by_order,
        campaigns,
        tickets_by_order,
    )


def build_sku_views(
    inventory_by_sku: dict[str, dict[str, str]],
    items_by_order: dict[str, list[dict[str, str]]],
    campaigns: list[dict[str, str]],
) -> dict[str, SkuView]:
    sold_units: dict[str, float] = defaultdict(float)
    for items in items_by_order.values():
        for item in items:
            sku = str(first_present(item, "sku", "product_sku", default=""))
            if not sku:
                continue
            qty = max(1, to_float(first_present(item, "quantity"), 1))
            sold_units[canon_id(sku)] += qty

    views: dict[str, SkuView] = {}
    for key, row in inventory_by_sku.items():
        sku = display_sku(first_present(row, "sku", "product_sku", default=key))
        product = str(first_present(row, "product_name", "product", default=sku))
        category = str(first_present(row, "category", default=""))
        size = str(first_present(row, "size", default=""))
        unit_price = max(to_float(first_present(row, "unit_price", "price", default=0)), 0)
        available = max(to_float(first_present(row, "inventory_available_units", "available_units", "stock")), 0)
        reserved = max(to_float(first_present(row, "inventory_reserved_units", "reserved_units")), 0)
        incoming = max(to_float(first_present(row, "inventory_incoming_units", "incoming_units")), 0)
        eta = str(first_present(row, "inventory_incoming_eta", default=""))
        sell_through = percent(first_present(row, "sell_through_rate_last_hour", "sell_through")) / 100
        page_views = to_float(first_present(row, "product_page_views_last_hour", "views_last_hour"))
        conversion = percent(first_present(row, "conversion_rate_last_hour", "conversion_rate")) / 100

        view = SkuView(
            sku=sku,
            product=product,
            category=category,
            size=size,
            unit_price=unit_price,
            available=available,
            reserved=reserved,
            incoming=incoming,
            incoming_eta=eta,
            sell_through=sell_through,
            views=page_views,
            conversion=conversion,
            units_sold_observed=sold_units.get(key, 0.0),
        )
        for campaign in campaigns:
            target_sku = str(first_present(campaign, "target_sku", "sku", default=""))
            if not target_sku or canon_id(target_sku) == key:
                view.campaigns.append(campaign)
        views[key] = view

    return views


# ---------------------------------------------------------------------------
# Calculo de features por pedido
# ---------------------------------------------------------------------------


def compute_order_features(case: OrderCase) -> None:
    row = case.row

    order_value = sum(
        to_float(r.get("order_value")) or to_float(r.get("unit_price")) * max(1, to_float(r.get("quantity"), 1))
        for r in case.rows
    )
    clv = to_float(first_present(row, "customer_lifetime_value", "clv", "ltv"))
    customer_orders = to_float(first_present(row, "customer_orders_count", "orders_count"))
    returns = to_float(first_present(row, "customer_returns_count", "returns_count"))
    is_vip = truthy(first_present(row, "is_vip", "vip", "customer_segment"))
    segment = str(first_present(row, "customer_segment", "segment")).lower()

    customer_risk = 0.0
    customer_risk += 35 if is_vip or "vip" in segment else 0
    customer_risk += 20 if segment in LOYAL_SEGMENTS else 0
    customer_risk += 25 if segment in AT_RISK_SEGMENTS else 0
    customer_risk += scaled(clv, SOFT_MAX_CLV_EUR) * 0.30
    customer_risk += scaled(customer_orders, 10) * 0.15
    customer_risk += scaled(returns, 5) * 0.10
    customer_risk += scaled(order_value, SOFT_MAX_ORDER_VALUE_EUR) * 0.20

    support_message = str(
        first_present(row, "support_ticket_message", "ticket_message", "message")
    )
    ticket_exists = bool(
        first_present(row, "support_ticket_id", "ticket_id", default="")
    ) or bool(support_message)
    support_risk = 0.0
    if ticket_exists:
        support_risk += 25
    support_risk += urgency_score(
        first_present(row, "support_ticket_urgency", "ticket_urgency", "urgency")
    ) * 0.40
    support_risk += sentiment_risk(
        first_present(row, "support_ticket_sentiment", "ticket_sentiment", "sentiment")
    ) * 0.30
    if re.search(
        r"talla|size|retras|delay|incorrect|dañ|dano|devol|refund|angry|enfad|queja|agot",
        support_message,
        re.I,
    ):
        support_risk += 18

    available = max(to_float(first_present(row, "inventory_available_units", "available_units", "stock")), 0)
    reserved = max(to_float(first_present(row, "inventory_reserved_units", "reserved_units")), 0)
    incoming = max(to_float(first_present(row, "inventory_incoming_units", "incoming_units")), 0)
    net_stock = available - reserved
    views = to_float(first_present(row, "product_page_views_last_hour", "views_last_hour"))
    conv = percent(first_present(row, "conversion_rate_last_hour", "conversion_rate"))
    camp = campaign_score(first_present(row, "campaign_intensity", "campaign_pressure"))
    demand_pressure = clamp((scaled(views, SOFT_MAX_VIEWS_PER_HOUR) * 0.40) + (conv * 0.30) + (camp * 0.30))
    stock_pressure = (
        100 if net_stock <= 0
        else 85 if net_stock <= 3
        else 65 if net_stock <= 10
        else 30 if net_stock <= 30
        else 5
    )
    incoming_relief = 15 if incoming > 0 else 0
    inventory_risk = clamp((stock_pressure * 0.6) + (demand_pressure * 0.5) - incoming_relief)

    logistics_risk = 0.0
    shipping_method = str(first_present(row, "shipping_method", "carrier", "method")).lower()
    if any(x in shipping_method for x in ["express", "urgent", "24"]):
        logistics_risk += 12

    order_status = str(first_present(row, "order_status")).lower()
    if order_status in {"payment_review", "payment-review", "paymentreview"}:
        logistics_risk += 25
    if order_status == "processing":
        logistics_risk += 5

    api = case.shipping_api or {}
    if api and not api.get("_api_error"):
        status = str(api.get("shipping_status", "")).lower()
        reason = str(api.get("delay_reason", "")).lower()
        delay_risk = to_float(api.get("delay_risk"))
        if status in RECOVERED_STATUSES:
            logistics_risk = max(0.0, logistics_risk - 25)
        else:
            logistics_risk += delay_risk * 50
            logistics_risk += 35 if status in SEVERE_SHIPPING_STATUSES else 0
            logistics_risk += 25 if reason in DELAY_REASONS_HIGH else 0
            logistics_risk += 30 if api.get("requires_manual_review") is True else 0
        case.confidence += 0.15

    commercial_impact = clamp(
        (scaled(order_value, SOFT_MAX_ORDER_VALUE_EUR) * 0.40)
        + (camp * 0.30)
        + (scaled(views, SOFT_MAX_VIEWS_PER_HOUR) * 0.20)
        + (conv * 0.10)
    )

    case.features = {
        "customer_risk": clamp(customer_risk),
        "support_risk": clamp(support_risk),
        "inventory_risk": clamp(inventory_risk),
        "logistics_risk": clamp(logistics_risk),
        "commercial_impact": clamp(commercial_impact),
    }

    case.score = (
        case.features["customer_risk"] * 0.22
        + case.features["inventory_risk"] * 0.22
        + case.features["support_risk"] * 0.24
        + case.features["logistics_risk"] * 0.22
        + case.features["commercial_impact"] * 0.10
    )

    if clv or customer_orders or is_vip:
        case.confidence += 0.10
    if available or reserved or incoming:
        case.confidence += 0.10
    if ticket_exists:
        case.confidence += 0.10
    case.confidence = min(0.95, case.confidence)


# ---------------------------------------------------------------------------
# Detectores de acciones
# ---------------------------------------------------------------------------
#
# La integracion con la Shipping Status API (HTTP, normalizacion, seleccion
# de pedidos relevantes y trazabilidad) vive en ``shipping_api.py``. Aqui
# solo consumimos sus helpers para enriquecer los detectores existentes.


def case_summary(case: OrderCase) -> dict[str, Any]:
    row = case.row
    return {
        "order_id": case.order_id,
        "customer_id": str(first_present(row, "customer_id", default="")),
        "sku": display_sku(first_present(row, "sku", "product_sku", default="")),
        "product": str(first_present(row, "product_name", "product", default="")),
        "city": str(first_present(row, "shipping_city", default="")),
        "method": str(first_present(row, "shipping_method", default="")),
        "status": str(first_present(row, "order_status", default="")),
        "segment": str(first_present(row, "customer_segment", default="")),
        "is_vip": truthy(first_present(row, "is_vip", default="")),
        "ticket_urgency": str(first_present(row, "support_ticket_urgency", default="")),
        "ticket_sentiment": str(first_present(row, "support_ticket_sentiment", default="")),
        "ticket_message": str(first_present(row, "support_ticket_message", default="")),
        "score": round(case.score, 2),
        "features": {k: round(v, 1) for k, v in case.features.items()},
        "confidence": round(case.confidence, 2),
    }


def detect_vip_rescue(cases: list[OrderCase]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for case in cases:
        s = case_summary(case)
        urgency = s["ticket_urgency"].lower()
        sentiment = s["ticket_sentiment"].lower()
        is_vip_like = (
            s["is_vip"]
            or s["segment"] in VIP_SEGMENTS | LOYAL_SEGMENTS
            or to_float(first_present(case.row, "customer_lifetime_value")) >= 800
        )
        if not is_vip_like or not s["ticket_message"]:
            continue
        if urgency not in HIGH_TICKET_LEVELS and sentiment not in NEGATIVE_SENTIMENTS:
            continue
        clv = to_float(first_present(case.row, "customer_lifetime_value"))
        score = clamp(
            70
            + (15 if urgency in URGENT_TICKET_LEVELS else 0)
            + (10 if sentiment in NEGATIVE_SENTIMENTS else 0)
            + min(15, clv / 200)
        )
        reason = (
            f"Cliente {s['customer_id']} ({s['segment']}, LTV {clv:.0f} EUR) tiene un ticket "
            f"{urgency or 'sin urgencia'} con sentimiento {sentiment or 'no clasificado'} sobre el pedido "
            f"{case.order_id} de {s['product'] or s['sku']} en {s['city'] or 'destino desconocido'}. "
            f"Mensaje literal: \"{s['ticket_message'][:140]}\"."
            + shipping_clause(case)
        )
        actions.append(
            {
                "rank": 0,
                "action_type": "vip_rescue",
                "target_id": case.order_id,
                "title": f"Rescate VIP para {s['customer_id']} (pedido {case.order_id})",
                "reason": reason,
                "expected_impact": (
                    "Salvar la relacion con un cliente top: contesta un agente senior en menos de 30 min, "
                    "verifica estado real, ofrece compensacion proporcional y blinda LTV."
                ),
                "confidence": min(0.95, case.confidence + 0.05),
                "owner": "customer_care",
                "automation_possible": False,
                "_score": score,
                "_signals": s,
            }
        )
    return actions


def detect_logistics_escalation(cases: list[OrderCase]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for case in cases:
        api = case.shipping_api or {}
        if not api or api.get("_api_error"):
            continue
        status = str(api.get("shipping_status", "")).lower()
        reason = str(api.get("delay_reason", "")).lower()
        manual = api.get("requires_manual_review") is True
        delay_risk = to_float(api.get("delay_risk"))
        delay_pct = delay_risk * 100 if delay_risk and delay_risk <= 1 else delay_risk
        if not (status in SEVERE_SHIPPING_STATUSES or reason in DELAY_REASONS_HIGH or manual or delay_pct >= 60):
            continue
        s = case_summary(case)
        score = clamp(
            70
            + (15 if status in SEVERE_SHIPPING_STATUSES else 0)
            + (15 if manual else 0)
            + min(20, delay_pct / 5)
            + (10 if s["is_vip"] or s["segment"] in VIP_SEGMENTS else 0)
        )
        if reason == "address_validation_error":
            action_type = "address_validation_fix"
            title = f"Corregir direccion del pedido {case.order_id}"
            owner = "operations"
            impact = (
                "Bloquear retrasos de 24-48h por error de validacion de direccion: contactar cliente, "
                "actualizar direccion en el sistema y relanzar etiqueta."
            )
        elif status in {"exception", "lost", "returned_to_sender"}:
            action_type = "carrier_escalation"
            title = f"Escalar incidencia logistica del pedido {case.order_id}"
            owner = "operations"
            impact = (
                "Abrir incidencia con transportista, ofrecer reposicion o reembolso anticipado y evitar "
                "ticket reactivo del cliente."
            )
        else:
            action_type = "manual_shipping_review"
            title = f"Revisar manualmente envio del pedido {case.order_id}"
            owner = "operations"
            impact = (
                "Detectado caso que requiere revision humana antes de continuar; resolver bloqueo evita "
                "que el pedido se quede atascado en el almacen."
            )

        api_clause = shipping_clause(case)
        actions.append(
            {
                "rank": 0,
                "action_type": action_type,
                "target_id": case.order_id,
                "title": title,
                "reason": (
                    f"Pedido {case.order_id} de {s['product'] or s['sku']} a {s['city'] or 'destino'} via "
                    f"{s['method'] or 'envio estandar'}. {api_clause.strip()} Cliente {s['customer_id']} "
                    f"({s['segment'] or 'segmento desconocido'})."
                ).strip(),
                "expected_impact": impact,
                "confidence": min(0.95, case.confidence + 0.1),
                "owner": owner,
                "automation_possible": action_type != "carrier_escalation",
                "_score": score,
                "_signals": s,
            }
        )
    return actions


def detect_payment_review_audit(cases: list[OrderCase]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for case in cases:
        s = case_summary(case)
        if s["status"].lower() not in {"payment_review", "payment-review", "paymentreview"}:
            continue
        order_value = to_float(first_present(case.row, "order_value"))
        if order_value <= 0:
            order_value = to_float(first_present(case.row, "unit_price")) * max(
                1, to_float(first_present(case.row, "quantity"), 1)
            )
        score = clamp(
            55 + min(25, order_value / 6) + (15 if s["segment"] in AT_RISK_SEGMENTS else 0)
        )
        actions.append(
            {
                "rank": 0,
                "action_type": "payment_review_audit",
                "target_id": case.order_id,
                "title": f"Validar pago del pedido {case.order_id}",
                "reason": (
                    f"Pedido en estado payment_review ({order_value:.2f} EUR) de {s['product'] or s['sku']} para "
                    f"cliente {s['customer_id']} ({s['segment']}). Sin desbloqueo el inventario sigue reservado y "
                    f"otros clientes podrian quedarse sin stock."
                    + shipping_clause(case)
                ),
                "expected_impact": (
                    "Liberar reserva de stock o confirmar pago en menos de 30 min para no bloquear ventas reales "
                    "ni cargar cargos sospechosos."
                ),
                "confidence": min(0.9, case.confidence + 0.05),
                "owner": "finance",
                "automation_possible": True,
                "_score": score,
                "_signals": s,
            }
        )
    return actions


def detect_express_priority(cases: list[OrderCase]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for case in cases:
        s = case_summary(case)
        method = s["method"].lower()
        if "express" not in method and "urgent" not in method:
            continue
        if s["status"].lower() not in {"paid", "processing"}:
            continue
        api = case.shipping_api or {}
        api_status = str(api.get("shipping_status", "")).lower()
        if api_status in {"out_for_delivery", "delivered"}:
            continue
        clv = to_float(first_present(case.row, "customer_lifetime_value"))
        score = clamp(
            45
            + (20 if api_status in SEVERE_SHIPPING_STATUSES else 0)
            + (15 if s["segment"] in VIP_SEGMENTS | LOYAL_SEGMENTS else 0)
            + min(15, clv / 200)
            + (10 if to_float(first_present(case.row, "order_value")) > 100 else 0)
        )
        if score < 55:
            continue
        actions.append(
            {
                "rank": 0,
                "action_type": "express_priority_pack",
                "target_id": case.order_id,
                "title": f"Empaquetar ya pedido express {case.order_id}",
                "reason": (
                    f"Pedido express en estado {s['status']} para {s['customer_id']} ({s['segment']}) en "
                    f"{s['city'] or 'destino'}. SKU {s['sku']} ({s['product']})."
                    + shipping_clause(case)
                ),
                "expected_impact": (
                    "Empaquetar y entregar al transportista en la siguiente recogida del dia evita ticket de "
                    "queja por shipping express incumplido."
                ),
                "confidence": min(0.9, case.confidence + 0.05),
                "owner": "operations",
                "automation_possible": True,
                "_score": score,
                "_signals": s,
            }
        )
    return actions


def detect_proactive_at_risk(cases: list[OrderCase]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for case in cases:
        s = case_summary(case)
        if s["segment"] not in AT_RISK_SEGMENTS:
            continue
        api = case.shipping_api or {}
        api_severe = str(api.get("shipping_status", "")).lower() in SEVERE_SHIPPING_STATUSES
        risky_status = s["status"].lower() in {"payment_review", "processing"}
        if not (api_severe or risky_status or s["ticket_message"]):
            continue
        score = clamp(
            55
            + (20 if api_severe else 0)
            + (15 if s["ticket_message"] else 0)
            + min(15, to_float(first_present(case.row, "customer_lifetime_value")) / 100)
        )
        actions.append(
            {
                "rank": 0,
                "action_type": "proactive_customer_contact",
                "target_id": case.order_id,
                "title": f"Contactar proactivamente cliente at_risk del pedido {case.order_id}",
                "reason": (
                    f"Cliente {s['customer_id']} marcado como at_risk con un nuevo pedido {case.order_id} de "
                    f"{s['product'] or s['sku']}. Estado actual {s['status']}."
                    + shipping_clause(case)
                ),
                "expected_impact": (
                    "Mensaje proactivo (email + DM) antes de que el cliente reclame: reduce churn, baja "
                    "tickets reactivos y deja trazabilidad."
                ),
                "confidence": min(0.85, case.confidence + 0.05),
                "owner": "customer_care",
                "automation_possible": True,
                "_score": score,
                "_signals": s,
            }
        )
    return actions


def detect_proactive_delay_outreach(cases: list[OrderCase]) -> list[dict[str, Any]]:
    """Contacto proactivo cuando la API confirma delay alto en cliente no-VIP.

    Complementa a ``detect_vip_rescue`` (cubre VIP) y ``detect_proactive_at_risk``
    (cubre segmento at_risk). Aqui caen los clientes "normales" cuyo envio se
    esta torciendo y vale la pena adelantarse al ticket reactivo.
    """
    actions: list[dict[str, Any]] = []
    for case in cases:
        api = case.shipping_api or {}
        if not api or api.get("_api_error"):
            continue
        status = str(api.get("shipping_status", "")).lower()
        risk = to_float(api.get("delay_risk"))
        manual = api.get("requires_manual_review") is True
        if not (status in {"delayed", "exception"} or risk >= 0.6 or manual):
            continue
        s = case_summary(case)
        if s["is_vip"] or s["segment"] in (VIP_SEGMENTS | LOYAL_SEGMENTS | AT_RISK_SEGMENTS):
            continue
        if s["ticket_message"]:
            continue
        score = clamp(
            55
            + risk * 30
            + (15 if status in SEVERE_SHIPPING_STATUSES else 0)
            + (15 if manual else 0)
        )
        actions.append(
            {
                "rank": 0,
                "action_type": "proactive_customer_contact",
                "target_id": case.order_id,
                "title": f"Contactar proactivamente a {s['customer_id']} (pedido {case.order_id})",
                "reason": (
                    f"La Shipping API anticipa retraso en {case.order_id} "
                    f"(estado {api.get('shipping_status')}, delay_risk {risk:.2f}, "
                    f"motivo {api.get('delay_reason') or 'sin clasificar'}). "
                    f"Cliente {s['customer_id']} segmento {s['segment'] or 'sin clasificar'} "
                    f"sin ticket abierto: aviso proactivo antes de que reclame."
                    + shipping_clause(case)
                ),
                "expected_impact": (
                    "Mensaje proactivo con nuevo ETA y opcion de seguimiento. Reduce CSAT drop, "
                    "evita ticket reactivo y protege experiencia del drop."
                ),
                "confidence": min(0.92, case.confidence + 0.08),
                "owner": "customer_care",
                "automation_possible": True,
                "_score": score,
                "_signals": s,
            }
        )
    return actions


def detect_oversell_prevention(skus: dict[str, SkuView]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for view in skus.values():
        if view.available <= 0 and view.reserved <= 0 and view.units_sold_observed <= 0:
            continue
        camp_intensity = max(
            (campaign_score(c.get("campaign_intensity")) for c in view.campaigns),
            default=0,
        )
        active_campaigns = [c for c in view.campaigns if str(c.get("status", "")).lower() == "active"]
        net_stock = view.net_stock
        if net_stock > 5 and camp_intensity < 70 and view.sell_through < 0.6:
            continue
        if view.available + view.incoming <= 0:
            continue

        if active_campaigns:
            action_type = "pause_campaign" if (net_stock <= 3 and camp_intensity >= 70) else "reduce_campaign_pressure"
            title_prefix = "Pausar" if action_type == "pause_campaign" else "Reducir presion de"
            title = f"{title_prefix} campana sobre {view.product} ({view.sku})"
            owner = "marketing"
            campaign_label = ", ".join(
                f"{c.get('campaign_id', 'campana')} ({c.get('campaign_source', 's/d')}, intensidad {c.get('campaign_intensity', 's/d')})"
                for c in active_campaigns
            )
            impact = (
                "Cortar pauta pagada antes de que el SKU se agote: protege CSAT, ahorra spend en clicks que "
                "no convierten y libera presupuesto para SKUs con margen disponible."
            )
        else:
            action_type = "throttle_traffic"
            title = f"Frenar trafico hacia {view.product} ({view.sku}) por riesgo de oversell"
            owner = "merchandising"
            campaign_label = "sin campana pagada activa, pero con demanda organica acelerada"
            impact = (
                "Mover el SKU a 'temporarily out' o sacarlo del home/colecciones hasta confirmar stock real "
                "y entrante; evita pedidos que luego habria que cancelar."
            )
        cost_eur = view.lost_revenue_eur(max(0.0, -net_stock) + max(0.0, view.units_per_hour - view.available))
        score = clamp(
            55
            + (25 if net_stock <= 0 else 18 if net_stock <= 3 else 8)
            + min(20, camp_intensity * 0.18)
            + min(15, view.sell_through * 25)
            + min(10, view.views / 600)
        )
        action = {
            "rank": 0,
            "action_type": action_type,
            "target_id": view.sku,
            "title": title,
            "reason": (
                f"SKU {view.sku} ({view.product}). Disponible {view.available:.0f}, reservado {view.reserved:.0f} "
                f"-> {view.stockout_phrase()}. Sell-through {view.sell_through * 100:.0f}%/h, "
                f"conversion {view.conversion * 100:.1f}% y {view.views:.0f} vistas/h. "
                f"Campanas: {campaign_label}. Coste estimado de no actuar la proxima hora: "
                f"~{cost_eur:.0f} EUR."
            ),
            "expected_impact": impact,
            "confidence": 0.82,
            "owner": owner,
            "automation_possible": True,
            "_score": score,
            "_signals": {
                "sku": view.sku,
                "product": view.product,
                "time_to_stockout_min": view.time_to_stockout_min,
                "campaign_intensity": camp_intensity,
                "net_stock": net_stock,
                "potential_loss_eur": round(cost_eur, 1),
            },
        }
        actions.append(action)
    return actions


def detect_stock_reallocation(skus: dict[str, SkuView]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for view in skus.values():
        if view.available + view.incoming <= 0:
            continue
        if view.net_stock <= 3 and view.incoming > 0:
            score = clamp(60 + min(25, view.incoming) + min(10, view.views / 800))
            actions.append(
                {
                    "rank": 0,
                    "action_type": "stock_reallocation",
                    "target_id": view.sku,
                    "title": f"Adelantar reposicion entrante de {view.product} ({view.sku})",
                    "reason": (
                        f"Stock neto {view.net_stock:.0f} con {view.incoming:.0f} unidades entrantes "
                        f"(ETA {view.incoming_eta or 'no informada'}). Sell-through "
                        f"{view.sell_through * 100:.0f}%/h y {view.views:.0f} vistas/h indican que la rotura "
                        f"llegara antes del ETA. Conviene priorizar entrada en almacen y transferir desde "
                        f"otra ubicacion si es posible."
                    ),
                    "expected_impact": (
                        "Anticipar la entrada de stock para no perder ventas durante el pico del drop. "
                        "Cubre el gap hasta la reposicion oficial."
                    ),
                    "confidence": 0.78,
                    "owner": "operations",
                    "automation_possible": False,
                    "_score": score,
                    "_signals": {"sku": view.sku, "incoming": view.incoming, "eta": view.incoming_eta},
                }
            )
    return actions


def detect_demand_forecast(skus: dict[str, SkuView]) -> list[dict[str, Any]]:
    """Prediccion de demanda por analogia con drops anteriores.

    Aunque Scuffers no comparte el historico explicito de drops anteriores,
    asumimos el patron tipico observado en lanzamientos capsula:

    - peak de trafico en hora 1-2,
    - decaimiento aproximado del 25%/h en las 4 horas siguientes,
    - multiplicador de campana 1.0x (sin pauta) hasta 1.5x (very_high).

    Aplicamos esa curva al sell_through observado en la ultima hora para
    estimar la demanda en las proximas horas y comparamos con el supply real
    (disponible + entrante). El gap se traduce en unidades y EUR estimados.
    """

    actions: list[dict[str, Any]] = []

    candidates: list[tuple[SkuView, float, float, float]] = []
    for view in skus.values():
        baseline_units_per_hour = view.units_per_hour
        if baseline_units_per_hour <= 0:
            continue
        camp_intensity = max(
            (campaign_score(c.get("campaign_intensity")) for c in view.campaigns),
            default=0,
        )
        camp_multiplier = 1.0 + camp_intensity / 200  # 1.0 a 1.5
        forecast_units = 0.0
        for h in range(DROP_FORECAST_HORIZON_H):
            forecast_units += baseline_units_per_hour * (DROP_DECAY_PER_HOUR ** h) * camp_multiplier
        gap = forecast_units - view.effective_supply
        candidates.append((view, forecast_units, gap, camp_intensity))

    candidates.sort(key=lambda x: x[2], reverse=True)
    top = [c for c in candidates if c[2] > -5][:6]

    for view, forecast, gap, camp_intensity in top:
        cost_eur = view.lost_revenue_eur(gap)
        score = clamp(55 + min(35, max(0, gap) * 0.9) + min(15, view.views / 800))
        if gap >= 5:
            recommendation = (
                f"Iniciar pre-pedido o lista de espera para {view.product} y reasignar trafico hacia "
                "SKUs alternativos (mismo producto otra talla/color) mientras se aprueba reposicion urgente."
            )
            action_type = "demand_forecast_alert"
        elif gap >= 0:
            recommendation = "Mantener campana bajo control: el supply cubre la demanda prevista por los pelos."
            action_type = "demand_forecast_watch"
        else:
            recommendation = "Supply cubre demanda prevista; reasignar presupuesto hacia SKUs con gap positivo."
            action_type = "demand_forecast_rebalance"

        actions.append(
            {
                "rank": 0,
                "action_type": action_type,
                "target_id": view.sku,
                "title": f"Pronostico de demanda para {view.product} ({view.sku})",
                "reason": (
                    f"Curva tipica de drops anteriores (peak hora 1-2, decay 25%/h) + multiplicador "
                    f"{camp_multiplier_label(camp_intensity)} sobre sell-through actual "
                    f"{view.sell_through * 100:.0f}%/h. Pronostico {DROP_FORECAST_HORIZON_H}h: "
                    f"~{forecast:.0f} ud demandadas vs {view.effective_supply:.0f} ud de supply (disp+entrante). "
                    f"Gap previsto {gap:+.0f} ud (~{cost_eur:.0f} EUR de venta en juego)."
                ),
                "expected_impact": (
                    f"{recommendation} Permite tomar decisiones de produccion, reposicion y trafico antes de "
                    "que la rotura sea visible para el cliente."
                ),
                "confidence": 0.65,
                "owner": "merchandising",
                "automation_possible": True,
                "_score": score,
                "_signals": {
                    "sku": view.sku,
                    "forecast_units": round(forecast, 1),
                    "supply": round(view.effective_supply, 1),
                    "gap": round(gap, 1),
                    "campaign_intensity": camp_intensity,
                    "potential_loss_eur": round(cost_eur, 1),
                },
            }
        )
    return actions


def camp_multiplier_label(intensity: float) -> str:
    if intensity >= 90:
        return "1.5x (very_high)"
    if intensity >= 70:
        return "1.4x (high)"
    if intensity >= 40:
        return "1.2x (medium)"
    return "1.0x (sin campana)"


def detect_macro_response(
    tickets_by_order: dict[str, list[dict[str, str]]],
) -> list[dict[str, Any]]:
    if not tickets_by_order:
        return []
    messages: list[tuple[str, str, str, str]] = []
    for order_id, tickets in tickets_by_order.items():
        for ticket in tickets:
            msg = str(first_present(ticket, "support_ticket_message", default="")).strip()
            if msg:
                messages.append(
                    (
                        msg,
                        order_id,
                        str(first_present(ticket, "support_ticket_urgency", default="")),
                        str(first_present(ticket, "channel", default="")),
                    )
                )
    counts = Counter(m[0] for m in messages)
    actions: list[dict[str, Any]] = []
    for message, count in counts.most_common(3):
        if count < 2:
            continue
        affected_orders = [m[1] for m in messages if m[0] == message]
        channels = ", ".join(sorted({m[3] for m in messages if m[0] == message}))
        urgencies = ", ".join(sorted({m[2] for m in messages if m[0] == message}))
        urgent_count = sum(1 for m in messages if m[0] == message and m[2].lower() in HIGH_TICKET_LEVELS)
        score = clamp(60 + count * 9 + urgent_count * 4)
        sample_id = affected_orders[0]
        actions.append(
            {
                "rank": 0,
                "action_type": "support_macro_response",
                "target_id": f"PATTERN-{slug(message)[:24]}",
                "title": f"Crear macro de respuesta para {count} tickets repetidos",
                "reason": (
                    f"{count} tickets distintos comparten el mismo mensaje literal: \"{message[:160]}\". "
                    f"Pedidos afectados: {', '.join(affected_orders[:5])}{'...' if len(affected_orders) > 5 else ''}. "
                    f"Canales: {channels or 'n/a'}. Urgencias detectadas: {urgencies or 'n/a'}."
                ),
                "expected_impact": (
                    "Crear macro/template + automatizacion de primera respuesta libera al equipo de soporte para "
                    "atender los casos realmente unicos. Reduce TFR (time to first response) en ~70%."
                ),
                "confidence": 0.8,
                "owner": "customer_care",
                "automation_possible": True,
                "_score": score,
                "_signals": {
                    "pattern": message,
                    "count": count,
                    "sample_order": sample_id,
                },
            }
        )
    return actions


def detect_carrier_capacity(
    cases: list[OrderCase],
) -> list[dict[str, Any]]:
    """Detecta picos por ciudad/metodo de envio que sugieren cuello de botella logistico."""

    bucket: dict[tuple[str, str], list[OrderCase]] = defaultdict(list)
    for case in cases:
        s = case_summary(case)
        method = s["method"].lower() or "standard"
        city = s["city"] or "desconocido"
        bucket[(city, method)].append(case)

    actions: list[dict[str, Any]] = []
    for (city, method), entries in bucket.items():
        if len(entries) < 12:
            continue
        api_called = any(
            c.shipping_api and not c.shipping_api.get("_api_error") for c in entries
        )
        delayed = [
            c
            for c in entries
            if str((c.shipping_api or {}).get("shipping_status", "")).lower() in SEVERE_SHIPPING_STATUSES
        ]
        manual_review = [
            c for c in entries if (c.shipping_api or {}).get("requires_manual_review") is True
        ]
        incidents = len(delayed) + len(manual_review)
        ratio_at_risk = incidents / len(entries) if entries else 0
        # Solo entra al top si hay senal real (incidencias) o volumen muy alto (>=40 pedidos
        # en la misma ruta en 2h, lo que ya satura una franja de recogida).
        if api_called and incidents == 0:
            continue
        if not api_called and len(entries) < 40:
            continue
        score = clamp(35 + len(entries) * 1.2 + ratio_at_risk * 70 + incidents * 8)
        actions.append(
            {
                "rank": 0,
                "action_type": "carrier_capacity_review",
                "target_id": f"{city}|{method}",
                "title": f"Revisar capacidad de {method or 'standard'} en {city}",
                "reason": (
                    f"{len(entries)} pedidos en {city} via {method or 'standard'} en la misma ventana "
                    f"({incidents} con incidencia o revision manual segun Shipping API, ratio "
                    f"{ratio_at_risk * 100:.0f}%). Cualquier incidencia se replica en cadena."
                ),
                "expected_impact": (
                    "Negociar slot extra con el transportista o repartir el batch en una segunda recogida "
                    "para no acumular tickets de retraso."
                ),
                "confidence": 0.7,
                "owner": "operations",
                "automation_possible": False,
                "_score": score,
                "_signals": {
                    "city": city,
                    "method": method,
                    "orders": len(entries),
                    "incidents": incidents,
                },
            }
        )
    return actions


# ---------------------------------------------------------------------------
# Priorizacion final
# ---------------------------------------------------------------------------


PRIORITY_FAMILY = {
    "vip_rescue": "vip",
    "carrier_escalation": "logistics",
    "address_validation_fix": "logistics",
    "manual_shipping_review": "logistics",
    "express_priority_pack": "logistics",
    "carrier_capacity_review": "logistics",
    "payment_review_audit": "finance",
    "proactive_customer_contact": "customer",
    "support_macro_response": "support",
    "pause_campaign": "marketing",
    "reduce_campaign_pressure": "marketing",
    "throttle_traffic": "marketing",
    "stock_reallocation": "inventory",
    "demand_forecast_alert": "forecast",
    "demand_forecast_watch": "forecast",
    "demand_forecast_rebalance": "forecast",
}

FAMILY_CAPS = {
    "vip": 3,
    "logistics": 3,
    "finance": 2,
    "customer": 2,
    "support": 2,
    "marketing": 4,
    "inventory": 2,
    "forecast": 2,
    "other": 2,
}


def diversify_actions(
    actions: list[dict[str, Any]], limit: int = 10
) -> list[dict[str, Any]]:
    actions_sorted = sorted(actions, key=lambda a: a["_score"], reverse=True)
    selected: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    family_count: dict[str, int] = defaultdict(int)
    target_id_count: Counter[str] = Counter()

    for action in actions_sorted:
        key = (action["action_type"], action["target_id"])
        family = PRIORITY_FAMILY.get(action["action_type"], "other")
        cap = FAMILY_CAPS.get(family, 2)
        if key in seen_keys:
            continue
        if family_count[family] >= cap:
            continue
        if target_id_count[action["target_id"]] >= 2:
            continue
        selected.append(action)
        seen_keys.add(key)
        family_count[family] += 1
        target_id_count[action["target_id"]] += 1
        if len(selected) == limit:
            break

    if len(selected) < limit:
        for action in actions_sorted:
            key = (action["action_type"], action["target_id"])
            if key in seen_keys:
                continue
            selected.append(action)
            seen_keys.add(key)
            if len(selected) == limit:
                break

    for idx, action in enumerate(selected, start=1):
        action["rank"] = idx
    return selected


# ---------------------------------------------------------------------------
# Salidas
# ---------------------------------------------------------------------------


def cleanup_for_json(action: dict[str, Any]) -> dict[str, Any]:
    cleaned = {k: v for k, v in action.items() if not k.startswith("_")}
    cleaned["confidence"] = round(float(cleaned.get("confidence", 0.7)), 2)
    cleaned["priority_score"] = round(float(action.get("_score", 0)), 1)
    cleaned["valid_for_minutes"] = ACTION_VALIDITY_BY_TYPE.get(
        action.get("action_type", ""), ACTION_VALIDITY_DEFAULT_MIN
    )
    return cleaned


def assess_data_quality(
    rows: list[dict[str, str]],
    cases: dict[str, OrderCase],
    skus: dict[str, SkuView],
    customers_by_id: dict[str, dict[str, str]],
    items_by_order: dict[str, list[dict[str, str]]],
    tickets_by_order: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    """Calcula un mini-reporte de calidad de datos para defender la solucion.

    No bloquea la ejecucion: simplemente expone donde tendria que actuar el
    equipo de datos en una segunda fase para subir la confianza del sistema.
    """

    def src(name: str) -> list[dict[str, str]]:
        return [r for r in rows if source_is(r, name)]

    orders = src("orders.csv") or [r for r in rows if first_present(r, "order_id")]
    items = src("order_items.csv")
    customers = src("customers.csv")
    inventory = src("inventory.csv")
    tickets = src("support_tickets.csv")
    campaigns = src("campaigns.csv")

    duplicate_orders = [
        oid for oid, count in Counter(r.get("order_id", "") for r in orders).items() if oid and count > 1
    ]
    duplicate_customers = [
        cid for cid, count in Counter(r.get("customer_id", "") for r in customers).items() if cid and count > 1
    ]

    orphan_items = [
        i.get("order_id", "")
        for i in items
        if i.get("order_id") and i.get("order_id") not in cases
    ]
    orphan_tickets = [
        t.get("order_id", "")
        for tlist in tickets_by_order.values()
        for t in tlist
        if t.get("order_id") and t.get("order_id") not in cases
    ]

    customer_ids_in_orders = {r.get("customer_id", "") for r in orders if r.get("customer_id")}
    missing_customers = sorted(c for c in customer_ids_in_orders if c not in customers_by_id)

    sku_ids_in_orders = {canon_id(r.get("sku", "")) for r in orders if r.get("sku")}
    missing_skus = sorted(
        display_sku(s)
        for s in sku_ids_in_orders
        if s and s not in skus
    )

    missing_order_value = sum(1 for r in orders if not (r.get("order_value") or "").strip())
    weird_order_value = sum(1 for r in orders if "€" in (r.get("order_value") or "") or "," in (r.get("order_value") or ""))
    empty_segment = sum(1 for r in orders if not (r.get("customer_segment") or "").strip())

    oversold_skus = [
        view.sku
        for view in skus.values()
        if view.reserved > view.available and view.available >= 0
    ]

    inconsistent_segments = []
    for cid, crow in customers_by_id.items():
        if to_float(crow.get("customer_orders_count")) == 0 and any(
            r for r in orders if r.get("customer_id") == cid
        ):
            inconsistent_segments.append(cid)

    payment_review_orders = [r.get("order_id", "") for r in orders if r.get("order_status", "").lower() == "payment_review"]

    return {
        "files": {
            "orders": len(orders),
            "order_items": len(items),
            "customers": len(customers),
            "inventory": len(inventory),
            "support_tickets": len(tickets),
            "campaigns": len(campaigns),
        },
        "duplicates": {
            "orders": duplicate_orders,
            "customers": duplicate_customers,
        },
        "orphans": {
            "items_without_order": orphan_items,
            "tickets_without_order": orphan_tickets,
            "orders_with_unknown_customer": missing_customers,
            "orders_with_sku_not_in_inventory": missing_skus,
        },
        "field_issues": {
            "missing_order_value": missing_order_value,
            "noisy_order_value_format": weird_order_value,
            "empty_customer_segment_in_orders": empty_segment,
        },
        "business_alerts": {
            "skus_with_reserved_above_available": oversold_skus,
            "customers_with_orders_count_0_but_with_orders": inconsistent_segments,
            "orders_in_payment_review": payment_review_orders,
        },
    }


def write_outputs(
    actions: list[dict[str, Any]],
    cases: list[OrderCase],
    skus: dict[str, SkuView],
    api_summary: dict[str, int],
    data_quality: dict[str, Any],
    out_dir: Path,
    *,
    demo_banner: str = "",
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    json_actions = [cleanup_for_json(a) for a in actions]
    (out_dir / "top_actions.json").write_text(
        json.dumps(json_actions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "data_quality.json").write_text(
        json.dumps(data_quality, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    api_log = api_summary.get("log") or []
    if api_log:
        log_payload = {
            "summary": {k: v for k, v in api_summary.items() if k != "log"},
            "calls": api_log,
        }
        (out_dir / "shipping_api_log.json").write_text(
            json.dumps(log_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    api_lifted = sorted(
        [c for c in cases if abs(getattr(c, "api_lifted_score", 0.0)) >= 1.0],
        key=lambda c: abs(c.api_lifted_score),
        reverse=True,
    )

    families = Counter(PRIORITY_FAMILY.get(a["action_type"], "other") for a in actions)
    dq_files = data_quality["files"]
    dq_field = data_quality["field_issues"]
    dq_orphans = data_quality["orphans"]
    dq_alerts = data_quality["business_alerts"]

    md_lines = [
        "# Scuffers AI Ops Control Tower",
        "",
        f"_Generado {datetime.now(timezone.utc).isoformat(timespec='seconds')}._",
        "",
        "## TL;DR",
        "",
        f"- {len(cases)} pedidos analizados, {len(skus)} SKUs con inventario, "
        f"{dq_files['support_tickets']} tickets de soporte y {dq_files['campaigns']} campanas activas.",
        "- Top 10 acciones repartidas por familia: "
        + ", ".join(f"{k}={v}" for k, v in families.most_common())
        + ".",
        f"- Shipping Status API consultada en {api_summary.get('called', 0)} pedidos "
        f"(ok={api_summary.get('ok', 0)}, errores={api_summary.get('errors', 0)}, "
        f"manual_review={api_summary.get('manual_review', 0)}, severos={api_summary.get('severe', 0)}, "
        f"recuperados={api_summary.get('recovered', 0)}, decisiones movidas={api_summary.get('lifted_decisions', 0)}).",
        f"- Calidad de datos: {dq_field['missing_order_value']} pedidos sin order_value, "
        f"{dq_field['noisy_order_value_format']} con formato ruidoso, "
        f"{dq_field['empty_customer_segment_in_orders']} sin segmento, "
        f"{len(dq_alerts['skus_with_reserved_above_available'])} SKUs con oversell consumado.",
        "",
        "## Top 10 acciones",
        "",
        "| # | Decision | Action type | Target | Owner | Score | Conf. | Validez | Auto |",
        "|---|----------|-------------|--------|-------|-------|-------|---------|------|",
    ]
    for action in actions:
        verb = ACTION_VERB.get(action["action_type"], action["action_type"])
        validity = ACTION_VALIDITY_BY_TYPE.get(action["action_type"], ACTION_VALIDITY_DEFAULT_MIN)
        md_lines.append(
            f"| {action['rank']} | **{verb}** | `{action['action_type']}` | `{action['target_id']}` | "
            f"{action['owner']} | {round(action['_score'], 1)} | {action['confidence']:.2f} | {validity} min | "
            f"{'auto' if action['automation_possible'] else 'humano'} |"
        )

    md_lines.append("")
    for action in actions:
        md_lines.extend(
            [
                f"### {action['rank']}. {action['title']}",
                "",
                f"- **Decision:** {ACTION_VERB.get(action['action_type'], action['action_type'])} "
                f"(`{action['action_type']}`)",
                f"- **Target:** `{action['target_id']}`",
                f"- **Owner:** `{action['owner']}`",
                f"- **Priority score:** {round(action['_score'], 1)} / 100  ·  "
                f"**Confianza:** {action['confidence']:.2f}  ·  "
                f"**Validez:** {ACTION_VALIDITY_BY_TYPE.get(action['action_type'], ACTION_VALIDITY_DEFAULT_MIN)} min  ·  "
                f"**Auto:** {action['automation_possible']}",
                f"- **Motivo:** {action['reason']}",
                f"- **Impacto esperado:** {action['expected_impact']}",
                "",
            ]
        )

    md_lines.extend(
        [
            "## Como se calcula el Priority Score",
            "",
            "1. **Ingesta tolerante**: cruzamos `orders + order_items + customers + inventory + support_tickets + campaigns` usando un `canon_id` que normaliza SKUs ruidosos (`HOODIE-BLK-M` vs `hoodie_blk_m`).",
            "2. **5 senales por pedido** (escala 0-100): customer_risk, support_risk, inventory_risk, logistics_risk, commercial_impact. Cada una usa parametros centralizados (`SOFT_MAX_CLV_EUR`, `SOFT_MAX_ORDER_VALUE_EUR`, `SOFT_MAX_VIEWS_PER_HOUR`).",
            "3. **Detectores de accion** (10 tipos): cada detector emite candidatos con su propio score interpretable, no un numero magico. Los scores agregan valor de negocio (CLV, severidad logistica, gap de demanda) y un coste estimado en EUR cuando aplica.",
            "4. **Diversificacion** con caps por familia (vip 3, marketing 4, logistics 3, support 2, forecast 2, customer 2, finance 2, inventory 2) y maximo 2 acciones por target_id. Se exponen `priority_score` y `valid_for_minutes` en cada accion para que ops tenga trazabilidad y ventana operativa.",
            "5. **API logistica selectiva**: solo se consulta para los pedidos top (configurable con `--api-top`). El resultado se reinyecta en el modelo para que pase de prioridad ciega a prioridad informada.",
            "",
            "## Supuestos y limitaciones",
            "",
            "- La curva de demanda asumida (peak hora 1-2, decay 25%/h) es un proxy razonable de drops capsula, no un modelo entrenado con histórico real. Cuando exista historial, se sustituye por un fit empirico.",
            "- El modelo no toca decisiones financieras (precios, descuentos): solo dispara revisiones humanas.",
            "- Los pesos de las 5 senales por pedido son heuristicos, defendibles, y se pueden mover en un fichero de config sin recompilar.",
            "- La API logistica puede caer; se trata como dato opcional, nunca bloqueante.",
            "",
            "## Calidad de datos detectada",
            "",
            f"- Archivos cargados: {', '.join(f'{k}={v}' for k, v in dq_files.items())}.",
            f"- Pedidos huerfanos (items sin pedido): {len(dq_orphans['items_without_order'])}.",
            f"- Tickets sin pedido: {len(dq_orphans['tickets_without_order'])}.",
            f"- Pedidos con SKU desconocido en inventario: {len(dq_orphans['orders_with_sku_not_in_inventory'])}.",
            f"- Pedidos con cliente desconocido: {len(dq_orphans['orders_with_unknown_customer'])}.",
            f"- SKUs con oversell consumado (reservado > disponible): "
            f"{', '.join(dq_alerts['skus_with_reserved_above_available']) or 'ninguno'}.",
            f"- Pedidos en `payment_review`: {len(dq_alerts['orders_in_payment_review'])}.",
            "",
            "Detalle completo en `data_quality.json`.",
            "",
        ]
    )

    if api_summary.get("called", 0) > 0:
        md_lines.extend(
            [
                "## Impacto de la Shipping Status API",
                "",
                f"- Pedidos consultados: {api_summary.get('called', 0)}  ·  "
                f"OK: {api_summary.get('ok', 0)}  ·  errores: {api_summary.get('errors', 0)}.",
                f"- Severos (delayed/exception/lost/returned): {api_summary.get('severe', 0)}  ·  "
                f"recuperados (delivered/out_for_delivery): {api_summary.get('recovered', 0)}  ·  "
                f"manual review: {api_summary.get('manual_review', 0)}.",
                f"- Decisiones movidas por la API (delta de score >= 1 punto): "
                f"{api_summary.get('lifted_decisions', 0)}.",
                "",
            ]
        )
        if api_lifted:
            md_lines.extend(
                [
                    "| Pedido | Estado API | Δ score | Motivo |",
                    "|--------|-----------|---------|--------|",
                ]
            )
            for case in api_lifted[:10]:
                api = case.shipping_api or {}
                badge_label, _ = shipping_badge(api)
                delta = case.api_lifted_score
                delta_str = f"+{delta:.1f}" if delta > 0 else f"{delta:.1f}"
                md_lines.append(
                    f"| `{case.order_id}` | {badge_label or '-'} | {delta_str} | "
                    f"{(api.get('delay_reason') or '').replace('_', ' ') or '—'} |"
                )
            md_lines.append("")
        (out_dir / "report.md").write_text("\n".join(md_lines), encoding="utf-8")
    else:
        (out_dir / "report.md").write_text("\n".join(md_lines), encoding="utf-8")

    write_dashboard(
        actions, cases, skus, api_summary, data_quality, out_dir / "dashboard.html",
        api_lifted=api_lifted, demo_banner=demo_banner,
    )


FAMILY_COLOR = {
    "vip": ("#ff3358", "#3b1620"),
    "logistics": ("#ff9f43", "#3a2913"),
    "marketing": ("#5b8def", "#172541"),
    "support": ("#a76bff", "#231640"),
    "forecast": ("#27c4b3", "#11302d"),
    "inventory": ("#5cd6ff", "#0f2832"),
    "finance": ("#ffd166", "#36290f"),
    "customer": ("#7bd389", "#13301c"),
    "other": ("#9aa0aa", "#1c1f29"),
}


# JS del feed en vivo. Se inyecta al final del dashboard. Aqui usamos un raw
# string para no tener que escapar llaves dentro del f-string del HTML; el
# placeholder __LIVE_FEED_DATA__ se sustituye con json.dumps(events).
LIVE_FEED_SCRIPT = r"""
<script>
(function () {
  const ORDERS = __LIVE_FEED_DATA__;
  if (!Array.isArray(ORDERS) || ORDERS.length === 0) return;

  const feed = document.getElementById('live-feed');
  const dot = document.getElementById('live-dot');
  const statusLabel = document.getElementById('live-status-label');
  const countEl = document.getElementById('live-count');
  const rateEl = document.getElementById('live-rate');
  const revenueEl = document.getElementById('live-revenue');
  const aovEl = document.getElementById('live-aov');
  const topSkuEl = document.getElementById('live-top-sku');
  const topCityEl = document.getElementById('live-top-city');
  const connectBtn = document.getElementById('live-connect');
  const pauseBtn = document.getElementById('live-pause');
  const clearBtn = document.getElementById('live-clear');
  const modal = document.getElementById('live-modal');
  const webhookInput = document.getElementById('live-webhook');
  const confirmBtn = document.getElementById('live-confirm');
  const cancelBtn = document.getElementById('live-cancel');

  let idx = 0;
  let received = 0;
  let revenue = 0;
  let connected = false;
  let paused = false;
  let intervalId = null;
  const recent = [];
  const startTs = Date.now();
  let liveFetchTimer = null;

  function fmtTime(iso) {
    if (!iso) return '--:--';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso.slice(11, 16);
    return d.toISOString().slice(11, 16);
  }

  function isVipLike(seg) {
    seg = (seg || '').toLowerCase();
    return seg.indexOf('vip') >= 0 || seg.indexOf('loyal') >= 0;
  }

  function emit(order, opts) {
    opts = opts || {};
    const li = document.createElement('li');
    li.className = 'new';
    const segClass = isVipLike(order.segment) ? 'vip' : '';
    const live = opts.live ? ' \u2022 live' : '';
    li.innerHTML =
      '<span class="time">' + fmtTime(order.created_at) + live + '</span>' +
      '<span class="oid ' + segClass + '">' + (order.order_id || '') + '</span>' +
      '<span class="sku">' + (order.sku || '') + '</span>' +
      '<span>' + (order.product || '') + ' \u00b7 ' + (order.city || 's/d') + ' \u00b7 ' + (order.method || 'standard') + '</span>' +
      '<span class="right">' + (order.value || 0).toFixed(2) + ' EUR</span>';
    feed.insertBefore(li, feed.firstChild);
    while (feed.children.length > 14) feed.removeChild(feed.lastChild);
    setTimeout(function () { li.classList.remove('new'); }, 600);

    received += 1;
    revenue += Number(order.value) || 0;
    recent.unshift(order);
    if (recent.length > 12) recent.pop();
    refreshStats();
  }

  function refreshStats() {
    countEl.textContent = received;
    revenueEl.textContent = revenue.toFixed(0) + ' EUR';
    aovEl.textContent = received ? 'AOV ' + (revenue / received).toFixed(1) + ' EUR' : 'AOV 0 EUR';
    const minutes = (Date.now() - startTs) / 60000;
    rateEl.textContent = (received / Math.max(0.05, minutes)).toFixed(1) + ' pedidos/min';

    if (recent.length === 0) {
      topSkuEl.textContent = '-';
      topCityEl.textContent = 'Ciudad: -';
      return;
    }
    const skuCount = {};
    const cityCount = {};
    for (let i = 0; i < recent.length; i++) {
      const r = recent[i];
      if (r.sku) skuCount[r.sku] = (skuCount[r.sku] || 0) + 1;
      if (r.city) cityCount[r.city] = (cityCount[r.city] || 0) + 1;
    }
    const topSku = Object.keys(skuCount).sort(function (a, b) { return skuCount[b] - skuCount[a]; })[0];
    const topCity = Object.keys(cityCount).sort(function (a, b) { return cityCount[b] - cityCount[a]; })[0];
    topSkuEl.textContent = topSku ? topSku + ' (' + skuCount[topSku] + ')' : '-';
    topCityEl.textContent = 'Ciudad: ' + (topCity || '-');
  }

  function tick() {
    if (paused) return;
    const order = ORDERS[idx % ORDERS.length];
    idx += 1;
    emit(order, { live: connected });
  }

  function start(rateMs) {
    stop();
    intervalId = setInterval(tick, rateMs);
  }

  function stop() {
    if (intervalId) clearInterval(intervalId);
    intervalId = null;
  }

  function setStatus(connectedNow, label) {
    connected = connectedNow;
    if (connectedNow) {
      dot.classList.add('online');
      statusLabel.textContent = label || 'Conectado al feed en vivo';
      connectBtn.textContent = 'Desconectar';
    } else {
      dot.classList.remove('online');
      statusLabel.textContent = label || 'Modo simulacion offline';
      connectBtn.textContent = 'Conectar feed en vivo';
    }
  }

  function tryFetchLive(url) {
    // Intento real: si el endpoint responde JSON con pedidos, los inyectamos.
    // Si falla por CORS o 4xx/5xx, seguimos en modo simulacion.
    if (!url || !url.match(/^https?:\/\//)) return;
    if (liveFetchTimer) clearInterval(liveFetchTimer);
    liveFetchTimer = setInterval(function () {
      fetch(url, { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data) return;
          const items = Array.isArray(data) ? data : (data.orders || data.items || []);
          for (let i = 0; i < items.length; i++) {
            const ev = items[i];
            emit({
              order_id: ev.order_id || ev.id || ('LIVE-' + Date.now()),
              customer_id: ev.customer_id || '',
              sku: ev.sku || (ev.line_items && ev.line_items[0] && ev.line_items[0].sku) || '',
              product: ev.product || (ev.line_items && ev.line_items[0] && ev.line_items[0].title) || '',
              city: ev.city || (ev.shipping_address && ev.shipping_address.city) || '',
              method: ev.shipping_method || (ev.shipping_lines && ev.shipping_lines[0] && ev.shipping_lines[0].title) || 'standard',
              segment: ev.segment || '',
              value: Number(ev.value || ev.total_price || 0),
              created_at: ev.created_at || new Date().toISOString(),
              status: ev.financial_status || ev.status || ''
            }, { live: true });
          }
        })
        .catch(function () { /* silencioso, modo simulacion sigue */ });
    }, 5000);
  }

  function stopFetchLive() {
    if (liveFetchTimer) clearInterval(liveFetchTimer);
    liveFetchTimer = null;
  }

  connectBtn.addEventListener('click', function () {
    if (connected) {
      stopFetchLive();
      setStatus(false, 'Desconectado del feed en vivo');
      start(2200);
      return;
    }
    webhookInput.value = '';
    modal.classList.add('open');
  });

  cancelBtn.addEventListener('click', function () { modal.classList.remove('open'); });

  confirmBtn.addEventListener('click', function () {
    const url = (webhookInput.value || '').trim();
    modal.classList.remove('open');
    setStatus(true, url ? 'Conectado: ' + url.replace(/^https?:\/\//, '').slice(0, 36) : 'Conectado (modo demo acelerado)');
    start(800);
    if (url) tryFetchLive(url);
  });

  pauseBtn.addEventListener('click', function () {
    paused = !paused;
    pauseBtn.textContent = paused ? 'Reanudar' : 'Pausar';
  });

  clearBtn.addEventListener('click', function () {
    feed.innerHTML = '';
    received = 0;
    revenue = 0;
    recent.length = 0;
    refreshStats();
  });

  // Arranque automatico en modo simulacion offline.
  start(2200);
})();
</script>
"""


def build_live_feed_payload(cases: list[OrderCase]) -> list[dict[str, Any]]:
    """Construye los eventos de pedido para el simulador en directo del dashboard.

    Ordena los pedidos por `created_at` y normaliza los campos minimos que
    necesita la UI: id, cliente, SKU, producto, ciudad, importe, segmento.
    """

    events: list[dict[str, Any]] = []
    for case in cases:
        row = case.row
        order_value = to_float(first_present(row, "order_value"))
        if order_value <= 0:
            order_value = to_float(first_present(row, "unit_price")) * max(
                1, to_float(first_present(row, "quantity"), 1)
            )
        events.append(
            {
                "order_id": case.order_id,
                "customer_id": str(first_present(row, "customer_id", default="")),
                "sku": display_sku(first_present(row, "sku", "product_sku", default="")),
                "product": str(first_present(row, "product_name", "product", default="")),
                "city": str(first_present(row, "shipping_city", default="")),
                "method": str(first_present(row, "shipping_method", default="")),
                "segment": str(first_present(row, "customer_segment", default="")),
                "value": round(order_value, 2),
                "created_at": str(first_present(row, "created_at", default="")),
                "status": str(first_present(row, "order_status", default="")),
            }
        )
    events.sort(key=lambda e: e["created_at"])
    return events


def write_dashboard(
    actions: list[dict[str, Any]],
    cases: list[OrderCase],
    skus: dict[str, SkuView],
    api_summary: dict[str, Any],
    data_quality: dict[str, Any],
    path: Path,
    *,
    api_lifted: list[OrderCase] | None = None,
    demo_banner: str = "",
) -> None:
    api_lifted = api_lifted or []
    families = Counter(PRIORITY_FAMILY.get(a["action_type"], "other") for a in actions)

    top_skus = sorted(
        skus.values(),
        key=lambda s: (s.net_stock <= 3, s.views, s.sell_through),
        reverse=True,
    )[:8]
    high_risk_cases = sorted(cases, key=lambda c: c.score, reverse=True)[:8]
    live_feed = build_live_feed_payload(cases)

    def family_chip(family: str, label: str) -> str:
        return f'<span class="chip chip-{family}">{html.escape(label)}</span>'

    def meta_chip(label: str) -> str:
        return f'<span class="chip chip-meta">{html.escape(label)}</span>'

    hero_cards = "".join(
        f"""
        <article class=\"hero hero-{PRIORITY_FAMILY.get(a['action_type'], 'other')}\">
            <header class=\"hero-head\">
                <span class=\"hero-rank\">{a['rank']:02d}</span>
                {family_chip(PRIORITY_FAMILY.get(a['action_type'], 'other'), ACTION_VERB.get(a['action_type'], a['action_type']))}
                <span class=\"hero-target mono\">{html.escape(a['target_id'])}</span>
            </header>
            <h3>{html.escape(a['title'])}</h3>
            <p class=\"hero-reason\">{html.escape(a['reason'][:240])}{'...' if len(a['reason']) > 240 else ''}</p>
            <div class=\"hero-meta\">
                <span><label>Score</label><strong>{round(a['_score'], 1)}</strong></span>
                <span><label>Confianza</label><strong>{a['confidence']:.2f}</strong></span>
                <span><label>Validez</label><strong>{ACTION_VALIDITY_BY_TYPE.get(a['action_type'], ACTION_VALIDITY_DEFAULT_MIN)} min</strong></span>
                <span><label>Modo</label><strong>{'Auto' if a['automation_possible'] else 'Humano'}</strong></span>
            </div>
        </article>
        """
        for a in actions[:3]
    )

    rows_actions = "".join(
        f"""
        <tr>
            <td class=\"rank mono\">{a['rank']:02d}</td>
            <td>{family_chip(PRIORITY_FAMILY.get(a['action_type'], 'other'), ACTION_VERB.get(a['action_type'], a['action_type']))}</td>
            <td><strong>{html.escape(a['title'])}</strong>
                <span class=\"meta mono\">{html.escape(a['action_type'])} · {html.escape(a['target_id'])}</span></td>
            <td>{html.escape(a['owner'])}</td>
            <td class=\"mono num\">{round(a['_score'], 1)}</td>
            <td class=\"mono num\">{a['confidence']:.2f}</td>
            <td class=\"mono num\">{ACTION_VALIDITY_BY_TYPE.get(a['action_type'], ACTION_VALIDITY_DEFAULT_MIN)}'</td>
            <td>{'Auto' if a['automation_possible'] else 'Humano'}</td>
            <td class=\"reason\">{html.escape(a['reason'])}</td>
        </tr>
        """
        for a in actions
    )

    def stockout_label(view: SkuView) -> str:
        eta = view.time_to_stockout_min
        if view.available <= 0 and view.reserved > 0:
            return "oversell"
        if eta is None:
            return "n/d"
        if eta <= 0:
            return "agotado"
        if eta < 60:
            return f"{eta:.0f} min"
        return f"{eta / 60:.1f} h"

    rows_skus = "".join(
        f"""
        <tr>
            <td class=\"mono\">{html.escape(s.sku)}</td>
            <td>{html.escape(s.product)}</td>
            <td class=\"mono num\">{s.available:.0f}</td>
            <td class=\"mono num\">{s.reserved:.0f}</td>
            <td class=\"mono num\">{s.incoming:.0f}{(' · ' + html.escape(s.incoming_eta[11:16])) if s.incoming_eta else ''}</td>
            <td class=\"mono num\">{s.sell_through * 100:.0f}%/h</td>
            <td class=\"mono num\">{stockout_label(s)}</td>
            <td class=\"mono num\">{s.views:.0f}</td>
            <td class=\"mono num\">{s.conversion * 100:.1f}%</td>
        </tr>
        """
        for s in top_skus
    )

    def api_chip_for(case: OrderCase) -> str:
        label, tone = shipping_badge(case.shipping_api)
        if not label:
            return '<span class="api-pill api-pill-neutral">—</span>'
        return (
            f'<span class="api-pill api-pill-{tone}" title="{html.escape(label)}">'
            f'{html.escape(label)}</span>'
        )

    rows_cases = "".join(
        f"""
        <tr>
            <td class=\"mono\">{html.escape(c.order_id)}</td>
            <td class=\"mono num\">{c.score:.1f}</td>
            <td class=\"mono num\">{c.features.get('customer_risk', 0):.0f}</td>
            <td class=\"mono num\">{c.features.get('support_risk', 0):.0f}</td>
            <td class=\"mono num\">{c.features.get('inventory_risk', 0):.0f}</td>
            <td class=\"mono num\">{c.features.get('logistics_risk', 0):.0f}</td>
            <td class=\"mono num\">{c.features.get('commercial_impact', 0):.0f}</td>
            <td>{api_chip_for(c)}</td>
        </tr>
        """
        for c in high_risk_cases
    )

    if api_lifted:
        api_lifted_rows = "".join(
            f"""
            <tr>
                <td class=\"mono\">{html.escape(c.order_id)}</td>
                <td>{api_chip_for(c)}</td>
                <td class=\"mono num\">{('+' if c.api_lifted_score > 0 else '') + format(c.api_lifted_score, '.1f')}</td>
                <td class=\"mono\">{html.escape(str((c.shipping_api or {}).get('delay_reason') or '—').replace('_', ' '))}</td>
                <td class=\"mono\">{'sí' if (c.shipping_api or {}).get('requires_manual_review') else '—'}</td>
                <td class=\"mono\">{html.escape(str((c.shipping_api or {}).get('estimated_delivery_date') or '—'))}</td>
            </tr>
            """
            for c in api_lifted[:10]
        )
        api_section = f"""
    <section>
        <div class=\"sec-head\">
            <span class=\"label\">Shipping API</span>
            <h2>Cómo cambia la decisión gracias a la API</h2>
            <p>Pedidos cuya prioridad se ha movido en al menos 1 punto al integrar la respuesta de la Shipping Status API. Si la API cae, el resto del sistema sigue funcionando con las señales internas.</p>
        </div>
        <div class=\"card\">
            <table class=\"data-table\">
                <thead><tr><th>Pedido</th><th>Estado API</th><th class=\"num\">Δ score</th><th>Motivo</th><th>Manual review</th><th>ETA</th></tr></thead>
                <tbody>{api_lifted_rows}</tbody>
            </table>
        </div>
    </section>"""
    else:
        api_section = ""

    families_html = "".join(family_chip(k, f"{k} · {v}") for k, v in families.most_common())

    demo_banner_html = (
        f'<div class="demo-banner">{html.escape(demo_banner)}</div>'
        if demo_banner else ""
    )

    if api_summary.get("called", 0) == 0:
        api_chip = "integrada · run offline (sin candidate id)"
    elif api_summary.get("ok", 0) == 0:
        api_chip = (
            f"{api_summary.get('errors', 0)} errores HTTP · "
            "fallback a datos internos sin perder ventana"
        )
    else:
        api_chip = (
            f"{api_summary.get('ok', 0)}/{api_summary.get('called', 0)} OK · "
            f"{api_summary.get('severe', 0)} severos · "
            f"{api_summary.get('manual_review', 0)} manual review · "
            f"{api_summary.get('lifted_decisions', 0)} decisiones movidas"
        )

    dq_files = data_quality["files"]
    dq_field = data_quality["field_issues"]
    dq_alerts = data_quality["business_alerts"]
    dq_orphans = data_quality["orphans"]
    dq_chips = "".join(
        meta_chip(label)
        for label in [
            f"orders · {dq_files['orders']}",
            f"items · {dq_files['order_items']}",
            f"tickets · {dq_files['support_tickets']}",
            f"campaigns · {dq_files['campaigns']}",
            f"sin order_value · {dq_field['missing_order_value']}",
            f"order_value ruidoso · {dq_field['noisy_order_value_format']}",
            f"sin segmento · {dq_field['empty_customer_segment_in_orders']}",
            f"oversell consumado · {len(dq_alerts['skus_with_reserved_above_available'])}",
            f"SKU desconocido · {len(dq_orphans['orders_with_sku_not_in_inventory'])}",
            f"clientes desconocidos · {len(dq_orphans['orders_with_unknown_customer'])}",
        ]
    )

    html_doc = f"""<!doctype html>
<html lang=\"es\">
<head>
<meta charset=\"utf-8\">
<title>Scuffers · AI Ops Control Tower</title>
<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">
<link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>
<link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap\" rel=\"stylesheet\">
<style>
:root {{
    /* Tokens de color: paleta clara, sobria, inspirada en la marca */
    --bg: #f3f1ec;
    --bg-soft: #ece9e1;
    --surface: #ffffff;
    --surface-soft: #fbfaf6;
    --glass: rgba(255, 255, 255, 0.62);
    --glass-strong: rgba(255, 255, 255, 0.78);
    --ink: #0f0e0c;
    --ink-soft: #44423d;
    --ink-mute: #8a877f;
    --ink-subtle: #b3afa5;
    --line: #e3dfd3;
    --line-soft: #ede9dc;

    /* Acentos por familia (tonos apagados, alta legibilidad) */
    --vip: #a3361f;            --vip-bg: #f6e6e0;
    --logistics: #9b6a1f;      --logistics-bg: #f4ead2;
    --marketing: #2c4d7a;      --marketing-bg: #e2eaf3;
    --support: #5a3287;        --support-bg: #ede4f3;
    --forecast: #1d6b62;       --forecast-bg: #def0ec;
    --inventory: #1d566a;      --inventory-bg: #dee9ef;
    --finance: #856719;        --finance-bg: #f3e9c7;
    --customer: #3e6a3a;       --customer-bg: #e2ece1;
    --other: #6b6860;          --other-bg: #ece8dc;

    /* Spacing scale */
    --s-1: 4px; --s-2: 8px; --s-3: 12px; --s-4: 16px; --s-5: 24px; --s-6: 32px; --s-7: 48px; --s-8: 72px;

    /* Radius */
    --r-sm: 6px; --r-md: 12px; --r-lg: 18px; --r-pill: 999px;

    /* Type */
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    --font-mono: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace;

    /* Shadows: muy sutiles */
    --shadow-1: 0 1px 2px rgba(15, 14, 12, 0.04);
    --shadow-2: 0 8px 24px rgba(15, 14, 12, 0.05);
    --shadow-glass: 0 1px 0 rgba(255, 255, 255, 0.7) inset, 0 12px 36px rgba(15, 14, 12, 0.05);
}}

*, *::before, *::after {{ box-sizing: border-box; }}
html, body {{ background: var(--bg); }}
body {{
    margin: 0;
    font-family: var(--font-sans);
    color: var(--ink);
    font-feature-settings: 'cv11' 1, 'ss01' 1, 'tnum' 1;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
    letter-spacing: -0.005em;
}}
.mono {{ font-family: var(--font-mono); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }}

/* Brand header */
.brand-header {{
    padding: var(--s-7) var(--s-7) var(--s-5);
    display: flex; justify-content: space-between; align-items: flex-end;
    gap: var(--s-5); flex-wrap: wrap;
    border-bottom: 1px solid var(--line);
    background: var(--bg);
}}
.brand-id {{ display: flex; flex-direction: column; gap: var(--s-2); }}
.brand-mark {{ font-size: 13px; font-weight: 600; letter-spacing: 0.22em; text-transform: uppercase; color: var(--ink); }}
.brand-product {{ font-size: 26px; font-weight: 400; letter-spacing: -0.02em; color: var(--ink); margin: 0; }}
.brand-tag {{ font-size: 12px; color: var(--ink-mute); letter-spacing: 0.02em; }}
.brand-meta {{ display: flex; flex-direction: column; align-items: flex-end; gap: var(--s-3); }}
.btn-dark-mini {{
    font-family: var(--font-sans); font-size: 10.5px; font-weight: 500;
    letter-spacing: 0.06em; text-transform: lowercase;
    padding: 5px 11px; border-radius: var(--r-pill); cursor: pointer;
    border: 1px solid var(--line); background: var(--surface); color: var(--ink-soft);
    text-decoration: none; line-height: 1; transition: background 0.15s ease, border-color 0.15s ease;
}}
.btn-dark-mini:hover {{ background: var(--surface-soft); border-color: var(--ink-subtle); color: var(--ink); }}
.brand-logo-wrap {{ display: block; margin-bottom: var(--s-3); }}
.brand-logo-wrap img {{
    height: auto;
    max-height: 36px;
    width: auto;
    max-width: 200px;
    display: block;
    object-fit: contain;
}}
.brand-time {{ font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-subtle); font-family: var(--font-mono); }}
.brand-pills {{ display: flex; gap: var(--s-2); flex-wrap: wrap; justify-content: flex-end; }}
.demo-banner {{
    display: flex; align-items: center; gap: 10px;
    padding: 8px 16px; margin: 0 var(--s-7);
    background: var(--surface-soft); border: 1px solid var(--line);
    border-radius: var(--r-pill);
    font-size: 11px; color: var(--ink-soft); letter-spacing: 0.02em;
    width: fit-content;
}}
.demo-banner::before {{
    content: 'DEMO'; font-weight: 600; letter-spacing: 0.16em;
    padding: 2px 8px; border-radius: var(--r-pill);
    background: var(--ink); color: var(--bg); font-size: 9.5px;
}}

/* Layout */
main {{
    max-width: 1440px; margin: 0 auto;
    padding: var(--s-6) var(--s-7) var(--s-8);
    display: flex; flex-direction: column; gap: var(--s-7);
}}

/* Section header (typography-led, editorial) */
.sec-head {{ display: flex; flex-direction: column; gap: var(--s-1); margin-bottom: var(--s-4); }}
.sec-head.row {{ flex-direction: row; align-items: flex-end; justify-content: space-between; gap: var(--s-4); flex-wrap: wrap; }}
.sec-head .label {{ font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-subtle); font-weight: 500; }}
.sec-head h2 {{ font-size: 24px; font-weight: 400; letter-spacing: -0.02em; margin: 0; }}
.sec-head p {{ margin: 0; font-size: 13px; color: var(--ink-mute); max-width: 60ch; line-height: 1.55; }}

/* Card (panel base) */
.card {{
    background: var(--surface); border: 1px solid var(--line);
    border-radius: var(--r-lg); padding: var(--s-5);
    box-shadow: var(--shadow-1);
}}
.card.glass {{
    background: var(--glass);
    backdrop-filter: blur(18px) saturate(140%);
    -webkit-backdrop-filter: blur(18px) saturate(140%);
    border: 1px solid rgba(227, 223, 211, 0.7);
    box-shadow: var(--shadow-glass);
}}

/* Hero (TOP 3) */
.hero-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--s-4); }}
@media (max-width: 980px) {{ .hero-grid {{ grid-template-columns: 1fr; }} }}
.hero {{
    position: relative; overflow: hidden;
    background: var(--surface); border: 1px solid var(--line);
    border-radius: var(--r-lg); padding: var(--s-5);
    display: flex; flex-direction: column; gap: var(--s-3);
    box-shadow: var(--shadow-1);
}}
.hero::before {{
    content: ''; position: absolute; left: 0; top: 0; bottom: 0;
    width: 2px; background: var(--ink);
}}
.hero-vip::before    {{ background: var(--vip); }}
.hero-logistics::before {{ background: var(--logistics); }}
.hero-marketing::before {{ background: var(--marketing); }}
.hero-support::before   {{ background: var(--support); }}
.hero-forecast::before  {{ background: var(--forecast); }}
.hero-inventory::before {{ background: var(--inventory); }}
.hero-finance::before   {{ background: var(--finance); }}
.hero-customer::before  {{ background: var(--customer); }}
.hero-head {{ display: flex; align-items: center; gap: var(--s-2); flex-wrap: wrap; }}
.hero-rank {{ font-family: var(--font-mono); font-size: 12px; color: var(--ink-subtle); letter-spacing: 0.02em; }}
.hero-target {{ font-size: 11px; color: var(--ink-mute); margin-left: auto; }}
.hero h3 {{ margin: 0; font-size: 17px; font-weight: 500; letter-spacing: -0.01em; line-height: 1.4; }}
.hero-reason {{ margin: 0; font-size: 13px; color: var(--ink-soft); line-height: 1.6; }}
.hero-meta {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--s-3); padding-top: var(--s-3); border-top: 1px solid var(--line-soft); }}
.hero-meta span {{ display: flex; flex-direction: column; gap: 2px; }}
.hero-meta label {{ font-size: 9px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-subtle); font-weight: 500; }}
.hero-meta strong {{ font-family: var(--font-mono); font-size: 14px; font-weight: 500; color: var(--ink); }}

/* Chip system */
.chip {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; border-radius: var(--r-pill);
    font-size: 11px; font-weight: 500; letter-spacing: 0.01em;
    border: 1px solid transparent; line-height: 1; white-space: nowrap;
}}
.chip-meta     {{ color: var(--ink-soft); background: var(--surface-soft); border-color: var(--line); }}
.chip-vip       {{ color: var(--vip); background: var(--vip-bg); border-color: rgba(163, 54, 31, 0.18); }}
.chip-logistics {{ color: var(--logistics); background: var(--logistics-bg); border-color: rgba(155, 106, 31, 0.18); }}
.chip-marketing {{ color: var(--marketing); background: var(--marketing-bg); border-color: rgba(44, 77, 122, 0.18); }}
.chip-support   {{ color: var(--support); background: var(--support-bg); border-color: rgba(90, 50, 135, 0.18); }}
.chip-forecast  {{ color: var(--forecast); background: var(--forecast-bg); border-color: rgba(29, 107, 98, 0.18); }}
.chip-inventory {{ color: var(--inventory); background: var(--inventory-bg); border-color: rgba(29, 86, 106, 0.18); }}
.chip-finance   {{ color: var(--finance); background: var(--finance-bg); border-color: rgba(133, 103, 25, 0.18); }}
.chip-customer  {{ color: var(--customer); background: var(--customer-bg); border-color: rgba(62, 106, 58, 0.18); }}
.chip-other     {{ color: var(--other); background: var(--other-bg); border-color: rgba(107, 104, 96, 0.18); }}

/* Live feed (panel translucido sutil) */
.live-controls {{ display: flex; align-items: center; gap: var(--s-3); flex-wrap: wrap; margin-bottom: var(--s-4); }}
.live-status {{ display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: var(--ink-mute); }}
.live-dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--vip); animation: pulse 1.6s infinite; }}
.live-dot.online {{ background: var(--forecast); animation: pulse-on 1.6s infinite; }}
@keyframes pulse {{ 0%,100% {{ box-shadow: 0 0 0 0 rgba(163, 54, 31, 0.35); }} 50% {{ box-shadow: 0 0 0 6px rgba(163, 54, 31, 0); }} }}
@keyframes pulse-on {{ 0%,100% {{ box-shadow: 0 0 0 0 rgba(29, 107, 98, 0.35); }} 50% {{ box-shadow: 0 0 0 6px rgba(29, 107, 98, 0); }} }}
.live-helper {{ font-size: 12px; color: var(--ink-mute); margin-left: auto; max-width: 50ch; text-align: right; }}
.live {{ display: grid; grid-template-columns: 2fr 1fr; gap: var(--s-4); }}
@media (max-width: 1080px) {{ .live {{ grid-template-columns: 1fr; }} }}
.live-feed {{
    list-style: none; padding: 0; margin: 0;
    max-height: 340px; overflow-y: auto;
    border: 1px solid var(--line-soft); border-radius: var(--r-md);
    background: var(--surface);
}}
.live-feed li {{
    display: grid; grid-template-columns: 64px 110px 124px 1fr 96px;
    gap: var(--s-3); padding: var(--s-3) var(--s-4);
    border-bottom: 1px solid var(--line-soft);
    align-items: center; font-size: 12px;
}}
.live-feed li:last-child {{ border-bottom: 0; }}
.live-feed li.new {{ animation: slidein 0.5s ease; background: rgba(15, 14, 12, 0.025); }}
@keyframes slidein {{ from {{ opacity: 0; transform: translateX(-12px); }} to {{ opacity: 1; transform: translateX(0); }} }}
.live-feed .time {{ font-family: var(--font-mono); font-size: 11px; color: var(--ink-subtle); }}
.live-feed .oid  {{ font-family: var(--font-mono); font-size: 11px; color: var(--ink); }}
.live-feed .sku  {{ font-family: var(--font-mono); font-size: 11px; color: var(--marketing); }}
.live-feed .right {{ text-align: right; font-family: var(--font-mono); font-size: 12px; color: var(--ink); }}
.live-feed .vip {{ color: var(--vip); font-weight: 600; }}
.live-stats {{ display: grid; grid-template-rows: auto auto auto; gap: var(--s-3); align-content: start; }}
.live-stat {{ background: var(--surface); border: 1px solid var(--line-soft); border-radius: var(--r-md); padding: var(--s-4); }}
.live-stat label {{ font-size: 9px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--ink-subtle); font-weight: 500; }}
.live-stat strong {{ display: block; font-family: var(--font-mono); font-size: 24px; font-weight: 500; letter-spacing: -0.02em; margin-top: var(--s-1); color: var(--ink); }}
.live-stat span {{ display: block; font-size: 11px; color: var(--ink-mute); margin-top: 2px; }}

/* Buttons */
.btn {{
    font-family: var(--font-sans); font-size: 12px; font-weight: 500; letter-spacing: 0.01em;
    padding: 8px 16px; border-radius: var(--r-pill); cursor: pointer;
    border: 1px solid var(--ink); background: var(--ink); color: var(--surface);
    transition: opacity 0.15s ease, transform 0.15s ease;
}}
.btn:hover {{ opacity: 0.86; transform: translateY(-1px); }}
.btn.ghost {{ background: transparent; color: var(--ink); border-color: var(--line); }}
.btn.ghost:hover {{ background: var(--surface); opacity: 1; transform: none; }}

/* Tables (editorial, finas, generosas) */
.data-table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; }}
.data-table thead th {{
    text-transform: uppercase; font-size: 9.5px; letter-spacing: 0.14em;
    font-weight: 500; color: var(--ink-subtle);
    padding: var(--s-3) var(--s-4); text-align: left;
    border-bottom: 1px solid var(--line); background: transparent;
}}
.data-table thead th.num {{ text-align: right; }}
.data-table tbody td {{
    padding: var(--s-4); border-bottom: 1px solid var(--line-soft);
    vertical-align: top; color: var(--ink); line-height: 1.55;
}}
.data-table tbody td.num {{ text-align: right; color: var(--ink-soft); }}
.data-table tbody tr:hover td {{ background: var(--surface-soft); }}
.data-table tbody tr:last-child td {{ border-bottom: 0; }}
.data-table .rank {{ font-size: 11px; color: var(--ink-subtle); }}
.data-table .reason {{ max-width: 420px; color: var(--ink-soft); font-size: 12.5px; }}
.data-table .meta {{ display: block; font-family: var(--font-mono); font-size: 10.5px; color: var(--ink-subtle); margin-top: 4px; letter-spacing: 0.01em; }}

/* Family chips strip */
.family-strip {{ display: flex; flex-wrap: wrap; gap: var(--s-2); margin-bottom: var(--s-4); }}

/* Grid 2-col panels */
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-5); }}
@media (max-width: 1080px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}

/* API pill (estado logistico compacto) */
.api-pill {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 2px 8px; border-radius: var(--r-pill);
    font-size: 10.5px; font-family: var(--font-mono); font-weight: 500;
    border: 1px solid; line-height: 1.4; white-space: nowrap;
}}
.api-pill-severe    {{ color: var(--vip);       background: var(--vip-bg);       border-color: rgba(163, 54, 31, 0.25); }}
.api-pill-manual    {{ color: var(--logistics); background: var(--logistics-bg); border-color: rgba(155, 106, 31, 0.25); }}
.api-pill-recovered {{ color: var(--forecast);  background: var(--forecast-bg);  border-color: rgba(29, 107, 98, 0.25); }}
.api-pill-ok        {{ color: var(--marketing); background: var(--marketing-bg); border-color: rgba(44, 77, 122, 0.25); }}
.api-pill-error     {{ color: var(--ink-soft);  background: var(--surface-soft); border-color: var(--line); border-style: dashed; }}
.api-pill-neutral   {{ color: var(--ink-subtle); background: transparent;        border-color: transparent; font-family: var(--font-sans); font-size: 11px; }}

/* DQ panel */
.dq-strip {{ display: flex; flex-wrap: wrap; gap: var(--s-2); }}
.dq-note {{ margin-top: var(--s-3); font-size: 12px; color: var(--ink-mute); }}
.dq-note code {{ font-family: var(--font-mono); padding: 1px 6px; background: var(--surface-soft); border: 1px solid var(--line-soft); border-radius: var(--r-sm); font-size: 11px; }}

/* Modal (glass overlay) */
.live-modal {{
    position: fixed; inset: 0; z-index: 50;
    background: rgba(15, 14, 12, 0.32);
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
    display: none; align-items: center; justify-content: center;
}}
.live-modal.open {{ display: flex; }}
.live-modal-card {{
    background: var(--surface); border: 1px solid var(--line);
    border-radius: var(--r-lg); padding: var(--s-6);
    max-width: 480px; width: 92%;
    box-shadow: var(--shadow-2);
}}
.live-modal-card h3 {{ margin: 0 0 var(--s-2); font-weight: 500; font-size: 18px; letter-spacing: -0.01em; }}
.live-modal-card p {{ color: var(--ink-mute); font-size: 13px; line-height: 1.6; margin: 0; }}
.live-modal-card input {{
    width: 100%; padding: 12px 14px; border-radius: var(--r-md);
    border: 1px solid var(--line); background: var(--surface-soft);
    color: var(--ink); font-family: var(--font-mono); font-size: 12.5px;
    margin: var(--s-4) 0;
}}
.live-modal-card input:focus {{ outline: none; border-color: var(--ink); background: var(--surface); }}
.live-modal-actions {{ display: flex; justify-content: flex-end; gap: var(--s-2); }}

/* Footer */
.brand-footer {{
    padding: var(--s-6) var(--s-7);
    border-top: 1px solid var(--line);
    color: var(--ink-subtle);
    font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase;
    text-align: center;
}}

::selection {{ background: var(--ink); color: var(--bg); }}
::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: var(--line); border-radius: var(--r-pill); border: 2px solid var(--bg); }}
::-webkit-scrollbar-thumb:hover {{ background: var(--ink-subtle); }}
</style>
</head>
<body>
<header class=\"brand-header\">
    <div class=\"brand-id\">
        <a href=\"https://www.scuffers.com/\" class=\"brand-logo-wrap\" target=\"_blank\" rel=\"noopener noreferrer\" title=\"Scuffers\">
            <img src=\"https://images.teamtailor-cdn.com/images/s3/teamtailor-production/gallery_picture-v6/image_uploads/b6a6d00e-1b18-4f33-a535-d9558125695c/original.png\" alt=\"Scuffers\" loading=\"lazy\" decoding=\"async\" />
        </a>
        <h1 class=\"brand-product\">AI Ops Control Tower</h1>
        <span class=\"brand-tag\">Las decisiones que hay que tomar mientras corre el drop.</span>
    </div>
    <div class=\"brand-meta\">
        <a href=\"https://scuffers-control-tower-dark-production.up.railway.app/\" class=\"btn-dark-mini\" target=\"_blank\" rel=\"noopener noreferrer\">dark mode</a>
        <span class=\"brand-time\">{datetime.now(timezone.utc).strftime('%Y · %m · %d  ·  %H:%M UTC')}</span>
        <div class=\"brand-pills\">
            {meta_chip(f'{len(cases)} pedidos')}
            {meta_chip(f'{len(skus)} SKUs')}
            {meta_chip(f'Shipping API · {api_chip}')}
        </div>
    </div>
</header>
{demo_banner_html}
<main>
    <section>
        <div class=\"sec-head\">
            <span class=\"label\">Now / Top 3</span>
            <h2>Las tres decisiones que el equipo debería ejecutar ya</h2>
            <p>Diversificadas por familia y validadas con datos internos del drop. Cada tarjeta lleva su priority score, confianza, ventana de validez y modo de ejecución.</p>
        </div>
        <div class=\"hero-grid\">{hero_cards}</div>
    </section>

    <section class=\"card glass\">
        <div class=\"sec-head row\">
            <div>
                <span class=\"label\">Live · Drop feed</span>
                <h2>Drop en directo</h2>
                <p>Replay cronológico de los pedidos del drop. Conecta un webhook real (Shopify orders/create, SSE o endpoint propio) para fusionar pedidos en tiempo real.</p>
            </div>
            <div class=\"live-controls\">
                <span class=\"live-status\"><span class=\"live-dot\" id=\"live-dot\"></span><span id=\"live-status-label\">Modo simulación offline</span></span>
                <button class=\"btn\" id=\"live-connect\">Conectar feed en vivo</button>
                <button class=\"btn ghost\" id=\"live-pause\">Pausar</button>
                <button class=\"btn ghost\" id=\"live-clear\">Limpiar</button>
            </div>
        </div>
        <div class=\"live\">
            <ul class=\"live-feed\" id=\"live-feed\"></ul>
            <div class=\"live-stats\">
                <div class=\"live-stat\"><label>Pedidos recibidos</label><strong id=\"live-count\">0</strong><span id=\"live-rate\">0 pedidos/min</span></div>
                <div class=\"live-stat\"><label>Importe acumulado</label><strong id=\"live-revenue\">0 EUR</strong><span id=\"live-aov\">AOV 0 EUR</span></div>
                <div class=\"live-stat\"><label>SKU más pedido (últimos 12)</label><strong id=\"live-top-sku\">—</strong><span id=\"live-top-city\">Ciudad: —</span></div>
            </div>
        </div>
    </section>

    <section>
        <div class=\"sec-head\">
            <span class=\"label\">Top 10 priorizado</span>
            <h2>Acciones recomendadas</h2>
            <p>Cada acción lleva owner, score interpretable, confianza, ventana de validez y motivo verificable. Diversificación por familia con caps definidos en el motor.</p>
        </div>
        <div class=\"family-strip\">{families_html}</div>
        <div class=\"card\">
            <table class=\"data-table\">
                <thead>
                    <tr><th>#</th><th>Decisión</th><th>Acción</th><th>Owner</th><th class=\"num\">Score</th><th class=\"num\">Conf.</th><th class=\"num\">Validez</th><th>Modo</th><th>Motivo</th></tr>
                </thead>
                <tbody>{rows_actions}</tbody>
            </table>
        </div>
    </section>
    {api_section}
    <div class=\"grid-2\">
        <section class=\"card\">
            <div class=\"sec-head\">
                <span class=\"label\">Inventario</span>
                <h2>SKUs críticos</h2>
                <p>Velocidad y stockout estimado al ritmo actual.</p>
            </div>
            <table class=\"data-table\">
                <thead><tr><th>SKU</th><th>Producto</th><th class=\"num\">Disp.</th><th class=\"num\">Reserv.</th><th class=\"num\">Entrante</th><th class=\"num\">STR/h</th><th class=\"num\">Stockout</th><th class=\"num\">Vistas/h</th><th class=\"num\">Conv.</th></tr></thead>
                <tbody>{rows_skus}</tbody>
            </table>
        </section>
        <section class=\"card\">
            <div class=\"sec-head\">
                <span class=\"label\">Pedidos</span>
                <h2>Mayor score de riesgo</h2>
                <p>Descomposición por las cinco señales explicables del modelo.</p>
            </div>
            <table class=\"data-table\">
                <thead><tr><th>Pedido</th><th class=\"num\">Score</th><th class=\"num\">Cliente</th><th class=\"num\">Soporte</th><th class=\"num\">Inv.</th><th class=\"num\">Logística</th><th class=\"num\">Impacto</th><th>API</th></tr></thead>
                <tbody>{rows_cases}</tbody>
            </table>
        </section>
    </div>

    <section>
        <div class=\"sec-head\">
            <span class=\"label\">Calidad de datos</span>
            <h2>Lo que el motor encontró al cargar los CSV</h2>
            <p>La confianza de cada acción se ajusta a estos hallazgos. Detalle completo en <code>data_quality.json</code>.</p>
        </div>
        <div class=\"card\">
            <div class=\"dq-strip\">{dq_chips}</div>
        </div>
    </section>
</main>
<footer class=\"brand-footer\">Python stdlib · Shipping Status API · score interpretable · diversificación por familia · validez por tipo</footer>
<div class=\"live-modal\" id=\"live-modal\">
    <div class=\"live-modal-card\">
        <h3>Conectar feed en vivo</h3>
        <p>Apunta a un webhook de Shopify (<code>orders/create</code>), un endpoint Server-Sent Events o cualquier streaming endpoint propio que devuelva JSON con campos <code>order_id, customer_id, sku, city, value</code>. El dashboard fusionará esos pedidos con el simulador del drop.</p>
        <input id=\"live-webhook\" placeholder=\"https://api.scuffers.com/webhooks/orders\" />
        <div class=\"live-modal-actions\">
            <button class=\"btn ghost\" id=\"live-cancel\">Cancelar</button>
            <button class=\"btn\" id=\"live-confirm\">Conectar</button>
        </div>
    </div>
</div>
</body>
</html>
"""
    script = LIVE_FEED_SCRIPT.replace(
        "__LIVE_FEED_DATA__", json.dumps(live_feed, ensure_ascii=False)
    )
    html_doc = html_doc.replace("</body>", script + "\n</body>")
    path.write_text(html_doc, encoding="utf-8")


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------


def run_pipeline(
    data_dir: Path,
    out_dir: Path,
    candidate_id: str,
    api_top: int,
    use_api: bool,
    *,
    demo_banner: str = "",
) -> dict[str, Any]:
    rows = load_csvs(data_dir)
    if not rows:
        raise RuntimeError(f"No se encontraron CSVs en: {data_dir}")

    (
        cases_by_id,
        customers_by_id,
        inventory_by_sku,
        items_by_order,
        campaigns,
        tickets_by_order,
    ) = assemble_order_cases(rows)
    cases = list(cases_by_id.values())
    for case in cases:
        compute_order_features(case)

    api_summary: dict[str, Any] = dict(EMPTY_API_SUMMARY)
    api_summary["log"] = []
    if use_api and candidate_id:
        api_summary = enrich_with_shipping_api(
            cases,
            candidate_id,
            api_top,
            recompute_features=compute_order_features,
        )

    skus = build_sku_views(inventory_by_sku, items_by_order, campaigns)

    candidates: list[dict[str, Any]] = []
    candidates.extend(detect_vip_rescue(cases))
    candidates.extend(detect_logistics_escalation(cases))
    candidates.extend(detect_payment_review_audit(cases))
    candidates.extend(detect_express_priority(cases))
    candidates.extend(detect_proactive_at_risk(cases))
    candidates.extend(detect_proactive_delay_outreach(cases))
    candidates.extend(detect_oversell_prevention(skus))
    candidates.extend(detect_stock_reallocation(skus))
    candidates.extend(detect_demand_forecast(skus))
    candidates.extend(detect_macro_response(tickets_by_order))
    candidates.extend(detect_carrier_capacity(cases))

    actions = diversify_actions(candidates, limit=10)
    data_quality = assess_data_quality(
        rows, cases_by_id, skus, customers_by_id, items_by_order, tickets_by_order
    )
    write_outputs(
        actions, cases, skus, api_summary, data_quality, out_dir,
        demo_banner=demo_banner,
    )

    return {
        "rows": len(rows),
        "orders": len(cases),
        "skus": len(skus),
        "candidates": len(candidates),
        "actions": len(actions),
        "api_summary": api_summary,
        "data_quality": {
            "files": data_quality["files"],
            "field_issues": data_quality["field_issues"],
            "oversold_skus": data_quality["business_alerts"]["skus_with_reserved_above_available"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scuffers AI Ops Control Tower (UDIA hackathon 2026)"
    )
    parser.add_argument("--data", default="data", help="Carpeta con CSVs del reto")
    parser.add_argument("--out", default="outputs", help="Carpeta de salida")
    parser.add_argument(
        "--candidate-id",
        default=os.getenv("SCF_CANDIDATE_ID", ""),
        help="ID de candidato (# opcional), ej. #SCF-2026-6594 para Shipping API",
    )
    parser.add_argument(
        "--api-top",
        type=int,
        default=25,
        help="Cuantos pedidos top enriquecer con la Shipping Status API",
    )
    parser.add_argument(
        "--no-api",
        action="store_true",
        help="No consultar la Shipping Status API",
    )
    parser.add_argument(
        "--demo-banner",
        default="",
        help=(
            "Si se pasa un texto, se muestra en el header del dashboard como "
            "etiqueta de demo (util para snapshots publicos con datos simulados)."
        ),
    )
    args = parser.parse_args()

    data_dir = Path(args.data)
    out_dir = Path(args.out)
    if not data_dir.exists():
        print(f"No existe la carpeta de datos: {data_dir}", file=sys.stderr)
        return 2

    candidate_id = args.candidate_id.strip().replace("#", "")
    use_api = not args.no_api and bool(candidate_id)
    if not use_api:
        print(
            "Shipping API omitida (define SCF_CANDIDATE_ID o usa --candidate-id para activarla)."
        )

    summary = run_pipeline(
        data_dir, out_dir, candidate_id, args.api_top, use_api,
        demo_banner=args.demo_banner.strip(),
    )

    print(
        f"Filas leidas: {summary['rows']} | Pedidos: {summary['orders']} | SKUs: {summary['skus']} | "
        f"Acciones candidatas: {summary['candidates']} | Top final: {summary['actions']}"
    )
    api = summary["api_summary"]
    print(
        f"Shipping API -> llamadas: {api.get('called', 0)}, ok: {api.get('ok', 0)}, "
        f"errores: {api.get('errors', 0)}, manual_review: {api.get('manual_review', 0)}, "
        f"severos: {api.get('severe', 0)}, recuperados: {api.get('recovered', 0)}, "
        f"decisiones movidas: {api.get('lifted_decisions', 0)}"
    )
    dq = summary["data_quality"]
    print(
        "Data quality -> "
        f"sin order_value: {dq['field_issues']['missing_order_value']}, "
        f"order_value ruidoso: {dq['field_issues']['noisy_order_value_format']}, "
        f"sin segmento: {dq['field_issues']['empty_customer_segment_in_orders']}, "
        f"oversell: {len(dq['oversold_skus'])} SKUs"
        + (f" ({', '.join(dq['oversold_skus'])})" if dq['oversold_skus'] else "")
    )
    print(f"Top 10 -> {out_dir / 'top_actions.json'}")
    print(f"Reporte -> {out_dir / 'report.md'}")
    print(f"Dashboard -> {out_dir / 'dashboard.html'}")
    print(f"Calidad de datos -> {out_dir / 'data_quality.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
