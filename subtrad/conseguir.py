"""Consigue el subtitulo original (normalmente en ingles) de cada video y verifica que corresponda al audio.

Candidatos, en orden: el archivo que ya esta al lado del video, las pistas de texto del video y, si ninguno sirve,
descargas de OpenSubtitles. Cada candidato se verifica contra el audio con alass y se queda el mejor.
"""
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import regex

from subtrad import opensubtitles, sincronizar, video as videos
from subtrad.archivos import cargar

EPISODIO = regex.compile(r'(?i)(?<![a-z0-9])S(\d{1,2})(?:E(\d{1,3})|\s*-\s*(\d{1,3}))')
# Estilo anime sin temporada: "Tenkuu_no_Escaflowne_-_01_(...)", "Serie - 01 [1080p]"
EPISODIO_ANIME = regex.compile(r'[ _]-[ _](\d{1,3})(?:v\d)?[ _.(\[]')
ACOTACION_SDH = regex.compile(r'\[[^\]]*\]|\([A-Z][A-Z \-]+\)')


@dataclass
class Candidato:
    """Un subtitulo posible para un video."""
    origen : str                 # 'existente', 'pista #N', 'opensubtitles <file_id>'
    ruta : Path
    sdh : bool = False
    verificacion : sincronizar.Verificacion|None = None


@dataclass
class ResultadoVideo:
    video : Path
    salida : Path|None
    elegido : Candidato|None
    candidatos : list[Candidato] = field(default_factory=list)
    detalle : str = ''


def temporada_y_episodio(archivo : Path) -> tuple[int|None, int|None]:
    coincidencia = EPISODIO.search(archivo.name)
    if coincidencia:
        return int(coincidencia.group(1)), int(coincidencia.group(2) or coincidencia.group(3))
    coincidencia = EPISODIO_ANIME.search(archivo.name)
    if coincidencia:
        return 1, int(coincidencia.group(1))
    return None, None


def es_sdh(ruta : Path, titulo : str = '') -> bool:
    """Subtitulos para sordos: lo dice el titulo de la pista o tienen muchas acotaciones [musica]."""
    if 'sdh' in titulo.lower() or 'sdh' in ruta.name.lower():
        return True
    eventos = [e.plaintext for e in cargar(ruta).events if e.plaintext.strip()]
    return bool(eventos) and sum(bool(ACOTACION_SDH.search(t)) for t in eventos) / len(eventos) > 0.1


def limpiar_sdh(ruta : Path) -> None:
    """Saca las acotaciones ([musica], (RISAS)) y las lineas que quedan vacias."""
    subs = cargar(ruta)
    for evento in subs.events:
        evento.text = regex.sub(r'\s{2,}', ' ', ACOTACION_SDH.sub('', evento.text)).strip()
        evento.text = regex.sub(r'^(\\N)+|(\\N)+$', '', evento.text)
    subs.events = [e for e in subs.events if e.plaintext.strip(' -')]
    subs.save(str(ruta), encoding='utf-8')


def _prioridad(candidato : Candidato) -> tuple[int, int, int]:
    """Primero los que encajan, despues los corridos parejo; entre ellos, sin SDH y con mas lineas."""
    estado = candidato.verificacion.estado if candidato.verificacion else sincronizar.NO_ENCAJA
    orden = {sincronizar.ENCAJA: 0, sincronizar.CORRIDO: 1}.get(estado, 9)
    return (orden, int(candidato.sdh), -len(cargar(candidato.ruta).events))


PALABRAS_INGLES = regex.compile(r"\b(the|you|and|what|this|that|is|are|it's|don't|i'm|to|of|my|your|we|have)\b", regex.IGNORECASE)


def parece_ingles(ruta : Path) -> bool:
    """El texto de la pista esta en ingles (mas de un tercio de las lineas con palabras muy comunes del ingles)."""
    textos = [e.plaintext for e in cargar(ruta).events if e.plaintext.strip()]
    return bool(textos) and sum(bool(PALABRAS_INGLES.search(t)) for t in textos) / len(textos) > 0.33


def _pistas_del_video(video : Path, idioma : str, temporal : Path) -> list[Candidato]:
    """Pistas de texto del idioma pedido.
    La etiqueta de idioma no alcanza (Escaflowne: los dialogos en ingles venian etiquetados "jpn", por ser para el
    audio japones, y la pista "eng" solo tenia canciones y carteles): en ingles se mira tambien el contenido."""
    codigos = videos.IDIOMAS.get(idioma, {idioma})
    candidatos = []
    for pista in videos.pistas_subtitulos(video):
        if pista.get('codec_name') not in videos.CODECS_TEXTO:
            continue
        etiqueta_coincide = pista.get('tags', {}).get('language', '').lower() in codigos
        if not etiqueta_coincide and idioma != 'en':
            continue

        extension, codec = videos.CODECS_TEXTO[pista['codec_name']]
        destino = temporal / f"pista{pista['index']}.{extension}"
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(video), '-map', f"0:{pista['index']}", '-c:s', codec, str(destino)])
        if not destino.exists() or (idioma == 'en' and not parece_ingles(destino)):
            continue
        titulo = pista.get('tags', {}).get('title', '')
        etiqueta = pista.get('tags', {}).get('language', '?')
        candidatos.append(Candidato(f"pista #{pista['index']} {etiqueta} '{titulo}'", destino, es_sdh(destino, titulo)))
    return candidatos


def conseguir_video(video : Path, idioma : str = 'en', consulta : str = '', cliente : opensubtitles.Cliente|None = None,
                    max_descargas : int = 2, idioma_audio : str|None = None) -> ResultadoVideo:
    """Elige y deja al lado del video el mejor subtitulo verificado: <video>.<idioma>.<ext>.
    Un subtitulo que ya estaba al lado del video tambien se verifica: puede estar mal."""
    temporal = Path(tempfile.mkdtemp(prefix='subtrad_'))
    try:
        existentes = [video.with_name(f'{video.stem}.{idioma}{ext}') for ext in ('.ass', '.srt', '.vtt')]
        existentes = [r for r in existentes if r.exists()]

        audio = sincronizar.extraer_audio(video, temporal / 'audio.wav', idioma_audio)
        candidatos = [Candidato('existente', r, es_sdh(r)) for r in existentes] + _pistas_del_video(video, idioma, temporal)
        for candidato in candidatos:
            candidato.verificacion = sincronizar.verificar(audio, candidato.ruta, temporal)

        sirven = [c for c in candidatos if c.verificacion and c.verificacion.estado != sincronizar.NO_ENCAJA]
        aviso = ''
        if not sirven and cliente is not None:
            temporada, episodio = temporada_y_episodio(video)
            for resultado in cliente.buscar(consulta, temporada, episodio, idioma, video)[:max_descargas]:
                try:
                    ruta = cliente.descargar(resultado, temporal)
                except opensubtitles.LimiteAgotado:
                    aviso = 'se agotaron las descargas de hoy en OpenSubtitles'
                    break
                candidato = Candidato(f'opensubtitles {resultado.file_id}', ruta, es_sdh(ruta))
                candidato.verificacion = sincronizar.verificar(audio, ruta, temporal)
                candidatos.append(candidato)
                if candidato.verificacion.estado != sincronizar.NO_ENCAJA:
                    sirven.append(candidato)
                    if candidato.verificacion.estado == sincronizar.ENCAJA:
                        break

        if not sirven:
            return ResultadoVideo(video, None, None, candidatos, aviso or 'ningun candidato corresponde al audio')

        elegido = min(sirven, key=_prioridad)
        fuente = elegido.verificacion.corregido if elegido.verificacion.estado == sincronizar.CORRIDO else elegido.ruta
        salida = video.with_name(f'{video.stem}.{idioma}{fuente.suffix}')

        # Respaldo si se reemplaza un archivo existente distinto del elegido
        for existente in existentes:
            if existente != fuente and existente.exists() and elegido.origen != 'existente':
                respaldo = video.parent / '.respaldo'
                respaldo.mkdir(exist_ok=True)
                shutil.move(str(existente), respaldo / existente.name)

        if fuente != salida:
            shutil.copyfile(fuente, salida)
        if elegido.sdh:
            limpiar_sdh(salida)
        return ResultadoVideo(video, salida, elegido, candidatos)
    finally:
        shutil.rmtree(temporal, ignore_errors=True)
