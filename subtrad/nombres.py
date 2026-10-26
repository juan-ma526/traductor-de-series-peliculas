"""Busca nombres propios en los subtitulos originales para armar o completar el perfil de una serie."""
import collections
from pathlib import Path

import regex

from subtrad.archivos import cargar
from subtrad.partes import eventos_traducibles
from subtrad.perfil import Perfil

NOMBRE = regex.compile(r"\b[A-Z][a-z]+(?:[ -][A-Z][a-z]+)*\b")
PALABRA = regex.compile(r"\b[a-z]+\b")

# Palabras que suelen ir con mayuscula sin ser nombres
COMUNES = {
    'I', 'Mr', 'Mrs', 'Ms', 'Sir', 'Lord', 'Lady', 'King', 'Queen', 'General', 'Captain', 'Commander', 'Your', 'His', 'Her',
    'Highness', 'Majesty', 'Okay', 'Oh', 'Hey', 'Yes', 'No', 'Huh', 'Wait', 'Damn', 'Next',
    'Tch', 'Hmph', 'Heh', 'Ugh', 'Gah', 'Whoa', 'Ah', 'Eh', 'Hm', 'Hmm',
}

# Palabras genericas que acompañan a un nombre: "Fei Xin Force" es "Fei Xin" + "Force"
GENERICAS = regex.compile(r'\s+(Force|Unit|Army|Gang|Squad|Corps|Pass|River|Castle|Fortress|Mountains?|Plains?|Hill|Clan|Family)$')


def candidatos(originales : list[Path], perfil : Perfil|None = None, minimo : int = 4) -> list[tuple[str, int]]:
    """Palabras con mayuscula que nunca aparecen en minuscula (probables nombres) y que el perfil no cubre."""
    textos = []
    for archivo in originales:
        subs = cargar(archivo)
        textos += [subs.events[i].plaintext.replace('\n', ' ') for i in eventos_traducibles(subs)]
    texto = ' '.join(textos)

    en_minuscula = set(PALABRA.findall(texto))
    conocidos = set()
    if perfil:
        conocidos = set(perfil.nombres_fijos) | set(perfil.mapear) | set(perfil.mapear.values()) | set(perfil.ambiguos) | set(perfil.unidades)
        conocidos.add(perfil.serie)

    conteo = collections.Counter(NOMBRE.findall(texto))
    resultado = []
    for nombre, n in conteo.most_common():
        primera = nombre.split()[0].split('-')[0]
        sin_generica = GENERICAS.sub('', nombre)
        if n < minimo or nombre in conocidos or sin_generica in conocidos or primera in COMUNES or primera.lower() in en_minuscula:
            continue
        resultado.append((nombre, n))
    return resultado
