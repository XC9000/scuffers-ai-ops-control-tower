# Enunciado resumido del reto

## Reto principal

**Scuffers AI Ops Control Tower**

Construir un sistema inteligente para priorizar decisiones operativas durante un lanzamiento de alta demanda.

Pregunta clave:

> ¿Qué debería hacer ahora mismo el equipo de operaciones de Scuffers para proteger la experiencia del cliente, evitar problemas logísticos y maximizar el impacto del lanzamiento?

## Contexto

Scuffers está preparando el lanzamiento de una colección cápsula con unidades limitadas. Durante las primeras horas se espera:

- volumen elevado de pedidos,
- presión sobre inventario,
- posibles incidencias logísticas,
- aumento de consultas de clientes.

El equipo no puede revisar manualmente todos los pedidos, clientes, productos e incidencias. Necesita identificar qué está ocurriendo, qué riesgos son importantes y qué acciones deberían ejecutarse primero.

## Datos disponibles

CSV simulados del negocio durante un lanzamiento. Pueden contener ruido, inconsistencias o valores incompletos.

Campos orientativos:

- `order_id`
- `customer_id`
- `created_at`
- `order_status`
- `sku`
- `product_name`
- `category`
- `size`
- `quantity`
- `unit_price`
- `order_value`
- `shipping_city`
- `shipping_country`
- `shipping_method`
- `customer_segment`
- `customer_lifetime_value`
- `customer_orders_count`
- `customer_returns_count`
- `is_vip`
- `inventory_available_units`
- `inventory_reserved_units`
- `inventory_incoming_units`
- `inventory_incoming_eta`
- `support_ticket_id`
- `support_ticket_message`
- `support_ticket_urgency`
- `support_ticket_sentiment`
- `campaign_source`
- `campaign_intensity`
- `product_page_views_last_hour`
- `conversion_rate_last_hour`

## Problemas a detectar y priorizar

- Pedidos con alto riesgo operativo.
- Clientes importantes que podrían tener mala experiencia.
- Productos con riesgo de rotura de stock.
- Campañas generando demasiada demanda sobre productos con poco stock.
- Tickets de soporte que deberían atenderse antes.
- Pedidos que deberían revisarse manualmente.
- Acciones comerciales que podrían empeorar logística o inventario.
- Casos donde conviene contactar proactivamente con el cliente.
- Casos donde conviene pausar, limitar o revisar una campaña.
- Casos donde conviene priorizar determinados pedidos frente a otros.

## Entregable

Una lista priorizada de máximo 10 acciones.

Formato ideal:

```json
{
  "rank": 1,
  "action_type": "prioritize_order",
  "target_id": "ORD-10492",
  "title": "Priorizar revisión manual del pedido ORD-10492",
  "reason": "Pedido con riesgo operativo alto: cliente con ticket abierto, bajo stock del SKU y alta presión de campaña en Madrid.",
  "expected_impact": "Reducir riesgo de mala experiencia y evitar incidencia de soporte.",
  "confidence": 0.86,
  "owner": "operations",
  "automation_possible": true
}
```

Restricción:

- Máximo 10 acciones prioritarias.
- No basta con detectar problemas. Hay que decidir qué es más importante y justificar por qué.

## Novedad urgente: Shipping Status API

Scuffers habilita una API logística con estado real de envío por pedido.

Endpoint:

```text
GET https://lkuutmnykcnbfmbpopcu.functions.supabase.co/api/shipping-status/{order_id}
```

Header obligatorio:

```text
X-Candidate-Id: SCF-2026-XXXX
```

Campos devueltos:

- `order_id`
- `shipping_status`
- `estimated_delivery_date`
- `delay_risk`
- `delay_reason`
- `delivery_attempts`
- `requires_manual_review`

Estados posibles:

- `label_created`
- `picked_up`
- `in_transit`
- `at_sorting_center`
- `out_for_delivery`
- `delivered`
- `delayed`
- `exception`
- `lost`
- `returned_to_sender`

Motivos de retraso:

- `high_volume`
- `carrier_capacity_issue`
- `address_validation_error`
- `weather_disruption`
- `warehouse_delay`
- `customs_hold`
- `unknown`

Qué debe cambiar en la solución:

- Consultar la API para los pedidos relevantes, no necesariamente todos.
- Incorporar el estado logístico al modelo de priorización.
- Reordenar o modificar acciones según la nueva información.
- Explicar cómo cambia la decisión gracias a la API.
- Manejar errores, respuestas incompletas o valores inesperados.

## Criterios de evaluación

- Funcionalidad: carga de datos, procesamiento, salida útil y demo clara.
- Calidad de priorización: identifica los casos realmente importantes y evita lo genérico.
- Criterio de negocio: acciones con sentido para Scuffers durante el lanzamiento.
- Uso de IA y automatización: uso inteligente de IA, agentes y desarrollo asistido.
- Robustez técnica: manejo de datos incompletos e inconsistentes.
- Claridad de comunicación: capacidad de explicar qué, por qué y cómo ayuda.

