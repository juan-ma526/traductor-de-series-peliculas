import io
import zipfile

import pytest

from subtrad import conseguir, fuentes, sincronizar, subdl


def _zip(archivos : dict[str, str]) -> bytes:
    contenido = io.BytesIO()
    with zipfile.ZipFile(contenido, 'w') as z:
        for nombre, texto in archivos.items():
            z.writestr(nombre, texto)
    return contenido.getvalue()


def test_titulo_y_año():
    assert fuentes.titulo_y_año('Catch Me If You Can (2002)') == ('Catch Me If You Can', 2002)
    assert fuentes.titulo_y_año('Ted Lasso') == ('Ted Lasso', None)


def test_zip_de_temporada_elige_el_episodio():
    # Subdl: paquetes de temporada completa con un archivo por episodio
    contenido = _zip({'Ted.Lasso.S02E01.srt': 'uno', 'Ted.Lasso.S02E10.srt': 'diez', 'leeme.txt': 'x'})
    assert fuentes.elegir_de_zip(contenido, 2, 10) == ('Ted.Lasso.S02E10.srt', b'diez')
    with pytest.raises(fuentes.ErrorFuente):
        fuentes.elegir_de_zip(contenido, 2, 5)


def test_zip_de_pelicula_elige_el_mas_grande():
    contenido = _zip({'peli.forced.srt': 'corto', 'peli.srt': 'el subtitulo completo'})
    assert fuentes.elegir_de_zip(contenido, None, None)[0] == 'peli.srt'


def test_guardar_ignora_rutas_del_zip(tmp_path):
    ruta = fuentes.guardar(b'x', '../../fuera/peli.srt', tmp_path, 'subdl')
    assert ruta.parent == tmp_path


def test_subdl_descarta_otros_episodios(monkeypatch):
    respuesta = {'status': True, 'subtitles': [
        {'url': '/a.zip', 'release_name': 'S02 completa', 'episode': None, 'full_season': True, 'hi': False},
        {'url': '/b.zip', 'release_name': 'S02E03', 'episode': 3, 'full_season': False, 'hi': False},
        {'url': '/c.zip', 'release_name': 'S02E01 SDH', 'episode': 1, 'full_season': False, 'hi': True},
        {'url': '/d.zip', 'release_name': 'S02E01', 'episode': 1, 'full_season': False, 'hi': False},
    ]}
    monkeypatch.setattr(subdl, 'pedir_json', lambda url: respuesta)
    resultados = subdl.Cliente('clave').buscar('Ted Lasso', 2, 1)
    assert [r.id for r in resultados] == ['/d.zip', '/c.zip', '/a.zip']


class FuenteFalsa:
    """Fuente que devuelve un resultado por llamado, o se queda sin cupo."""
    def __init__(self, nombre : str, agotada : bool = False):
        self.nombre, self.agotada, self.descargadas = nombre, agotada, 0

    def buscar(self, consulta, temporada, episodio, idioma='en', video=None):
        return [fuentes.Resultado(id='1', release=f'{self.nombre}-release')]

    def descargar(self, resultado, carpeta):
        if self.agotada:
            raise fuentes.LimiteAgotado('sin cupo')
        self.descargadas += 1
        ruta = carpeta / f'{self.nombre}.srt'
        ruta.write_text('1\n00:00:01,000 --> 00:00:02,000\nHello.\n', encoding='utf-8')
        return ruta


def test_sigue_con_la_proxima_fuente_si_una_se_agota(tmp_path, monkeypatch):
    video = tmp_path / 'Serie - S01E01.mkv'
    video.write_bytes(b'')
    monkeypatch.setattr(sincronizar, 'extraer_audio', lambda *args: tmp_path / 'audio.wav')
    monkeypatch.setattr(conseguir, '_pistas_del_video', lambda *args: [])
    monkeypatch.setattr(sincronizar, 'verificar', lambda audio, ruta, carpeta: sincronizar.Verificacion(sincronizar.ENCAJA, 0, 1))

    agotada, segunda, tercera = FuenteFalsa('opensubtitles', agotada=True), FuenteFalsa('subdl'), FuenteFalsa('gestdown')
    resultado = conseguir.conseguir_video(video, 'en', 'Serie', [agotada, segunda, tercera])

    assert resultado.salida is not None and resultado.salida.exists()
    assert resultado.elegido is not None and resultado.elegido.origen.startswith('subdl')
    assert tercera.descargadas == 0
