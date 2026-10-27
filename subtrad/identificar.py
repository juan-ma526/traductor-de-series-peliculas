"""Identifica que serie o pelicula hay en una carpeta, para cargar o crear su perfil.

Fuentes (sin clave): AniList (anime) y TVmaze (series). Opcional: TMDB (series y peliculas) con TMDB_API_KEY.
Si queda una sola identidad clara se usa; si no, el agente le pregunta al usuario mostrando los candidatos.
Ejemplo del problema: "Kingdom" puede ser el anime (2012), la serie coreana de Netflix (2019) o la de 2014.
"""
import json
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import regex
import yaml

from subtrad import config
from subtrad.video import videos as listar_videos

AGENTE = 'subtrad (traductor de subtitulos)'
CARPETA_TEMPORADA = regex.compile(r'(?i)^(season|temporada|series|s)\s*\d+$')
AÑO = regex.compile(r'\((\d{4})\)|\b(19\d{2}|20\d{2})\b')
RUIDO = regex.compile(r'\[[^\]]*\]|\([^)]*(?:\d{3,4}p|bd|web|x26[45]|hevc|dual|audio)[^)]*\)', regex.IGNORECASE)


@dataclass
class Candidato:
    """Una posible identidad de la serie, con los ids de cada fuente que la encontro."""
    titulo : str
    año : int|None
    tipo : str                       # anime, serie, pelicula
    titulos : set[str] = field(default_factory=set)
    ids : dict[str, int] = field(default_factory=dict)
    episodios : int|None = None
    detalle : str = ''               # idioma, cadena, formato
    puntaje : int = 0


@dataclass
class Pistas:
    """Lo que se deduce de la carpeta y los archivos."""
    titulo : str
    año : int|None
    videos : int


@dataclass
class Resultado:
    pistas : Pistas
    perfil : Path|None
    candidatos : list[Candidato]

    @property
    def claro(self) -> bool:
        """Una sola identidad con buena coincidencia, o una claramente mejor que las demas."""
        if self.perfil is not None:
            return True
        if not self.candidatos:
            return False
        mejor = self.candidatos[0]
        segundo = self.candidatos[1].puntaje if len(self.candidatos) > 1 else -99
        return mejor.puntaje >= 4 and mejor.puntaje - segundo >= 2


def normalizar(texto : str) -> str:
    """Minusculas, sin tildes ni signos, sin articulo inicial: "The Vision of Escaflowne" -> "vision of escaflowne"."""
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    texto = regex.sub(r'[^a-z0-9]+', ' ', texto.lower()).strip()
    return regex.sub(r'^(the|a|an|el|la|los|las)\s+', '', texto)


def pistas_de_carpeta(carpeta : Path) -> Pistas:
    """Titulo y año desde el nombre de la carpeta ("Kingdom (2012)/Season 3" -> Kingdom, 2012)."""
    nombre = carpeta.name
    if CARPETA_TEMPORADA.match(nombre.strip()) and carpeta.parent.name:
        nombre = carpeta.parent.name
    coincidencia = AÑO.search(nombre)
    año = int(coincidencia.group(1) or coincidencia.group(2)) if coincidencia else None
    titulo = RUIDO.sub(' ', AÑO.sub(' ', nombre))
    titulo = regex.sub(r'[._]+', ' ', titulo)
    return Pistas(regex.sub(r'\s+', ' ', titulo).strip(), año, len(listar_videos(carpeta)) if carpeta.is_dir() else 0)


def _pedir(url : str, datos : dict|None = None, cabeceras : dict|None = None) -> object:
    cuerpo = json.dumps(datos).encode() if datos is not None else None
    todas = {'User-Agent': AGENTE, 'Accept': 'application/json', **(cabeceras or {})}
    if cuerpo is not None:
        todas['Content-Type'] = 'application/json'
    with urllib.request.urlopen(urllib.request.Request(url, data=cuerpo, headers=todas), timeout=20) as respuesta:
        return json.loads(respuesta.read())


def buscar_anilist(titulo : str) -> list[Candidato]:
    consulta = '''query($q:String){Page(perPage:10){media(search:$q,type:ANIME){
        id title{romaji english native} synonyms seasonYear format episodes countryOfOrigin}}}'''
    datos = _pedir('https://graphql.anilist.co', {'query': consulta, 'variables': {'q': titulo}})
    candidatos = []
    for m in datos['data']['Page']['media']:
        titulos = {t for t in (m['title']['romaji'], m['title']['english'], m['title']['native'], *m.get('synonyms', [])) if t}
        tipo = 'pelicula' if m['format'] == 'MOVIE' else 'anime'
        candidatos.append(Candidato(m['title']['english'] or m['title']['romaji'], m['seasonYear'], tipo, titulos,
                                   {'anilist': m['id']}, m['episodes'], f"anime {m['format']}"))
    return candidatos


def buscar_tvmaze(titulo : str) -> list[Candidato]:
    datos = _pedir('https://api.tvmaze.com/search/shows?' + urllib.parse.urlencode({'q': titulo}))
    candidatos = []
    for r in datos:
        s = r['show']
        año = int(s['premiered'][:4]) if s.get('premiered') else None
        tipo = 'anime' if s.get('type') == 'Animation' and s.get('language') == 'Japanese' else 'serie'
        cadena = (s.get('network') or s.get('webChannel') or {}).get('name', '')
        candidatos.append(Candidato(s['name'], año, tipo, {s['name']}, {'tvmaze': s['id']}, None,
                                   f"{s.get('type', '')}, {s.get('language', '')}, {cadena}".strip(', ')))
    return candidatos


def buscar_tmdb(titulo : str) -> list[Candidato]:
    clave = config.valor('TMDB_API_KEY')
    if not clave:
        return []
    datos = _pedir('https://api.themoviedb.org/3/search/multi?' + urllib.parse.urlencode({'query': titulo, 'api_key': clave}))
    candidatos = []
    for r in datos.get('results', []):
        if r.get('media_type') not in ('tv', 'movie'):
            continue
        nombre = r.get('name') or r.get('title') or ''
        fecha = r.get('first_air_date') or r.get('release_date') or ''
        tipo = 'pelicula' if r['media_type'] == 'movie' else 'serie'
        titulos = {nombre, r.get('original_name') or r.get('original_title') or nombre}
        candidatos.append(Candidato(nombre, int(fecha[:4]) if fecha[:4].isdigit() else None, tipo, titulos,
                                   {'tmdb': r['id']}, None, f"{r['media_type']}, {r.get('original_language', '')}"))
    return candidatos


def _puntuar(candidato : Candidato, pistas : Pistas) -> int:
    buscado = normalizar(pistas.titulo)
    titulos = _claves(candidato)
    puntaje = 3 if buscado in titulos else (1 if any(buscado in t or t in buscado for t in titulos) else -3)
    if pistas.año and candidato.año:
        puntaje += 3 if pistas.año == candidato.año else (1 if abs(pistas.año - candidato.año) == 1 else -4)
    if pistas.videos > 1 and candidato.tipo == 'pelicula':
        puntaje -= 2
    if pistas.videos and candidato.episodios == pistas.videos:
        puntaje += 1
    return puntaje


def _claves(candidato : Candidato) -> set[str]:
    """Titulos normalizados; los que quedan vacios (titulos en japones) no sirven para comparar."""
    return {n for n in (normalizar(t) for t in candidato.titulos | {candidato.titulo}) if n}


def _unir(candidatos : list[Candidato]) -> list[Candidato]:
    """La misma serie encontrada en varias fuentes (mismo titulo y año) queda como un solo candidato."""
    unidos : list[Candidato] = []
    for c in candidatos:
        igual = next((u for u in unidos if u.año == c.año and _claves(c) & _claves(u)), None)
        if igual:
            igual.ids.update(c.ids)
            igual.titulos |= c.titulos
            igual.episodios = igual.episodios or c.episodios
            igual.tipo = 'anime' if 'anime' in (igual.tipo, c.tipo) else igual.tipo
            igual.detalle = igual.detalle or c.detalle
        else:
            unidos.append(c)
    return unidos


def perfil_existente(pistas : Pistas, carpeta_perfiles : Path) -> Path|None:
    """Perfil de series/ con el mismo titulo (y año, si se conoce)."""
    for ruta in sorted(carpeta_perfiles.glob('*.yaml')):
        datos = yaml.safe_load(ruta.read_text(encoding='utf-8')) or {}
        if normalizar(str(datos.get('serie', ''))) == normalizar(pistas.titulo) and (not pistas.año or datos.get('año') == pistas.año):
            return ruta
    return None


def identificar(carpeta : Path, carpeta_perfiles : Path, buscadores : list|None = None) -> Resultado:
    pistas = pistas_de_carpeta(carpeta)
    perfil = perfil_existente(pistas, carpeta_perfiles)
    if perfil:
        return Resultado(pistas, perfil, [])

    candidatos : list[Candidato] = []
    for buscar in buscadores or (buscar_anilist, buscar_tvmaze, buscar_tmdb):
        try:
            candidatos += buscar(pistas.titulo)
        except (OSError, ValueError, KeyError):
            continue        # una fuente caida no impide usar las demas
    candidatos = _unir(candidatos)
    for c in candidatos:
        c.puntaje = _puntuar(c, pistas)
    candidatos = sorted((c for c in candidatos if c.puntaje > 0), key=lambda c: -c.puntaje)
    return Resultado(pistas, None, candidatos)


def crear_perfil(candidato : Candidato, carpeta_perfiles : Path) -> Path:
    """Perfil base para una serie nueva: identidad y reglas por defecto. Los nombres se completan despues."""
    nombre = regex.sub(r'[^a-z0-9]+', '-', normalizar(candidato.titulo)).strip('-')
    ruta = carpeta_perfiles / f"{nombre}-{candidato.año or 'sin-año'}.yaml"
    datos = {
        'serie': candidato.titulo, 'año': candidato.año, 'tipo': candidato.tipo, 'ids': candidato.ids,
        'idioma_destino': 'Latin American Spanish', 'codigo': 'es', 'tratamiento': 'tuteo',
        'prompt': 'Translate to natural Latin American Spanish. Keep character, place and organization names unchanged.',
        'nombres_fijos': [],
    }
    ruta.write_text(f"# {candidato.titulo} ({candidato.año}). Creado por subtrad identificar; completar nombres_fijos.\n\n"
                    + yaml.safe_dump(datos, allow_unicode=True, sort_keys=False), encoding='utf-8')
    return ruta
