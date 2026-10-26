---
description: Traduce los subtitulos de una carpeta de videos de punta a punta (conseguir, perfil, traducir, corregir, revisar)
---

Traducir los subtitulos de esta carpeta: $ARGUMENTS

Segui el flujo completo descripto en `.claude/skills/traducir-serie/SKILL.md` (es el mismo para Claude Code y OpenCode).
Leelo antes de empezar. Las unicas diferencias en OpenCode:

- La raiz del repo es el directorio de trabajo actual. La CLI es `subtrad`, o `.venv/Scripts/python -m subtrad` (Windows) / `.venv/bin/python -m subtrad`.
- En el paso 5 (traducir), en vez de la herramienta Agent con Haiku, usa el subagente `@traductor-subtitulos`
  (con la herramienta task), uno por capitulo, pasandole este mensaje:
  "Lee el archivo <ruta de INSTRUCCIONES.txt> y segui exactamente esas instrucciones."
  Lanza varios a la vez si el modelo lo permite; si no, uno por uno.
- Para preguntarle algo al usuario (serie ambigua, reglas de un perfil nuevo), preguntale directamente y espera la respuesta.
- Alternativa sin subagentes: `subtrad traducir <carpeta> --perfil <perfil>` traduce todo por API (ver README, motor API).
