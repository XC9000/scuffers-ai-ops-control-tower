# Scuffers AI Ops Control Tower

_Generado 2026-04-28T17:57:56+00:00._

## TL;DR

- 180 pedidos analizados, 22 SKUs con inventario, 18 tickets de soporte y 5 campanas activas.
- Top 10 acciones repartidas por familia: marketing=4, vip=2, support=2, forecast=2.
- Shipping Status API consultada en 0 pedidos (ok=0, errores=0, manual_review=0, severos=0, recuperados=0, decisiones movidas=0).
- Calidad de datos: 2 pedidos sin order_value, 3 con formato ruidoso, 2 sin segmento, 5 SKUs con oversell consumado.

## Top 10 acciones

| # | Decision | Action type | Target | Owner | Score | Conf. | Validez | Auto |
|---|----------|-------------|--------|-------|-------|-------|---------|------|
| 1 | **Rescatar** | `vip_rescue` | `ORD-10567` | customer_care | 100.0 | 0.90 | 30 min | humano |
| 2 | **Pausar** | `pause_campaign` | `HOODIE-BLK-M` | marketing | 100.0 | 0.82 | 30 min | auto |
| 3 | **Pausar** | `pause_campaign` | `TEE-WHT-S` | marketing | 100.0 | 0.82 | 30 min | auto |
| 4 | **Frenar** | `throttle_traffic` | `JORTS-BLU-M` | merchandising | 100.0 | 0.82 | 30 min | auto |
| 5 | **Pausar** | `pause_campaign` | `ZIP-BLK-M` | marketing | 100.0 | 0.82 | 30 min | auto |
| 6 | **Crear macro** | `support_macro_response` | `PATTERN-me_preocupa_que_se_agote` | customer_care | 100.0 | 0.80 | 120 min | auto |
| 7 | **Pronosticar** | `demand_forecast_alert` | `TEE-WHT-S` | merchandising | 96.1 | 0.65 | 90 min | auto |
| 8 | **Pronosticar** | `demand_forecast_alert` | `HOODIE-BLK-M` | merchandising | 95.7 | 0.65 | 90 min | auto |
| 9 | **Crear macro** | `support_macro_response` | `PATTERN-necesito_saber_si_mi_ped` | customer_care | 95 | 0.80 | 120 min | auto |
| 10 | **Rescatar** | `vip_rescue` | `ORD-10460` | customer_care | 90.6 | 0.90 | 30 min | humano |

### 1. Rescate VIP para CUS-2004 (pedido ORD-10567)

- **Decision:** Rescatar (`vip_rescue`)
- **Target:** `ORD-10567`
- **Owner:** `customer_care`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.90  ·  **Validez:** 30 min  ·  **Auto:** False
- **Motivo:** Cliente CUS-2004 (vip_customer, LTV 1246 EUR) tiene un ticket urgent con sentimiento negative sobre el pedido ORD-10567 de Red Logo Tee en Barcelona. Mensaje literal: "Es un regalo y necesito confirmación de entrega.".
- **Impacto esperado:** Salvar la relacion con un cliente top: contesta un agente senior en menos de 30 min, verifica estado real, ofrece compensacion proporcional y blinda LTV.

### 2. Pausar campana sobre Black Hoodie (HOODIE-BLK-M)

- **Decision:** Pausar (`pause_campaign`)
- **Target:** `HOODIE-BLK-M`
- **Owner:** `marketing`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.82  ·  **Validez:** 30 min  ·  **Auto:** True
- **Motivo:** SKU HOODIE-BLK-M (Black Hoodie). Disponible 2, reservado 32 -> agotamiento estimado en ~4 min al ritmo actual. Sell-through 82%/h, conversion 7.6% y 4573 vistas/h. Campanas: CMP-778 (tiktok, intensidad very_high). Coste estimado de no actuar la proxima hora: ~3918 EUR.
- **Impacto esperado:** Cortar pauta pagada antes de que el SKU se agote: protege CSAT, ahorra spend en clicks que no convierten y libera presupuesto para SKUs con margen disponible.

### 3. Pausar campana sobre White Essential Tee (TEE-WHT-S)

- **Decision:** Pausar (`pause_campaign`)
- **Target:** `TEE-WHT-S`
- **Owner:** `marketing`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.82  ·  **Validez:** 30 min  ·  **Auto:** True
- **Motivo:** SKU TEE-WHT-S (White Essential Tee). Disponible 2, reservado 40 -> agotamiento estimado en ~3 min al ritmo actual. Sell-through 86%/h, conversion 7.1% y 4846 vistas/h. Campanas: CMP-779 (tiktok, intensidad high). Coste estimado de no actuar la proxima hora: ~2520 EUR.
- **Impacto esperado:** Cortar pauta pagada antes de que el SKU se agote: protege CSAT, ahorra spend en clicks que no convierten y libera presupuesto para SKUs con margen disponible.

### 4. Frenar trafico hacia Blue Denim Jorts (JORTS-BLU-M) por riesgo de oversell

- **Decision:** Frenar (`throttle_traffic`)
- **Target:** `JORTS-BLU-M`
- **Owner:** `merchandising`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.82  ·  **Validez:** 30 min  ·  **Auto:** True
- **Motivo:** SKU JORTS-BLU-M (Blue Denim Jorts). Disponible 16, reservado 25 -> agotamiento estimado en ~39 min al ritmo actual. Sell-through 61%/h, conversion 6.8% y 3257 vistas/h. Campanas: sin campana pagada activa, pero con demanda organica acelerada. Coste estimado de no actuar la proxima hora: ~1071 EUR.
- **Impacto esperado:** Mover el SKU a 'temporarily out' o sacarlo del home/colecciones hasta confirmar stock real y entrante; evita pedidos que luego habria que cancelar.

### 5. Pausar campana sobre Black Zip Hoodie (ZIP-BLK-M)

- **Decision:** Pausar (`pause_campaign`)
- **Target:** `ZIP-BLK-M`
- **Owner:** `marketing`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.82  ·  **Validez:** 30 min  ·  **Auto:** True
- **Motivo:** SKU ZIP-BLK-M (Black Zip Hoodie). Disponible 6, reservado 37 -> agotamiento estimado en ~11 min al ritmo actual. Sell-through 75%/h, conversion 7.6% y 3783 vistas/h. Campanas: CMP-780 (instagram, intensidad high). Coste estimado de no actuar la proxima hora: ~4578 EUR.
- **Impacto esperado:** Cortar pauta pagada antes de que el SKU se agote: protege CSAT, ahorra spend en clicks que no convierten y libera presupuesto para SKUs con margen disponible.

### 6. Crear macro de respuesta para 4 tickets repetidos

- **Decision:** Crear macro (`support_macro_response`)
- **Target:** `PATTERN-me_preocupa_que_se_agote`
- **Owner:** `customer_care`
- **Priority score:** 100.0 / 100  ·  **Confianza:** 0.80  ·  **Validez:** 120 min  ·  **Auto:** True
- **Motivo:** 4 tickets distintos comparten el mismo mensaje literal: "Me preocupa que se agote y no recibirme el pedido.". Pedidos afectados: ORD-10452, ORD-10460, ORD-10517, ORD-10568. Canales: email, instagram_dm. Urgencias detectadas: high, urgent.
- **Impacto esperado:** Crear macro/template + automatizacion de primera respuesta libera al equipo de soporte para atender los casos realmente unicos. Reduce TFR (time to first response) en ~70%.

### 7. Pronostico de demanda para White Essential Tee (TEE-WHT-S)

- **Decision:** Pronosticar (`demand_forecast_alert`)
- **Target:** `TEE-WHT-S`
- **Owner:** `merchandising`
- **Priority score:** 96.1 / 100  ·  **Confianza:** 0.65  ·  **Validez:** 90 min  ·  **Auto:** True
- **Motivo:** Curva tipica de drops anteriores (peak hora 1-2, decay 25%/h) + multiplicador 1.4x (high) sobre sell-through actual 86%/h. Pronostico 4h: ~141 ud demandadas vs 32 ud de supply (disp+entrante). Gap previsto +109 ud (~3806 EUR de venta en juego).
- **Impacto esperado:** Iniciar pre-pedido o lista de espera para White Essential Tee y reasignar trafico hacia SKUs alternativos (mismo producto otra talla/color) mientras se aprueba reposicion urgente. Permite tomar decisiones de produccion, reposicion y trafico antes de que la rotura sea visible para el cliente.

### 8. Pronostico de demanda para Black Hoodie (HOODIE-BLK-M)

- **Decision:** Pronosticar (`demand_forecast_alert`)
- **Target:** `HOODIE-BLK-M`
- **Owner:** `merchandising`
- **Priority score:** 95.7 / 100  ·  **Confianza:** 0.65  ·  **Validez:** 90 min  ·  **Auto:** True
- **Motivo:** Curva tipica de drops anteriores (peak hora 1-2, decay 25%/h) + multiplicador 1.5x (very_high) sobre sell-through actual 82%/h. Pronostico 4h: ~115 ud demandadas vs 2 ud de supply (disp+entrante). Gap previsto +113 ud (~7902 EUR de venta en juego).
- **Impacto esperado:** Iniciar pre-pedido o lista de espera para Black Hoodie y reasignar trafico hacia SKUs alternativos (mismo producto otra talla/color) mientras se aprueba reposicion urgente. Permite tomar decisiones de produccion, reposicion y trafico antes de que la rotura sea visible para el cliente.

### 9. Crear macro de respuesta para 3 tickets repetidos

- **Decision:** Crear macro (`support_macro_response`)
- **Target:** `PATTERN-necesito_saber_si_mi_ped`
- **Owner:** `customer_care`
- **Priority score:** 95 / 100  ·  **Confianza:** 0.80  ·  **Validez:** 120 min  ·  **Auto:** True
- **Motivo:** 3 tickets distintos comparten el mismo mensaje literal: "Necesito saber si mi pedido llegará antes del viernes.". Pedidos afectados: ORD-10404, ORD-10496, ORD-10556. Canales: chat, instagram_dm. Urgencias detectadas: high, medium.
- **Impacto esperado:** Crear macro/template + automatizacion de primera respuesta libera al equipo de soporte para atender los casos realmente unicos. Reduce TFR (time to first response) en ~70%.

### 10. Rescate VIP para CUS-2033 (pedido ORD-10460)

- **Decision:** Rescatar (`vip_rescue`)
- **Target:** `ORD-10460`
- **Owner:** `customer_care`
- **Priority score:** 90.6 / 100  ·  **Confianza:** 0.90  ·  **Validez:** 30 min  ·  **Auto:** False
- **Motivo:** Cliente CUS-2033 (vip_customer, LTV 2120 EUR) tiene un ticket high con sentimiento negative sobre el pedido ORD-10460 de Black Zip Hoodie en Bilbao. Mensaje literal: "Me preocupa que se agote y no recibirme el pedido.".
- **Impacto esperado:** Salvar la relacion con un cliente top: contesta un agente senior en menos de 30 min, verifica estado real, ofrece compensacion proporcional y blinda LTV.

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
