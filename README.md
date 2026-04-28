# Scuffers — Material de preparación

Este directorio contiene los materiales preparados para el hackathon y la futura entrevista del proceso de selección de Scuffers.

## Archivos

- `Propuesta tecnica detallada Scuffers.docx`: propuesta técnica completa explicando, pregunta a pregunta y caso a caso, cómo se llevarían a cabo realmente las soluciones planteadas en las respuestas del proceso anterior. Incluye arquitecturas, herramientas concretas, flujos paso a paso, métricas y frases para defender cada idea.
- `Guia completa IA y automatizacion Scuffers.docx`: manual de referencia con conceptos, herramientas, estándares de la industria, creación de agentes, automatización, RAG, crawling, bases de datos, evaluación, seguridad y estrategia para el hackathon. Sirve como guía para mañana y como base para los primeros 90 días en el rol.
- `hackathon_control_tower/`: carpeta específica para el reto real del hackathon. Incluye el enunciado resumido, plan de resolución, starter Python funcional, datos de ejemplo y guía de pitch/demo.

## Fuente editable

- `propuesta_tecnica_detallada.md`
- `guia_completa_ia_automatizacion.md`

Si quieres modificar contenido y regenerar los `.docx`, edita los `.md` y ejecuta:

```
python generar_docx.py
```

El script no requiere dependencias externas; produce archivos `.docx` válidos con estilos limpios usando solo la librería estándar.

## Cómo aprovechar el material

1. Lee primero la **guía completa** para fijar conceptos y vocabulario.
2. Pasa luego a la **propuesta técnica detallada** y memoriza las "frases para defender" de cada pregunta. Son las que te hacen sonar senior.
3. La noche antes del hackathon, repasa las secciones 8 y 10 de la propuesta (estrategia y demo recomendada).
4. Durante el reto, usa la sección 7 de la guía como cheatsheet de plantillas (system prompt, esqueleto RAG, esqueleto agente).
5. Para el reto real, entra en `hackathon_control_tower/` y usa `PLAN_RETO_SCUFFERS.md`, `PITCH_Y_DEMO.md` y `control_tower.py`.
