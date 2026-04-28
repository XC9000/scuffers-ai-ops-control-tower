# Scuffers · AI Ops Control Tower

Sistema de priorización operativa para la ventana crítica de un drop: unifica pedidos, inventario, campañas, soporte y señal logística vía **Shipping Status API** (opcional), y produce un **Top 10 de acciones** con score interpretable, owner, confianza y ventana de validez.

**Stack:** Python 3 (stdlib únicamente) · salidas JSON, Markdown y dashboard HTML autocontenido.

---

## Demo y documentación de entrega

| Recurso | Enlace |
|--------|--------|
| **Dashboard (GitHub Pages)** | [Abrir demo en vivo](https://xc9000.github.io/scuffers-ai-ops-control-tower/) |
| **Repositorio** | [github.com/XC9000/scuffers-ai-ops-control-tower](https://github.com/XC9000/scuffers-ai-ops-control-tower) |
| **Resumen ejecutivo y arquitectura** | [ENTREGA.md](ENTREGA.md) |
| **Top 10 (JSON)** | [docs/top_actions.json](docs/top_actions.json) |
| **Reporte operativo** | [docs/report.md](docs/report.md) |
| **Auditoría Shipping API** (cuando aplica) | [docs/shipping_api_log.json](docs/shipping_api_log.json) |

> El snapshot servido en Pages incluye la integración de la API de envíos con respuestas simuladas (mock) para mostrar la cadena completa en un entorno público; el pipeline es el mismo que contra la API del enunciado. Detalle en `ENTREGA.md`.

---

## Cómo ejecutar (local)

Desde `hackathon_control_tower/`:

```powershell
# Análisis sin llamadas externas (misma lógica, sin enriquecimiento logístico)
python control_tower.py --data ../scuffers_all_mock_data/candidate_csvs --out outputs_full --no-api

# Con Shipping Status API (definir candidate id del organizador)
python control_tower.py --data ../scuffers_all_mock_data/candidate_csvs --out outputs_full --candidate-id SCF-2026-XXXX
```

Variables útiles: `SCF_CANDIDATE_ID` (candidate id por defecto), `SCF_SHIPPING_API_BASE` (override del endpoint, p. ej. mock local para demo).

Salidas en `--out`: `top_actions.json`, `report.md`, `dashboard.html`, `data_quality.json`, y `shipping_api_log.json` si hubo llamadas a la API.

---

## Arquitectura (visión de ingeniería)

1. **Ingesta tolerante** — Cruza órdenes, líneas, clientes, inventario, tickets y campañas; normaliza SKUs ruidosos y campos inconsistentes.
2. **Scoring explicable** — Cinco dimensiones por pedido (`customer_risk`, `support_risk`, `inventory_risk`, `logistics_risk`, `commercial_impact`), combinadas en un priority score auditable.
3. **Capa logística incremental** — Módulo [`shipping_api.py`](hackathon_control_tower/shipping_api.py): llamadas selectivas, normalización defensiva de respuesta, fallback si la API falla; recalcula scoring sin sustituir la lógica base.
4. **Detectores de acción** — Diez familias de intervención (rescate VIP, pausa de campaña, throttle por oversell, pronóstico de demanda por analogía con drops previos, macros de soporte, escalado carrier, etc.).
5. **Diversificación** — Límite por familia y por `target_id` para evitar un Top 10 homogéneo.
6. **Presentación** — JSON para integración, Markdown para briefings, HTML para operaciones en sala de control.

Documentación técnica ampliada: [`hackathon_control_tower/README.md`](hackathon_control_tower/README.md).

---

## Estructura del repositorio

| Ruta | Contenido |
|------|------------|
| `hackathon_control_tower/` | Código del Control Tower, módulo de API, guías de pitch y plan de reto |
| `docs/` | Assets estáticos para GitHub Pages (no modificar para la demo en producción salvo acuerdo explícito) |
| `scuffers_all_mock_data/` | CSVs de candidato / reto |
| `ENTREGA.md` | Texto de entrega: resumen, arquitectura, top 10, limitaciones |
| `*.md` / `generar_docx.py` | Material de preparación y generación de documentos Word (proceso de selección) |

---

## Preparación al proceso (material adicional)

Proyecto base con guías y propuestas técnicas en Markdown; generación de `.docx` con `python generar_docx.py` (sin dependencias externas). No forma parte del entregable mínimo del Control Tower; ver archivos en raíz y `Propuesta tecnica detallada` / `Guia completa` en `.docx` si aplica.

---

**Autor / candidato:** entrega hackathon Scuffers (UDIA) · 2026
