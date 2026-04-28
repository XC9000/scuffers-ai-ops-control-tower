# Scuffers AI Ops Control Tower — entregable del hackathon

Carpeta lista para ejecutar y entregar. Solo Python stdlib, sin dependencias.

## Resumen ejecutivo (60 segundos)

> En las primeras horas de un drop el problema no es la falta de datos, es la falta de foco. La Control Tower lee los seis CSV reales aunque vengan rotos, los cruza con tolerancia a ruido (SKUs en mayúscula y minúscula, precios `€34,9`, segmentos vacíos), aplica diez detectores de acción y devuelve un top 10 priorizado en el formato exacto del enunciado. Cada acción es interpretable: rescate VIP, pausa de campaña con tiempo real de stockout y coste estimado en EUR, predicción de demanda por analogía con drops anteriores, macro de soporte para tickets repetidos, escalado logístico cuando la API lo justifica. La Shipping Status API se llama solo en los pedidos top y, si cae, el sistema sigue produciendo el top 10 con menor confianza. Dashboard autocontenido, sin servidor; abrir con doble click y se entiende en 30 segundos.

## Archivos clave

- `control_tower.py`: pipeline completo (carga, normalización, scoring, API logística, detectores, salidas).
- `ENUNCIADO_RESUMIDO.md`: enunciado real reconstruido a partir del bundle de la web.
- `PLAN_RETO_SCUFFERS.md`: plan estratégico con señales y opciones de solución.
- `PITCH_Y_DEMO.md`: pitch de 60 s, frases senior, supuestos/limitaciones y respuestas a preguntas difíciles.
- `outputs_full/`: salida ya generada con los CSVs reales.

## Comandos esenciales

Modo offline (sin la Shipping Status API):

```powershell
python control_tower.py --data ..\scuffers_all_mock_data\candidate_csvs --out outputs_full --no-api
```

Modo enriquecido (con tu candidate ID; lo recibes del organizador):

```powershell
python control_tower.py --data ..\scuffers_all_mock_data\candidate_csvs --out outputs_full --candidate-id SCF-2026-XXXX
```

Si la API tarda o falla, el sistema sigue funcionando: las acciones se basan en datos internos, se anota explícitamente que la API no respondió y la confianza se ajusta.

## Salidas generadas

Cada ejecución crea en `--out`:

- `top_actions.json`: top 10 con el formato del enunciado más `priority_score` y `valid_for_minutes` para trazabilidad.
- `report.md`: reporte ejecutivo con TL;DR, tabla resumen, racional de scoring, supuestos y calidad de datos.
- `dashboard.html`: panel autocontenido (TOP 3 hero + tabla del top 10 + SKUs críticos + pedidos en riesgo + barra de calidad de datos). Ábrelo con doble click.
- `data_quality.json`: detalle de la calidad de datos (orphans, duplicados, oversell consumado, segmentos inconsistentes, pedidos en `payment_review`).

## Lógica del sistema (cómo lo defiendes)

1. **Ingesta tolerante**: cruza `orders + order_items + customers + inventory + support_tickets + campaigns` usando `canon_id` para SKUs ruidosos. Los precios estilo `€34,9` y los campos vacíos se normalizan al cargar.
2. **5 señales por pedido** (escala 0-100): `customer_risk`, `support_risk`, `inventory_risk`, `logistics_risk`, `commercial_impact`. Magic numbers centralizados en `SOFT_MAX_CLV_EUR`, `SOFT_MAX_ORDER_VALUE_EUR`, `SOFT_MAX_VIEWS_PER_HOUR`.
3. **10 detectores de acción**:
   - `vip_rescue`
   - `carrier_escalation` / `address_validation_fix` / `manual_shipping_review`
   - `express_priority_pack`
   - `payment_review_audit`
   - `proactive_customer_contact`
   - `pause_campaign` / `reduce_campaign_pressure` / `throttle_traffic` (oversell prevention con tiempo real de stockout y coste EUR)
   - `stock_reallocation`
   - `demand_forecast_alert` / `demand_forecast_watch` / `demand_forecast_rebalance`
   - `support_macro_response`
   - `carrier_capacity_review` (solo dispara con incidencia real o volumen >= 40 pedidos en la misma ruta)
4. **Diversificación**: caps por familia (vip 3, marketing 4, logistics 3, support 2, forecast 2, customer 2, finance 2, inventory 2) y máx 2 acciones por target_id.
5. **Cada acción expone**: `priority_score` (0-100), `confidence` (0-1), `valid_for_minutes` (ventana operativa) y un motivo verificable con tiempo a stockout en minutos y coste estimado en EUR cuando aplica.
6. **Shipping API selectiva**: solo se consulta para los pedidos top (`--api-top`, default 25) y los resultados se reinyectan en el modelo. Caída de API ≠ caída del sistema.

## Predicción de demanda por analogía con drops anteriores

Aunque no nos dan histórico explícito, el detector `detect_demand_forecast` modela la curva típica de un drop cápsula:

- Velocidad base por hora = `sell_through_rate_last_hour * (disponibles + reservados)` (con fallback a unidades observadas en `order_items`).
- Decaimiento del 25 % por hora durante las próximas 4 horas (peak en hora 1-2, después decae).
- Multiplicador de campaña: 1.0x sin pauta → 1.5x con `very_high`.
- Compara forecast vs `available + incoming` y traduce el gap a unidades **y** a euros (gap × `unit_price`).

Output por SKU:

- `demand_forecast_alert` si gap ≥ 5 (pre-pedido / lista de espera + reasignación de tráfico).
- `demand_forecast_watch` si gap entre 0 y 5 (campaña al límite).
- `demand_forecast_rebalance` si gap < 0 (mover presupuesto a SKUs con gap positivo).

## Calidad de datos detectada (mostrar al evaluador)

- 5 SKUs con oversell consumado (`reserved > available`): HOODIE-BLK-M, HOODIE-CRM-M, TEE-WHT-S, JORTS-BLU-M, ZIP-BLK-M.
- 10 clientes en `customer_orders_count = 0` que aparecen en `orders.csv` (snapshot inconsistente, no bloqueante).
- 10 pedidos en `payment_review`.
- 2 pedidos sin `order_value` y 3 con formato ruidoso (`€34,9`).
- 2 pedidos sin segmento.

Todo expuesto en `data_quality.json` y resumido en la barra inferior del dashboard.

## Top 10 ya validado

Top 10 producido con los CSVs reales (`scuffers_all_mock_data/candidate_csvs`):

| # | Decisión | Action type | Target | Owner | Score | Conf. | Validez | Auto |
|---|----------|-------------|--------|-------|-------|-------|---------|------|
| 1 | Rescatar | `vip_rescue` | ORD-10567 | customer_care | 100 | 0.90 | 30 min | humano |
| 2 | Pausar | `pause_campaign` | HOODIE-BLK-M | marketing | 100 | 0.82 | 30 min | auto |
| 3 | Pausar | `pause_campaign` | TEE-WHT-S | marketing | 100 | 0.82 | 30 min | auto |
| 4 | Frenar | `throttle_traffic` | JORTS-BLU-M | merchandising | 100 | 0.82 | 30 min | auto |
| 5 | Pausar | `pause_campaign` | ZIP-BLK-M | marketing | 100 | 0.82 | 30 min | auto |
| 6 | Crear macro | `support_macro_response` | PATTERN-me_preocupa_que_se_agote | customer_care | 100 | 0.80 | 120 min | auto |
| 7 | Pronosticar | `demand_forecast_alert` | TEE-WHT-S | merchandising | 96 | 0.65 | 90 min | auto |
| 8 | Pronosticar | `demand_forecast_alert` | HOODIE-BLK-M | merchandising | 96 | 0.65 | 90 min | auto |
| 9 | Crear macro | `support_macro_response` | PATTERN-necesito_saber_si_mi_ped | customer_care | 95 | 0.80 | 120 min | auto |
| 10 | Rescatar | `vip_rescue` | ORD-10460 | customer_care | 91 | 0.90 | 30 min | humano |

## Supuestos y limitaciones (lee esto antes del Q&A)

- La curva de demanda asumida (peak hora 1-2, decay 25 %/h) es un proxy razonable, no un modelo entrenado con histórico real.
- Los pesos de las 5 señales y de cada detector son heurísticos, defendibles, y se pueden mover a un fichero de config sin recompilar.
- El sistema no toma decisiones financieras: no toca precios ni descuentos, solo escala a humano cuando hace falta.
- `order_value` ruidoso o vacío se reconstruye con `unit_price * quantity` siempre que sea posible.
- La API logística es opcional; el top 10 se entrega también en modo offline con la confianza ajustada.
- Sin LLM en el flujo crítico: el LLM se reservaría para redactar mensajes a cliente o resumir el top 10 en lenguaje natural; la priorización es determinista y auditable.
