---
description: Consigue el subtitulo original (ingles) de cada video de una carpeta, verificado contra el audio
---

Conseguir los subtitulos originales de esta carpeta: $ARGUMENTS

1. Ejecuta `subtrad conseguir "<carpeta>" --serie "<titulo de la serie>"`
   (si `subtrad` no esta en el PATH: `.venv/Scripts/python -m subtrad` en Windows o `.venv/bin/python -m subtrad`).
   Junta las pistas del video, el archivo que ya este al lado y, si ninguno corresponde al audio, descargas de OpenSubtitles.
2. Informa el resultado por capitulo. Si alguno queda `SIN SUBS`, explica por que (no hay en OpenSubtitles, se agoto el limite diario, falta configurar alass o la API key: ver README, seccion Configuracion).

Nunca confies en una pista solo porque viene en el video: puede ser de otro contenido.
