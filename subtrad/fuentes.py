"""Lo comun a las fuentes de descarga de subtitulos (OpenSubtitles, Subdl, Gestdown).

Cada fuente busca los subtitulos de un episodio o pelicula y descarga uno a una carpeta.
Lo que se descarga siempre se verifica despues contra el audio, venga de donde venga.
"""
import io
import json
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import regex

from subtrad import __version__

AGENTE = f'subtrad v{__version__}'
EXTENSIONES = ('.srt', '.ass', '.ssa', '.vtt')
AÑO = regex.compile(r'\s*[\(\[]((?:19|20)\d{2})[\)\]]\s*')
EPISODIO = regex.compile(r'(?i)S(\d{1,2})[ ._-]?E(\d{1,3})')


class ErrorFuente(Exception):
    """Fallo de una fuente (clave invalida, red, respuesta inesperada...)."""


class LimiteAgotado(ErrorFuente):
    """Se agoto el limite de descargas de la fuente."""


@dataclass
class Resultado:
    """Un subtitulo encontrado en una fuente."""
    id : str                     # lo que la fuente necesita para descargarlo
    release : str
    descargas : int = 0
    coincide_hash : bool = False
    titulo : str = ''
    datos : dict = field(default_factory=dict)


class Fuente(Protocol):
    """Lo que conseguir.py necesita de una fuente."""
    nombre : str

    def buscar(self, consulta : str, temporada : int|None, episodio : int|None, idioma : str = 'en',
               video : Path|None = None) -> list[Resultado]: ...

    def descargar(self, resultado : Resultado, carpeta : Path) -> Path: ...


def titulo_y_año(consulta : str) -> tuple[str, int|None]:
    """Separa el año de un nombre de carpeta: "Catch Me If You Can (2002)" -> ("Catch Me If You Can", 2002)."""
    coincidencia = AÑO.search(consulta)
    if not coincidencia:
        return consulta.strip(), None
    return AÑO.sub(' ', consulta).strip(), int(coincidencia.group(1))


def pedir(url : str, cabeceras : dict|None = None, datos : bytes|None = None, metodo : str = 'GET',
          timeout : int = 30) -> bytes:
    """Pedido HTTP; los errores salen como ErrorFuente, sin la URL (puede llevar la clave)."""
    pedido = urllib.request.Request(url, data=datos, headers={'User-Agent': AGENTE, **(cabeceras or {})}, method=metodo)
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as respuesta:
            return respuesta.read()
    except urllib.error.HTTPError as error:
        detalle = error.read()[:200].decode('utf-8', 'replace')
        raise ErrorFuente(f'HTTP {error.code}: {detalle}') from error
    except urllib.error.URLError as error:
        raise ErrorFuente(f'Sin conexion: {error.reason}') from error


def pedir_json(url : str, cabeceras : dict|None = None) -> dict:
    try:
        return json.loads(pedir(url, {'Accept': 'application/json', **(cabeceras or {})}))
    except json.JSONDecodeError as error:
        raise ErrorFuente(f'Respuesta que no es JSON: {error}') from error


def guardar(contenido : bytes, nombre : str, carpeta : Path, prefijo : str) -> Path:
    """Guarda un subtitulo con un nombre seguro (solo el nombre base, nunca rutas que vengan de afuera)."""
    base = regex.sub(r'[^\w.\- ]', '_', Path(nombre.replace('\\', '/')).name) or 'subtitulo.srt'
    ruta = carpeta / f'{prefijo}_{base}'
    ruta.write_bytes(contenido)
    return ruta


def elegir_de_zip(contenido : bytes, temporada : int|None, episodio : int|None) -> tuple[str, bytes]:
    """El subtitulo que corresponde dentro de un zip.
    Los paquetes de temporada completa traen un archivo por episodio: se elige por SxxEyy.
    En peliculas partidas (CD1, CD2) o con varias versiones se elige el mas grande."""
    try:
        archivo = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile as error:
        raise ErrorFuente('El zip descargado esta dañado') from error

    with archivo:
        candidatos = [i for i in archivo.infolist() if not i.is_dir() and i.filename.lower().endswith(EXTENSIONES)]
        if episodio is not None:
            def es_el_episodio(nombre : str) -> bool:
                coincidencia = EPISODIO.search(Path(nombre).name)
                return bool(coincidencia) and int(coincidencia.group(2)) == episodio and \
                    (temporada is None or int(coincidencia.group(1)) == temporada)
            del_episodio = [i for i in candidatos if es_el_episodio(i.filename)]
            # Si hay uno solo y su nombre no dice el episodio, es ese.
            # Si dice otro, no: Subdl marca como temporada completa zips que solo traen el S01E01.
            sin_numero = [i for i in candidatos if not EPISODIO.search(Path(i.filename).name)]
            candidatos = del_episodio or (sin_numero if len(candidatos) == 1 else [])
        if not candidatos:
            raise ErrorFuente('El zip no trae un subtitulo para este video')
        elegido = max(candidatos, key=lambda i: i.file_size)
        return elegido.filename, archivo.read(elegido)
