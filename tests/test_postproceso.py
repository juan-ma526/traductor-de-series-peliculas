from pathlib import Path

from subtrad.archivos import cargar
from subtrad.postproceso import aplicar_perfil


def textos(ruta : Path) -> list[str]:
    return [e.text for e in cargar(ruta).events]


def test_nombre_largo_antes_que_sus_partes(escribir, perfil_kingdom):
    # Error real: "He Liao Diao" quedaba "He Liao Ten" porque "Diao" se reemplazaba primero
    ruta = escribir('S5E01.es.ass', [('Default', 'He Liao Diao y Diao.'), ('Default', 'El general Wu Qing.')])
    aplicar_perfil(ruta, perfil_kingdom)
    assert textos(ruta) == ['Karyo Ten y Ten.', 'El general Gokei.']


def test_nombre_despues_de_salto_de_linea(escribir, perfil_kingdom):
    ruta = escribir('S4E01.es.ass', [('Default', 'Vamos a\\NXianyang.')])
    aplicar_perfil(ruta, perfil_kingdom)
    assert textos(ruta) == ['Vamos a\\NKanyou.']


def test_carteles_en_mayusculas(escribir, perfil_kingdom):
    ruta = escribir('S6E01.es.ass', [('Default', '{\\pos(10,10)}HANDAN'), ('Default', 'YA GUANG')])
    aplicar_perfil(ruta, perfil_kingdom)
    assert textos(ruta) == ['{\\pos(10,10)}KANTAN', 'AKOU']


def test_no_toca_el_estilo_ni_el_actor(escribir, perfil_kingdom):
    # Error real: el estilo "Quanrong Language" se habria renombrado y la linea perdia su formato
    ruta = escribir('S6E01.es.ass', [('Quanrong Language', 'Hablan la lengua de Quanrong.')])
    aplicar_perfil(ruta, perfil_kingdom)
    evento = cargar(ruta).events[0]
    assert evento.style == 'Quanrong Language'
    assert evento.text == 'Hablan la lengua de Kenjuu.'


def test_ambiguos_segun_temporada(escribir, perfil_kingdom):
    t1 = escribir('[HGS]_Kingdom_S1E05.es.ass', [('Default', 'Xiang murió.'), ('Default', 'Qiang Xiang.')])
    t2 = escribir('[HGS]_Kingdom_S2E05.es.ass', [('Default', '¡No levantes la cabeza, Xiang!')])
    t3 = escribir('[HGS]_Kingdom_S3E05.es.ass', [('Default', 'Qing.')])
    for ruta in (t1, t2, t3):
        aplicar_perfil(ruta, perfil_kingdom)
    assert textos(t1) == ['Shou murió.', 'Kyou Shou.']
    assert textos(t2) == ['¡No levantes la cabeza, Kou!']
    assert textos(t3) == ['Qing.']


def test_unidades(escribir, perfil_kingdom):
    ruta = escribir('S4E01.es.ass', [
        ('Default', 'La Hi Shin Force avanza.'),
        ('Default', 'Shin de la Fuerza Fei Xin.'),
        ('Default', "el Lu Wuwei's Army ataca."),
        ('Default', '¡Tenbu Unit! ¡Media vuelta!'),
    ])
    aplicar_perfil(ruta, perfil_kingdom)
    assert textos(ruta) == [
        'La Unidad Hi Shin avanza.',
        'Shin de la Unidad Hi Shin.',
        'El ejército de Lu Wuwei ataca.',
        '¡Unidad Tenbu! ¡Media vuelta!',
    ]


def test_srt(tmp_path, perfil_kingdom):
    ruta = tmp_path / 'S1E32.es.srt'
    ruta.write_text('1\n00:00:01,000 --> 00:00:02,000\nXin y Piao.\n', encoding='utf-8')
    aplicar_perfil(ruta, perfil_kingdom)
    assert ruta.read_text(encoding='utf-8') == '1\n00:00:01,000 --> 00:00:02,000\nShin y Hyou.\n'


def test_no_cambia_palabras_en_español(escribir, perfil_kingdom):
    ruta = escribir('S4E01.es.ass', [('Default', 'Tengo que ir. Bienvenido.')])
    aplicar_perfil(ruta, perfil_kingdom)
    assert textos(ruta) == ['Tengo que ir. Bienvenido.']
