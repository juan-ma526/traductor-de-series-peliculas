"""Extraccion de pistas de subtitulos embebidas en videos, con ffmpeg."""
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

VIDEOS = {'.mkv', '.mp4', '.m4v', '.avi', '.webm', '.mov', '.ts'}

# Codecs de texto que se pueden extraer, con la extension y el codec de salida
CODECS_TEXTO = {
    'ass': ('ass', 'copy'),
    'ssa': ('ass', 'copy'),
    'subrip': ('srt', 'copy'),
    'srt': ('srt', 'copy'),
    'webvtt': ('vtt', 'copy'),
    'mov_text': ('srt', 'srt'),
    'text': ('srt', 'srt'),
}

IDIOMAS = {
    'en': {'en', 'eng'}, 'es': {'es', 'spa'}, 'pt': {'pt', 'por'}, 'fr': {'fr', 'fre', 'fra'},
    'de': {'de', 'ger', 'deu'}, 'it': {'it', 'ita'}, 'ja': {'ja', 'jpn'},
}

# Pistas que no son de dialogos completos
PALABRAS_PARCIALES = ('sign', 'song', 'forced', 'karaoke', 'commentary')


class FfmpegNoEncontrado(Exception):
    """ffmpeg o ffprobe no estan instalados o no estan en el PATH."""


@dataclass
class Resultado:
    """Resultado de procesar un video."""
    video : Path
    estado : str            # 'extraido', 'existe', 'sin_pista', 'no_extraible', 'error'
    salida : Path|None = None
    detalle : str = ''


def herramienta(nombre : str) -> str:
    ruta = shutil.which(nombre)
    if not ruta:
        raise FfmpegNoEncontrado(f"No se encontro {nombre}. En Windows: winget install Gyan.FFmpeg")
    return ruta


def pistas_subtitulos(video : Path) -> list[dict]:
    """Pistas de subtitulos del video segun ffprobe."""
    salida = subprocess.run(
        [herramienta('ffprobe'), '-v', 'error', '-select_streams', 's', '-show_entries',
         'stream=index,codec_name:stream_tags=language,title:stream_disposition=default,forced',
         '-of', 'json', str(video)],
        capture_output=True, text=True, encoding='utf-8')
    if salida.returncode != 0:
        return []
    return json.loads(salida.stdout or '{}').get('streams', [])


def elegir_pista(pistas : list[dict], idioma : str) -> dict|None:
    """La pista de dialogos completos en el idioma pedido; evita las de carteles o canciones."""
    codigos = IDIOMAS.get(idioma, {idioma})
    candidatas = [p for p in pistas if p.get('tags', {}).get('language', '').lower() in codigos]

    # Una unica pista sin idioma se asume que es la buscada
    if not candidatas and len(pistas) == 1 and not pistas[0].get('tags', {}).get('language'):
        candidatas = pistas

    def puntaje(pista : dict) -> tuple[int, int, int]:
        titulo = pista.get('tags', {}).get('title', '').lower()
        parcial = any(palabra in titulo for palabra in PALABRAS_PARCIALES)
        es_texto = pista.get('codec_name') in CODECS_TEXTO
        return (int(es_texto), int(not parcial), -int(pista['index']))

    return max(candidatas, key=puntaje) if candidatas else None


def describir(pista : dict) -> str:
    tags = pista.get('tags', {})
    return f"#{pista['index']} {pista.get('codec_name')} {tags.get('language', '?')} '{tags.get('title', '')}'"


def extraer_video(video : Path, idioma : str = 'en', sobrescribir : bool = False) -> Resultado:
    """Extrae la pista de subtitulos del idioma pedido al lado del video (video.<idioma>.<ext>)."""
    pista = elegir_pista(pistas_subtitulos(video), idioma)
    if pista is None:
        return Resultado(video, 'sin_pista')

    codec = pista.get('codec_name', '')
    if codec not in CODECS_TEXTO:
        return Resultado(video, 'no_extraible', detalle=f"{codec}: subtitulo de imagen o formato desconocido")

    extension, codec_salida = CODECS_TEXTO[codec]
    salida = video.with_name(f"{video.stem}.{idioma}.{extension}")
    if salida.exists() and not sobrescribir:
        return Resultado(video, 'existe', salida)

    resultado = subprocess.run(
        [herramienta('ffmpeg'), '-v', 'error', '-y', '-i', str(video), '-map', f"0:{pista['index']}", '-c:s', codec_salida, str(salida)],
        capture_output=True, text=True, encoding='utf-8')
    if resultado.returncode != 0 or not salida.exists():
        return Resultado(video, 'error', detalle=resultado.stderr.strip()[:200])

    return Resultado(video, 'extraido', salida, describir(pista))


def videos(carpeta : Path) -> list[Path]:
    return sorted(v for v in carpeta.iterdir() if v.is_file() and v.suffix.lower() in VIDEOS)
