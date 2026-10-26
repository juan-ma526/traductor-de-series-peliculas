"""Divide un subtitulo en partes de texto para el traductor y reinserta la traduccion validandola.

El traductor (cualquier motor) solo ve lineas "[id] texto".
Tiempos, estilos y posiciones nunca pasan por el modelo.
"""
import json
import sys
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import pysubs2
import regex

from subtrad.archivos import cargar
from subtrad.perfil import Perfil

LINEA_TRADUCIDA = regex.compile(r'^\[(\d+)\]\s?(.*)$')
TAGS_ASS = regex.compile(r'\{[^}]*\}')
DIBUJO_ASS = regex.compile(r'\\p[1-9]')
KARAOKE = regex.compile(r'\\[kK][fo]?\d')
# Estilos de canciones: palabras sueltas (OP, ED, Song...) o partes de un nombre mas largo
# (Escaflowne usa "romajied", "romajied5" para la letra del ending)
ESTILO_CANCION = regex.compile(r'romaji|kanji|karaoke|lyric|(^|[\s_-])(op|ed|opening|ending|song|songs|kara|insert)($|[\s_\d-])', regex.IGNORECASE)

# Restos del formato interno de otras herramientas (llm-subtrans) que no deben llegar a pantalla
ETIQUETAS_COLADAS = regex.compile(r'(?:^|\\N)(?:Original|Translation)[:>]?\\N')

LINEAS_POR_PARTE = 120


class ErrorInsercion(Exception):
    """La traduccion no se puede insertar sin romper el subtitulo."""
    def __init__(self, errores : list[str]):
        super().__init__('\n'.join(errores))
        self.errores = errores


@dataclass
class Manifiesto:
    """Lo que se extrajo de un subtitulo, para poder reinsertarlo."""
    archivo : str
    eventos : list[int]
    partes : list[str] = field(default_factory=list)


def una_linea(texto : str) -> str:
    """Cada subtitulo en una sola linea, usando el salto de linea de ASS."""
    return texto.replace('\r', '').replace('\n', '\\N')


def eventos_traducibles(subs : pysubs2.SSAFile) -> list[int]:
    """Indices de los eventos con texto visible.
    Se omiten comentarios, dibujos ASS y canciones (karaoke o estilos de OP/ED), que quedan como estan."""
    indices = []
    for i, evento in enumerate(subs.events):
        if evento.is_comment or DIBUJO_ASS.search(evento.text):
            continue
        if KARAOKE.search(evento.text) or ESTILO_CANCION.search(evento.style):
            continue
        if evento.plaintext.strip():
            indices.append(i)
    return indices


def preparar(archivo : Path, trabajo : Path, lineas_por_parte : int = LINEAS_POR_PARTE) -> Manifiesto:
    """Escribe 001.txt, 002.txt... con lineas "[id] texto" y un manifiesto.json en la carpeta de trabajo."""
    subs = cargar(archivo)
    indices = eventos_traducibles(subs)
    trabajo.mkdir(parents=True, exist_ok=True)

    manifiesto = Manifiesto(str(archivo), indices)
    for inicio in range(0, len(indices), lineas_por_parte):
        nombre = f"{len(manifiesto.partes) + 1:03d}"
        bloque = indices[inicio:inicio + lineas_por_parte]
        texto = '\n'.join(f"[{i}] {una_linea(subs.events[i].text)}" for i in bloque)
        (trabajo / f"{nombre}.txt").write_text(texto + '\n', encoding='utf-8')
        manifiesto.partes.append(nombre)

    (trabajo / 'manifiesto.json').write_text(json.dumps(manifiesto.__dict__, indent=1), encoding='utf-8')
    return manifiesto


def _plantilla(nombre : str) -> str:
    return resources.files('subtrad').joinpath(f'plantillas/{nombre}').read_text(encoding='utf-8')


def reglas(perfil : Perfil) -> str:
    """Reglas de traduccion comunes a todos los motores (agente o API), completadas con el perfil."""
    nombres = ', '.join(perfil.nombres_fijos) if perfil.nombres_fijos else '(ninguna lista adicional)'
    tratamiento = {
        'tuteo': 'Usar SIEMPRE tuteo (tu, tienes, sabes, dime, eres). NUNCA voseo (vos, tenes, sabes con tilde, deci, sos). Usted solo para superiores o nobles.',
        'voseo': 'Usar voseo rioplatense (vos, tenes, sabes).',
        'usted': 'Usar usted en el trato formal.',
    }.get(perfil.tratamiento, '')
    return (_plantilla('reglas.md')
            .replace('{REGLAS_USUARIO}', perfil.prompt or f"Translate to natural {perfil.idioma_destino}.")
            .replace('{NOMBRES}', nombres)
            .replace('{TRATAMIENTO}', tratamiento))


def prompt_api(perfil : Perfil) -> str:
    """Mensaje de sistema para traducir por API, parte por parte."""
    return _plantilla('api.md').replace('{IDIOMA}', perfil.idioma_destino).replace('{REGLAS}', reglas(perfil))


def escribir_instrucciones(trabajo : Path, origen : Path, salida : Path, perfil : Perfil) -> Path:
    """Escribe INSTRUCCIONES.txt para el agente traductor a partir de la plantilla y el perfil."""
    manifiesto = json.loads((trabajo / 'manifiesto.json').read_text(encoding='utf-8'))
    comando = f'"{sys.executable}" -m subtrad insertar "{origen.as_posix()}" "{trabajo.as_posix()}" "{salida.as_posix()}"'

    texto = (_plantilla('traductor.md')
             .replace('{IDIOMA}', perfil.idioma_destino)
             .replace('{REGLAS}', reglas(perfil))
             .replace('{TRABAJO}', trabajo.as_posix())
             .replace('{PARTES}', ', '.join(f"{p}.txt" for p in manifiesto['partes']))
             .replace('{COMANDO_INSERTAR}', comando))

    ruta = trabajo / 'INSTRUCCIONES.txt'
    ruta.write_text(texto, encoding='utf-8')

    # El manifiesto recuerda la salida, para saber despues si el capitulo quedo terminado
    manifiesto['salida'] = str(salida)
    (trabajo / 'manifiesto.json').write_text(json.dumps(manifiesto, indent=1), encoding='utf-8')
    return ruta


def leer_lineas(texto : str, nombre : str = '') -> tuple[dict[int, str], list[str]]:
    """Lineas "[id] texto" -> {id: texto}, mas los errores de formato encontrados."""
    traducciones : dict[int, str] = {}
    errores : list[str] = []
    for linea in texto.splitlines():
        if not linea.strip():
            continue
        coincidencia = LINEA_TRADUCIDA.match(linea.strip())
        if not coincidencia:
            errores.append(f"{nombre}: linea sin [id]: {linea[:60]}".lstrip(': '))
            continue
        traducciones[int(coincidencia.group(1))] = coincidencia.group(2)
    return traducciones, errores


def leer_traducciones(trabajo : Path, partes : list[str]) -> tuple[dict[int, str], list[str]]:
    """Lee los NNN.out.txt; devuelve {id: texto} y los errores de formato encontrados."""
    traducciones : dict[int, str] = {}
    errores : list[str] = []
    for nombre in partes:
        ruta = trabajo / f"{nombre}.out.txt"
        if not ruta.exists():
            errores.append(f"falta {ruta.name}")
            continue
        leidas, errores_parte = leer_lineas(ruta.read_text(encoding='utf-8-sig'), ruta.name)
        traducciones.update(leidas)
        errores += errores_parte
    return traducciones, errores


def validar(subs : pysubs2.SSAFile, esperados : set[int], traducciones : dict[int, str]) -> list[str]:
    """Errores que impiden insertar: ids faltantes o de mas, tags alterados, etiquetas coladas, lineas pegadas."""
    errores = []
    faltantes = sorted(esperados - traducciones.keys())
    sobrantes = sorted(traducciones.keys() - esperados)
    if faltantes:
        errores.append(f"ids sin traducir: {faltantes[:20]}")
    if sobrantes:
        errores.append(f"ids inesperados: {sobrantes[:20]}")

    for i in sorted(esperados & traducciones.keys()):
        texto = traducciones[i]
        if sorted(TAGS_ASS.findall(subs.events[i].text)) != sorted(TAGS_ASS.findall(texto)):
            errores.append(f"[{i}] tags de estilo alterados")
        if ETIQUETAS_COLADAS.search(texto):
            errores.append(f"[{i}] tiene etiquetas Original/Translation")
        if LINEA_TRADUCIDA.search(texto) or regex.search(r'\s\[\d+\]\s', texto):
            errores.append(f"[{i}] parece contener otra linea pegada")
    return errores


def insertar(archivo : Path, trabajo : Path, salida : Path) -> int:
    """Reinserta las partes traducidas y guarda el subtitulo en `salida`.
    Valida ids, tags de estilo y restos de formato; si algo falla no escribe nada y lanza ErrorInsercion."""
    manifiesto = json.loads((trabajo / 'manifiesto.json').read_text(encoding='utf-8'))
    subs = cargar(archivo)
    traducciones, errores = leer_traducciones(trabajo, manifiesto['partes'])
    errores += validar(subs, set(manifiesto['eventos']), traducciones)
    if errores:
        raise ErrorInsercion(errores)

    for i, texto in traducciones.items():
        subs.events[i].text = texto
    subs.save(str(salida), encoding='utf-8')
    return len(traducciones)
