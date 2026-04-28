# Propuesta técnica detallada para Scuffers

## Cómo se llevarían a cabo realmente las soluciones planteadas en el proceso de selección

## 0. Contexto del documento

Este documento toma cada una de las 7 preguntas y los 2 casos del proceso de selección y los convierte en una propuesta técnica concreta, con arquitectura, herramientas específicas, flujos paso a paso, datos necesarios, métricas y riesgos. El objetivo es que puedas defender cada idea en la siguiente fase como si la hubieras construido tú, entendiendo de verdad lo que hay debajo.

La filosofía global es la misma para todas las respuestas:

- Datos primero, IA después.
- RAG para conocimiento, SQL para métricas, agentes para acciones.
- Empezar con bajo riesgo, alto volumen y trazabilidad total.
- Humano en el loop en todo lo que toque cliente, marca, dinero o reputación.

Frase para repetir en la entrevista:

"No quiero meter IA por meter IA. Quiero diseñar capas operativas que conecten datos, procesos y equipos, con métricas claras y control humano donde haga falta."

---

## 1. Pregunta 1 — Automatización propia (caso EF Bristol)

### 1.1. Resumen de tu respuesta

Centralizaste la operativa de residencias, transportes, llegadas y salidas en hojas de Excel y montaste sobre Make una capa que automatizaba avisos, estados y seguimiento entre equipos, con el principio de "primero ordenar el proceso, luego automatizar".

### 1.2. Cómo se llevaría a cabo realmente

#### 1.2.1. Diagnóstico previo (lo que de verdad hay que hacer antes)

Antes de tocar Make hay que hacer tres cosas que en una entrevista senior se valoran muchísimo:

- Mapear el proceso end-to-end: actores, inputs, outputs, decisiones, tiempos, puntos de fricción y SLAs.
- Inventariar fuentes de datos: hojas, emails, formularios, sistemas de reservas, pagos.
- Definir el modelo de datos canónico: qué es un "caso", qué estados tiene, qué campos son obligatorios, qué relaciones existen entre residencia, transporte, alumno, llegada y salida.

Esto se documenta normalmente con:

- Un diagrama BPMN o un flujo en Miro/Lucidchart.
- Una tabla de estados (state machine) con transiciones permitidas.
- Un diccionario de datos.

#### 1.2.2. Modelo de datos

En Excel/Sheets se simula con pestañas, pero la versión correcta sería:

- `students` (id, nombre, programa, fecha_llegada, fecha_salida, estado, ...).
- `residences` (id, nombre, capacidad, contacto, ...).
- `transports` (id, tipo, fecha, hora, origen, destino, vehiculo, conductor, ...).
- `arrivals` y `departures` (id, student_id, transport_id, residence_id, estado, timestamp, responsable, ...).
- `events` (id, entidad, tipo_evento, payload, created_at) — log de auditoría.

En producción esto va en una base relacional (PostgreSQL). En MVP se puede dejar en Google Sheets / Airtable, que es exactamente lo que hiciste, pero con una estructura limpia y un campo `estado` con valores cerrados (no texto libre).

#### 1.2.3. Arquitectura de la automatización

Esquema lógico:

```text
Sheets/Airtable (fuente)
   ↓ webhook on edit / scheduled trigger
Make (orquestador)
   ↓ branches según estado
Email / WhatsApp / Slack (notificaciones)
   ↓ acciones
Sheets/Airtable (estado actualizado)
   ↓ logs
Sheets "events" (auditoría)
```

Patrones aplicados:

- Event-driven: cada cambio en el sheet dispara un escenario.
- State machine: cada estado define qué transiciones y notificaciones son válidas.
- Idempotencia: si un escenario se ejecuta dos veces, el resultado es el mismo (clave porque Make a veces reintenta).
- Logging: cada acción se escribe en una pestaña de eventos con timestamp, usuario, payload.

#### 1.2.4. Flujos concretos típicos en este caso

Flujo "llegada de alumno":

1. Cuando se crea/edita una fila en `arrivals`, Make recibe el webhook.
2. Valida campos obligatorios (vuelo, hora, residencia, contacto).
3. Si faltan datos, marca estado `incompleto` y avisa al responsable por email/Slack.
4. Si están completos, calcula ventana de recogida (hora vuelo ± buffer) y asigna transporte.
5. Notifica al conductor con detalles y al alumno con horario y punto de encuentro.
6. Cambia estado a `programado` y registra en `events`.
7. Un job programado revisa T-24h, T-2h y T+1h para mandar recordatorios o detectar incidencias.

Flujo "incidencia transporte":

1. El conductor responde "retraso 30min" en Slack/WhatsApp.
2. Make captura mensaje, lo parsea (regex o LLM clasificador).
3. Actualiza estado a `retrasado`, recalcula ETA, avisa a residencia y a alumno.
4. Si el retraso supera umbral, escala a manager humano.

#### 1.2.5. Cómo medir el impacto (lo que tu respuesta menciona pero hay que concretar)

Métricas operativas:

- Tiempo medio entre evento (vuelo aterriza) y notificación al conductor.
- Tasa de errores de comunicación (alumno no avisado).
- Número de tareas manuales eliminadas por semana.
- Reducción de emails internos.
- Tiempo medio de resolución de incidencias.

Cómo se mide: comparando ventanas antes/después con datos del log `events` y con encuestas cortas a los equipos.

### 1.3. Cómo defenderlo en la entrevista

Frases:

- "El valor no estaba en Make, estaba en haber definido bien el modelo de datos y la máquina de estados antes de automatizar."
- "Make fue suficiente porque el riesgo era bajo y la lógica era determinista; si la lógica fuera no determinista o crítica, lo habría hecho en código."
- "Lo que aprendí ahí es que la IA y la automatización solo aportan valor si el proceso ya está bien definido. Una automatización sobre un proceso roto rompe más rápido."

---

## 2. Pregunta 2 — Qué automatizar primero en una marca con 150 incidencias diarias

### 2.1. Resumen de tu respuesta

Automatizar lo repetitivo, frecuente y de bajo riesgo: tracking, FAQs, cambios y devoluciones, dudas de talla. Stack mental: Shopify + helpdesk + Make + LLM clasificador. Dejar manual lo que tiene carga de criterio o impacto de marca.

### 2.2. Cómo se llevaría a cabo realmente

#### 2.2.1. Mapa de tickets y matriz de priorización

Lo primero es taxonomía. Hay que clasificar los 150 tickets/día por:

- Intent: tracking, talla, devolución, cambio, queja, fraude, VIP, otros.
- Complejidad: baja / media / alta.
- Riesgo: bajo / medio / alto (impacto en marca, dinero o legal).
- Volumen y SLA actual.

Esto se monta con un dataset histórico de 2-4 semanas. Se puede etiquetar manualmente una muestra (300-500 tickets) y entrenar un clasificador o usar un LLM con few-shot. La salida es una matriz volumen × riesgo. La regla es: automatizar lo que está en alto volumen + bajo riesgo. El resto, asistido o manual.

#### 2.2.2. Stack concreto recomendado

- Ecommerce: Shopify (Admin API + webhooks `orders/*`, `fulfillments/*`, `refunds/*`).
- Helpdesk: Gorgias o Zendesk (ambos con API y webhooks; Gorgias es muy fuerte para Shopify).
- Orquestador: Make o n8n para integraciones simples; FastAPI/LangGraph en código si la lógica crece.
- LLM: OpenAI GPT-4.1/4o-mini para clasificación, GPT-4.1 o Claude Sonnet 4.x para redacción.
- Vector DB: pgvector sobre Postgres para FAQs y políticas.
- Logística: integración con la API del carrier (Sendcloud, SEUR, Correos Express, etc.).
- Observabilidad: LangSmith o Arize Phoenix.

#### 2.2.3. Arquitectura de la capa de soporte automatizado

```text
Cliente → Web chat / WhatsApp / Email / IG DMs
        ↓
Helpdesk (Gorgias) → webhook ticket creado
        ↓
Router/Clasificador (LLM small + reglas)
        ↓
   ┌────────────┬─────────────┬───────────────┐
   ↓            ↓             ↓               ↓
Tracking      FAQ/Talla    Devolución     Escalado humano
agent         agent (RAG)  agent          (queja, VIP, fraude)
   ↓            ↓             ↓               ↓
Shopify API   Vector DB    Política +    Asignación a agente
+ Carrier     (políticas)  Shopify       con resumen IA
   ↓            ↓             ↓               ↓
Respuesta + acción + log + métricas
```

#### 2.2.4. Implementación de cada agente

Agente de tracking:

1. Detecta intent "dónde está mi pedido".
2. Pide email + nº pedido si no los tiene (verificación ligera).
3. Llama a `shopify.get_order(order_id)` y luego `carrier.get_tracking(tracking_number)`.
4. Resume el estado en lenguaje humano y con tono Scuffers.
5. Si hay incidencia (retraso > X días, devuelto a almacén, etc.), escala con resumen.

Agente de FAQ y tallas:

1. RAG sobre: política de envíos, devoluciones, cambios, guía de tallas, FAQs.
2. Para tallas, además consulta la ficha del producto (medidas reales, materiales, fit).
3. Si la consulta es comparativa ("vengo de talla X en marca Y"), sigue una tabla de equivalencias o un protocolo de preguntas.
4. Devuelve respuesta + fuentes citadas + nivel de confianza.

Agente de devoluciones/cambios estándar:

1. Verifica ventana de devolución según política y fecha de pedido.
2. Genera etiqueta de devolución vía API del carrier.
3. Crea registro de devolución en Shopify y en helpdesk.
4. Manda instrucciones al cliente.
5. Si el motivo es "producto dañado/incorrecto", pasa a humano (esto entronca con tu pregunta 3).

Reglas de escalado a humano (siempre):

- Cliente VIP (segmento en Shopify o CRM).
- Producto dañado/incorrecto.
- Reembolso fuera de política.
- Sentiment negativo fuerte (umbral del clasificador).
- Mención pública o exposición reputacional.
- Confianza del agente < umbral.

#### 2.2.5. Cómo se ve en código (esquema, no producción)

```python
# Pseudocódigo del flujo principal
def handle_ticket(ticket):
    intent = classify(ticket.text)  # LLM small + reglas
    if needs_human(ticket, intent):
        return escalate(ticket, reason=...)

    agent = ROUTER[intent]
    result = agent.run(ticket)

    log(ticket, result)            # trazabilidad
    if result.confidence < 0.75 or result.requires_human:
        return escalate(ticket, draft=result.reply)

    helpdesk.reply(ticket.id, result.reply)
    return result
```

#### 2.2.6. Métricas que demuestran que esto funciona

- Deflection rate (tickets resueltos sin humano) por intent.
- Tiempo medio de primera respuesta y de resolución.
- CSAT post-resolución (encuesta 1-5 con un comentario opcional).
- Tasa de escalado y motivo.
- Errores detectados por QA humano sobre una muestra.
- Coste por ticket atendido (LLM + infra) vs coste humano equivalente.

### 2.3. Cómo defenderlo en la entrevista

Frases:

- "Empezaría por taxonomía y volumen. Sin entender los 150 tickets, automatizar es ruido."
- "Tracking, FAQs y cambios son perfectos para automatizar: alto volumen, bajo riesgo, mucho dato deterministico que el LLM no debería inventar."
- "El LLM no calcula nada crítico. Para tracking llamo a Shopify y al carrier. El LLM solo redacta y enruta."
- "Cualquier acción con dinero o reputación pasa por humano con un buen resumen y un borrador listo."

---

## 3. Pregunta 3 — Qué NO automatizarías nunca

### 3.1. Resumen de tu respuesta

No automatizar la decisión final en producto dañado, pedido incorrecto o clientes con mala experiencia previa. La IA puede asistir (clasificar, resumir, priorizar, proponer borrador), pero la resolución final es humana.

### 3.2. Cómo se llevaría a cabo realmente

Aquí lo importante es traducir esa intuición a un sistema concreto: la IA hace 80% del trabajo invisible (preparación), el humano hace el 20% visible (decisión final).

#### 3.2.1. Patrón "human-in-the-loop con paquete de decisión"

Para cada caso sensible, el sistema debe entregar al agente humano un "paquete" estandarizado:

- Resumen del caso en 5 líneas.
- Histórico del cliente: pedidos, devoluciones, tickets previos, NPS si existe.
- Clasificación: tipo, gravedad, riesgo reputacional, exposición pública.
- Política aplicable (extracto del documento).
- Borrador de respuesta en tono Scuffers.
- Opciones recomendadas: reembolso parcial, reenvío, código descuento, gesto extra.
- Estimación de coste de cada opción.
- Banderas de cuidado: cliente VIP, segunda incidencia, mención en redes, etc.

El humano ve todo eso en una pantalla, marca la opción y la ejecuta con un clic. Esto es lo que hacen Gorgias Macros + plantillas IA, Intercom Fin, Zendesk AI, etc.

#### 3.2.2. Detección de casos "no automatizables"

Reglas duras que siempre fuerzan humano:

- Producto dañado/incorrecto (clasificador con foto si la sube; multimodal LLM verifica).
- Reclamación legal (palabras clave, tono, mención de organismos).
- Cliente con histórico de mala experiencia (flag en CRM).
- Compensación > umbral configurable.
- Caso público (mención en redes o review pública).
- Fraude potencial (reglas de Shopify + scoring propio).

#### 3.2.3. Por qué esto NO es una limitación, es diseño

En una entrevista quedará bien si lo formulas así:

- "Automatizar la decisión final en estos casos es lo más caro que puedes hacer: una mala respuesta en un caso sensible cuesta más que automatizar miles de tickets fáciles."
- "El humano en el loop no es lentitud, es control de calidad asimétrico: ahorras tiempo en lo barato para invertirlo en lo caro."

### 3.3. Cómo defenderlo en la entrevista

Frases:

- "La IA no decide; prepara la decisión. El criterio se queda en el humano cuando hay marca, dinero o emoción de por medio."
- "El objetivo no es 100% automatización. Es 100% asistencia y automatización solo donde el riesgo lo permite."

---

## 4. Pregunta 4 — Debug del flujo de Make (Shopify → HubSpot → email VIP → ERP → Sendcloud)

### 4.1. Resumen de tu respuesta

Si stock y envío sí ocurren, el fallo está en la rama VIP o en el módulo de email. Plan: revisar ejecución real, validar el dato (>3 compras), revisar tipo/operador del filtro, añadir un log antes del IF, y si pasa el filtro, revisar email (consentimiento, plantilla, campo vacío).

### 4.2. Cómo se haría realmente paso a paso (debug profesional)

#### 4.2.1. Hipótesis ordenadas (de más probable a menos)

1. El filtro VIP no se está cumpliendo:
   - El campo `total_orders` o `lifetime_orders` no llega o llega como string.
   - Operador mal configurado (`equal` en lugar de `greater than`).
   - Comparación entre tipos distintos ("3" vs 3).
   - El contacto en HubSpot se acaba de crear y todavía no tiene historial agregado.
2. El filtro sí se cumple, pero el módulo de email falla:
   - Plantilla con variable vacía (`{{first_name}}`) que rompe el render.
   - Falta de consentimiento de marketing.
   - Dirección de remitente/dominio no autenticado (SPF/DKIM/DMARC).
   - Rate limiting o lista de supresión.
   - Campo `email` vacío o mal formado.
3. Idempotencia / duplicados:
   - El cliente ya recibió el email en otro pedido y hay deduplicación silenciosa.

#### 4.2.2. Procedimiento de diagnóstico (cómo lo haría un senior en Make)

1. En Make, abrir el escenario y filtrar el History por un pedido VIP real reciente que debería haber recibido el email.
2. Ver la ejecución completa: cada bundle de cada módulo.
3. Mirar el módulo "Crear contacto en HubSpot" → ver el output completo (ID del contacto, número de compras devuelto).
4. Mirar el módulo "Filtro VIP" (router/filter) → ver qué condición falla. Make muestra "Condition not met" con los valores reales.
5. Si la condición falla por tipo: convertir el valor con `parseNumber()` o `toNumber()` antes de comparar.
6. Si la condición falla por valor: comprobar en HubSpot que el contacto realmente tiene 3+ compras agregadas en la propiedad usada.
7. Añadir un módulo "Tools → Set variable" antes del filtro con el valor evaluado y un módulo "Sleep + Notify" que mande a un canal de Slack qué está leyendo. Esto es el equivalente a un `print()` para Make.
8. Si el filtro pasa correctamente, ir al módulo de email:
   - Probar la plantilla con datos reales (preview).
   - Revisar logs del proveedor de email (HubSpot, Klaviyo, Mailchimp).
   - Comprobar consentimiento de marketing del contacto.
   - Comprobar dominio remitente y reputación.

#### 4.2.3. Causas raíz frecuentes en este patrón (errores reales del sector)

- HubSpot tarda en agregar la propiedad de "número de compras" si depende de un workflow propio de HubSpot. El filtro de Make ve un valor desactualizado.
- El campo se calcula sobre "deals" en HubSpot pero los pedidos de Shopify se sincronizan como "contacts" sin "deals". El contador queda a 0.
- Doble opt-in: el cliente VIP no marcó consentimiento de marketing → HubSpot bloquea el envío sin error visible.
- Race condition: el módulo de email se ejecuta antes de que termine la sincronización Shopify→HubSpot.

#### 4.2.4. Correcciones recomendadas

- Normalizar tipos antes del filtro y testear con un dataset de pedidos reales.
- Añadir un Data Store en Make (o tabla en Sheets/Postgres) que guarde "VIP enviado a customer X el día Y" para evitar duplicados y tener auditoría.
- Mover la lógica VIP a Shopify Customer Tags o a un campo calculado en el CRM, no a un cálculo on-the-fly en Make. Lo que cambia poco se calcula upstream.
- Añadir alertas: si en 24h ningún pedido pasa el filtro VIP, mandar warning al canal de operaciones.
- Añadir un test sintético: un escenario que cada noche cree un pedido de prueba con un cliente VIP de prueba y valide que recibe el email.

#### 4.2.5. Cómo se haría esto en producción "bien"

En cuanto el flujo es crítico (afecta a stock, dinero, comunicación), conviene salir de Make y montarlo en código:

- Webhook de Shopify → endpoint FastAPI.
- Cola (Redis/SQS) para garantizar entrega.
- Worker que procesa el pedido, hace upsert en CRM, valida VIP contra una vista materializada, manda email vía proveedor (Klaviyo/SendGrid).
- Idempotency key por `order_id` para no duplicar.
- Tests unitarios + tests de contrato con Shopify mock.
- Métricas en Datadog/Grafana: tasa de éxito, latencia, errores por paso.

### 4.3. Cómo defenderlo en la entrevista

Frases:

- "Mi heurística para debuggear flujos no-code: lo que sí ocurre te dice dónde NO está el fallo. Si stock y envío van bien, el fallo está aislado en la rama que falla."
- "En Make, lo primero es siempre el History con un caso real. No se debuggea por intuición, se debuggea por ejecución."
- "Cuando un flujo se vuelve crítico, deja de ser tarea de Make. Make orquesta integraciones; la lógica crítica vive en código con tests, colas e idempotencia."

---

## 5. Pregunta 5 — Sistema de inteligencia comercial para drops y stock

### 5.1. Resumen de tu respuesta

Sistema con crawling, IA y automatización que consolida señales internas (ventas históricas, estacionalidad, capacidad de compra por mercado) y externas (tendencias en redes, competencia, intereses emergentes) para sugerir qué lanzar, cuándo y con qué profundidad de stock por categoría/talla. MVP en 3h: crawler + clasificador de tendencias + dashboard de recomendaciones.

### 5.2. Cómo se llevaría a cabo realmente

Esta es la respuesta más ambiciosa y la más vendible. Hay que explicarla por capas, dejando claro qué es MVP y qué es producción.

#### 5.2.1. Arquitectura objetivo

```text
[ Señales internas ]                         [ Señales externas ]
- Ventas por SKU/talla/mercado/fecha         - TikTok, Instagram, Reddit
- Stock y devoluciones                       - Google Trends, Search Console
- PDP analytics (visitas, ATC, wishlist)     - Competidores (catálogo, precios, drops)
- Calendario de campañas y drops             - Reviews, foros, blogs
                ↓                                      ↓
        [ Capa de ingesta ]
   APIs (Shopify, GA4, Meta, TikTok)   +   Crawlers (Playwright/Firecrawl/Apify)
                ↓
        [ Almacenamiento ]
   Postgres (operacional) + DWH (BigQuery/Snowflake) + pgvector (texto)
                ↓
        [ Capa de features ]
   - Velocidad de venta por SKU/talla/mercado
   - Sell-through rate por drop pasado
   - Curvas estacionales
   - Tendencias emergentes (NER + clustering + scoring)
   - Brand fit y competidor mirror
                ↓
        [ Capa de decisión ]
   - Modelos simples (regresión, scoring, similitud) + LLM razonador
   - Reglas de negocio (mínimos, márgenes, capacidad)
                ↓
        [ Outputs accionables ]
   - Calendario sugerido de drops (fecha, categoría, mercado)
   - Profundidad recomendada por talla y color
   - Alertas tempranas de tendencia
   - Dashboard ejecutivo + export a planning
```

#### 5.2.2. Datos y features que de verdad usarías

Internos:

- Ventas por (sku, talla, color, mercado, día) últimos 24 meses.
- Devoluciones y motivos.
- Stock inicial vs sell-through por drop pasado.
- Visitas a PDP, add-to-cart, wishlist, conversión (GA4 o Shopify Analytics).
- Calendario de campañas y presupuesto.
- Datos de email/SMS (Klaviyo): aperturas, clics, segmentos.

Externos:

- TikTok / Instagram: hashtags relevantes (#streetwear, #y2k, #scuffers, etc.), creadores de la comunidad, sonidos en tendencia.
- Google Trends: queries por mercado.
- Reddit: subreddits de moda (r/streetwear, r/malefashionadvice, etc.).
- Catálogos de competidores: nuevos drops, precios, materiales, fit.
- Reviews públicas y comentarios.

#### 5.2.3. Crawling (cómo se hace correctamente)

- Donde haya API oficial, usar API (Meta Graph, TikTok Research API si aplica, Google Trends mediante librerías o serpapi).
- Donde no la haya, usar Playwright (control de navegador) o Firecrawl/Apify (gestionados) respetando robots.txt, ToS y rate limit.
- Headless browser cuando hay JS pesado; HTTP simple cuando hay HTML estático.
- Rotación de user-agents y proxies (Bright Data, Smartproxy) para crawl masivo. Solo si es legal y necesario.
- Pipeline: fetch → parse → normalizar → deduplicar → guardar (raw + curado) → enriquecer (NER, sentimiento, clasificación).
- Programado con Prefect/Airflow/Temporal o cron simple en MVP.

Riesgos a comunicar:

- Legales: ToS, GDPR, scraping de datos personales.
- Técnicos: bloqueo, CAPTCHAs, cambios de DOM.
- Calidad: ruido, duplicados, sesgos.

#### 5.2.4. Clasificación de tendencias

Pipeline:

1. Recoger texto y metadatos (post, hashtag, fecha, engagement).
2. Limpiar y normalizar.
3. Embeddings (OpenAI text-embedding-3-large o open source bge-large).
4. Clustering (HDBSCAN o k-means) sobre embeddings para detectar grupos de conceptos.
5. Para cada cluster, un LLM nombra el tema y extrae entidades (prenda, color, fit, material, estética, target).
6. Scoring por cluster: tamaño, crecimiento semana a semana, engagement medio, novedad respecto al catálogo de Scuffers.
7. Filtrado por brand fit (otra capa de embeddings + reglas).

Output esperado:

- Top tendencias emergentes ordenadas por potencial.
- Cada tendencia con: descripción, ejemplos, métricas, productos relacionados, mercado dominante.

#### 5.2.5. Predicción de demanda y profundidad de stock

Para producción no hace falta un modelo complejo desde el día 1. Una buena heurística vale:

```text
score_riesgo_rotura(sku, talla) =
   0.45 * velocidad_ventas_28d (suavizada)
 - 0.30 * stock_actual_dias_cobertura
 + 0.15 * señales_externas (tendencia ligada al SKU)
 + 0.10 * factor_estacional
```

Para drops nuevos sin histórico:

- Buscar productos análogos por embeddings de descripción + atributos.
- Usar su sell-through como prior.
- Ajustar con tendencia externa y mercado objetivo.

Esto es defendible y explicable. Un modelo opaco con pocos datos se rompe en preguntas.

En producción real se evolucionaría a modelos como:

- Prophet/NeuralProphet para series temporales.
- LightGBM con features tabulares.
- Hierarchical forecasting por categoría/mercado.

#### 5.2.6. Capa de decisión y output

El LLM no calcula stock. El LLM:

- Razona sobre las tendencias y las traduce a recomendaciones en lenguaje claro.
- Genera el "memo de drop" para dirección: por qué este lanzamiento, qué mercado, qué riesgo, qué alternativa.
- Estructura el output en JSON validado para que el dashboard lo pinte.

Ejemplo de salida:

```json
{
  "drop": "SS26 cargo evolution",
  "fecha_recomendada": "2026-05-14",
  "mercados_prioritarios": ["ES", "FR", "UK"],
  "tallas_profundidad": {"S": 0.18, "M": 0.30, "L": 0.28, "XL": 0.16, "XXL": 0.08},
  "racional": "Crecimiento +35% menciones cargo en TikTok ES/FR últimas 4 semanas; sell-through medio en cargo previo 78% con rotura en M/L.",
  "riesgos": ["dependencia de stock proveedor X", "solapamiento con campaña de competidor Y"],
  "confianza": 0.74
}
```

#### 5.2.7. MVP de 3 horas (lo que de verdad enseñarías)

- 1 dataset reducido de ventas históricas simuladas.
- 1 dataset de 200-500 posts/comentarios de redes (puedes preprocesarlos).
- 1 script Python que: hace embeddings, clusteriza, genera ranking de tendencias.
- 1 endpoint FastAPI o app Streamlit con:
  - tabla de tendencias detectadas,
  - tabla de SKUs análogos,
  - recomendación de drop con racional generado por LLM,
  - botón "exportar a planning".

Este MVP es defendible y se construye en 2-3 horas si llevas el dataset listo.

### 5.3. Cómo defenderlo en la entrevista

Frases:

- "Esto no es un modelo predictivo opaco. Es una capa de decisión explicable que combina datos internos, señales externas y reglas de negocio."
- "El LLM no predice ventas. Predice ventas el modelo o la heurística. El LLM explica y comunica."
- "El valor para Scuffers es reducir decisiones basadas solo en intuición sin matar la creatividad. La IA aporta consistencia, no creatividad."

---

## 6. Pregunta 6 — Automatización de respuestas a reseñas negativas en Instagram

### 6.1. Resumen de tu respuesta

Piloto con guardrails. IA clasifica por tema, urgencia y riesgo, genera borradores en tono de marca, no responde libremente. Empezar por baja gravedad, medir tiempo, sentimiento, calidad y resultados. Escalar solo si demuestra valor sin riesgo.

### 6.2. Cómo se llevaría a cabo realmente

Este es un caso clásico de conflicto CEO vs marca, y el patrón correcto es "co-piloto, no piloto automático".

#### 6.2.1. Arquitectura del piloto

```text
Meta/Instagram Graph API (webhook de menciones/comentarios)
        ↓
Ingesta y normalización (texto, autor, follower count, contexto del post)
        ↓
Clasificador (LLM small)
   - tema: producto, envío, talla, atención, marca, queja general, troll
   - sentimiento: -1 a +1
   - urgencia: baja/media/alta
   - riesgo reputacional: bajo/medio/alto
   - clienteVIP/influencer: bool
        ↓
Router
   - Riesgo bajo + sentimiento ligeramente negativo → borrador IA → cola "auto-aprobado tras N min si nadie objeta" (modo conservador: nunca publica solo)
   - Riesgo medio → borrador IA + revisión humana obligatoria
   - Riesgo alto / queja seria / mención de medios → escala directa a brand/CS, sin borrador público
        ↓
Panel de revisión (Notion/Retool/app interna)
   - Comentario original
   - Clasificación IA + confianza
   - Borrador en tono Scuffers + 2 alternativas
   - Política aplicable
   - Acción sugerida (responder en público / DM / no responder / escalar)
        ↓
Publicación + log + métricas
```

#### 6.2.2. Guardrails concretos

- Nunca responde sola en comentarios públicos durante el piloto. Siempre humano valida.
- Lista de palabras prohibidas en el output (jergas no de marca, promesas, descuentos, fechas).
- Validador de tono: clasificador secundario que puntúa el borrador vs ejemplos aprobados de marca.
- Confianza mínima para mostrar borrador: 0.7. Por debajo, "sin sugerencia, escalar".
- Detección de troll/bait: no responder, marcar.
- Detección de queja real con datos personales: pasar a DM con plantilla legal.
- Limitador: máximo N respuestas/hora por cuenta, para no parecer automatizada.

#### 6.2.3. Cómo se vende internamente este piloto

Al CEO:

- Mejora tiempo de respuesta de horas a minutos.
- Permite escalar a 10x volumen sin contratar.
- Estandariza la calidad de respuesta.

Al equipo de marca:

- Mantiene el control: nada se publica sin revisión.
- Aprende del estilo del equipo (los borradores se refinan con feedback).
- Da datos: qué se queja la gente, en qué temas, en qué momento.

Al equipo de CS:

- Resúmenes semanales de issues recurrentes.
- Borradores que ahorran 60-70% del tiempo de redacción.

#### 6.2.4. Métricas del piloto a 30/60 días

- Volumen procesado.
- % borradores aceptados sin edición.
- % editados ligeramente.
- % rechazados o escalados.
- Tiempo medio de respuesta.
- Sentimiento medio de la conversación post-respuesta.
- Tickets evitados que llegaban a CS desde redes.
- Incidencias detectadas (errores de tono, alucinaciones, malentendidos) — esto es lo que valida o tumba el piloto.

#### 6.2.5. Cuándo se "abre" el piloto a más automatización

Solo si:

- Aceptación sin edición > 70% sostenida 4 semanas.
- 0 incidentes graves.
- Sentimiento post-respuesta no empeora.
- El equipo de marca está conforme con muestreo aleatorio.

Y aun así, solo se permite respuesta semi-autónoma en categorías de mínimo riesgo (ej: "¿cuándo reponéis?", "¿hacéis envíos a X?"), nunca en quejas de producto o atención.

### 6.3. Cómo defenderlo en la entrevista

Frases:

- "Una respuesta automática mal redactada en una marca como Scuffers cuesta más que cien respuestas humanas tarde."
- "El patrón correcto es co-piloto: la IA prepara, el humano decide. Y solo se abre la mano cuando hay datos que demuestran que es seguro."
- "La discusión CEO vs marca no se resuelve eligiendo bando. Se resuelve diseñando un piloto medible que enseñe a ambos qué pasa de verdad."

---

## 7. Pregunta 7 — KPI a 14 días para saber si la automatización fue un error

### 7.1. Resumen de tu respuesta

Para el sistema de drops: precisión de stock vs lanzamientos anteriores (rotura/sobrestock), priorización de fechas/categorías/mercados con impacto en ventas por drop, y porcentaje de información producida que acaba implementándose. Complementario: feedback cliente, comentarios, recurrencia de compra.

### 7.2. Cómo se llevaría a cabo realmente

A 14 días no se puede medir efecto en sell-through real (un drop tarda más en madurar). Hay que medir señales tempranas de calidad y adopción.

#### 7.2.1. KPIs por capa

Calidad del sistema:

- Precisión del clasificador de tendencias (revisión humana sobre muestra).
- % de SKUs análogos correctos según equipo de producto.
- Coherencia interna de las recomendaciones (las mismas premisas dan los mismos outputs).
- Latencia y coste por recomendación.

Calidad de las recomendaciones:

- Brier score / accuracy frente a una pequeña validación retrospectiva: aplicar el sistema a drops pasados conocidos y ver si habría acertado.
- Solapamiento con la decisión que tomaría el equipo sin IA (proxy de razonabilidad).
- Diversidad: que no recomiende siempre lo mismo.

Adopción y proceso:

- % de recomendaciones revisadas por el equipo.
- % aceptadas, modificadas o rechazadas.
- Tiempo de planning ahorrado por reunión semanal de buying/merchandising.
- Número de decisiones que entran al sistema con racional documentado.

Negocio (a 30-90 días):

- Sell-through del primer drop influido por el sistema vs drop comparable previo.
- Roturas tempranas (% SKUs sin stock antes de día 7).
- Sobrestock (% inventario por debajo del 30% sell-through a día 30).
- Devoluciones por talla en SKUs donde el sistema sugirió profundidad.
- CSAT y comentarios sobre disponibilidad.

#### 7.2.2. Cómo decidir si fue un error a los 14 días

Reglas simples:

- Si la precisión del clasificador < 60% en muestra de revisión: error de sistema.
- Si la aceptación de recomendaciones < 20%: error de adopción.
- Si las recomendaciones se basan en datos sucios o contradicen sentido común reiteradamente: error de datos.
- Si todas son verdes pero negocio no toca el sistema: error de proceso (falta integrar en el ritual de planning).

#### 7.2.3. Qué se hace si falla

- Volver a etiquetar y mejorar el dataset.
- Ajustar el scoring de tendencias.
- Cambiar el formato del output (que sea menos técnico, más decisional).
- Integrar al equipo de producto desde el principio (co-creación, no entrega).
- Medir adopción con un campeón interno.

### 7.3. Cómo defenderlo en la entrevista

Frases:

- "A 14 días no mido ventas, mido calidad de sistema y adopción. Las ventas son consecuencia, no señal temprana."
- "La automatización fracasa más por falta de adopción que por error técnico. Por eso meto adopción como KPI desde el día 1."
- "Si nadie usa la recomendación, da igual lo bien que la calcule. La métrica más importante es % de recomendaciones que entran en la decisión real."

---

## 8. Caso 1 — Lanzamiento de colección, pico x8 de pedidos, 40% incidencias talla, colapso de soporte

### 8.1. Resumen de tu respuesta

Tres frentes: prevención (analítica + protocolos por SKU de riesgo), web (aviso de alta demanda + guía de talla mejorada), agentes automatizados (tracking, cambios estándar, dudas) con escalado humano cuando hay excepción, frustración, riesgo o VIP. Panel en tiempo real. Foco: respuesta eficiente sin contratar.

### 8.2. Cómo se llevaría a cabo realmente

Hay tres horizontes temporales: antes del drop (T-7d a T-0), durante las primeras 6h (T0 a T+6h), después (T+6h+).

#### 8.2.1. Pre-drop (T-7d a T-0)

Análisis de riesgo:

- Identificar SKUs con histórico de incidencias de talla > umbral.
- Cruzar con catálogo nuevo: prendas con fit similar a las problemáticas heredan el riesgo.
- Cruzar con velocidad de venta esperada para priorizar las que más volumen van a generar.

Acciones preventivas:

- Reescribir guías de talla en PDP de SKUs de riesgo, con tablas, equivalencias con marcas referencia y "cómo le queda al modelo (altura X, peso Y, lleva talla Z)".
- Añadir guía interactiva: 3 preguntas (altura, peso/contextura, fit preferido) → recomendación de talla.
- FAQ predictivo: preparar respuestas plantilla para las dudas que sabemos que van a llegar.
- Macros del helpdesk listas con el tono de marca.
- Stock de etiquetas de devolución pre-generadas.

Capacity planning:

- Calcular volumen esperado de tickets (histórico × multiplicador de drop).
- Dimensionar agentes IA y humanos en paralelo.
- Acordar criterios de escalado y plantillas de respuesta para casos sensibles.

#### 8.2.2. Durante las primeras 6h

Capa de prevención en sitio:

- Banner sutil de alta demanda en PDP, checkout y post-compra ("Estamos viviendo un momento increíble. Los envíos pueden tardar X horas más de lo habitual.").
- Mensaje contextual en confirmación de pedido: "Si tienes dudas de talla, aquí tienes nuestra guía rápida + nuestro equipo está aquí."
- Modal opcional de selector de talla guiado en SKUs de riesgo.

Capa de soporte automatizada (agentes):

- Agente de tracking: cubre todas las consultas de "dónde está mi pedido". Llama a Shopify y carrier. Responde con plazos realistas.
- Agente de tallas: RAG sobre guías + ficha de producto + comentarios validados. Responde con recomendación + reasegura ("si no es exacta, el cambio es gratis con esta etiqueta").
- Agente de cambios estándar: gestiona devolución/cambio si el motivo es talla, ventana válida y SKU no excepcional. Genera etiqueta y crea registro.
- Agente de FAQs varias: stock, envíos a otros países, fechas estimadas.

Reglas de escalado obligatorias:

- Producto dañado o incorrecto.
- Cliente VIP.
- Sentimiento muy negativo o palabras de reclamación.
- Mención pública en redes.
- Pedido de alto valor.
- Excepción no contemplada.

Panel en tiempo real (operativo):

- Volumen de tickets por intent y por canal.
- Tasa de deflection en vivo.
- Latencia media.
- Top motivos del momento.
- Alertas: si la tasa de devolución por talla en SKU X supera Y%, equipo de producto recibe ping para revisar PDP.

#### 8.2.3. Después de las 6h (cierre del pico)

- Resumen automático del pico: volumen, top intents, SKUs con más fricción, categorías de tallas más afectadas.
- Lista priorizada de mejoras a aplicar antes del próximo drop.
- Actualización de guías de talla y FAQs con lo aprendido.

#### 8.2.4. Stack concreto para este caso

- Shopify (catálogo, pedidos, tags VIP).
- Helpdesk: Gorgias (mejor para Shopify) o Zendesk.
- Live chat: Tidio, Intercom o un widget propio.
- LLM: GPT-4.1/4o-mini para clasificación, GPT-4.1 o Claude Sonnet para redacción.
- Vector DB: pgvector con FAQs, políticas y guías.
- Backend: FastAPI con LangGraph para orquestar el agente principal.
- Carrier: API Sendcloud o equivalente.
- Observabilidad: LangSmith + un dashboard en Metabase/Grafana.
- Notificaciones internas: Slack.

#### 8.2.5. Cómo se vería el agente principal en código

```python
# Esquema simplificado con LangGraph
graph = StateGraph(SupportState)

graph.add_node("classify", classify_intent_and_risk)
graph.add_node("rag_policy", retrieve_policies_and_size_guide)
graph.add_node("call_tools", call_shopify_or_carrier)
graph.add_node("draft", draft_reply_with_brand_voice)
graph.add_node("validate", validate_tone_and_facts)
graph.add_node("escalate", escalate_to_human)
graph.add_node("send", send_reply_and_log)

graph.set_entry_point("classify")
graph.add_conditional_edges("classify", needs_escalation,
    {True: "escalate", False: "rag_policy"})
graph.add_edge("rag_policy", "call_tools")
graph.add_edge("call_tools", "draft")
graph.add_edge("draft", "validate")
graph.add_conditional_edges("validate", is_valid,
    {True: "send", False: "escalate"})
```

#### 8.2.6. Métricas del caso

- Tickets gestionados por hora (vs día normal).
- % deflection automático.
- Tiempo medio de primera respuesta y de resolución.
- % devoluciones por talla por SKU.
- CSAT del pico.
- Incidencias escaladas correctamente vs incidencias que se escaparon.

### 8.3. Cómo defenderlo en la entrevista

Frases:

- "Un pico no se gestiona contratando. Se gestiona previniendo, automatizando lo repetitivo y escalando bien lo crítico."
- "Las primeras 6 horas se ganan en los 7 días previos: guías de talla, FAQs, plantillas, agentes preparados, dashboards."
- "El sistema no solo absorbe volumen; deja datos que mejoran el siguiente drop."

---

## 9. Caso 2 — 3.000 menciones de influencers, ventas por región, presupuesto limitado

### 9.1. Resumen de tu respuesta

No buscar al más grande, sino al de impacto real y encaje de marca. Capa 1: engagement real (comentarios, consistencia, alcance/interacción, audiencia inflada). Capa 2: brand fit (estética, tono, comunidad, sentido comercial por región). Output: ranking accionable (alto impacto + alto fit / alto fit pero menor alcance / buen alcance pero poco fit / descartados) con recomendaciones de acción (contactar, mandar muestra, no invertir).

### 9.2. Cómo se llevaría a cabo realmente

#### 9.2.1. Pipeline end-to-end

```text
[ Fuentes ]
- Lista de 3.000 menciones (handle, post, fecha, métricas básicas)
- Datos de ventas por región (Shopify por country)
- Datos de campañas previas (si los hay)

       ↓ enriquecimiento
[ Ingesta y enrichment por handle ]
- Meta/Instagram Graph API o IG Business para datos públicos
- Scraping legal de bio, posts recientes, hashtags
- Servicios opcionales: Modash, HypeAuditor, Heepsy, CreatorIQ (datos de calidad de audiencia)
       ↓
[ Capa 1 — Engagement real ]
- ER = (likes + comments) / followers
- ER ponderado por consistencia (varianza de ER en últimos N posts)
- Ratio comentarios/likes (los comentarios son señal más fuerte)
- Reach orgánico estimado / followers
- Detección de audiencia inflada:
   * % seguidores con cero posts
   * % comentarios genéricos ("nice", "🔥")
   * Patrón temporal de crecimiento (saltos sospechosos)
   * Geografía de la audiencia vs perfil
       ↓
[ Capa 2 — Brand fit ]
- Embeddings de bio, captions y comentarios → similitud con embeddings de la marca (manifesto, productos, campañas)
- Clasificador multi-etiqueta de estética (streetwear, y2k, gorpcore, minimal, etc.)
- Análisis de tono (formal/informal, irónico, agresivo, etc.)
- Coherencia visual: clip-embeddings de imágenes/video vs moodboard de marca (si se usa multimodal)
       ↓
[ Capa 3 — Encaje comercial por región ]
- Ventas Scuffers por país en últimos 12m
- Audiencia del influencer por país (Modash/HypeAuditor)
- Ratio audiencia_pais / venta_pais → potencial de activación
       ↓
[ Scoring final ]
score = w1*engagement_real + w2*brand_fit + w3*encaje_comercial
       ↓
[ Clasificación en 4 cuadrantes ]
A) alto impacto + alto encaje → contactar ya, prioridad seeding/colab
B) alto fit, menor alcance → mandar muestras, micro-influencer (mejor ROI)
C) buen alcance, poco fit → no invertir, valorar UGC orgánico
D) descartados (audiencia inflada, fit bajo, riesgo)
       ↓
[ Output ]
- Ranking exportable (Sheets/Notion/Airtable)
- Plan por región y por presupuesto
- Plantillas de outreach personalizadas por LLM
- Scoring explicable (por qué este influencer está aquí)
```

#### 9.2.2. Datos y herramientas concretas

- Datos públicos: Meta Graph API, scraping respetuoso para datos no sensibles.
- Datos de calidad de audiencia: Modash o HypeAuditor (APIs comerciales, baratos para 3.000 perfiles).
- LLM: GPT-4.1 o Claude Sonnet para análisis cualitativo.
- Embeddings: text-embedding-3-large (texto), CLIP/SigLIP (imagen) si vas multimodal.
- Vector DB: pgvector.
- Orquestador: Prefect o Airflow para corrida batch.
- Output: dashboard en Streamlit o Retool, export a Sheets/Notion.

#### 9.2.3. Detección de audiencia inflada (lo que diferencia un análisis serio)

Reglas:

- % seguidores sin foto de perfil > 30%.
- % seguidores sin posts > 50%.
- Comentarios con texto único (set de comentarios distintos / total) < 0.4.
- Crecimiento mensual con saltos > 3σ.
- País dominante de audiencia incoherente con idioma del contenido.

Esto se calcula con datos de Modash/HypeAuditor o se estima con muestras.

#### 9.2.4. Brand fit (cómo se hace bien)

- Construir una "ficha de marca" con: manifesto, descripciones de campañas, copys aprobados, palabras OK y palabras NO, estética visual.
- Generar embeddings de ese conjunto y un centroide "marca".
- Para cada influencer, generar embeddings de su contenido reciente y calcular similitud con el centroide.
- Complementar con un LLM que dé un veredicto cualitativo en 3 frases con ejemplos.

#### 9.2.5. Output accionable de verdad

Una tabla por influencer con:

- Cuadrante (A/B/C/D).
- Score total y desglose.
- Acción recomendada: contactar para colaboración, enviar muestra, observar, descartar.
- Plantilla de mensaje generada por LLM, personalizada con detalles de su contenido reciente.
- Notas de cuidado: temas controvertidos, colaboraciones con competidores, etc.

#### 9.2.6. Presupuesto limitado: cómo asignarlo

- Reservar 60-70% para cuadrante A (los seguros).
- 20-30% para cuadrante B (micro con alta afinidad, buen ROI).
- 10% experimentación.
- Por región, ponderar por potencial comercial real, no solo por audiencia.

#### 9.2.7. MVP defendible en 2-3h

- Cargar 3.000 menciones simuladas (CSV).
- Calcular engagement básico con datos disponibles.
- Generar embeddings de captions y comparar con marca.
- Mostrar ranking en Streamlit, con filtros por región y por cuadrante.
- Generar mensajes de outreach con LLM para los 20 primeros.
- Explicar los siguientes pasos (datos de audiencia con Modash, etc.).

### 9.3. Cómo defenderlo en la entrevista

Frases:

- "Followers no es influencia. Influencia es engagement real con audiencia auténtica que comparte el mundo de la marca."
- "El brand fit no es subjetivo si lo defines bien: embeddings de marca, embeddings del creador, distancia. Y sobre eso, criterio humano."
- "Con presupuesto limitado, los micro-influencers con alto fit suelen tener mejor ROI que los grandes con fit medio. El sistema lo demuestra con datos."

---

## 10. Síntesis estratégica para el hackathon

### 10.1. La idea más fuerte que combina todas tus respuestas

"Scuffers AI Operating Layer": una capa operativa que combina conocimiento interno (RAG), señales externas (crawling) y agentes con herramientas para tres flujos:

- Soporte aumentado (preguntas 2, 3, caso 1).
- Inteligencia comercial y planificación (pregunta 5, caso 2).
- Co-piloto de marca/comunidad (pregunta 6).

Este framing te permite posicionarte por encima de la mayoría: no presentas un chatbot, presentas una arquitectura.

### 10.2. Demo que se puede construir en 2h

Lo más realista y defendible:

1. RAG con 15-25 documentos (FAQs, política devoluciones, guía de tallas, manifesto de marca).
2. 5-10 productos simulados con tallas y stock.
3. Agente con 4 herramientas: `consultar_pedido`, `consultar_stock`, `recomendar_talla`, `crear_ticket`.
4. Output estructurado (JSON) con respuesta, fuentes, confianza, acciones, motivo de escalado si lo hay.
5. Interfaz: Streamlit con dos pestañas (Atención al cliente / Tendencias y stock).
6. Pestaña tendencias: dataset pequeño de comentarios → clusters → top 3 oportunidades + memo IA.

Lo presentas con dos casos:

- Caso A: cliente pregunta por devolución de hace 20 días → el sistema responde con tono Scuffers, cita política, propone etiqueta y resumen interno.
- Caso B: equipo pregunta "tenemos muchos comentarios sobre talla en cargo" → el sistema agrega señales y propone 3 acciones (PDP, FAQ, respuesta estándar).

### 10.3. Mensajes que fijan la sensación de senior

- "RAG para conocimiento, SQL para métricas, agentes para acciones."
- "Datos primero, IA después. Una IA buena sobre datos malos sigue siendo mala."
- "El humano en el loop no es lentitud, es control de calidad asimétrico."
- "Empezar con bajo riesgo, alto volumen y trazabilidad total."
- "Lo que diferencia una demo de un sistema productivo es la evaluación, los logs y el coste por interacción."
- "Mejor un sistema explicable y mediocre que un modelo opaco brillante. Lo segundo se cae a la primera pregunta."

### 10.4. Errores que tienes que evitar el día del reto

- Usar buzzwords sin explicar valor.
- Calcular métricas críticas dentro del LLM.
- Presentar como producto cerrado lo que es un MVP.
- Prometer 100% de automatización.
- Diseñar sin pensar en el equipo que va a usarlo.
- Olvidarte de seguridad, privacidad y GDPR.
- No mostrar qué pasa cuando el sistema NO sabe.

### 10.5. Cierre

"Mi propuesta no es una demo más de IA. Es una capa operativa que conecta datos, agentes, herramientas y procesos, con métricas de negocio y control humano donde toca. Empieza pequeña y escala, y desde el día 1 está pensada para que el equipo de Scuffers la adopte sin perder identidad ni criterio."
