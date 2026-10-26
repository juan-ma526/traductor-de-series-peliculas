"""Aplica el perfil de una serie a subtitulos ya traducidos: nombres, unidades y reemplazos fijos.

Reglas aprendidas a la fuerza:
- Solo se toca el texto; en ASS nunca el estilo ni el actor (un estilo "Quanrong Language" se rompia).
- Los nombres van de mayor a menor largo ("He Liao Diao" antes que "Diao").
- Un nombre puede venir pegado a un salto de linea ASS (\\N), donde \\b no ve el inicio de palabra.
- Los carteles suelen ir en mayusculas ("HANDAN" -> "KANTAN").
- Los nombres ambiguos solo se reemplazan en las temporadas indicadas en el perfil.
"""
import collections
from pathlib import Path

import regex

from subtrad.archivos import temporada as temporada_de
from subtrad.perfil import Perfil

# Inicio de palabra que tambien acepta un salto de linea ASS (\N) justo antes
INICIO = r'(?:(?<=\\[Nn])|(?<!\w))'
NOMBRE_PROPIO = r"[A-Z][a-z]+(?: [A-Z][a-z]+)*"
TIEMPO_O_NUMERO = regex.compile(r'^\d+$|-->|^WEBVTT')

Regla = tuple[regex.Pattern, str]


def reglas_nombres(mapeo : dict[str, str], mapeo_regex : dict[str, str]) -> list[Regla]:
    """Reglas de nombres, de mayor a menor largo, cada una tambien en mayusculas."""
    reglas : list[Regla] = []
    for origen, destino in sorted(mapeo.items(), key=lambda par: -len(par[0])):
        reglas.append((regex.compile(rf'{INICIO}{regex.escape(origen)}\b'), destino))
        if origen.upper() != origen:
            reglas.append((regex.compile(rf'{INICIO}{regex.escape(origen.upper())}\b'), destino.upper()))
    for patron, destino in mapeo_regex.items():
        reglas.append((regex.compile(rf'{INICIO}(?:{patron})\b'), destino))
    return reglas


def reglas_unidades(unidades : list[str]) -> list[Regla]:
    """"Hi Shin Force" / "Fuerza Hi Shin" -> "Unidad Hi Shin"; "X's Army" -> "el ejercito de X"."""
    reglas : list[Regla] = []
    for nombre in sorted(unidades, key=len, reverse=True):
        n = regex.escape(nombre)
        reglas.append((regex.compile(rf'{INICIO}(?:{n} (?:Force|Unit|Army)|[Ff]uerza {n}|unidad {n})\b'), f"Unidad {nombre}"))
    reglas.append((regex.compile(rf"{INICIO}(?:[Ll]a |[Ee]l )?({NOMBRE_PROPIO})'s Army\b"), r"el ejército de \1"))
    reglas.append((regex.compile(rf"{INICIO}(?:[Ll]a |[Ee]l )?({NOMBRE_PROPIO})'s (?:Unit|Force)\b"), r"la unidad de \1"))
    return reglas


def reglas_reemplazos(reemplazos : dict[str, str]) -> list[Regla]:
    return [(regex.compile(rf'{INICIO}{regex.escape(k)}(?!\w)'), v) for k, v in sorted(reemplazos.items(), key=lambda par: -len(par[0]))]


def aplicar_reglas(texto : str, reglas : list[Regla], conteo : collections.Counter) -> str:
    for patron, reemplazo in reglas:
        texto, n = patron.subn(reemplazo, texto)
        if n:
            conteo[reemplazo] += n

    # "el ejército de X" al comienzo de una frase
    return regex.sub(r'(^|\\N|[.!?¡¿] )el ejército de', lambda m: m.group(1) + 'El ejército de', texto)


def procesar_texto(contenido : str, es_ass : bool, reglas : list[Regla], conteo : collections.Counter) -> str:
    """Aplica las reglas solo al texto visible de un archivo ASS o SRT/VTT."""
    lineas = contenido.split('\n')
    for i, linea in enumerate(lineas):
        if es_ass:
            if not linea.startswith('Dialogue:'):
                continue
            campos = linea.split(',', 9)
            if len(campos) == 10:
                lineas[i] = ','.join(campos[:9] + [aplicar_reglas(campos[9], reglas, conteo)])
        elif linea.strip() and not TIEMPO_O_NUMERO.search(linea.strip()):
            lineas[i] = aplicar_reglas(linea, reglas, conteo)
    return '\n'.join(lineas)


def aplicar_perfil(archivo : Path, perfil : Perfil, temporada : int|None = None) -> collections.Counter:
    """Aplica el perfil a un subtitulo traducido, en el lugar. Devuelve cuantas veces se aplico cada reemplazo."""
    temporada = temporada if temporada is not None else temporada_de(archivo)
    reglas = (reglas_nombres(perfil.mapeo_para(temporada), perfil.mapear_regex)
              + reglas_unidades(perfil.unidades)
              + reglas_reemplazos(perfil.reemplazos))

    conteo : collections.Counter = collections.Counter()
    contenido = archivo.read_text(encoding='utf-8-sig')
    nuevo = procesar_texto(contenido, archivo.suffix.lower() in ('.ass', '.ssa'), reglas, conteo)
    if nuevo != contenido:
        archivo.write_text(nuevo, encoding='utf-8')
    return conteo
