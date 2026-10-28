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

## Configuracion

Copiar `.env.example` a `.env` (no se sube al repo) y completar:

- `OPENSUBTITLES_API_KEY`: para descargar subtitulos cuando los videos no los traen o vienen mal.
  Se saca gratis en opensubtitles.com -> perfil -> API Consumers.
- `OPENSUBTITLES_USERNAME` / `OPENSUBTITLES_PASSWORD` (opcional): sube el limite de 5 a 20 descargas por dia.
- `SUBDL_API_KEY` (opcional): segunda fuente de descargas (subdl.com, cuenta gratis), para peliculas y series.
  Las fuentes se prueban en orden: OpenSubtitles, Subdl y Gestdown (subtitulos de Addic7ed, solo series, sin clave).
  Si una se queda sin cupo o falla, se sigue con la siguiente.
- `ALASS_PATH`: ruta a `alass-cli` ([github.com/kaegi/alass](https://github.com/kaegi/alass/releases)), que verifica y corrige la sincronia contra el audio.

## Uso con Claude Code (recomendado)

Abrir Claude Code en la carpeta del repo y pedir:

```
/traducir-serie "<carpeta de la temporada o pelicula>"
```

Identifica la serie (pregunta si hay dudas), carga o crea su perfil, extrae el ingles de los videos, revisa lo que ya estaba traducido, traduce los capitulos con subagentes (Haiku, para ahorrar consumo), corrige nombres y unidades, controla la calidad y deja un reporte.
No hace falta API key: usa la suscripcion de Claude.

Para solo sacar los subtitulos de los videos: `/extraer-subtitulos "<carpeta>"`.

## Uso con OpenCode

Abrir OpenCode en la carpeta del repo: los comandos estan en `.opencode/commands/` y el subagente traductor en `.opencode/agents/`.

```
/traducir-serie "<carpeta>"
/extraer-subtitulos "<carpeta>"
```

El flujo es el mismo que en Claude Code; cada capitulo lo traduce el subagente `@traductor-subtitulos`.
Si su modelo falla (no disponible, cupo agotado), se usa `@traductor-subtitulos-respaldo`.

Modelos por defecto (elegidos comparando 15 modelos de OpenCode Go con un capitulo de Ted Lasso contra la traduccion oficial):

| Subagente | Modelo | Por que |
|---|---|---|
| `traductor-subtitulos` | `opencode-go/gpt-6-luna` | Calidad casi a la par de los mejores, el mas rapido y el mas barato |
| `traductor-subtitulos-respaldo` | `opencode-go/deepseek-v4.1-flash` | Buena calidad, rapido y barato |

Para cambiarlo, editar la linea `model:` de `.opencode/agents/traductor-subtitulos.md` (o del respaldo).
Los modelos disponibles se listan con `opencode models`.
Otras opciones que tradujeron bien: `opencode-go/gemini-4-argon` (la mejor calidad, unas 20 veces mas cara) y `opencode-go/glm-5.3-flash` (barato pero lento).

## Uso por API (sin agentes)

Con cualquier API compatible con OpenAI (OpenAI, OpenRouter, DeepSeek, Ollama local...), configurada en `.env`:

```bash
subtrad traducir "<carpeta>" --perfil series/<serie>.yaml [--modelo gpt-4o-mini] [--paralelo 3]
```

Prepara, traduce parte por parte (validando cada respuesta y pidiendole al modelo que corrija si algo falla), inserta, aplica el perfil y revisa.
Al final informa los tokens usados.

## Uso (comandos sueltos)

```bash
subtrad identificar "<carpeta>"                   # que serie es: perfil existente o candidatos (AniList, TVmaze, TMDB)
subtrad identificar "<carpeta>" --crear 1         # crea el perfil base del candidato elegido
subtrad conseguir "<carpeta>" --serie "<titulo>"   # el ingles de cada video: pistas o descarga, verificado contra el audio
subtrad extraer "<carpeta>"                       # saca los subs en ingles de los videos (.en.ass), sin verificar
subtrad pendientes "<carpeta>"                    # que falta traducir y que ya esta traducido
subtrad nombres "<carpeta>" --perfil <perfil>     # nombres propios que el perfil todavia no cubre
subtrad preparar "<carpeta>" --perfil series/kingdom-2012.yaml
#   -> <carpeta>/.traduccion/<capitulo>/001.txt, 002.txt... + INSTRUCCIONES.txt para el agente traductor
subtrad insertar ep.en.ass <trabajo> ep.es.ass    # reinserta y valida la traduccion (lo ejecuta el agente)
subtrad limpiar "<carpeta>"                       # borra las carpetas de trabajo terminadas
subtrad postproceso "<carpeta>" --perfil series/kingdom-2012.yaml   # nombres, unidades
subtrad revisar "<carpeta>" --perfil series/kingdom-2012.yaml       # controles de calidad
```

El skill `/traducir-serie` usa estos mismos comandos; cualquier otro agente (OpenCode, etc.) puede seguir el mismo flujo, descripto en [.claude/skills/traducir-serie/SKILL.md](.claude/skills/traducir-serie/SKILL.md).

## Perfiles de serie

Cada serie tiene un archivo YAML en `series/` con el idioma, las reglas del traductor y el glosario.
[`series/kingdom-2012.yaml`](series/kingdom-2012.yaml) es el ejemplo completo: nombres que no se traducen, nombres chinos que pasan a su lectura japonesa, nombres ambiguos por temporada y unidades militares.

## Tests

```bash
.venv/Scripts/python -m pytest
```

## Licencia

MIT. Ver [LICENSE](LICENSE).
