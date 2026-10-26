# Guia para agentes

Instrucciones para agentes de IA (Claude Code, OpenCode, etc.) que trabajan en este repo.

## Que es
Traductor de subtitulos de series y peliculas con IA.
El nucleo es el paquete Python `subtrad` (CLI); los agentes traducen las partes de texto y usan la CLI para todo lo demas.
El plan y las decisiones estan en `docs/PLAN.md`.

## Estructura
- `subtrad/` nucleo: archivos, video (ffmpeg), partes (preparar/insertar), postproceso, revisar, nombres, cli.
- `subtrad/plantillas/traductor.md` prompt del agente traductor.
- `series/*.yaml` perfiles de serie (glosario, reglas). `kingdom-2012.yaml` es el ejemplo completo.
- `.claude/skills/` skills de Claude Code (`/traducir-serie`, `/extraer-subtitulos`).
- `tests/` tests con subtitulos inventados que se generan en cada test.

## Comandos
- Entorno: `python -m venv .venv` y `.venv/Scripts/python -m pip install -e ".[dev]"` (Linux/Mac: `.venv/bin/python`).
- Tests: `.venv/Scripts/python -m pytest`. Correrlos antes de terminar cualquier cambio de codigo.
- CLI: `subtrad --help`.

## Reglas
- Nunca subir subtitulos, videos, `.env` ni rutas personales (la carpeta de la biblioteca del usuario). El `.gitignore` los cubre; no forzarlo.
- Cada error real encontrado traduciendo se convierte en un control de `revisar` y en un test.
- Los reemplazos sobre subtitulos tocan solo el texto (en ASS, el campo Text), van de mayor a menor largo y aceptan nombres pegados a `\N`.
- Lo especifico de una serie va en su perfil YAML, no en el codigo.
- Codigo: Python 3.10+, type hints, funciones y variables en español y snake_case, comentarios que expliquen el por que.
- Mensajes en consola sin caracteres especiales de Unicode (rompen la consola de Windows).
- No pushear sin el OK del usuario.
