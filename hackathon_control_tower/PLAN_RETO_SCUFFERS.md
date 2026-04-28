# Plan para resolver el reto: Scuffers AI Ops Control Tower

## 1. Qué pide realmente el reto

El reto consiste en construir un sistema inteligente que ayude al equipo de operaciones de Scuffers durante un lanzamiento de alta demanda.

La pregunta central es:

> ¿Qué debería hacer ahora mismo el equipo de operaciones para proteger la experiencia del cliente, evitar problemas logísticos y maximizar el impacto del lanzamiento?

Datos disponibles:

- Varios CSV simulados del lanzamiento.
- Pueden tener ruido, inconsistencias y valores incompletos.
- Campos orientativos: pedidos, cliente, SKU, producto, categoría, talla, país, método de envío, segmento, CLV, historial de compras/devoluciones, VIP, inventario disponible/reservado/entrante, tickets de soporte, sentimiento, urgencia, fuente de campaña, intensidad de campaña, views y conversión última hora.
- Novedad urgente: Shipping Status API para consultar estado real de envío por `order_id`.

Entregable principal:

- Máximo 10 acciones prioritarias.
- Cada acción debería tener:
  - `rank`
  - `action_type`
  - `target_id`
  - `title`
  - `reason`
  - `expected_impact`
  - `confidence`
  - `owner`
  - `automation_possible`

Criterios de evaluación:

- Funcionalidad: carga de datos, procesamiento, salida útil y demo clara.
- Calidad de priorización: identificar lo importante, evitar lo genérico.
- Criterio de negocio: acciones que tengan sentido para Scuffers durante el lanzamiento.
- Uso de IA y automatización: IA/agentes/desarrollo asistido con cabeza.
- Robustez técnica: manejar datos incompletos e inconsistentes.
- Claridad de comunicación: explicar qué hace, por qué y cómo ayuda.

## 2. Estrategia ganadora

No hay que construir “un dashboard bonito” ni “un agente que habla”. Hay que construir un **motor de decisión operativo**.

La solución debe hacer cuatro cosas muy bien:

1. Leer datos imperfectos.
2. Calcular señales de riesgo y oportunidad.
3. Priorizar acciones concretas.
4. Explicar cada acción en lenguaje de negocio.

Frase para defender:

> “No he intentado detectar todos los problemas. He construido un sistema que decide qué 10 cosas debería hacer ahora el equipo, con racional, impacto esperado y dueño operativo.”

## 3. Enfoque recomendado: scoring explicable + enriquecimiento API + resumen IA

Arquitectura:

```text
CSVs del reto
   ↓
Normalización robusta
   ↓
Feature engineering operativo
   ↓
Scoring por riesgo/oportunidad
   ↓
Consulta selectiva a Shipping Status API (solo pedidos relevantes)
   ↓
Re-scoring con estado logístico real
   ↓
Generador de acciones top 10
   ↓
Dashboard / JSON / reporte ejecutivo
```

Por qué este enfoque es fuerte:

- Es rápido de construir en 2h.
- Es explicable y defendible.
- No depende de un modelo opaco.
- Usa la API nueva “en caliente” como pide el reto.
- Permite añadir IA sin que el LLM invente decisiones.

## 4. Señales que debe calcular el sistema

### 4.1. Riesgo de cliente

Sube si:

- `is_vip = true`
- `customer_lifetime_value` alto
- `customer_orders_count` alto
- `support_ticket_sentiment` negativo
- `support_ticket_urgency` alta
- `customer_returns_count` alto, si el problema apunta a talla o producto

Acciones derivadas:

- Priorizar revisión manual.
- Contacto proactivo.
- Asignar a customer care senior.

### 4.2. Riesgo logístico

Sube si:

- La API devuelve `delay_risk` alto.
- `shipping_status` es `delayed`, `exception`, `lost` o `returned_to_sender`.
- `delay_reason` es `address_validation_error`, `warehouse_delay`, `carrier_capacity_issue` o `customs_hold`.
- `requires_manual_review = true`.
- Pedido con valor alto o VIP y riesgo de retraso.

Acciones derivadas:

- Revisar pedido manualmente.
- Contactar cliente antes de que pregunte.
- Priorizar preparación o escalado con carrier.

### 4.3. Riesgo de inventario

Sube si:

- `inventory_available_units - inventory_reserved_units` bajo.
- `campaign_intensity` alto.
- `product_page_views_last_hour` alto.
- `conversion_rate_last_hour` alto.
- `inventory_incoming_eta` lejano.
- Muchos pedidos del mismo SKU/talla.

Acciones derivadas:

- Pausar o reducir campaña sobre SKU con poco stock.
- Mostrar aviso de pocas unidades.
- Priorizar reposición o transferir stock.

### 4.4. Riesgo de soporte

Sube si:

- Ticket abierto.
- Urgencia alta.
- Sentimiento negativo.
- Mensaje menciona talla, retraso, devolución, producto incorrecto o queja.

Acciones derivadas:

- Responder primero tickets críticos.
- Crear macro de respuesta.
- Escalar casos sensibles.

### 4.5. Oportunidad comercial

Sube si:

- Producto con alto tráfico y suficiente stock.
- Campaña fuerte con buena conversión y stock sano.
- Segmento cliente alto, sin riesgo logístico.

Acciones derivadas:

- Mantener o incrementar campaña.
- Empujar producto alternativo con stock.
- Cross-sell/upsell post-compra.

## 5. Tipos de acciones recomendadas

Usar un catálogo cerrado de acciones ayuda a sonar profesional:

- `prioritize_order`: priorizar pedido concreto.
- `manual_review`: revisar manualmente un pedido/caso.
- `proactive_customer_contact`: contactar proactivamente al cliente.
- `pause_campaign`: pausar campaña por riesgo de stock/logística.
- `reduce_campaign_pressure`: bajar intensidad de campaña.
- `increase_campaign_pressure`: aprovechar oportunidad con stock sano.
- `update_pdp_message`: actualizar mensaje en página de producto.
- `stock_transfer`: mover stock entre almacenes/mercados.
- `customer_care_escalation`: escalar ticket a soporte humano.
- `create_support_macro`: crear respuesta estándar para tickets repetidos.
- `carrier_escalation`: escalar con transportista.
- `alternative_product_push`: redirigir demanda a producto alternativo.

## 6. Cómo usar la Shipping Status API sin perder tiempo

No consultar todos los pedidos. Eso puede ser lento y no aporta criterio.

Estrategia:

1. Calcular un score inicial con CSVs.
2. Seleccionar top 20-30 pedidos/casos con más riesgo inicial.
3. Consultar la API solo para esos `order_id`.
4. Enriquecer el score:
   - `delay_risk >= 0.8`: +30 puntos.
   - `delay_risk >= 0.6`: +20 puntos.
   - `shipping_status` en `exception/lost/returned_to_sender`: +40 puntos.
   - `requires_manual_review`: +35 puntos.
5. Explicar en la acción:
   - “Esta acción sube de prioridad tras consultar la API logística: estado X, riesgo Y, motivo Z.”

Frase para jurado:

> “La nueva API no sustituye el análisis inicial; lo enriquece. Primero detecto candidatos de riesgo, luego gasto llamadas API donde realmente cambia la decisión.”

## 7. Tres posibles soluciones

### Opción A — La más segura: CLI + reporte JSON/Markdown

Qué construir:

- Script Python que lee CSVs de una carpeta.
- Normaliza columnas.
- Calcula scores.
- Consulta API para top candidatos.
- Genera `top_actions.json` y `report.md`.

Ventajas:

- Muy rápido.
- Muy robusto.
- Difícil que falle en demo.
- Bueno si el WiFi o Streamlit falla.

Desventaja:

- Menos visual.

### Opción B — La más presentable: Streamlit dashboard

Qué construir:

- Todo lo de la opción A.
- UI con:
  - carga de CSVs,
  - resumen de KPIs,
  - top 10 acciones,
  - filtros por owner/action type,
  - botón “consultar API logística”,
  - export JSON/CSV.

Ventajas:

- Mucho mejor para jurado.
- Se entiende rápido.
- Permite contar historia.

Desventaja:

- Más piezas pueden fallar.

### Opción C — La más “IA”: agente con herramientas

Qué construir:

- Motor de scoring determinista.
- Tool `load_csvs`.
- Tool `score_cases`.
- Tool `get_shipping_status`.
- Tool `generate_actions`.
- LLM solo para redactar rationale ejecutivo y agrupar acciones.

Ventajas:

- Encaja con el rol de IA/agentes.
- Permite hablar de arquitectura avanzada.

Desventaja:

- Puede parecer humo si no hay output funcional.

Recomendación: construir A como base, envolverlo en B si da tiempo, y explicar que C sería la evolución productiva. No hagas depender la demo de un agente.

## 8. Fórmula de scoring inicial

Score total por pedido/caso:

```text
score_total =
  0.25 * customer_risk
+ 0.25 * inventory_risk
+ 0.20 * support_risk
+ 0.20 * logistics_risk
+ 0.10 * commercial_impact
```

Después de la API:

```text
score_total_final =
  score_total
+ shipping_delay_boost
+ manual_review_boost
+ severe_status_boost
```

Confidence:

```text
confidence =
  0.55
+ 0.10 si datos de cliente completos
+ 0.10 si datos de inventario completos
+ 0.10 si ticket tiene sentimiento/urgencia
+ 0.15 si API logística respondió correctamente
```

Capar a 0.95 para no prometer certeza absoluta.

## 9. Qué presentar en 3 minutos

Guion:

1. “El problema no es analizar todo, es decidir qué hacer primero.”
2. “Construí una Control Tower que convierte CSVs imperfectos + API logística en 10 acciones priorizadas.”
3. “Separé cálculo determinista de explicación: SQL/Python calcula, IA explica.”
4. Demo: cargar CSVs → ver top riesgos → consultar API → ver cómo cambia el ranking → exportar JSON.
5. “Cada acción tiene owner, impacto esperado, confianza y si se puede automatizar.”
6. “En producción lo conectaría a Shopify, Gorgias, ERP, carrier y campañas, con trazabilidad y human-in-the-loop.”

Frase final:

> “Esto no pretende sustituir a operaciones; pretende que en las primeras horas de un drop el equipo sepa exactamente dónde mirar y qué decisión tomar primero.”

## 10. Checklist de ejecución en el hackathon

Primeros 10 minutos:

- Abrir CSVs, ver columnas reales.
- Identificar si hay múltiples archivos y relaciones.
- Decidir qué columna es `order_id`, `sku`, `customer_id`.

Minutos 10-40:

- Cargar y normalizar datos.
- Agregar por pedido y por SKU.
- Calcular scores básicos.

Minutos 40-70:

- Generar acciones top 10.
- Añadir razones y owners.
- Export JSON/Markdown.

Minutos 70-90:

- Integrar Shipping Status API para top candidatos.
- Re-score y explicar cambios.

Minutos 90-110:

- UI rápida o reporte bonito.
- Preparar 2 casos para explicar.

Minutos 110-120:

- Ensayar pitch y asegurar que export funciona.

## 11. Qué NO hacer

- No construir un chatbot genérico.
- No usar LLM para calcular riesgos numéricos.
- No intentar predecir demanda con un modelo complejo.
- No consultar la API para todo si no hace falta.
- No sacar 50 recomendaciones. El reto pide máximo 10.
- No olvidar explicar qué cambió al añadir la API.

