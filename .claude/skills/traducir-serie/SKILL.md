---
name: traducir-serie
description: Traduce los subtitulos de una carpeta de videos (temporada o pelicula) de punta a punta - identifica la serie, carga o crea su perfil, extrae el ingles, revisa lo ya traducido, traduce con subagentes, corrige nombres y controla la calidad. Usar cuando el usuario indique una carpeta de videos o subtitulos para traducir.
argument-hint: <carpeta> [perfil] [idioma] ["reglas"]
---

# Traducir una serie de punta a punta

El usuario indica una carpeta. Vos hacés todo lo demás y preguntás solo cuando hace falta.

## Herramienta

Todo lo mecánico lo hace la CLI `subtrad` del repo.
La raíz del repo está tres niveles arriba de la carpeta de este skill.
Si `subtrad` no está en el PATH, usar el Python del entorno del repo:
- Windows: `<repo>/.venv/Scripts/python -m subtrad ...`
- Linux/Mac: `<repo>/.venv/bin/python -m subtrad ...`

Comandos: `extraer`, `pendientes`, `nombres`, `preparar`, `insertar`, `limpiar`, `postproceso`, `revisar` (ver `subtrad --help`).

## Pasos

### 1. Identificar la serie
- Mirar el nombre de la carpeta, de la carpeta padre y de los archivos: título, año, `S3E01`, grupo del release.
- Buscar un perfil que coincida en `<repo>/series/*.yaml` (claves `serie`, `año`, `tipo`).
- Si hay una sola coincidencia clara, usarla.
- Si el título es ambiguo o falta el año, PREGUNTAR al usuario mostrando las opciones posibles.
  Ejemplo: "Kingdom" puede ser el anime (2012), la serie coreana de Netflix (2019) o las películas live action japonesas.

### 2. Cargar o crear el perfil
Si no existe perfil para la serie, crear `<repo>/series/<serie>-<año>.yaml` (formato de `kingdom-2012.yaml`):
- Preguntar idioma destino y reglas, o usar las del argumento.
  Por defecto: `Latin American Spanish`, tuteo, nombres de personajes/unidades/lugares sin traducir.
- Correr `subtrad nombres <carpeta>` sobre los originales y proponer al usuario la lista de `nombres_fijos`.
- Si los nombres vienen en una lectura distinta a la que conoce el usuario (ej. chino vs. japonés en anime), preguntar cuál quiere y armar `mapear`.

### 3. Conseguir el original en inglés
- `subtrad conseguir <carpeta> --serie "<titulo para buscar>"`.
  Junta candidatos (archivo al lado, pistas del video y, si ninguno sirve, descargas de OpenSubtitles) y verifica cada uno contra el audio con alass.
  Deja al lado de cada video el que corresponde (`<video>.en.<ext>`); si estaba corrido parejo, ya corregido; si es SDH, sin acotaciones.
- NUNCA confiar en una pista solo porque viene en el video: puede ser de otro contenido (pasó en World Is Dancing).
- Si un capítulo queda `SIN SUBS`, avisar al usuario (puede faltar en OpenSubtitles o haberse agotado el límite diario de descargas).
- Si falta alass o la API key, el comando lo dice: explicarle al usuario cómo configurarlo (README, sección Configuración).

### 4. Revisar lo que ya está traducido
Los capítulos que ya tienen traducción NO se saltean a ciegas (pueden venir de otro lado y estar mal):
- `subtrad revisar <carpeta> --perfil <perfil>`.
- Sin problemas graves: dejarlos; en el paso 6 se les aplica el postproceso.
- Con problemas graves (corrimiento, etiquetas, bloques sin traducir): corregir lo puntual si son pocas líneas, o preguntar si se retraduce el capítulo.
  Antes de pisar un archivo, copiarlo a `<carpeta>/.respaldo/`.

### 5. Traducir los pendientes
- `subtrad preparar <carpeta> --perfil <perfil>` imprime una línea `INSTRUCCIONES\t<ruta>` por capítulo pendiente.
  Para retraducir capítulos ya traducidos agregar `--rehacer` (solo con el OK del usuario).
- Lanzar un subagente por capítulo con la herramienta Agent, `model: "haiku"`, `subagent_type: "general-purpose"`, de a 5 en paralelo:
  > Lee con Read el archivo "<ruta de INSTRUCCIONES.txt>" y segui exactamente esas instrucciones. Son tu tarea completa.
- Cuando cada uno termina, confirmar que existe el `.es` y lanzar el siguiente.
- Al terminar todos: `subtrad limpiar <carpeta>`.

### 6. Postproceso
`subtrad postproceso <carpeta> --perfil <perfil>`: nombres del perfil (de mayor a menor largo, ambiguos por temporada, carteles en mayúsculas) y unidades.

### 7. Control de calidad
`subtrad revisar <carpeta> --perfil <perfil>` y actuar según el tipo:
- `corrimiento`: retraducir solo ese tramo (leer original y traducido, reescribir las líneas con pysubs2) o el capítulo entero.
- `sin_traducir` / `ingles` / `etiquetas`: traducir o limpiar esas líneas.
- `voseo`: pasar a tuteo (un subagente Haiku con la consigna de cambiar solo el voseo).
- `nombres`: si son nombres nuevos, agregarlos al perfil (preguntando la forma correcta si no es obvia) y repetir el paso 6.
- `largo_raro`: mirar la línea; casi siempre es una traducción más corta y está bien.
Repetir hasta que no queden problemas graves.

### 8. Reporte final
Informar al usuario:
- capítulos traducidos, revisados y corregidos;
- problemas que quedaron y por qué;
- nombres dudosos que convendría agregar al perfil (`subtrad nombres <carpeta> --perfil <perfil>`);
- tokens aproximados usados (los informa cada subagente).

## Reglas
- Nunca modificar los videos.
- Nunca borrar ni pisar un subtítulo existente sin copia en `<carpeta>/.respaldo/`.
- Los nombres ambiguos (que cambian según la temporada) nunca se reemplazan en todas partes: van en `ambiguos` del perfil.
- No commitear subtítulos ni rutas personales al repo; solo perfiles y código.
