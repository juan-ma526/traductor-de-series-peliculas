# Traductor de series y peliculas

Traduce subtitulos de series y peliculas con IA, respetando los nombres y el glosario de cada serie.
Pensado para bibliotecas de Plex: deja el subtitulo traducido al lado del video (`episodio.es.ass`) para que Plex lo detecte solo.

> Estado: en construccion. El plan completo esta en [docs/PLAN.md](docs/PLAN.md).

## Que hace

- Saca los subtitulos en ingles que vienen dentro del video (mkv/mp4).
- Traduce solo el texto: tiempos, estilos y posiciones quedan intactos.
- Respeta un perfil por serie: nombres que no se traducen, lectura de los nombres, tratamiento (tu/usted), unidades militares, etc.
- Controla la calidad: lineas corridas, tags perdidos, partes sin traducir, nombres mal traducidos.
- Funciona con distintos motores de IA: Claude Code, OpenCode o una API compatible con OpenAI.

## Requisitos

- Python 3.10+
- ffmpeg y ffprobe en el PATH (en Windows: `winget install Gyan.FFmpeg`)

## Instalacion

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Windows
.venv/bin/python -m pip install -e ".[dev]"         # Linux/Mac
```

## Uso (comandos sueltos)

```bash
subtrad extraer "<carpeta>"                       # saca los subs en ingles de los videos (.en.ass)
subtrad pendientes "<carpeta>"                    # que falta traducir y que ya esta traducido
subtrad preparar ep.en.ass trabajo/ --perfil series/kingdom-2012.yaml
#   -> trabajo/001.txt, 002.txt... + INSTRUCCIONES.txt para el agente traductor
subtrad insertar ep.en.ass trabajo/ ep.es.ass     # reinserta y valida la traduccion
subtrad postproceso "<carpeta>" --perfil series/kingdom-2012.yaml   # nombres, unidades
subtrad revisar "<carpeta>" --perfil series/kingdom-2012.yaml       # controles de calidad
```

El flujo completo de punta a punta (`/traducir-serie "<carpeta>"`) se arma sobre estos comandos; ver [docs/PLAN.md](docs/PLAN.md).

## Perfiles de serie

Cada serie tiene un archivo YAML en `series/` con el idioma, las reglas del traductor y el glosario.
[`series/kingdom-2012.yaml`](series/kingdom-2012.yaml) es el ejemplo completo: nombres que no se traducen, nombres chinos que pasan a su lectura japonesa, nombres ambiguos por temporada y unidades militares.

## Tests

```bash
.venv/Scripts/python -m pytest
```

## Licencia

MIT. Ver [LICENSE](LICENSE).
