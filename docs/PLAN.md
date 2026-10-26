# Plan: traductor de subtitulos con IA

Repo nuevo para traducir subtitulos de series y peliculas de una biblioteca (Plex) con agentes de IA, respetando nombres y glosarios de cada serie.
Nace de lo armado sobre el clon de `llm-subtrans`, del que no se usa el codigo.

---

## 0. Flujo principal: "aca estan los videos"

El usuario solo indica la carpeta (y opcionalmente idioma y reglas).
Todo lo demas lo hace el agente, preguntando solo cuando hace falta:

```
/traducir-serie "<carpeta de la temporada>"
```

1. **Identificar la serie** por la carpeta y los archivos. Si es ambigua (ej. Kingdom anime vs. Kingdom de Netflix), preguntar.
2. **Cargar el perfil** de la serie (`series/<serie>.yaml`).
   Si no existe, crearlo: preguntar idioma y reglas (o usar las por defecto) y proponer la lista de nombres que no se traducen.
3. **Conseguir el ingles** de cada capitulo: pista dentro del video, archivo al lado o descarga + sincronizacion.
4. **Revisar lo que ya esta traducido** (capitulos que ya tienen `.es`, hechos por nosotros o conseguidos de otro lado). No se saltean a ciegas:
   - se les pasan los mismos controles de calidad (seccion 7): sincronizacion con el ingles o con el audio, lineas sin traducir, etiquetas coladas, voseo, nombres segun el perfil;
   - si pasan, solo se les aplica el postproceso del perfil (nombres, unidades) y se dejan;
   - si fallan, se corrige lo puntual (como el bloque en ingles de Kingdom S2E05) o se propone retraducir el capitulo entero, preguntando antes de pisar el archivo y guardando una copia del original.
5. **Traducir** cada capitulo con el motor elegido (Claude Code, OpenCode o API), en paralelo.
6. **Postproceso** del perfil: nombres, unidades, carteles.
7. **Controles de calidad** (seccion 7) y correccion automatica de lo que se pueda.
8. **Reporte final**: capitulos listos, problemas encontrados, nombres dudosos para agregar al perfil.

El resultado queda al lado de cada video (`episodio.es.ass`) para que Plex lo tome solo.
Los pasos 1-8 tambien existen como comandos sueltos para usarlos por separado.

---

## 1. Decision: repo nuevo, no subir el clon

- `llm-subtrans` (MIT, de machinewrapped) es otro proyecto: GUI, proveedores por API key, miles de archivos.
  De eso no usamos nada: la traduccion la hacen agentes y el resto son scripts propios.
- Se arma un repo nuevo desde cero con lo nuestro. El clon queda local y despues se puede borrar.
- Si en algun momento se copia codigo de `llm-subtrans`, mantener su licencia MIT y dar credito.

## 2. Que se lleva del trabajo actual

| Archivo actual | Que hace | En el repo nuevo |
|---|---|---|
| `.claude/skills/traducir-subtitulos/subtitulos.py` | `listar`, `extraer` (partes `[id] texto`), `insertar` (valida ids y tags) | Nucleo, comandos `preparar` / `insertar` |
| `.claude/skills/extraer-subtitulos/extraer.py` | Saca la pista de subs del mkv con ffmpeg | Nucleo, comando `extraer` |
| `.claude/skills/*/SKILL.md` | Instrucciones para Claude Code | Adaptador de Claude Code |
| `glosarios/kingdom_nombres_japones.py` | Nombres chinos -> japoneses | Pasa a datos: `series/kingdom-2012.yaml` |
| `glosarios/kingdom_unidades.py` | "Hi Shin Force" -> "Unidad Hi Shin" | Regla generica + datos del perfil |
| Scripts sueltos (`alineacion.py`, `revisar.py`) | Controles de calidad | Comando `revisar` |
| Plantilla `INSTRUCCIONES.txt` | Prompt del traductor | `prompts/traductor.md` |

Lo que NO se sube: subtitulos ni videos (derechos de autor), `.env`, rutas personales (la carpeta de la biblioteca) -> van a un `config.local.yaml` ignorado por git.

## 3. Arquitectura propuesta

La idea clave: el formato de trabajo `[id] texto` no depende del modelo.
Cualquier motor (Claude, OpenCode, una API) recibe partes de texto y devuelve partes traducidas.
El nucleo en Python se encarga de todo lo demas.

```
subtrad/                     nucleo (Python, CLI "subtrad")
  identificar.py             que serie es (carpeta, año, TMDB/AniList) -> pregunta si hay dudas
  conseguir.py               pista embebida -> archivo al lado -> descarga de internet
  sincronizar.py             ajusta tiempos de subs descargados al video (ffsubsync / alass)
  preparar.py                extrae texto en partes [id] texto (filtra OP/ED, karaoke, dibujos)
  insertar.py                reinserta y valida (ids, tags {..}, \N)
  postproceso.py             aplica el perfil de la serie (nombres, unidades, titulos)
  revisar.py                 controles de calidad (ver seccion 7)
motores/
  claude-code/               skills /traducir-subtitulos y /extraer-subtitulos (subagentes Haiku)
  opencode/                  comandos y agentes equivalentes para OpenCode
  api/                       traduccion directa por API compatible con OpenAI
series/
  kingdom-2012.yaml          perfil de Kingdom (anime)
prompts/
  traductor.md               plantilla del prompt (reglas fijas + reglas del perfil)
```

### Motores de traduccion intercambiables

| Motor | Como funciona | Costo |
|---|---|---|
| Claude Code | Skill que lanza un subagente por capitulo (`model: haiku`) | Suscripcion de Claude, sin API key |
| OpenCode | Mismo flujo con comandos/agentes de OpenCode; permite elegir modelo (Claude, GPT, Gemini, locales) | Segun el modelo elegido |
| API (OpenAI y compatibles) | El nucleo llama directo a la API por parte. Sirve para OpenAI, OpenRouter, DeepSeek, Ollama local, etc. | Por token, necesita API key en `.env` |

Las reglas (prompt, glosario, validaciones) son las mismas para los tres.
Solo cambia quien traduce cada parte.

## 4. Perfiles de serie (YAML)

Todo lo especifico de una serie pasa de codigo Python a datos.
El formato es generico: cada serie tiene su archivo en `series/`.
Kingdom se usa como ejemplo en todo este plan porque es donde se aprendio todo, y `series/kingdom-2012.yaml` viene en el repo como perfil de ejemplo completo.

```yaml
serie: Kingdom
año: 2012
tipo: anime                  # anime | live-action | pelicula
ids: { tmdb: 46004, anilist: 13671 }   # verificar
idioma_destino: Latin American Spanish
codigo: es
prompt: >
  Translate to natural Latin American Spanish.
  Keep character, military unit, city, and state names unchanged.
tratamiento: tuteo           # nunca voseo
nombres_fijos: [Shin, Ei Sei, Karyo Ten, Kyou Kai, Ouki, Duke Hyou, Riboku, ...]
lectura: japonesa            # los subs en ingles a veces vienen en chino
mapear:                      # chino -> japones, se aplica de mas largo a mas corto
  He Liao Diao: Karyo Ten
  Lü Buwei: Ryofui
  Xin: Shin
  ...
ambiguos:                    # nunca se mapean globalmente
  Xiang: { temporada 1: Kyou Shou, temporadas 2-4: Kou }
  Qing: { temporada 5: Kei }  # solo el estandarte de Keisha
unidades:
  regla: "se conserva el nombre propio y se traduce la palabra generica"
  ejemplos: { Hi Shin Force: Unidad Hi Shin, "Wang Jian's Army": el ejército de Ousen }
```

## 5. Identificar la serie (y preguntar si hay dudas)

Problema: "Kingdom" puede ser el anime (2012), la serie coreana de zombies de Netflix (2019) o las peliculas live action japonesas.
Cada una tiene otros nombres y otro glosario.

1. Leer nombre de carpeta y archivos: `Kingdom (2012)`, `[HGS-Renc]`, `S3E01`.
2. Buscar candidatos en TMDB (series/peliculas) y AniList (anime).
3. Si hay un unico candidato claro (titulo + año + tipo), usarlo.
4. Si hay mas de uno o falta el año: **preguntar al usuario** mostrando los candidatos (titulo, año, tipo, sinopsis corta).
5. Guardar la eleccion en el perfil, asi no vuelve a preguntar.

## 6. Conseguir subtitulos en ingles si el video no los trae

Orden de busqueda:
1. Pista de texto embebida en el video (lo que hace hoy `/extraer-subtitulos`).
2. Archivo `.en.ass` / `.en.srt` al lado del video.
3. Descarga de internet:
   - **OpenSubtitles** (API oficial, cuenta gratis con limite diario). Busca por hash del video, que da el subtitulo exacto del release.
   - **Subdl** (API, alternativa).
   - Para anime: **Animetosho** (publica los subs de los releases de anime) y **Jimaku**.
4. Elegir el candidato que coincida con el release (grupo, resolucion, duracion).
5. **Sincronizar siempre** lo descargado con el audio del video (`ffsubsync` o `alass`), porque otro release suele tener tiempos distintos.
6. Validar: duracion parecida, sin huecos raros, idioma correcto.
7. Si la pista embebida es imagen (PGS/VobSub), avisar: hace falta OCR o descargar una de texto.

Respetar los terminos de cada sitio y no subir los subtitulos descargados al repo.

## 7. Controles de calidad (lecciones aprendidas)

Todo esto aparecio revisando las temporadas 1 a 6 de Kingdom y tiene que quedar automatizado:

- [ ] **Alineacion**: cada linea traducida debe corresponder a su original. Detectar corrimientos comparando largos (paso en S6E02: dos frases unidas corrieron 9 lineas).
- [ ] **Ids y tags**: mismos `[id]`, mismas `{\i1}...{\i0}` y tags de posicion (Haiku los pierde seguido; el script lo frena).
- [ ] **Etiquetas filtradas**: buscar `Original\N`, `Translation\N`, `Original:` en el texto (S2 tenia 150 lineas asi, hecha con llm-subtrans).
- [ ] **Bloques sin traducir**: lineas identicas al ingles (S2E05 tenia 61 seguidas).
- [ ] **Voseo** si el destino es español latino neutro (S3 tuvo 4 capitulos con voseo).
- [ ] **Nombres**: contar cada nombre del glosario en original y traduccion; si faltan, buscar como se tradujeron ("duque Hyou").
- [ ] **Reemplazos seguros**:
  - solo sobre el campo Text, nunca estilo ni actor (un estilo "Quanrong Language" se habria roto);
  - de mayor a menor largo ("He Liao Diao" quedo como "He Liao Ten" 489 veces por hacerlo al reves);
  - aceptar el inicio de palabra despues de `\N` (`\b` falla ahi);
  - incluir version en MAYUSCULAS para carteles ("HANDAN" -> "KANTAN");
  - nombres ambiguos solo por temporada, nunca globales.
- [ ] **Titulos en pantalla** sin traducir (estilo/actor "Title").
- [ ] **OP/ED**: no traducir karaoke ni estilos de canciones salvo que se pida.
- [ ] **Caracteres raros** (cirilico u otros alfabetos que se cuelan).
- [ ] **Backup** antes de cada postproceso y reporte final por capitulo.
- [x] **Pista equivocada**: una pista que viene dentro del video puede ser de OTRO contenido (World Is Dancing: 6 de 9 capitulos con subs traian pistas de otro anime). Toda pista, archivo o descarga se verifica contra el audio con alass: si el corrimiento no es parejo, se descarta.
- [x] **Sincronizacion por audio**: ffsubsync fallo con este anime (musica de fondo); alass funciono. Para alass se extrae el audio a WAV (con ffprobe nuevo no puede leer algunos mkv).

## 8. Pasos para armar el repo nuevo

1. [x] Crear el repo vacio en GitHub (nombre a definir) con `README`, `LICENSE` (MIT), `.gitignore`.
2. [x] Pasar los scripts actuales a un paquete Python `subtrad` con CLI y dependencias declaradas (`pysubs2`, `regex`, `charset-normalizer`, `pyyaml`).
3. [x] Convertir los glosarios de Kingdom a `series/kingdom-2012.yaml` y hacer `postproceso.py` generico.
4. [x] Pasar los controles de calidad (seccion 7) a `subtrad revisar` con tests unitarios usando subtitulos de ejemplo inventados.
5. [x] Adaptador Claude Code: skills que llaman a la CLI (sin rutas fijas `D:\...`).
6. [ ] Adaptador OpenCode: comandos y agentes equivalentes.
7. [ ] Motor por API compatible con OpenAI (API key en `.env`).
8. [ ] `identificar.py` con TMDB/AniList y pregunta al usuario si hay dudas.
9. [~] `conseguir.py` + `sincronizar.py`: hecho con OpenSubtitles + alass (verifica pistas, archivos y descargas contra el audio). Falta: Subdl/Animetosho como fuentes extra.
10. [ ] Documentar en el README: instalacion, flujo completo y como crear el perfil de una serie nueva.
11. [ ] Borrar el clon de `llm-subtrans` cuando todo funcione en el repo nuevo.

## 9. Preguntas abiertas

- Nombre del repo.
- ¿Prioridad de motores? (sugerencia: Claude Code primero, despues API, despues OpenCode)
- ¿Cuenta de OpenSubtitles para la API? (gratis, hace falta registrarse)
- ¿Publico o privado?
- Personajes de Kingdom que quedaron en lectura china (S5: Ji Chang, Wu Yi, Jiao Yun...; S6: Nanci, Kuang, Ba Jio...) para completar el perfil.
