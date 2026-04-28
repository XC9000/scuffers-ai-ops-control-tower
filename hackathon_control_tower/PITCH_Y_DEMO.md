# Pitch y demo para defender la solución

## 0. Pitch final de 60 segundos

> “En las primeras horas de un drop de Scuffers el problema no es la falta de datos, es la falta de foco. He construido la **AI Ops Control Tower**: lee los seis CSV reales aunque vengan rotos, normaliza SKUs ruidosos, precios con coma y segmentos vacíos, y aplica diez detectores de acción. Cada acción es interpretable: el primero es un rescate VIP de un cliente con LTV de 2.000 EUR y ticket urgente; los cuatro siguientes son pausa o throttle de campañas TikTok e Instagram sobre SKUs que se van a agotar en menos de cuatro minutos al ritmo actual; los pronósticos de demanda usan la curva típica de drops anteriores y avisan de un gap de 100 unidades en las próximas cuatro horas, equivalente a 7.000 EUR de venta en juego. Cada acción lleva owner, priority score, ventana de validez y un motivo verificable; la Shipping Status API se llama solo en los pedidos que importan y, si cae, el sistema sigue produciendo el top 10 con menor confianza. Sin dependencias externas, dashboard que se abre con doble click y se entiende en treinta segundos. En operaciones reales, eso es lo que falta: foco, evidencia y degradación elegante.”

## 1. Mensaje principal

> “He construido una Control Tower operativa para las primeras horas de un drop. El sistema no intenta detectar todos los problemas: prioriza las 10 decisiones que más impacto tienen ahora mismo, combinando datos de pedidos, clientes, inventario, soporte, campañas y estado logístico real.”

## 2. Estructura de presentación en 3 minutos

### Apertura — 20 segundos

“En un lanzamiento de alta demanda, el problema no es la falta de datos, sino la falta de foco. Operaciones tiene pedidos, tickets, inventario, campañas y logística pasando a la vez. Mi solución convierte todo eso en una lista corta de acciones priorizadas.”

### Qué construí — 30 segundos

“Construí un motor de scoring que lee CSVs imperfectos, normaliza campos y calcula cinco señales: riesgo de cliente, riesgo de inventario, riesgo de soporte, riesgo logístico e impacto comercial. Después consulta la Shipping Status API para los casos donde la información logística puede cambiar la decisión.”

### Demo — 60 segundos

Orden sugerido:

1. Abrir `outputs_full/dashboard.html` en el navegador (es un único archivo, sin servidor): se ve un panel con KPIs, top 10 acciones, SKUs críticos y pedidos en riesgo.
2. Volver a la terminal y ejecutar:

```bash
python control_tower.py --data ../scuffers_all_mock_data/candidate_csvs --out outputs_full --no-api
```

3. Mostrar `outputs_full/top_actions.json` y leer las primeras 3 acciones del top con los datos reales del reto:
   - **#1** Rescate VIP de `CUS-2004` con ticket `urgent + negative` sobre `ORD-10567`.
   - **#2** Pausar campaña `tiktok` `very_high` sobre `HOODIE-BLK-M` (stock disponible 2, sell-through 82%/h).
   - **#7-#8** Pronóstico de demanda con la curva típica de drops anteriores: gap de +109 unidades para `TEE-WHT-S` y +113 para `HOODIE-BLK-M`, con recomendación de pre-pedido.
4. Re-ejecutar con API:

```bash
python control_tower.py --data ../scuffers_all_mock_data/candidate_csvs --out outputs_full --candidate-id SCF-2026-XXXX
```

5. Explicar qué cambia: si la API marca un pedido como `exception`, `lost`, `address_validation_error` o `requires_manual_review`, baja en prioridad la acción de marketing y sube la acción logística para ese pedido. Aunque la API caiga (401/timeout) el sistema sigue produciendo el top 10 con la confianza ajustada.

### Por qué es buena solución — 40 segundos

“La parte crítica está separada: Python calcula y prioriza de forma determinista; la IA o el LLM se usaría para redactar el rationale ejecutivo y adaptar mensajes, pero no para inventar scores. Esto hace que sea trazable, rápido y defendible. Además incluyo predicción de demanda por analogía con drops anteriores: aunque no tenemos histórico de drops anteriores, modelo la curva típica (peak en hora 1-2, decay 25%/h) y aplico un multiplicador por intensidad de campaña, lo que permite estimar el gap entre supply y demanda en las próximas 4h y disparar pre-pedido o reasignación de tráfico antes de la rotura.”

### Roadmap producción — 30 segundos

“En producción lo conectaría a Shopify, Gorgias/Zendesk, ERP/WMS, carrier y plataformas de campañas. Añadiría trazas, permisos, colas, alertas en Slack y human-in-the-loop para decisiones sensibles como compensaciones, VIPs o cambios de campaña.”

### Cierre — 10 segundos

“La idea no es sustituir al equipo, sino que en las primeras horas de un drop sepan exactamente dónde mirar y qué decisión tomar primero.”

## 3. Frases para sonar senior

- “No he hecho un chatbot porque el reto no pide conversación; pide priorización operativa.”
- “El LLM puede explicar, pero el scoring debe ser calculable y auditable.”
- “La API logística no sustituye el análisis inicial, lo enriquece.”
- “Priorizo máximo 10 acciones porque operaciones necesita foco, no otro dashboard infinito.”
- “Cada acción tiene owner, impacto esperado y si se puede automatizar o requiere criterio humano.”
- “La calidad está en elegir qué NO automatizar: VIPs, quejas sensibles y excepciones logísticas pasan por humano.”
- “Si mañana conectamos esto a Shopify/Gorgias/ERP, el flujo ya tiene forma de producto.”

## 4. Respuestas a preguntas difíciles

### “¿Por qué no usar un modelo de IA para decidir todo?”

Porque los datos son estructurados y las decisiones deben ser auditables. Uso scoring determinista para priorizar y reservaría el LLM para redactar, resumir y explicar. Así evito alucinaciones y puedo defender cada decisión.

### “¿Qué haces si los CSVs tienen datos incompletos?”

El sistema calcula confianza. Si faltan datos críticos, baja la confianza pero no se rompe. Además usa alias de columnas y defaults conservadores. En producción añadiría validación de esquema y alertas de calidad.

### “¿Por qué máximo 10 acciones?”

Porque operaciones en crisis necesita foco. La restricción del reto es correcta: priorizar implica decidir qué queda fuera. Si doy 40 problemas, no estoy ayudando.

### “¿Qué cambia al aparecer la Shipping Status API?”

Primero calculo riesgo con datos internos. Luego consulto la API solo en pedidos candidatos, porque no todas las llamadas aportan decisión. Si la API indica retraso, excepción o revisión manual, subo prioridad y cambio owner/action type si corresponde.

### “¿Dónde meterías IA generativa?”

En tres lugares:

- Redacción del rationale ejecutivo de cada acción.
- Agrupación de patrones de tickets o comentarios.
- Generación de mensajes para cliente o macros de soporte.

Pero no en el cálculo base de riesgo.

### “¿Cómo lo conectarías a Scuffers real?”

Shopify para pedidos y stock, Gorgias/Zendesk para tickets, ERP/WMS para inventario, Sendcloud/carrier para estado logístico, Meta/TikTok/Klaviyo para campañas. Todo alimenta la Control Tower y las acciones se publican en Slack, dashboard o sistema de tickets.

## 5. Si hay que improvisar con poco tiempo

Prioridad de construcción:

1. Cargar CSVs.
2. Generar top 10 acciones.
3. Explicar scores.
4. Integrar API.
5. Hacer UI.
6. Añadir IA generativa.

Si hay que sacrificar algo, sacrifica UI o IA generativa, no el top 10 funcional.

## 6. Demo alternativa si falla la API

Di:

“La solución está preparada para enriquecer con API logística, pero mantiene funcionamiento degradado si la API falla. Eso también es parte del diseño: en operaciones, una dependencia externa no puede tumbar todo el sistema.”

Y enseña:

- `--no-api`
- `confidence` más bajo sin API.
- `reason` indicando que la API no respondió si hubo error.

## 7. Checklist antes de entregar

- `top_actions.json` existe.
- Tiene máximo 10 acciones.
- Cada acción tiene todos los campos requeridos.
- Hay al menos 3 tipos de acción distintos si los datos lo permiten.
- La primera acción se entiende sin explicar código.
- Puedes explicar por qué el ranking 1 va antes que el ranking 2.
- Puedes explicar qué harías en producción.

## 7b. Supuestos y limitaciones (di esto antes de que te pregunten)

- **Curva de demanda**: peak en hora 1-2, decay 25 %/h, multiplicador de campaña 1.0x → 1.5x. Es un proxy razonable de drops cápsula; cuando exista histórico real, lo sustituyo por un fit empírico.
- **Pesos de scoring** (5 señales por pedido y dentro de cada detector) son heurísticos, defendibles, y se pueden mover a un fichero de config sin recompilar.
- **No tomo decisiones financieras**: no toco precios ni descuentos, solo escalo a humano (`payment_review_audit`, `vip_rescue`).
- **`order_value` ruidoso/vacío** se reconstruye con `unit_price * quantity` cuando es posible; cuando no, baja la confianza del caso.
- **API logística**: opcional. Si falla o tarda, se anota en el motivo y la confianza baja, pero el top 10 se entrega igual.
- **Datos esnapshot**: hay 10 clientes con `customer_orders_count = 0` que aparecen en `orders.csv`; lo trato como inconsistencia del snapshot, no como error bloqueante. Lo expongo en `data_quality.json`.
- **Texto libre** (mensaje de ticket) lo uso solo para detectar palabras de riesgo, nunca para inventar campos.
- **No hay LLM en el flujo crítico**: el LLM se reservaría para redactar mensajes a cliente o resumir el top 10 en lenguaje natural; la priorización es determinista y auditable.

## 8. Top 10 generado con los CSVs reales del enunciado

| # | Tipo | Target | Resumen |
|---|------|--------|---------|
| 1 | `vip_rescue` | `ORD-10567` | CUS-2004 (VIP, LTV 1246€), ticket urgent+negative |
| 2 | `pause_campaign` | `HOODIE-BLK-M` | Stock 2, very_high TikTok, sell-through 82%/h |
| 3 | `pause_campaign` | `TEE-WHT-S` | Stock 2, high TikTok, sell-through 86%/h |
| 4 | `throttle_traffic` | `JORTS-BLU-M` | Stock neto -9, demanda orgánica acelerada |
| 5 | `pause_campaign` | `ZIP-BLK-M` | Stock 6, high Instagram, sell-through 75%/h |
| 6 | `support_macro_response` | `PATTERN-me_preocupa_que_se_agote` | 4 tickets idénticos high/urgent |
| 7 | `demand_forecast_alert` | `TEE-WHT-S` | Gap previsto +109 ud en 4h |
| 8 | `demand_forecast_alert` | `HOODIE-BLK-M` | Gap previsto +113 ud en 4h |
| 9 | `support_macro_response` | `PATTERN-necesito_saber_si_mi_ped` | 3 tickets idénticos |
| 10 | `vip_rescue` | `ORD-10460` | CUS-2033 (VIP, LTV 2120€), ticket high+negative |

Esto te da la narrativa completa: dos rescates VIP, cuatro acciones de marketing/inventario, dos de soporte (macros) y dos de pronóstico de demanda. Familias bien repartidas, todo justificado con datos reales.

