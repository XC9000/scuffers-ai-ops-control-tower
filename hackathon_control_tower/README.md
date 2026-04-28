# Scuffers AI Ops Control Tower — Documentación técnica

Entregable del reto: pipeline batch en **Python 3, solo stdlib**, diseñado para priorizar decisiones en un drop con datos imperfectos y enriquecimiento opcional vía **Shipping Status API**.

---

## Objetivo del producto

Reducir la carga cognitiva del equipo de operaciones en la ventana crítica: en lugar de consumir seis fuentes a la vez, el operador recibe **hasta 10 acciones** con:

- `priority_score` (0–100) y trazabilidad
- `confidence` y `valid_for_minutes` (ventana operativa)
- `owner` (customer_care, marketing, merchandising, operations)
- Motivo verificable (incl. tiempo a stockout y estimaciones EUR cuando aplica)

---

## Ejecución

```powershell
cd hackathon_control_tower

# Producción / revisión sin API (priorización solo con datos internos)
python control_tower.py --data ..\scuffers_all_mock_data\candidate_csvs --out outputs_full --no-api

# Con Shipping Status API (variable de entorno o flag)
python control_tower.py --data ..\scuffers_all_mock_data\candidate_csvs --out outputs_full --candidate-id '#SCF-2026-6594' --api-top 25

# Banner opcional en el HTML (ej. snapshot público etiquetado como demo)
python control_tower.py ... --demo-banner "Texto breve para revisores"
```

**Variables de entorno**

| Variable | Uso |
|----------|-----|
| `SCF_CANDIDATE_ID` | Candidate ID por defecto si no se pasa `--candidate-id` |
| `SCF_SHIPPING_API_BASE` | Override del prefijo URL de la API (p. ej. mock local para validación end-to-end) |

La API es **opt-in**: si no hay candidate id o se usa `--no-api`, el sistema sigue generando el Top 10 con la misma lógica de scoring sobre CSV; la confianza no se incrementa por capa logística no consultada.

---

## Salidas

Cada run escribe en `--out`:

| Archivo | Descripción |
|---------|-------------|
| `top_actions.json` | Top 10 con el esquema del enunciado + `priority_score` y `valid_for_minutes` |
| `report.md` | TL;DR, tablas, racional de scoring, impacto de la API si hubo llamadas, supuestos y data quality |
| `dashboard.html` | Panel operativo: hero Top 3, feed de pedidos, Top 10, tablas de SKUs y riesgo, sección de impacto API |
| `data_quality.json` | Duplicados, huérfanos, oversell, campos ruidosos, etc. |
| `shipping_api_log.json` | Solo si hubo llamadas: latencia, estado, delta de score por pedido |

---

## Ingeniería

### Módulos principales

- **`control_tower.py`** — Orquestación: carga, features, detectores, diversificación, escritura de salidas.
- **`shipping_api.py`** — Cliente HTTP, normalización defensiva de payload, política de pedidos relevantes para consultar, helpers de texto/UI.

### Flujo de datos (resumen)

1. Carga y ensamblado de casos por pedido (`assemble_order_cases`).
2. Cálculo de features y score base (`compute_order_features`).
3. Enriquecimiento opcional por API (`enrich_with_shipping_api` → recálculo de features).
4. Detección de candidatos por tipo de acción (rescates, marketing, forecast, soporte, logística…).
5. `diversify_actions`: caps por familia y deduplicación por target.

### Detectores (familias)

Incluyen entre otros: `vip_rescue`, `pause_campaign` / `throttle_traffic`, `demand_forecast_*`, `support_macro_response`, `carrier_escalation` / `address_validation_fix` / `manual_shipping_review`, `payment_review_audit`, `proactive_customer_contact`, `carrier_capacity_review` (con umbral estricto para evitar ruido).

### Pronóstico de demanda

Heurística por analogía con drops tipo cápsula (pico y decaimiento configurable) cuando no hay histórico explícito en los datos; gap traducido a unidades y EUR para soporte a decisión de merchandising.

---

## Referencias en este directorio

| Documento | Contenido |
|-----------|-----------|
| `ENUNCIADO_RESUMIDO.md` | Contexto del reto reconstruido |
| `PLAN_RETO_SCUFFERS.md` | Estrategia de solución y scoring |
| `PITCH_Y_DEMO.md` | Pitch corto, demo guiada, Q&A |

---

## Fuente de verdad del Top 10

Las tablas estáticas en documentación quedan obsoletas ante cualquier cambio de datos o modo API. Para revisión objetiva, usar siempre el **`top_actions.json`** generado en el último run (en el repo público: carpeta `docs/` como snapshot de entrega).

---

## Limitaciones operativas (transparencia)

- Pesos y umbrales son heurísticos y auditables; sustituibles por configuración o por aprendizaje offline cuando existan etiquetas de resultado.
- La curva de demanda sin histórico real es un proxy; con datos de drops previos se sustituye el núcleo sin cambiar el resto del pipeline.
- Sin persistencia entre ejecuciones: diseño batch reproducible; extensión natural = base de datos operativa y jobs programados.

Para el texto de entrega consolidado (resumen ejecutivo, arquitectura, limitaciones), ver **`../ENTREGA.md`** en la raíz del repositorio.
