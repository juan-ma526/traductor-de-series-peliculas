"""Lectura de subtitulos, nombres de archivo y codigos de idioma."""
from dataclasses import dataclass
from pathlib import Path

import charset_normalizer
import pysubs2
import regex

EXTENSIONES_SUBTITULOS = {'.srt', '.ass', '.ssa', '.vtt', '.sub'}
CODIGO_IDIOMA = regex.compile(r'[a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?')

# "S3E01", "S03E01" o "S6 - 01" (formato SubsPlease); puede venir pegado a "_" como en "Kingdom_S3E01"
TEMPORADA = regex.compile(r'(?i)(?<![a-z0-9])S(\d{1,2})(?:E\d|\s*-\s*\d)')

# Con pocos datos la deteccion automatica de encoding no es confiable
MINIMO_PARA_DETECTAR = 2000


@dataclass
class Pendiente:
    """Un subtitulo original y el archivo traducido que le corresponde."""
    origen : Path
    salida : Path

    @property
    def ya_traducido(self) -> bool:
        return self.salida.exists()


def cargar(archivo : Path) -> pysubs2.SSAFile:
    """Carga un subtitulo detectando su encoding.
    UTF-8 primero; si no, deteccion automatica (solo con datos suficientes) o Windows-1252, el caso mas comun."""
    datos = archivo.read_bytes()
    encoding = 'utf-8-sig'
    try:
        datos.decode(encoding)
    except UnicodeDecodeError:
        detectado = charset_normalizer.from_bytes(datos).best() if len(datos) >= MINIMO_PARA_DETECTAR else None
        encoding = detectado.encoding if detectado else 'cp1252'

    return pysubs2.load(str(archivo), encoding=encoding)


def codigo_idioma(archivo : Path) -> str|None:
    """Codigo de idioma del nombre del archivo, ej. 'en' para episodio.en.ass."""
    partes = archivo.name.split('.')
    if len(partes) >= 3 and CODIGO_IDIOMA.fullmatch(partes[-2]):
        return partes[-2].lower()
    return None


def ruta_salida(archivo : Path, destino : str) -> Path:
    """Ruta del traducido: reemplaza el codigo de idioma (ep.en.ass -> ep.es.ass) o lo agrega (ep.srt -> ep.es.srt)."""
    base = archivo.name[:-len(archivo.suffix)]
    if codigo_idioma(archivo):
        base = base.rsplit('.', 1)[0]
    return archivo.with_name(f"{base}.{destino}{archivo.suffix}")


def ruta_original(traducido : Path, origen : str = 'en') -> Path|None:
    """Subtitulo original de un traducido, buscando el mismo nombre con el codigo de origen."""
    base = traducido.name[:-len(traducido.suffix)].rsplit('.', 1)[0]
    for extension in (traducido.suffix, '.ass', '.srt', '.vtt'):
        candidato = traducido.with_name(f"{base}.{origen}{extension}")
        if candidato.exists():
            return candidato
    return None


def temporada(archivo : Path) -> int|None:
    """Numero de temporada segun el nombre del archivo, si lo tiene."""
    coincidencia = TEMPORADA.search(archivo.name)
    return int(coincidencia.group(1)) if coincidencia else None


def pendientes(carpeta : Path, destino : str) -> list[Pendiente]:
    """Subtitulos originales de una carpeta, con la ruta de su traduccion (exista o no)."""
    resultado = []
    for archivo in sorted(carpeta.iterdir()):
        if not archivo.is_file() or archivo.suffix.lower() not in EXTENSIONES_SUBTITULOS:
            continue

        # Ya esta en el idioma destino: es una traduccion, no un original
        if codigo_idioma(archivo) == destino.lower():
            continue

        resultado.append(Pendiente(archivo, ruta_salida(archivo, destino)))
    return resultado
