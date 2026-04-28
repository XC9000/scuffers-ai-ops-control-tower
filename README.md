# Scuffers · AI Ops Control Tower

En la ventana crítica de un drop, el problema rara vez es la falta de datos: es **ordenar el caos** antes de que se convierta en cancelaciones, tickets y reputación en riesgo. Esta torre de control une pedidos, inventario, campañas, soporte y, cuando aplica, la señal logística de la **Shipping Status API**, y devuelve un **Top 10 de acciones** con score interpretable, responsable asignado y ventana de validez.

Cuando el ritmo lo impone todo, la interfaz debe ganar en claridad y perder en ruido: prioridades visibles al instante, motivos verificables y una lectura que funcione tanto en sala de crisis como frente a un comité.

### Demo alternativa (Railway) · tema oscuro y más funciones

Versión desplegada en Railway con interfaz **dark** y funcionalidades ampliadas respecto al snapshot estático de Pages:

**→ [https://scuffers-control-tower-dark-production.up.railway.app/](https://scuffers-control-tower-dark-production.up.railway.app/)**

### Demo en vivo

**→ [https://xc9000.github.io/scuffers-ai-ops-control-tower/](https://xc9000.github.io/scuffers-ai-ops-control-tower/)**

No requiere instalación: dashboard autocontenido, pensado para revisión rápida desde cualquier navegador.

**Stack:** Python 3 (stdlib únicamente) · salidas JSON, Markdown y HTML.

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

## Arquitectura (visión de ingeniería)

1. **Ingesta tolerante** — Cruza órdenes, líneas, clientes, inventario, tickets y campañas; normaliza SKUs ruidosos y campos inconsistentes.
2. **Scoring explicable** — Cinco dimensiones por pedido (`customer_risk`, `support_risk`, `inventory_risk`, `logistics_risk`, `commercial_impact`), combinadas en un priority score auditable.
3. **Capa logística incremental** — Módulo [`shipping_api.py`](hackathon_control_tower/shipping_api.py): llamadas selectivas, normalización defensiva de respuesta, fallback si la API falla; recalcula scoring sin sustituir la lógica base.
4. **Detectores de acción** — Diez familias de intervención (rescate VIP, pausa de campaña, throttle por oversell, pronóstico de demanda por analogía con drops previos, macros de soporte, escalado carrier, etc.).
5. **Diversificación** — Límite por familia y por `target_id` para evitar un Top 10 homogéneo.
6. **Presentación** — JSON para integración, Markdown para briefings, HTML para operaciones en sala de control.

Documentación técnica ampliada (incluye ejecución local del pipeline): [`hackathon_control_tower/README.md`](hackathon_control_tower/README.md).

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
