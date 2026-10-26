"""Utilidades para crear subtitulos de prueba inventados."""
from pathlib import Path

import pytest

ENCABEZADO_ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1
Style: OP Romaji,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1
Style: Quanrong Language,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ass(eventos : list[tuple[str, str]]) -> str:
    """Arma un ASS con eventos (estilo, texto), uno por segundo."""
    lineas = []
    for i, (estilo, texto) in enumerate(eventos):
        inicio, fin = f"0:00:{i * 2:02d}.00", f"0:00:{i * 2 + 1:02d}.50"
        lineas.append(f"Dialogue: 0,{inicio},{fin},{estilo},,0,0,0,,{texto}")
    return ENCABEZADO_ASS + '\n'.join(lineas) + '\n'


@pytest.fixture
def escribir(tmp_path : Path):
    """Escribe un ASS de prueba en tmp_path y devuelve su ruta."""
    def _escribir(nombre : str, eventos : list[tuple[str, str]]) -> Path:
        ruta = tmp_path / nombre
        ruta.write_text(ass(eventos), encoding='utf-8')
        return ruta
    return _escribir


@pytest.fixture
def perfil_kingdom():
    from subtrad.perfil import cargar_perfil
    return cargar_perfil(Path(__file__).parent.parent / 'series' / 'kingdom-2012.yaml')
