"""Verifica y corrige la sincronia de un subtitulo contra el audio del video, con alass.

alass (https://github.com/kaegi/alass) se instala aparte: su ruta va en ALASS_PATH (entorno o .env) o en el PATH.
Lecciones de las pruebas:
- Una pista que viene dentro del video puede ser de OTRO contenido (paso en World Is Dancing). Hay que verificarla igual.
- Un subtitulo de otro contenido no tiene un corrimiento parejo: alass lo mueve distinto en cada tramo.
- Con ffprobe nuevo, alass a veces no puede leer el video; por eso se le pasa el audio extraido a WAV.
- En escenas con musica y sin dialogo alass inventa cortes (World Is Dancing E03: tramos movidos -36 s y +62 s
  en un subtitulo correcto). Por eso se calcula un corrimiento unico (--no-split) y se mide cuantas lineas
  coinciden con el en el modo con cortes: los subtitulos correctos dan 60-100 %, los de otro contenido menos del 10 %.
"""
import shutil
import statistics
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pysubs2

from subtrad import config
from subtrad.archivos import cargar

ENCAJA = 'encaja'
CORRIDO = 'corrido'
NO_ENCAJA = 'no_encaja'

# Umbrales
MOVIMIENTO_TOLERADO = 1000      # ms: una linea "coincide" si se mueve menos que esto respecto del corrimiento unico
CORRIMIENTO_DESPRECIABLE = 300  # ms: por debajo de esto no vale la pena corregir
COINCIDENCIA_MINIMA = 0.5       # fraccion de lineas que deben coincidir con el corrimiento unico
# Si el corrimiento unico es practicamente cero alcanza con menos: un subtitulo de otro contenido no cae justo en cero.
# Caso real (Escaflowne E15): corrimiento -30 ms y 46 % de lineas que coinciden, subtitulo correcto.
COINCIDENCIA_MINIMA_SIN_CORRIMIENTO = 0.3


class AlassNoEncontrado(Exception):
    """alass no esta instalado ni configurado en ALASS_PATH."""


@dataclass
class Verificacion:
    """Resultado de comparar un subtitulo con el audio."""
    estado : str                 # ENCAJA, CORRIDO o NO_ENCAJA
    corrimiento_ms : float       # corrimiento unico que propone alass (con signo)
    quietas : float              # fraccion de lineas que coinciden con ese corrimiento unico
    corregido : Path|None = None # subtitulo con el corrimiento unico aplicado (si el estado es CORRIDO)


def ruta_alass() -> str:
    configurada = config.valor('ALASS_PATH')
    if configurada and Path(configurada).exists():
        return configurada
    for nombre in ('alass-cli', 'alass'):
        encontrada = shutil.which(nombre)
        if encontrada:
            return encontrada
    raise AlassNoEncontrado("No se encontro alass. Descargalo de github.com/kaegi/alass y pone su ruta en ALASS_PATH (.env)")


# Idiomas originales tipicos de anime y series asiaticas: si el video trae doblaje, el audio original es el que manda
IDIOMAS_ORIGINALES = ('jpn', 'ja', 'kor', 'ko', 'chi', 'zho', 'zh')


def elegir_pista_audio(video : Path, idioma : str|None = None) -> int:
    """Indice (entre las pistas de audio) del audio contra el que se verifica.
    Error real (Escaflowne): la primera pista era el doblaje en ingles y el subtitulo sigue al audio japones."""
    salida = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream_tags=language',
                             '-of', 'csv=p=0', str(video)], capture_output=True, text=True)
    idiomas = [l.strip().lower() for l in salida.stdout.splitlines()]
    preferidos = (idioma.lower(),) if idioma else IDIOMAS_ORIGINALES
    for i, codigo in enumerate(idiomas):
        if codigo in preferidos:
            return i
    return 0


def extraer_audio(video : Path, destino : Path, idioma_audio : str|None = None) -> Path:
    """Audio mono a 16 kHz, suficiente para detectar voz y mucho mas liviano que el video."""
    pista = elegir_pista_audio(video, idioma_audio)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(video), '-map', f'0:a:{pista}', '-ac', '1', '-ar', '16000', str(destino)],
                   check=True)
    return destino


def _movimientos(alass : str, audio : Path, subtitulo : Path, salida : Path, sin_cortes : bool) -> list[int]:
    """Cuanto mueve alass cada linea con texto."""
    comando = [alass, *(['--no-split'] if sin_cortes else []), str(audio), str(subtitulo), str(salida)]
    subprocess.run(comando, capture_output=True)
    if not salida.exists():
        return []
    originales, movidos = cargar(subtitulo).events, pysubs2.load(str(salida)).events
    return [b.start - a.start for a, b in zip(originales, movidos) if a.plaintext.strip()]


def verificar(audio : Path, subtitulo : Path, carpeta_temporal : Path|None = None) -> Verificacion:
    """Compara el subtitulo con el audio: corrimiento unico y cuantas lineas lo confirman."""
    carpeta = carpeta_temporal or Path(tempfile.mkdtemp())
    alass = ruta_alass()
    corregido = carpeta / f'unico_{subtitulo.name}'
    unico = _movimientos(alass, audio, subtitulo, corregido, sin_cortes=True)
    con_cortes = _movimientos(alass, audio, subtitulo, carpeta / f'cortes_{subtitulo.name}', sin_cortes=False)
    if not unico or not con_cortes:
        return Verificacion(NO_ENCAJA, 0, 0)

    corrimiento = statistics.median(unico)
    coinciden = sum(abs(m - corrimiento) < MOVIMIENTO_TOLERADO for m in con_cortes) / len(con_cortes)

    despreciable = abs(corrimiento) < CORRIMIENTO_DESPRECIABLE
    minimo = COINCIDENCIA_MINIMA_SIN_CORRIMIENTO if despreciable else COINCIDENCIA_MINIMA
    if coinciden < minimo:
        return Verificacion(NO_ENCAJA, corrimiento, coinciden)
    if despreciable:
        return Verificacion(ENCAJA, corrimiento, coinciden)
    return Verificacion(CORRIDO, corrimiento, coinciden, corregido)
