# Scuffers AI Ops Control Tower · Entrega hackathon UDIA

> Sistema de priorización operativa para drops de alta demanda. Lee los CSV
> sucios del negocio, los cruza, calcula riesgos explicables, consulta de
> forma selectiva la Shipping Status API y devuelve las 10 acciones que el
> equipo de Scuffers debería ejecutar **ahora mismo**, con owner, ventana de
> validez y confianza.

---

## 1. Resumen ejecutivo (60s)

Durante un drop, el equipo de Scuffers ve cien señales sueltas y tiene que
decidir en minutos. Hemos construido una **AI Ops Control Tower**: un único
panel que une pedidos, inventario, soporte, campañas y la API logística, y
devuelve **las 10 decisiones priorizadas con score interpretable, owner y
ventana de validez**. El motor ya recoge oversell consumado en 5 SKUs, anticipa
roturas con un pronóstico de demanda por analogía a drops anteriores y propone
acciones automáticas (pausar campaña, reasignar stock, macro de soporte) y
acciones humanas (rescate VIP, escalado a carrier). La Shipping Status API se
integra como **capa incremental**: se llama solo a los pedidos relevantes
(top score + VIP + tickets urgentes + internacionales + payment_review),
enriquece el `logistics_risk` y mueve la decisión hasta **+19 puntos** cuando
detecta `exception · warehouse_delay`. Si la API cae, el sistema sigue
funcionando con datos internos. Demo abierta en navegador, dashboard
self-contained, JSON conforme al esquema del enunciado.

---

## 2. Enfoque y arquitectura

**Stack**: Python 3.11 stdlib (cero dependencias) → arranca en cualquier
portátil. HTML + CSS + JS vanilla para el dashboard.

```
[ 6 CSV imperfectos ]                     [ Shipping Status API ]
        │                                            │
        ▼                                            ▼
  load_csvs ──► assemble_order_cases ──► compute_order_features
        │                                            │
        │                                            │ (callback recompute)
        ▼                                            ▼
  build_sku_views                       enrich_with_shipping_api
        │           │                                │
        ▼           ▼                                │
  10 detectores de acciones  ◄────── shipping_clause / shipping_badge
   (vip_rescue, pause_campaign, throttle_traffic,
    carrier_escalation, address_validation_fix,
    manual_shipping_review, payment_review_audit,
    proactive_customer_contact, oversell_prevention,
    stock_reallocation, demand_forecast, support_macro,
    carrier_capacity_review)
        │
        ▼
   diversify_actions ──► top 10 con caps por familia y dedup por target
        │
        ▼
  write_outputs
   ├── top_actions.json      (formato del enunciado)
   ├── report.md             (ejecutivo + impacto API)
   ├── dashboard.html        (TOP 3 hero + drop en directo + Top 10 + impacto API)
   ├── data_quality.json     (auditoría de datos)
   └── shipping_api_log.json (auditoría de cada llamada con latencia y delta)
```

**Capas y módulos**

| Archivo | Rol |
|---|---|
| `hackathon_control_tower/control_tower.py` | Pipeline principal: carga, scoring, detectores, diversificación, salidas. |
| `hackathon_control_tower/shipping_api.py` | Módulo aislado de integración API: HTTP, normalización defensiva, política de relevancia, helpers UI, logging. |
| `hackathon_control_tower/_mock_shipping_api.py` | Servidor stdlib para validar el camino feliz en demo sin tocar el backend real. |
| `docs/index.html` | Snapshot del dashboard servido en GitHub Pages. |

**Priority score interpretable** = combinación ponderada de cinco señales por
pedido (`customer_risk`, `support_risk`, `inventory_risk`, `logistics_risk`,
`commercial_impact`) en escala 0–100. Caps por familia para diversificar
(`vip 3 · marketing 4 · logistics 3 · support 2 · forecast 2 · ...`). Dedup
por `target_id`. Cada acción lleva `priority_score`, `confidence`,
`valid_for_minutes`, owner y motivo verificable.

**Robustez**: tolerancia a CSV partidos / denormalizados, normalización de SKUs
(`canon_id`), validación defensiva de la respuesta de la API
(`normalize_shipping_payload`), fallback completo si la API cae. Modo offline
con `--no-api`.

---

## 3. Repositorio

> **URL pública**: `https://github.com/<TU_USUARIO>/scuffers-ai-ops-control-tower`
> _(rellena tras crear el repo en github.com — instrucciones abajo)._

Estructura mínima:

```
.
├── ENTREGA.md                       ← este documento
├── README.md                        ← visión técnica
├── docs/                            ← snapshot servido en GitHub Pages
│   ├── index.html
│   ├── top_actions.json
│   ├── report.md
│   └── data_quality.json
├── hackathon_control_tower/
│   ├── control_tower.py             ← pipeline principal
│   ├── shipping_api.py              ← integración Shipping Status API
│   ├── _mock_shipping_api.py        ← mock para demo
│   ├── ENUNCIADO_RESUMIDO.md
│   ├── PLAN_RETO_SCUFFERS.md
│   ├── PITCH_Y_DEMO.md
│   └── README.md
├── scuffers_all_mock_data/          ← CSVs del reto
├── propuesta_tecnica_detallada.md
└── guia_completa_ia_automatizacion.md
```

---

## 4. Demo en vivo

> **Dashboard público**: `https://<TU_USUARIO>.github.io/scuffers-ai-ops-control-tower/`
> _(rellena tras activar GitHub Pages — instrucciones abajo)._

**Recorrido sugerido (90s)**

1. **Now / Top 3** → tres hero cards: rescate VIP, pausar Black Hoodie, pausar White Tee. Cada una con score, confianza y validez.
2. **Drop en directo** → panel translúcido con replay de los 180 pedidos del CSV. Botón **"Conectar feed en vivo"** abre modal para apuntar a un webhook real (Shopify `orders/create` o SSE). Botones Pausar y Limpiar.
3. **Top 10 priorizado** → tabla editorial con familia, owner, score, validez y motivo.
4. **Cómo cambia la decisión gracias a la Shipping API** _(visible solo cuando se consulta la API real)_ → tabla con Δ score por pedido. Δ máximo +19.4 puntos en `exception · warehouse_delay`; Δ negativo −2.6 puntos en `delivered`.
5. **SKUs críticos** → 8 SKUs con tiempo a stockout dinámico ("4 min", "39 min", "oversell").
6. **Pedidos en riesgo** → descomposición por las 5 señales + chip API.
7. **Calidad de datos** → 10 chips con hallazgos (oversell, SKU desconocido, customer desconocido, etc.).

### Reproducir la demo desde otro ordenador

```bash
git clone https://github.com/<TU_USUARIO>/scuffers-ai-ops-control-tower.git
cd scuffers-ai-ops-control-tower/hackathon_control_tower

# Modo offline (sin API)
python control_tower.py --data ../scuffers_all_mock_data/candidate_csvs --out outputs_full --no-api

# Modo API real
python control_tower.py --data ../scuffers_all_mock_data/candidate_csvs --out outputs_full_api --candidate-id SCF-2026-XXXX --api-top 25

# Demo del camino feliz con mock local
python _mock_shipping_api.py 8765
# en otra terminal:
$env:SCF_SHIPPING_API_BASE = "http://127.0.0.1:8765/api/shipping-status"
python control_tower.py --data ../scuffers_all_mock_data/candidate_csvs --out outputs_demo --candidate-id SCF-2026-DEMO --api-top 8

# Abrir el dashboard
start outputs_full/dashboard.html
```

---

## 5. Top 10 acciones priorizadas

| # | Decisión | Familia | Target | Owner | Score | Conf. | Validez | Auto |
|---|----------|---------|--------|-------|------:|------:|--------:|------|
| 1 | **Rescatar** | vip | `ORD-10567` | customer_care | 100.0 | 0.90 | 30 min | humano |
| 2 | **Pausar campaña** | marketing | `HOODIE-BLK-M` | marketing | 100.0 | 0.82 | 30 min | auto |
| 3 | **Pausar campaña** | marketing | `TEE-WHT-S` | marketing | 100.0 | 0.82 | 30 min | auto |
| 4 | **Frenar tráfico** | marketing | `JORTS-BLU-M` | merchandising | 100.0 | 0.82 | 30 min | auto |
| 5 | **Pausar campaña** | marketing | `ZIP-BLK-M` | marketing | 100.0 | 0.82 | 30 min | auto |
| 6 | **Crear macro** | support | `PATTERN-me_preocupa_que_se_agote` | customer_care | 100.0 | 0.80 | 120 min | auto |
| 7 | **Pronosticar demanda** | forecast | `TEE-WHT-S` | merchandising | 96.1 | 0.65 | 90 min | auto |
| 8 | **Pronosticar demanda** | forecast | `HOODIE-BLK-M` | merchandising | 95.7 | 0.65 | 90 min | auto |
| 9 | **Crear macro** | support | `PATTERN-necesito_saber_si_mi_ped` | customer_care | 95.0 | 0.80 | 120 min | auto |
| 10 | **Rescatar** | vip | `ORD-10460` | customer_care | 90.6 | 0.90 | 30 min | humano |

JSON crudo: [`docs/top_actions.json`](./docs/top_actions.json) · Reporte: [`docs/report.md`](./docs/report.md) · Calidad de datos: [`docs/data_quality.json`](./docs/data_quality.json).

**Lectura rápida de la lista**:
- 2 rescates VIP humanos en clientes con LTV > 1200 EUR y ticket urgente.
- 4 acciones de freno de tráfico/campaña sobre los SKUs en riesgo de oversell (HOODIE-BLK-M se agota en ~4 min al ritmo actual).
- 2 macros de soporte cubren 7 tickets repetidos.
- 2 alertas de pronóstico anticipan gaps de 109 y 113 unidades en las próximas 4 horas.

---

## 6. Limitaciones conocidas

- **Sin histórico real de drops anteriores**: la curva de demanda asume peak en las horas 1–2 y decay del 25% / hora, calibrada con conocimiento de drops capsula similares. Cuando exista historial real, el modelo se sustituye por un fit empírico sin tocar el resto del pipeline.
- **Reloj asumido**: usamos `datetime.utcnow` para calcular `time_to_stockout`. En un drop real conviene anclar al `started_at` del drop para evitar derivas.
- **Heurística, no ML entrenado**: pesos de las 5 señales fijados por diseño (defendibles en demo); el siguiente paso natural es aprender los pesos contra outcomes reales.
- **Shipping Status API**: solo se consultan los pedidos relevantes (~25 por defecto, ajustable con `--api-top`). No es un crawl masivo, por diseño. Sin reintento con backoff todavía.
- **Sin persistencia**: el sistema es un batch reproducible. No hay base de datos ni historial entre runs. Para producción se conectaría a Postgres + cola (Temporal o similar).
- **Webhook en vivo**: el botón "Conectar feed en vivo" del dashboard hace polling a un endpoint que devuelva JSON con `order_id, customer_id, sku, city, value`. Sin auth ni firma; en producción se usaría HMAC sobre `X-Shopify-Hmac-Sha256`.
- **Decisiones financieras**: el motor nunca toca precios o descuentos directamente; solo dispara revisión humana en `payment_review_audit`.
- **Privacidad**: la demo incluye `customer_id` y mensajes de soporte por trazabilidad. En producción se anonimizan en el front, se enmascara PII y se aplica RBAC al visor.

---

## 7. Cómo dejar repo + dashboard accesibles desde otro PC (5 min)

Tu PC no tiene `gh` CLI ni el proyecto inicializado en git. Dos pasos:

### A. Crear repo en GitHub e inicializar git

1. En `https://github.com/new` crea un repo público llamado
   `scuffers-ai-ops-control-tower`. **No** marques "Initialize with README".
2. Desde la raíz del proyecto:

```powershell
cd "C:\Users\LCS\Projects\scuffers claude"
git init
git branch -M main
git add .
git commit -m "Scuffers AI Ops Control Tower - entrega hackathon UDIA"
git remote add origin https://github.com/<TU_USUARIO>/scuffers-ai-ops-control-tower.git
git push -u origin main
```

### B. Activar GitHub Pages para el dashboard público

1. Ve a `Settings → Pages` del repo recién creado.
2. **Source**: Deploy from a branch.
3. **Branch**: `main` · **Folder**: `/docs`. Save.
4. Tras 30–60 s la URL será:
   `https://<TU_USUARIO>.github.io/scuffers-ai-ops-control-tower/`

### Alternativa instant (sin GitHub Pages)

Arrastra la carpeta `docs/` a `https://app.netlify.com/drop` y obtienes una
URL pública en menos de 30 segundos. Sirve incluso sin cuenta de Netlify.

Una vez tengas las dos URLs, sustituye los placeholders `<TU_USUARIO>` en las
secciones 3 y 4 de este documento y haz un nuevo commit.
