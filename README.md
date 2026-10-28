# Traductor de series y peliculas

Traduce subtitulos de series y peliculas con IA, respetando los nombres y el glosario de cada serie.
Pensado para bibliotecas de Plex: deja el subtitulo traducido al lado del video (`episodio.es.ass`) para que Plex lo detecte solo.

> Probado con anime (Kingdom, The Eminence in Shadow, Escaflowne, World Is Dancing), una serie (Ted Lasso) y una pelicula (Catch Me If You Can).
> El plan y las decisiones estan en [docs/PLAN.md](docs/PLAN.md).

## Que hace

- Consigue el original en ingles: la pista que viene dentro del video (mkv/mp4), un archivo al lado o una descarga, siempre verificado contra el audio.
  No hace falta que los videos traigan subtitulos.
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

No hace falta API key: usa la suscripcion de Claude, y los capitulos los traducen subagentes Haiku para ahorrar consumo.

### Que pasa cuando le das una carpeta

1. **Identifica la serie o pelicula** por el nombre de la carpeta (si es "Season 1", usa la de arriba) y la busca en AniList, TVmaze y TMDB.
   Si hay varias posibles (ej. "Kingdom": el anime de 2012 o la serie coreana de 2019), te pregunta cual es.
2. **Avisa si los videos ya traen subtitulos en tu idioma** (ej. Ted Lasso trae español latino oficial) y te pregunta si igual queres traducir.
3. **Carga el perfil de la serie** (`series/<serie>.yaml`) o lo crea: te propone los nombres propios que encontro en los subtitulos para que no se traduzcan, y te pregunta las reglas si queres algo especial.
4. **Consigue el ingles de cada capitulo** y lo verifica contra el audio con alass: una pista del video puede ser de otro contenido o estar corrida.
   Si ninguna sirve, descarga de OpenSubtitles, Subdl o Gestdown, en ese orden. Si el subtitulo es para sordos, le saca las acotaciones ("[musica]", "MAN:").
5. **Revisa lo que ya estaba traducido**: no lo pisa a ciegas, le pasa los controles de calidad y solo propone retraducir si esta mal.
6. **Traduce** solo el texto, en partes de 120 lineas, con varios subagentes en paralelo. Las peliculas largas se reparten entre varios.
   Cada parte se valida al reinsertarla (mismas lineas, mismas etiquetas de formato); si algo falla, el subagente lo corrige.
7. **Aplica el perfil**: nombres, lecturas y unidades.
8. **Controla la calidad** (lineas corridas, partes sin traducir, voseo, palabras de España, etiquetas coladas, otros alfabetos) y corrige lo que encuentre.
9. **Te deja un reporte**: capitulos listos, problemas y nombres dudosos para agregar al perfil.

El resultado queda al lado de cada video (`episodio.es.ass` o `.es.srt`) y Plex lo detecta solo.
Los tiempos, estilos y posiciones no se tocan. Si algun archivo se reemplaza, el anterior queda en `<carpeta>/.respaldo/`.

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

Cada serie o pelicula tiene un archivo YAML en `series/` con el idioma, las reglas del traductor y el glosario.
`/traducir-serie` lo crea solo la primera vez (preguntando lo necesario); tambien se puede crear o retocar a mano.

### Crear uno nuevo

1. `subtrad identificar "<carpeta>"` muestra los candidatos; `subtrad identificar "<carpeta>" --crear N` crea `series/<serie>-<año>.yaml` con el elegido.
2. `subtrad nombres "<carpeta>" --perfil series/<serie>-<año>.yaml` lista los nombres propios de los subtitulos que el perfil todavia no cubre.
   Copiar a `nombres_fijos` los que no se deben traducir (personajes, lugares, equipos, empresas).
3. Escribir en `prompt` las reglas propias de la serie, en una o varias lineas.

Ejemplo minimo (una serie de comedia):

```yaml
serie: Ted Lasso
año: 2020
tipo: serie                     # anime, serie o pelicula
idioma_destino: Latin American Spanish
codigo: es                      # sufijo del archivo traducido: episodio.es.srt
tratamiento: tuteo              # tuteo, voseo o usted

prompt: >
  Translate to natural Latin American Spanish.
  It is a comedy: keep the jokes natural and funny in Spanish, not literal.
  "Coach" is "entrenador" (or "Coach" when used as a name: "Coach Beard").

nombres_fijos: [Ted Lasso, Ted, Rebecca, Keeley, Roy Kent, AFC Richmond, Greyhounds]
```

### Campos

| Campo | Para que |
|---|---|
| `serie`, `año`, `tipo`, `ids` | Identificacion (`ids`: anilist, tvmaze, tmdb; los completa `identificar`) |
| `idioma_destino`, `codigo` | Idioma de la traduccion y sufijo del archivo |
| `tratamiento` | `tuteo` (por defecto, y avisa si aparece voseo), `voseo` o `usted` |
| `prompt` | Reglas para el traductor: tono, epoca, cuando usar usted, terminos de la serie |
| `nombres_fijos` | Nombres que nunca se traducen |
| `mapear` | Reemplazos de nombres despues de traducir (ej. lectura china a japonesa: `Xin: Shin`) |
| `mapear_regex` | Igual, con expresiones regulares (ej. "el señor Changwen" -> "Shoubunkun") |
| `ambiguos` | Un mismo nombre que cambia segun la temporada (`Xiang: {'1': Shou, '2-6': Kou}`) |
| `unidades` | Unidades militares: se conserva el nombre y se antepone "Unidad" |
| `reemplazos` | Reemplazos literales al final (ej. `Thousand Man Unit: Unidad de Mil Hombres`) |

Ejemplos completos:

- [`kingdom-2012.yaml`](series/kingdom-2012.yaml): anime con lecturas chinas a japonesas, nombres por temporada y unidades militares.
- [`eminence-in-shadow-2022.yaml`](series/eminence-in-shadow-2022.yaml): anime con muchos nombres y reglas para apodos y letras griegas.
- [`catch-me-if-you-can-2002.yaml`](series/catch-me-if-you-can-2002.yaml): pelicula ambientada en los 60, con reglas de usted/tu y alias.
- [`ted-lasso-2020.yaml`](series/ted-lasso-2020.yaml): comedia, con indicaciones para los chistes.

## Tests

```bash
.venv/Scripts/python -m pytest
```

## Licencia

MIT. Ver [LICENSE](LICENSE).
