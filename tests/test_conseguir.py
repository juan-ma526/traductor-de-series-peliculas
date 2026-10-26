from pathlib import Path

import pysubs2
import pytest

from subtrad import conseguir, sincronizar
from subtrad.opensubtitles import hash_video


def test_temporada_y_episodio():
    assert conseguir.temporada_y_episodio(Path('World.Is.Dancing.S01E10.1080p.mkv')) == (1, 10)
    assert conseguir.temporada_y_episodio(Path('[HGS-Renc]_Kingdom_S3E01_[BD1080].mkv')) == (3, 1)
    assert conseguir.temporada_y_episodio(Path('[SubsPlease] Kingdom S6 - 02 (1080p).mkv')) == (6, 2)
    assert conseguir.temporada_y_episodio(Path('pelicula.mkv')) == (None, None)


def test_limpiar_sdh(tmp_path):
    ruta = tmp_path / 'ep.en.srt'
    ruta.write_text('1\n00:00:01,000 --> 00:00:02,000\n[somber music]\n\n'
                    '2\n00:00:03,000 --> 00:00:04,000\n- All things must\ncome to an end. [sighs]\n', encoding='utf-8')
    assert conseguir.es_sdh(ruta)
    conseguir.limpiar_sdh(ruta)
    eventos = pysubs2.load(str(ruta)).events
    assert [e.plaintext for e in eventos] == ['- All things must\ncome to an end.']


def test_hash_video_es_estable(tmp_path):
    ruta = tmp_path / 'video.mkv'
    ruta.write_bytes(bytes(range(256)) * 1024)
    assert hash_video(ruta) == hash_video(ruta)
    assert len(hash_video(ruta)) == 16


def _subtitulo(tmp_path : Path, inicios : list[int]) -> Path:
    subs = pysubs2.SSAFile()
    for i, inicio in enumerate(inicios):
        subs.append(pysubs2.SSAEvent(start=inicio, end=inicio + 1500, text=f'Linea {i}'))
    ruta = tmp_path / 'candidato.srt'
    subs.save(str(ruta))
    return ruta


@pytest.mark.parametrize('movimientos, esperado', [
    ([100] * 20, sincronizar.ENCAJA),                              # ya estaba bien
    ([3500] * 20, sincronizar.CORRIDO),                            # corrido parejo: se corrige
    ([(-1) ** i * 20000 + i * 3000 for i in range(20)], sincronizar.NO_ENCAJA),   # otro contenido
])
def test_verificar_clasifica_segun_lo_que_mueve_alass(tmp_path, monkeypatch, movimientos, esperado):
    original = _subtitulo(tmp_path, [i * 5000 + 30000 for i in range(20)])

    # alass simulado: escribe la salida moviendo cada linea lo indicado
    def alass_falso(comando, **_kwargs):
        subs = pysubs2.load(comando[2])
        for evento, movimiento in zip(subs.events, movimientos):
            evento.start += movimiento
            evento.end += movimiento
        subs.save(comando[3])

    monkeypatch.setattr(sincronizar, 'ruta_alass', lambda: 'alass')
    monkeypatch.setattr(sincronizar.subprocess, 'run', alass_falso)
    resultado = sincronizar.verificar(tmp_path / 'audio.wav', original, tmp_path)
    assert resultado.estado == esperado
