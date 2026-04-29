# Scuffers AI Ops Control Tower

_Generado 2026-04-29T00:10:45+00:00._

## TL;DR

- 180 pedidos analizados, 22 SKUs con inventario, 18 tickets de soporte y 5 campanas activas.
- Top 10 acciones repartidas por familia: marketing=4, logistics=3, vip=1, support=1, forecast=1.
- Shipping Status API consultada en 17 pedidos (ok=17, errores=0, manual_review=5, severos=6, recuperados=3, decisiones movidas=16).
- Calidad de datos: 2 pedidos sin order_value, 3 con formato ruidoso, 2 sin segmento, 5 SKUs con oversell consumado.

## Top 10 acciones

| # | Decision | Action type | Target | Owner | Score | Conf. | Validez | Auto |
|---|----------|-------------|--------|-------|-------|-------|---------|------|
| 1 | **Rescatar** | `vip_rescue` | `ORD-10567` | customer_care | 100.0 | 0.95 | 30 min | humano |
| 2 | **Escalar** | `carrier_escalation` | `ORD-10460` | operations | 100.0 | 0.95 | 30 min | humano |
| 3 | **Escalar** | `carrier_escalation` | `ORD-10515` | operations | 100.0 | 0.95 | 30 min | humano |
| 4 | **Escalar** | `carrier_escalation` | `ORD-10530` | operations | 100.0 | 0.95 | 30 min | humano |
| 5 | **Pausar** | `pause_campaign` | `HOODIE-BLK-M` | marketing | 100.0 | 0.82 | 30 min | auto |
| 6 | **Pausar** | `pause_campaign` | `TEE-WHT-S` | marketing | 100.0 | 0.82 | 30 min | auto |
| 7 | **Frenar** | `throttle_traffic` | `JORTS-BLU-M` | merchandising | 100.0 | 0.82 | 30 min | auto |
| 8 | **Pausar** | `pause_campaign` | `ZIP-BLK-M` | marketing | 100.0 | 0.82 | 30 min | auto |
| 9 | **Crear macro** | `support_macro_response` | `PATTERN-me_preocupa_que_se_agote` | customer_care | 100.0 | 0.80 | 120 min | auto |
| 10 | **Pronosticar** | `demand_forecast_alert` | `TEE-WHT-S` | merchandising | 96.1 | 0.65 | 90 min | auto |

### 1. Rescate VIP para CUS-2004 (pedido ORD-10567)

- **Decision:** Rescatar (`vip_rescue`)
- **Target:** `ORD-10567`
- **Owner:** `customer_care`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.95  ·  **Validez:** 30 min  ·  **Auto:** False
- **Motivo:** Cliente CUS-2004 (vip_customer, LTV 1246 EUR) tiene un ticket urgent con sentimiento negative sobre el pedido ORD-10567 de Red Logo Tee en Barcelona. Mensaje literal: "Es un regalo y necesito confirmación de entrega.". La Shipping Status API confirma estado returned_to_sender, ETA 2026-04-33, delay_risk 0.56.
- **Impacto esperado:** Salvar la relacion con un cliente top: contesta un agente senior en menos de 30 min, verifica estado real, ofrece compensacion proporcional y blinda LTV.

### 2. Escalar incidencia logistica del pedido ORD-10460

- **Decision:** Escalar (`carrier_escalation`)
- **Target:** `ORD-10460`
- **Owner:** `operations`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.95  ·  **Validez:** 30 min  ·  **Auto:** False
- **Motivo:** Pedido ORD-10460 de Black Zip Hoodie a Bilbao via express. La Shipping Status API confirma estado exception, ETA 2026-04-33, delay_risk 0.42, motivo warehouse_delay, requires_manual_review=True. Cliente CUS-2033 (vip_customer).
- **Impacto esperado:** Abrir incidencia con transportista, ofrecer reposicion o reembolso anticipado y evitar ticket reactivo del cliente.

### 3. Escalar incidencia logistica del pedido ORD-10515

- **Decision:** Escalar (`carrier_escalation`)
- **Target:** `ORD-10515`
- **Owner:** `operations`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.95  ·  **Validez:** 30 min  ·  **Auto:** False
- **Motivo:** Pedido ORD-10515 de Blue Denim Jorts a Valencia via express. La Shipping Status API confirma estado returned_to_sender, ETA 2026-04-33, delay_risk 0.74, requires_manual_review=True. Cliente CUS-2068 (new_customer).
- **Impacto esperado:** Abrir incidencia con transportista, ofrecer reposicion o reembolso anticipado y evitar ticket reactivo del cliente.

### 4. Escalar incidencia logistica del pedido ORD-10530

- **Decision:** Escalar (`carrier_escalation`)
- **Target:** `ORD-10530`
- **Owner:** `operations`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.95  ·  **Validez:** 30 min  ·  **Auto:** False
- **Motivo:** Pedido ORD-10530 de Black Zip Hoodie a Sevilla via standard. La Shipping Status API confirma estado exception, ETA 2026-04-33, delay_risk 0.67, motivo warehouse_delay, requires_manual_review=True. Cliente CUS-2066 (new_customer).
- **Impacto esperado:** Abrir incidencia con transportista, ofrecer reposicion o reembolso anticipado y evitar ticket reactivo del cliente.

### 5. Pausar campana sobre Black Hoodie (HOODIE-BLK-M)

- **Decision:** Pausar (`pause_campaign`)
- **Target:** `HOODIE-BLK-M`
- **Owner:** `marketing`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.82  ·  **Validez:** 30 min  ·  **Auto:** True
- **Motivo:** SKU HOODIE-BLK-M (Black Hoodie). Disponible 2, reservado 32 -> agotamiento estimado en ~4 min al ritmo actual. Sell-through 82%/h, conversion 7.6% y 4573 vistas/h. Campanas: CMP-778 (tiktok, intensidad very_high). Coste estimado de no actuar la proxima hora: ~3918 EUR.
- **Impacto esperado:** Cortar pauta pagada antes de que el SKU se agote: protege CSAT, ahorra spend en clicks que no convierten y libera presupuesto para SKUs con margen disponible.

### 6. Pausar campana sobre White Essential Tee (TEE-WHT-S)

- **Decision:** Pausar (`pause_campaign`)
- **Target:** `TEE-WHT-S`
- **Owner:** `marketing`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.82  ·  **Validez:** 30 min  ·  **Auto:** True
- **Motivo:** SKU TEE-WHT-S (White Essential Tee). Disponible 2, reservado 40 -> agotamiento estimado en ~3 min al ritmo actual. Sell-through 86%/h, conversion 7.1% y 4846 vistas/h. Campanas: CMP-779 (tiktok, intensidad high). Coste estimado de no actuar la proxima hora: ~2520 EUR.
- **Impacto esperado:** Cortar pauta pagada antes de que el SKU se agote: protege CSAT, ahorra spend en clicks que no convierten y libera presupuesto para SKUs con margen disponible.

### 7. Frenar trafico hacia Blue Denim Jorts (JORTS-BLU-M) por riesgo de oversell

- **Decision:** Frenar (`throttle_traffic`)
- **Target:** `JORTS-BLU-M`
- **Owner:** `merchandising`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.82  ·  **Validez:** 30 min  ·  **Auto:** True
- **Motivo:** SKU JORTS-BLU-M (Blue Denim Jorts). Disponible 16, reservado 25 -> agotamiento estimado en ~39 min al ritmo actual. Sell-through 61%/h, conversion 6.8% y 3257 vistas/h. Campanas: sin campana pagada activa, pero con demanda organica acelerada. Coste estimado de no actuar la proxima hora: ~1071 EUR.
- **Impacto esperado:** Mover el SKU a 'temporarily out' o sacarlo del home/colecciones hasta confirmar stock real y entrante; evita pedidos que luego habria que cancelar.

### 8. Pausar campana sobre Black Zip Hoodie (ZIP-BLK-M)

- **Decision:** Pausar (`pause_campaign`)
- **Target:** `ZIP-BLK-M`
- **Owner:** `marketing`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.82  ·  **Validez:** 30 min  ·  **Auto:** True
- **Motivo:** SKU ZIP-BLK-M (Black Zip Hoodie). Disponible 6, reservado 37 -> agotamiento estimado en ~11 min al ritmo actual. Sell-through 75%/h, conversion 7.6% y 3783 vistas/h. Campanas: CMP-780 (instagram, intensidad high). Coste estimado de no actuar la proxima hora: ~4578 EUR.
- **Impacto esperado:** Cortar pauta pagada antes de que el SKU se agote: protege CSAT, ahorra spend en clicks que no convierten y libera presupuesto para SKUs con margen disponible.

### 9. Crear macro de respuesta para 4 tickets repetidos

- **Decision:** Crear macro (`support_macro_response`)
- **Target:** `PATTERN-me_preocupa_que_se_agote`
- **Owner:** `customer_care`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.80  ·  **Validez:** 120 min  ·  **Auto:** True
- **Motivo:** 4 tickets distintos comparten el mismo mensaje literal: "Me preocupa que se agote y no recibirme el pedido.". Pedidos afectados: ORD-10452, ORD-10460, ORD-10517, ORD-10568. Canales: email, instagram_dm. Urgencias detectadas: high, urgent.
- **Impacto esperado:** Crear macro/template + automatizacion de primera respuesta libera al equipo de soporte para atender los casos realmente unicos. Reduce TFR (time to first response) en ~70%.

### 10. Pronostico de demanda para White Essential Tee (TEE-WHT-S)

- **Decision:** Pronosticar (`demand_forecast_alert`)
- **Target:** `TEE-WHT-S`
- **Owner:** `merchandising`
- **Priority score:** 96.1 / 100  ·  **Confianza:** 0.65  ·  **Validez:** 90 min  ·  **Auto:** True
- **Motivo:** Curva tipica de drops anteriores (peak hora 1-2, decay 25%/h) + multiplicador 1.4x (high) sobre sell-through actual 86%/h. Pronostico 4h: ~141 ud demandadas vs 32 ud de supply (disp+entrante). Gap previsto +109 ud (~3806 EUR de venta en juego).
- **Impacto esperado:** Iniciar pre-pedido o lista de espera para White Essential Tee y reasignar trafico hacia SKUs alternativos (mismo producto otra talla/color) mientras se aprueba reposicion urgente. Permite tomar decisiones de produccion, reposicion y trafico antes de que la rotura sea visible para el cliente.

## Como se calcula el Priority Score

1. **Ingesta tolerante**: cruzamos `orders + order_items + customers + inventory + support_tickets + campaigns` usando un `canon_id` que normaliza SKUs ruidosos (`HOODIE-BLK-M` vs `hoodie_blk_m`).
2. **5 senales por pedido** (escala 0-100): customer_risk, support_risk, inventory_risk, logistics_risk, commercial_impact. Cada una usa parametros centralizados (`SOFT_MAX_CLV_EUR`, `SOFT_MAX_ORDER_VALUE_EUR`, `SOFT_MAX_VIEWS_PER_HOUR`).
3. **Detectores de accion** (10 tipos): cada detector emite candidatos con su propio score interpretable, no un numero magico. Los scores agregan valor de negocio (CLV, severidad logistica, gap de demanda) y un coste estimado en EUR cuando aplica.
4. **Diversificacion** con caps por familia (vip 3, marketing 4, logistics 3, support 2, forecast 2, customer 2, finance 2, inventory 2) y maximo 2 acciones por target_id. Se exponen `priority_score` y `valid_for_minutes` en cada accion para que ops tenga trazabilidad y ventana operativa.
5. **API logistica selectiva**: solo se consulta para los pedidos top (configurable con `--api-top`). El resultado se reinyecta en el modelo para que pase de prioridad ciega a prioridad informada.

## Supuestos y limitaciones

- La curva de demanda asumida (peak hora 1-2, decay 25%/h) es un proxy razonable de drops capsula, no un modelo entrenado con histórico real. Cuando exista historial, se sustituye por un fit empirico.
- El modelo no toca decisiones financieras (precios, descuentos): solo dispara revisiones humanas.
- Los pesos de las 5 senales por pedido son heuristicos, defendibles, y se pueden mover en un fichero de config sin recompilar.
- La API logistica puede caer; se trata como dato opcional, nunca bloqueante.

## Calidad de datos detectada

- Archivos cargados: orders=180, order_items=180, customers=120, inventory=22, support_tickets=18, campaigns=5.
- Pedidos huerfanos (items sin pedido): 0.
- Tickets sin pedido: 0.
- Pedidos con SKU desconocido en inventario: 0.
- Pedidos con cliente desconocido: 0.
- SKUs con oversell consumado (reservado > disponible): HOODIE-BLK-M, HOODIE-CRM-M, TEE-WHT-S, JORTS-BLU-M, ZIP-BLK-M.
- Pedidos en `payment_review`: 10.

Detalle completo en `data_quality.json`.

## Impacto de la Shipping Status API

- Pedidos consultados: 17  ·  OK: 17  ·  errores: 0.
- Severos (delayed/exception/lost/returned): 6  ·  recuperados (delivered/out_for_delivery): 3  ·  manual review: 5.
- Decisiones movidas por la API (delta de score >= 1 punto): 16.

| Pedido | Estado API | Δ score | Motivo |
|--------|-----------|---------|--------|
| `ORD-10530` | exception · warehouse_delay | +22.0 | warehouse delay |
| `ORD-10460` | exception · warehouse_delay | +19.4 | warehouse delay |
| `ORD-10515` | returned_to_sender | +19.4 | unknown |
| `ORD-10419` | manual review | +14.2 | unknown |
| `ORD-10466` | exception · customs_hold | +13.9 | customs hold |
| `ORD-10475` | exception · weather_disruption | +13.9 | weather disruption |
| `ORD-10567` | returned_to_sender | +13.9 | unknown |
| `ORD-10553` | label created | +8.9 | unknown |
| `ORD-10556` | label created | +6.8 | unknown |
| `ORD-10425` | in transit | +5.0 | unknown |
