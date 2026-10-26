@AGENTS.md

## Notas para Claude Code
- Los skills del repo estan en `.claude/skills/`: `/traducir-serie` (flujo completo) y `/extraer-subtitulos`.
- Para traducir, los subagentes se lanzan con `model: "haiku"` para ahorrar consumo; el agente principal solo coordina y revisa.
