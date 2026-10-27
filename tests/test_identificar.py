from pathlib import Path

import yaml

from subtrad import identificar
from subtrad.identificar import Candidato


def anilist_falso(_titulo):
    return [
        Candidato('Kingdom', 2012, 'anime', {'Kingdom', 'キングダム'}, {'anilist': 12031}, 38, 'anime TV'),
        Candidato('Gold Kingdom and Water Kingdom', 2023, 'pelicula', {'Kin no Kuni Mizu no Kuni', '金の国'}, {'anilist': 151300}, 1),
        Candidato('ANIA KINGDOM', 2023, 'anime', {'Bouken Tairiku Ania Kingdom', 'アニア'}, {'anilist': 168555}, 39),
    ]


def tvmaze_falso(_titulo):
    return [
        Candidato('Kingdom', 2012, 'anime', {'Kingdom'}, {'tvmaze': 13853}),
        Candidato('Kingdom', 2019, 'serie', {'Kingdom'}, {'tvmaze': 26153}, None, 'Scripted, Korean, Netflix'),
        Candidato('Kingdom', 2014, 'serie', {'Kingdom'}, {'tvmaze': 214}),
    ]


BUSCADORES = [anilist_falso, tvmaze_falso]


def test_pistas_de_carpeta_de_temporada(tmp_path):
    carpeta = tmp_path / 'Kingdom (2012)' / 'Season 4'
    carpeta.mkdir(parents=True)
    pistas = identificar.pistas_de_carpeta(carpeta)
    assert (pistas.titulo, pistas.año) == ('Kingdom', 2012)


def test_sin_año_es_ambiguo(tmp_path):
    carpeta = tmp_path / 'Kingdom'
    carpeta.mkdir()
    resultado = identificar.identificar(carpeta, tmp_path, BUSCADORES)
    assert not resultado.claro
    assert {c.año for c in resultado.candidatos[:3]} == {2012, 2014, 2019}


def test_con_año_queda_claro_y_une_las_fuentes(tmp_path):
    carpeta = tmp_path / 'Kingdom (2012)'
    carpeta.mkdir()
    resultado = identificar.identificar(carpeta, tmp_path, BUSCADORES)
    assert resultado.claro
    assert resultado.candidatos[0].ids == {'anilist': 12031, 'tvmaze': 13853}


def test_titulos_en_japones_no_unen_series_distintas(tmp_path):
    # Error real: dos series con titulo nativo en japones (que normalizado queda vacio) se unian
    carpeta = tmp_path / 'Kingdom'
    carpeta.mkdir()
    resultado = identificar.identificar(carpeta, tmp_path, BUSCADORES)
    oro = next(c for c in resultado.candidatos if c.titulo.startswith('Gold'))
    assert oro.ids == {'anilist': 151300}


def test_usa_el_perfil_existente_aunque_falte_el_articulo(tmp_path):
    perfiles = tmp_path / 'series'
    perfiles.mkdir()
    (perfiles / 'wid.yaml').write_text('serie: World Is Dancing\naño: 2026\n', encoding='utf-8')
    carpeta = tmp_path / 'The World Is Dancing'
    carpeta.mkdir()
    resultado = identificar.identificar(carpeta, perfiles, BUSCADORES)
    assert resultado.perfil == perfiles / 'wid.yaml'


def test_crear_perfil_base(tmp_path):
    ruta = identificar.crear_perfil(Candidato('The Vision of Escaflowne', 1996, 'anime', ids={'anilist': 182}), tmp_path)
    datos = yaml.safe_load(ruta.read_text(encoding='utf-8'))
    assert ruta.name == 'vision-of-escaflowne-1996.yaml'
    assert datos['serie'] == 'The Vision of Escaflowne' and datos['ids'] == {'anilist': 182}
    assert datos['tratamiento'] == 'tuteo'
