from pathlib import Path

from subtrad import archivos


def test_ruta_salida_reemplaza_o_agrega_el_codigo():
    assert archivos.ruta_salida(Path('ep.en.ass'), 'es').name == 'ep.es.ass'
    assert archivos.ruta_salida(Path('ep.srt'), 'es').name == 'ep.es.srt'
    assert archivos.ruta_salida(Path('[HGS]_Kingdom_S3E01_[BD1080].en.ass'), 'es').name == '[HGS]_Kingdom_S3E01_[BD1080].es.ass'


def test_temporada_en_distintos_formatos_de_nombre():
    assert archivos.temporada(Path('[HGS-Renc]_Kingdom_S3E01_[BD1080][AV1].es.ass')) == 3
    assert archivos.temporada(Path('[HGS-Renc]_Kingdom_S05E12_[BD1080][AV1].es.ass')) == 5
    assert archivos.temporada(Path('[SubsPlease] Kingdom S6 - 01 (1080p) [843B9F19].es.ass')) == 6
    assert archivos.temporada(Path('pelicula.es.srt')) is None


def test_pendientes_omite_traducciones_y_marca_las_existentes(tmp_path):
    for nombre in ('a.en.ass', 'a.es.ass', 'b.en.ass', 'c.srt'):
        (tmp_path / nombre).write_text('', encoding='utf-8')

    resultado = {p.origen.name: p.ya_traducido for p in archivos.pendientes(tmp_path, 'es')}
    assert resultado == {'a.en.ass': True, 'b.en.ass': False, 'c.srt': False}


def test_cargar_detecta_encoding_latin1(tmp_path):
    ruta = tmp_path / 'viejo.srt'
    ruta.write_bytes('1\r\n00:00:01,000 --> 00:00:02,000\r\nÉcho Company\r\n'.encode('cp1252'))
    assert archivos.cargar(ruta).events[0].plaintext == 'Écho Company'
