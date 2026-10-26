---
name: extraer-subtitulos
description: Extrae la pista de subtitulos (por defecto en ingles) embebida en los videos de una carpeta y la guarda al lado de cada video como .en.ass/.en.srt. Usar cuando el usuario quiera sacar subtitulos de archivos de video sin traducirlos.
argument-hint: <carpeta> [idioma]
---

# Extraer subtitulos de videos

Usa la CLI `subtrad` del repo (la raíz está tres niveles arriba de este skill).
Si no está en el PATH: `<repo>/.venv/Scripts/python -m subtrad` (Windows) o `<repo>/.venv/bin/python -m subtrad`.

1. `subtrad extraer "<carpeta>" --listar` para ver las pistas de cada video.
   Si un video tiene varias pistas del idioma y no es obvio cuál es la de diálogos completos, mostrárselas al usuario.
2. `subtrad extraer "<carpeta>" --idioma <codigo>` (por defecto `en`).
   Omite los que ya existen salvo `--sobrescribir`.
3. Informar el resumen:
   - `NO_EXTRAIBLE`: pista de imagen (PGS/VobSub), necesita OCR o descargar otra.
   - `SIN_PISTA`: el video no trae subtítulos en ese idioma.

Para traducir después, usar `/traducir-serie` sobre la misma carpeta.
