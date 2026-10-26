"""Controles de calidad de un subtitulo traducido, comparandolo con su original.

Cada control sale de un error real encontrado traduciendo Kingdom:
lineas corridas, bloques sin traducir, etiquetas de otras herramientas coladas, voseo, nombres sin adaptar,
caracteres de otros alfabetos y estilos inexistentes.
"""
import math
import statistics
from dataclasses import dataclass
from pathlib import Path

import pysubs2
import regex

from subtrad.archivos import cargar, ruta_original, temporada as temporada_de
from subtrad.partes import ETIQUETAS_COLADAS, eventos_traducibles
from subtrad.perfil import Perfil
from subtrad.postproceso import INICIO

GRAVE = 'grave'
AVISO = 'aviso'

INGLES = regex.compile(r"\b(the|you|and|what|this|that|is|are|we|it's|don't|I'm|of|to|your|have|will)\b", regex.IGNORECASE)
ESPANOL = regex.compile(r'\b(el|la|los|las|que|de|y|es|no|un|una|por|con|se|lo|su|mi|tu|yo)\b', regex.IGNORECASE)
VOSEO = regex.compile(r'\b(vos|sos|tenés|sabés|querés|podés|decí|mirá|escuchá|vení|andá|hacé|esperá|fijate|dejame|decime|permitime|creés)\b', regex.IGNORECASE)
# Vocabulario de España que no va en español latinoamericano ("vale" solo como interjeccion suelta)
ESPAÑOLISMOS = regex.compile(r'\b(vosotr[oa]s|vuestr[oa]s?|habéis|tenéis|sabéis|queréis|podéis|melocot[oó]n(es)?|ordenador(es)?|zumo|gafas|chaval(es)?|gilipollas|guay)\b|(^|[.!?¡¿,] ?)[Vv]ale[.!?,]', regex.IGNORECASE)
OTROS_ALFABETOS =regex.compile(r'[\p{Cyrillic}\p{Han}\p{Hiragana}\p{Katakana}\p{Hangul}\p{Arabic}]')
TAGS = regex.compile(r'\{[^}]*\}')

# Una linea es sospechosa de estar corrida si su largo difiere mucho del original
RAZON_MAXIMA = 2.6
RAZON_MINIMA = 0.35
LARGO_MINIMO = 20
VENTANA = 6


@dataclass
class Problema:
    """Algo a revisar en un subtitulo traducido."""
    tipo : str
    gravedad : str
    detalle : str
    linea : int|None = None


def _texto(evento : pysubs2.SSAEvent) -> str:
    return evento.plaintext.replace('\n', ' ').strip()


def _sospechosa(original : str, traducida : str) -> bool:
    largo_o, largo_t = len(original), len(traducida)
    if max(largo_o, largo_t) < LARGO_MINIMO:
        return False
    razon = largo_t / max(largo_o, 1)
    return razon > RAZON_MAXIMA or razon < RAZON_MINIMA


def _costo(largos_o : list[float], largos_t : list[float], inicio : int, fin : int, desplazamiento : int) -> float:
    """Que tan mal encajan los largos traducidos con los originales desplazados."""
    costo, n = 0.0, 0
    for j in range(inicio, fin):
        k = j + desplazamiento
        if 0 <= k < len(largos_o):
            costo += abs(largos_t[j] - largos_o[k])
            n += 1
    return costo / n if n else float('inf')


def lineas_corridas(original : pysubs2.SSAFile, traducido : pysubs2.SSAFile) -> list[int]:
    """Indices donde la traduccion encaja mejor con la linea vecina del original que con la propia.
    Con largos en escala logaritmica, en ventanas de 6 lineas: detecta frases unidas o partidas que corren todo lo que sigue."""
    largos_o = [math.log(len(_texto(e)) + 4) for e in original.events]
    largos_t = [math.log(len(_texto(e)) + 4) for e in traducido.events]
    corridas = set()
    for inicio in range(0, max(len(largos_t) - VENTANA + 1, 0)):
        fin = inicio + VENTANA
        propio = _costo(largos_o, largos_t, inicio, fin, 0)
        vecino = min(_costo(largos_o, largos_t, inicio, fin, -1), _costo(largos_o, largos_t, inicio, fin, 1))
        if propio > 0.25 and vecino < propio * 0.5:
            corridas.update(range(inicio, fin))
    return sorted(corridas)


def _rangos(indices : list[int]) -> list[tuple[int, int]]:
    rangos : list[tuple[int, int]] = []
    for i in indices:
        if rangos and i == rangos[-1][1] + 1:
            rangos[-1] = (rangos[-1][0], i)
        else:
            rangos.append((i, i))
    return rangos


def revisar_alineacion(original : pysubs2.SSAFile, traducido : pysubs2.SSAFile) -> list[Problema]:
    """Mismo numero de eventos: busca tramos corridos y lineas sueltas con un largo muy distinto al original."""
    problemas = []
    corridas = lineas_corridas(original, traducido)
    for inicio, fin in _rangos(corridas):
        problemas.append(Problema('corrimiento', GRAVE, f"lineas {inicio}-{fin} parecen corridas respecto del original", inicio))

    for i, (o, t) in enumerate(zip(original.events, traducido.events)):
        if i not in corridas and _sospechosa(_texto(o), _texto(t)):
            problemas.append(Problema('largo_raro', AVISO, f"largo muy distinto al original: {_texto(t)[:50]!r}", i))
    return problemas


def revisar_sincronizacion(original : pysubs2.SSAFile, traducido : pysubs2.SSAFile) -> list[Problema]:
    """Distinto numero de eventos (otra fuente o lineas partidas): compara los tiempos de inicio."""
    inicios = [e.start for e in original.events if e.plaintext.strip()]
    if not inicios:
        return []
    distancias = [min(abs(e.start - s) for s in inicios) for e in traducido.events if e.plaintext.strip()]
    mediana = statistics.median(distancias) if distancias else 0
    if mediana > 500:
        return [Problema('desincronizado', GRAVE, f"los tiempos difieren del original en {mediana:.0f} ms de mediana")]
    return []


def revisar_sin_traducir(original : pysubs2.SSAFile, traducido : pysubs2.SSAFile) -> list[Problema]:
    """Lineas iguales al original que tienen palabras en ingles."""
    textos_originales = {e.text.strip() for e in original.events}
    sin_traducir = [i for i in eventos_traducibles(traducido)
                    if traducido.events[i].text.strip() in textos_originales and INGLES.search(_texto(traducido.events[i]))]
    if not sin_traducir:
        return []
    gravedad = GRAVE if len(sin_traducir) >= 3 else AVISO
    return [Problema('sin_traducir', gravedad, f"{len(sin_traducir)} lineas quedaron en ingles (ej. {_texto(traducido.events[sin_traducir[0]])[:50]!r})", sin_traducir[0])]


def revisar_texto(traducido : pysubs2.SSAFile, perfil : Perfil|None, temporada : int|None) -> list[Problema]:
    """Controles que solo miran el texto traducido."""
    problemas = []
    etiquetas, voseo, ingles, alfabetos, españolismos = [], [], [], [], []
    for i in eventos_traducibles(traducido):
        crudo = traducido.events[i].text
        texto = TAGS.sub('', crudo)
        if ETIQUETAS_COLADAS.search(crudo) or regex.search(r'\b(Original|Translation)[:>]', texto):
            etiquetas.append(i)
        if VOSEO.search(texto):
            voseo.append(i)
        if len(INGLES.findall(texto)) >= 2 and not ESPANOL.search(texto):
            ingles.append(i)
        if OTROS_ALFABETOS.search(texto):
            alfabetos.append(i)
        if ESPAÑOLISMOS.search(texto):
            españolismos.append(i)

    if etiquetas:
        problemas.append(Problema('etiquetas', GRAVE, f"{len(etiquetas)} lineas con etiquetas Original/Translation en pantalla", etiquetas[0]))
    if voseo and (perfil is None or perfil.tratamiento == 'tuteo'):
        problemas.append(Problema('voseo', GRAVE if len(voseo) >= 3 else AVISO, f"{len(voseo)} lineas con voseo", voseo[0]))
    if ingles:
        problemas.append(Problema('ingles', GRAVE if len(ingles) >= 3 else AVISO, f"{len(ingles)} lineas parecen estar en ingles", ingles[0]))
    if alfabetos:
        problemas.append(Problema('alfabeto', AVISO, f"{len(alfabetos)} lineas con caracteres de otros alfabetos", alfabetos[0]))
    latino = perfil is None or 'latin' in perfil.idioma_destino.lower()
    if españolismos and latino:
        problemas.append(Problema('españolismos', AVISO, f"{len(españolismos)} lineas con vocabulario de España (ej. {_texto(traducido.events[españolismos[0]])[:50]!r})", españolismos[0]))

    if perfil:
        restantes = []
        texto_total = '\n'.join(traducido.events[i].text for i in eventos_traducibles(traducido))
        for nombre in sorted(perfil.mapeo_para(temporada), key=len, reverse=True):
            cantidad = len(regex.findall(rf'{INICIO}{regex.escape(nombre)}\b', texto_total))
            if cantidad:
                restantes.append(f"{nombre} ({cantidad})")
        if restantes:
            problemas.append(Problema('nombres', AVISO, "nombres sin adaptar al perfil: " + ', '.join(restantes[:10])))
    return problemas


def revisar_estilos(original : pysubs2.SSAFile|None, traducido : pysubs2.SSAFile) -> list[Problema]:
    """Eventos que usan un estilo inexistente (solo si el original no lo tenia ya)."""
    rotos = {e.style for e in traducido.events if e.style not in traducido.styles}
    if original is not None:
        rotos -= {e.style for e in original.events if e.style not in original.styles}
    return [Problema('estilos', AVISO, f"estilos inexistentes: {', '.join(sorted(rotos))}")] if rotos else []


def revisar_archivo(traducido_ruta : Path, perfil : Perfil|None = None, origen : str = 'en') -> list[Problema]:
    """Todos los controles para un subtitulo traducido. Si encuentra el original al lado, lo usa para comparar."""
    traducido = cargar(traducido_ruta)
    original_ruta = ruta_original(traducido_ruta, origen)
    original = cargar(original_ruta) if original_ruta else None

    problemas : list[Problema] = []
    if original is None:
        problemas.append(Problema('sin_original', AVISO, f"no se encontro el original .{origen}; solo se revisa el texto"))
    elif len(original.events) == len(traducido.events):
        problemas += revisar_alineacion(original, traducido)
    else:
        problemas += revisar_sincronizacion(original, traducido)

    if original is not None:
        problemas += revisar_sin_traducir(original, traducido)
    problemas += revisar_texto(traducido, perfil, temporada_de(traducido_ruta))
    if traducido_ruta.suffix.lower() in ('.ass', '.ssa'):
        problemas += revisar_estilos(original, traducido)
    return problemas
