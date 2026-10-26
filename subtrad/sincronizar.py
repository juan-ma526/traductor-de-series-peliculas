"""Verifica y corrige la sincronia de un subtitulo contra el audio del video, con alass.

alass (https://github.com/kaegi/alass) se instala aparte: su ruta va en ALASS_PATH (entorno o .env) o en el PATH.
Lecciones de las pruebas:
- Una pista que viene dentro del video puede ser de OTRO contenido (paso en World Is Dancing). Hay que verificarla igual.
- Un subtitulo de otro contenido no tiene un corrimiento parejo: alass lo mueve distinto en cada tramo.
- Con ffprobe nuevo, alass a veces no puede leer el video; por eso se le pasa el audio extraido a WAV.
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

# Umbrales en milisegundos
MOVIMIENTO_TOLERADO = 1000
DISPERSION_MAXIMA = 1500


class AlassNoEncontrado(Exception):
    """alass no esta instalado ni configurado en ALASS_PATH."""


@dataclass
class Verificacion:
    """Resultado de comparar un subtitulo con el audio."""
    estado : str                 # ENCAJA, CORRIDO o NO_ENCAJA
    corrimiento_ms : float       # mediana del movimiento que propone alass (con signo)
    quietas : float              # fraccion de lineas que casi no se mueven
    dispersion_ms : float        # diferencia entre el percentil 90 y el 10 del movimiento
    corregido : Path|None = None # subtitulo movido por alass (si el estado es CORRIDO)


def ruta_alass() -> str:
    configurada = config.valor('ALASS_PATH')
    if configurada and Path(configurada).exists():
        return configurada
    for nombre in ('alass-cli', 'alass'):
        encontrada = shutil.which(nombre)
        if encontrada:
            return encontrada
    raise AlassNoEncontrado("No se encontro alass. Descargalo de github.com/kaegi/alass y pone su ruta en ALASS_PATH (.env)")


def extraer_audio(video : Path, destino : Path, pista_audio : int = 0) -> Path:
    """Audio mono a 16 kHz, suficiente para detectar voz y mucho mas liviano que el video."""
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(video), '-map', f'0:a:{pista_audio}', '-ac', '1', '-ar', '16000', str(destino)],
                   check=True)
    return destino


def verificar(audio : Path, subtitulo : Path, carpeta_temporal : Path|None = None) -> Verificacion:
    """Pasa el subtitulo por alass y mide cuanto y que tan parejo lo mueve."""
    carpeta = carpeta_temporal or Path(tempfile.mkdtemp())
    movido = carpeta / f'alass_{subtitulo.name}'
    subprocess.run([ruta_alass(), str(audio), str(subtitulo), str(movido)], capture_output=True)
    if not movido.exists():
        return Verificacion(NO_ENCAJA, 0, 0, 0)

    originales, movidos = cargar(subtitulo).events, pysubs2.load(str(movido)).events
    movimientos = sorted(b.start - a.start for a, b in zip(originales, movidos) if a.plaintext.strip())
    if not movimientos:
        return Verificacion(NO_ENCAJA, 0, 0, 0)

    mediana = statistics.median(movimientos)
    quietas = sum(abs(m) < MOVIMIENTO_TOLERADO for m in movimientos) / len(movimientos)
    dispersion = movimientos[int(len(movimientos) * 0.9)] - movimientos[int(len(movimientos) * 0.1)]

    if abs(mediana) < MOVIMIENTO_TOLERADO * 1.5 and quietas >= 0.8:
        return Verificacion(ENCAJA, mediana, quietas, dispersion)
    if dispersion <= DISPERSION_MAXIMA:
        return Verificacion(CORRIDO, mediana, quietas, dispersion, movido)
    return Verificacion(NO_ENCAJA, mediana, quietas, dispersion)
