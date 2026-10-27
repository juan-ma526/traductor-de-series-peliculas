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
    # Copias de un cartel (mismo estilo y texto, otra posicion): id de la copia -> id que se traduce
    duplicados : dict[str, int] = field(default_factory=dict)


# Tags de un cartel ubicado o animado en pantalla (no es un dialogo comun)
POSICIONADO = regex.compile(r'\\(?:pos|move|clip|iclip|org)\(|\\t\(')


def una_linea(texto : str) -> str:
    """Cada subtitulo en una sola linea, usando el salto de linea de ASS."""
    return texto.replace('\r', '').replace('\n', '\\N')


def estilos_decorativos(subs : pysubs2.SSAFile) -> set[str]:
    """Estilos de karaoke silaba por silaba: la mayoria de sus lineas tienen 3 letras o menos.
    Caso real (Eminence in Shadow): "neo shadow OE" / "neo shadow OR", ~1800 silabas del opening por capitulo."""
    textos : dict[str, list[str]] = {}
    for evento in subs.events:
        if not evento.is_comment and evento.plaintext.strip():
            textos.setdefault(evento.style, []).append(evento.plaintext.strip())

    def mediana_corta(lista : list[str]) -> bool:
        largos = sorted(len(t) for t in lista)
        return largos[len(largos) // 2] <= 3

    decorativos = {estilo for estilo, lista in textos.items()
                   if len(lista) >= 20 and (mediana_corta(lista) or mediana_corta(list(set(lista))))}
    # Variantes numeradas de un estilo decorativo ("neo shadow OR2" de "neo shadow OR") tambien lo son
    familias = {regex.sub(r'\d+$', '', e).strip() for e in decorativos}
    return decorativos | {e for e in textos if regex.sub(r'\d+$', '', e).strip() in familias}


def eventos_traducibles(subs : pysubs2.SSAFile) -> list[int]:
    """Indices de los eventos con texto visible.
    Se omiten comentarios, dibujos ASS y canciones (karaoke o estilos de OP/ED), que quedan como estan."""
    decorativos = estilos_decorativos(subs)
    indices = []
    for i, evento in enumerate(subs.events):
        if evento.is_comment or DIBUJO_ASS.search(evento.text):
            continue
        if KARAOKE.search(evento.text) or ESTILO_CANCION.search(evento.style) or evento.style in decorativos:
            continue
        if evento.plaintext.strip():
            indices.append(i)
    return indices


def eventos_de_dialogo(subs : pysubs2.SSAFile) -> list[int]:
    """Traducibles que no son carteles ubicados en pantalla: sirven para detectar idioma y sincronia
    sin que miles de carteles animados cuadro por cuadro tapen los dialogos."""
    return [i for i in eventos_traducibles(subs) if not POSICIONADO.search(subs.events[i].text)]


def _agrupar_copias(subs : pysubs2.SSAFile, indices : list[int]) -> tuple[list[int], dict[str, int]]:
    """Un cartel que sigue el movimiento de la camara se repite cuadro por cuadro con el mismo texto.
    Se traduce una sola vez y se copia (caso real: "Deceased ~ Kageno Minoru (18)", 51 copias)."""
    primero : dict[tuple[str, str], int] = {}
    unicos, duplicados = [], {}
    for i in indices:
        evento = subs.events[i]
        if not POSICIONADO.search(evento.text):
            unicos.append(i)
            continue
        clave = (evento.style, evento.plaintext.strip())
        if clave in primero:
            duplicados[str(i)] = primero[clave]
        else:
            primero[clave] = i
            unicos.append(i)
    return unicos, duplicados


def preparar(archivo : Path, trabajo : Path, lineas_por_parte : int = LINEAS_POR_PARTE) -> Manifiesto:
    """Escribe 001.txt, 002.txt... con lineas "[id] texto" y un manifiesto.json en la carpeta de trabajo."""
    subs = cargar(archivo)
    indices, duplicados = _agrupar_copias(subs, eventos_traducibles(subs))
    trabajo.mkdir(parents=True, exist_ok=True)

    manifiesto = Manifiesto(str(archivo), indices, duplicados=duplicados)
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


CURSIVA = regex.compile(r'\{\\i[01]?\}')
OTROS_ALFABETOS = regex.compile(r'[\p{Cyrillic}\p{Han}\p{Hiragana}\p{Katakana}\p{Hangul}\p{Arabic}]')


def _toda_en_cursiva(texto : str) -> bool:
    """Cada renglon (separado por \\N) esta envuelto en {\\i1}...{\\i} o {\\i0}, sin otros tags."""
    renglones = texto.split('\\N')
    return all(regex.fullmatch(r'\{\\i1\}[^{}]*\{\\i0?\}', r.strip()) for r in renglones)


def reparar(subs : pysubs2.SSAFile, traducciones : dict[int, str]) -> dict[int, str]:
    """Arreglos mecanicos antes de validar.
    Lineas enteras en cursiva (un par de tags por renglon): los modelos suelen dejar un solo par para toda la linea.
    Error frecuente en Kingdom y Escaflowne; se rearma igual que el original."""
    reparadas = dict(traducciones)
    for i, texto in traducciones.items():
        original = subs.events[i].text
        if i < len(subs.events) and _toda_en_cursiva(original) and not _toda_en_cursiva(texto):
            cierre = '{\\i0}' if '{\\i0}' in original else '{\\i}'
            limpio = CURSIVA.sub('', texto)
            if not TAGS_ASS.search(limpio):
                reparadas[i] = '\\N'.join(f'{{\\i1}}{r}{cierre}' for r in limpio.split('\\N'))
    return reparadas


ERROR_CURSIVAS = 'cursivas alteradas'
ERROR_TAGS = 'tags de estilo alterados'
TAGS_INICIALES = regex.compile(r'^(?:\{[^}]*\})+')


def forzar_tags(original : str, traduccion : str) -> str:
    """Ultimo recurso cuando el modelo no logra ubicar los tags: tags iniciales del original + texto traducido +
    los tags intermedios al final (donde ya no afectan a nada).
    Conserva posicion, fuente y color base; solo se pierde, por ejemplo, el color distinto de una palabra.
    Caso real (Escaflowne): carteles de titulo "The Secret {\\3c..}Door" con una palabra de otro color."""
    inicio = TAGS_INICIALES.match(original)
    iniciales = inicio.group(0) if inicio else ''
    intermedios = ''.join(TAGS_ASS.findall(original[len(iniciales):]))
    return iniciales + TAGS_ASS.sub('', traduccion).strip() + intermedios


def _tags(texto : str, sin_cursivas : bool = False) -> list[str]:
    """Tags de estilo normalizados: {\\i0} y {\\i} cierran la cursiva igual."""
    tags = [t.replace('{\\i0}', '{\\i}') for t in TAGS_ASS.findall(texto)]
    if sin_cursivas:
        tags = [t for t in tags if not CURSIVA.fullmatch(t)]
    return sorted(tags)


def validar(subs : pysubs2.SSAFile, esperados : set[int], traducciones : dict[int, str],
            tolerar_cursivas : bool = False) -> list[str]:
    """Errores que impiden insertar: ids faltantes o de mas, tags alterados, etiquetas coladas, lineas pegadas.
    Con tolerar_cursivas, una cursiva movida o perdida no es error (solo los demas tags: posicion, color, animacion)."""
    errores = []
    faltantes = sorted(esperados - traducciones.keys())
    sobrantes = sorted(traducciones.keys() - esperados)
    if faltantes:
        errores.append(f"ids sin traducir: {faltantes[:20]}")
    if sobrantes:
        errores.append(f"ids inesperados: {sobrantes[:20]}")

    for i in sorted(esperados & traducciones.keys()):
        texto = traducciones[i]
        original = subs.events[i].text
        if _tags(original, sin_cursivas=True) != _tags(texto, sin_cursivas=True):
            errores.append(f"[{i}] {ERROR_TAGS}")
        elif not tolerar_cursivas and _tags(original) != _tags(texto):
            errores.append(f"[{i}] {ERROR_CURSIVAS}")
        if ETIQUETAS_COLADAS.search(texto):
            errores.append(f"[{i}] tiene etiquetas Original/Translation")
        if LINEA_TRADUCIDA.search(texto) or regex.search(r'\s\[\d+\]\s', texto):
            errores.append(f"[{i}] parece contener otra linea pegada")
        # Error real (Escaflowne E18): el modelo metio caracteres chinos en medio de una frase
        if OTROS_ALFABETOS.search(texto) and not OTROS_ALFABETOS.search(subs.events[i].text):
            errores.append(f"[{i}] tiene caracteres de otro alfabeto")
    return errores


def insertar(archivo : Path, trabajo : Path, salida : Path) -> int:
    """Reinserta las partes traducidas y guarda el subtitulo en `salida`.
    Valida ids, tags de estilo y restos de formato; si algo falla no escribe nada y lanza ErrorInsercion."""
    manifiesto = json.loads((trabajo / 'manifiesto.json').read_text(encoding='utf-8'))
    subs = cargar(archivo)
    traducciones, errores = leer_traducciones(trabajo, manifiesto['partes'])
    traducciones = reparar(subs, traducciones)
    errores += validar(subs, set(manifiesto['eventos']), traducciones, manifiesto.get('tolerar_cursivas', False))
    if errores:
        raise ErrorInsercion(errores)

    for i, texto in traducciones.items():
        subs.events[i].text = texto

    # Copias de carteles: el texto traducido con los tags (posicion de ese cuadro) de cada copia
    for copia, original in manifiesto.get('duplicados', {}).items():
        evento = subs.events[int(copia)]
        if original in traducciones:
            evento.text = forzar_tags(evento.text, traducciones[original])
    subs.save(str(salida), encoding='utf-8')
    return len(traducciones) + len(manifiesto.get('duplicados', {}))
