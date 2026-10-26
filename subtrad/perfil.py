"""Perfil de una serie: idioma, reglas de traduccion y glosario, cargados desde YAML."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class PerfilInvalido(Exception):
    """El archivo de perfil no tiene el formato esperado."""


@dataclass
class Perfil:
    """Todo lo especifico de una serie que no es codigo."""
    serie : str
    año : int|None = None
    tipo : str = ''
    idioma_destino : str = 'Latin American Spanish'
    codigo : str = 'es'
    prompt : str = ''
    tratamiento : str = 'tuteo'
    nombres_fijos : list[str] = field(default_factory=list)

    # Reemplazos de nombres despues de traducir: siempre (mapear) o solo en ciertas temporadas (ambiguos)
    mapear : dict[str, str] = field(default_factory=dict)
    mapear_regex : dict[str, str] = field(default_factory=dict)
    ambiguos : dict[str, dict[int, str]] = field(default_factory=dict)

    # Unidades militares cuyo nombre se conserva y se antepone "Unidad"
    unidades : list[str] = field(default_factory=list)
    reemplazos : dict[str, str] = field(default_factory=dict)

    def mapeo_para(self, temporada : int|None) -> dict[str, str]:
        """Nombres a reemplazar en una temporada: los fijos mas los ambiguos que corresponden."""
        mapeo = dict(self.mapear)
        if temporada is not None:
            for nombre, por_temporada in self.ambiguos.items():
                if temporada in por_temporada:
                    mapeo[nombre] = por_temporada[temporada]
        return mapeo


def _temporadas(clave : str|int) -> list[int]:
    """'1' -> [1], '2-4' -> [2, 3, 4]."""
    texto = str(clave).strip()
    if '-' in texto:
        inicio, fin = (int(x) for x in texto.split('-', 1))
        return list(range(inicio, fin + 1))
    return [int(texto)]


def cargar_perfil(ruta : Path) -> Perfil:
    """Lee un perfil YAML (ver series/kingdom-2012.yaml)."""
    datos = yaml.safe_load(ruta.read_text(encoding='utf-8')) or {}
    if not isinstance(datos, dict) or 'serie' not in datos:
        raise PerfilInvalido(f"{ruta}: falta la clave 'serie'")

    ambiguos : dict[str, dict[int, str]] = {}
    for nombre, por_temporada in (datos.get('ambiguos') or {}).items():
        ambiguos[nombre] = {t: valor for clave, valor in por_temporada.items() for t in _temporadas(clave)}

    return Perfil(
        serie=datos['serie'],
        año=datos.get('año'),
        tipo=datos.get('tipo', ''),
        idioma_destino=datos.get('idioma_destino', 'Latin American Spanish'),
        codigo=datos.get('codigo', 'es'),
        prompt=(datos.get('prompt') or '').strip(),
        tratamiento=datos.get('tratamiento', 'tuteo'),
        nombres_fijos=list(datos.get('nombres_fijos') or []),
        mapear=dict(datos.get('mapear') or {}),
        mapear_regex=dict(datos.get('mapear_regex') or {}),
        ambiguos=ambiguos,
        unidades=list(datos.get('unidades') or []),
        reemplazos=dict(datos.get('reemplazos') or {}),
    )
