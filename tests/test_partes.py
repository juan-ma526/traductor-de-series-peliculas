import pytest

from subtrad import partes
from subtrad.archivos import cargar


def traducir(trabajo, reemplazos : dict[int, str]):
    """Simula al agente traductor: copia las partes cambiando las lineas indicadas."""
    for parte in sorted(trabajo.glob('[0-9][0-9][0-9].txt')):
        lineas = []
        for linea in parte.read_text(encoding='utf-8').splitlines():
            i = int(linea[1:linea.index(']')])
            lineas.append(f"[{i}] {reemplazos.get(i, linea.split('] ', 1)[1])}")
        parte.with_suffix('.out.txt').write_text('\n'.join(lineas) + '\n', encoding='utf-8')


def test_ida_y_vuelta_conserva_tiempos_y_tags(escribir, tmp_path):
    origen = escribir('ep.en.ass', [('Default', '{\\i1}Hello{\\i0}\\Nfriend.'), ('Default', 'Goodbye.')])
    trabajo = tmp_path / 'trabajo'
    partes.preparar(origen, trabajo)
    traducir(trabajo, {0: '{\\i1}Hola{\\i0}\\Namigo.', 1: 'Adiós.'})

    salida = tmp_path / 'ep.es.ass'
    assert partes.insertar(origen, trabajo, salida) == 2
    en, es = cargar(origen), cargar(salida)
    assert [e.start for e in en.events] == [e.start for e in es.events]
    assert es.events[0].text == '{\\i1}Hola{\\i0}\\Namigo.'


def test_no_extrae_canciones_ni_comentarios(escribir, tmp_path):
    origen = escribir('ep.en.ass', [
        ('Default', 'Hello.'),
        ('OP Romaji', 'kimi no sora'),
        ('Default', '{\\k20}la{\\k30}la'),
        ('Default', '{\\p1}m 0 0 l 10 10{\\p0}'),
    ])
    manifiesto = partes.preparar(origen, tmp_path / 'trabajo')
    assert manifiesto.eventos == [0]


def test_rechaza_tags_perdidos(escribir, tmp_path):
    origen = escribir('ep.en.ass', [('Default', '{\\i1}Hello{\\i0}')])
    trabajo = tmp_path / 'trabajo'
    partes.preparar(origen, trabajo)
    traducir(trabajo, {0: 'Hola'})

    with pytest.raises(partes.ErrorInsercion):
        partes.insertar(origen, trabajo, tmp_path / 'ep.es.ass')
    assert not (tmp_path / 'ep.es.ass').exists()


def test_rechaza_lineas_faltantes(escribir, tmp_path):
    origen = escribir('ep.en.ass', [('Default', 'One.'), ('Default', 'Two.')])
    trabajo = tmp_path / 'trabajo'
    partes.preparar(origen, trabajo)
    (trabajo / '001.out.txt').write_text('[0] Uno y dos.\n', encoding='utf-8')

    with pytest.raises(partes.ErrorInsercion) as error:
        partes.insertar(origen, trabajo, tmp_path / 'ep.es.ass')
    assert any('sin traducir' in e for e in error.value.errores)


def test_rechaza_etiquetas_de_otras_herramientas(escribir, tmp_path):
    origen = escribir('ep.en.ass', [('Default', 'I can hear it.')])
    trabajo = tmp_path / 'trabajo'
    partes.preparar(origen, trabajo)
    traducir(trabajo, {0: 'Original\\NI can hear it.\\NTranslation\\NLos escucho.'})

    with pytest.raises(partes.ErrorInsercion):
        partes.insertar(origen, trabajo, tmp_path / 'ep.es.ass')


def test_instrucciones_incluyen_reglas_del_perfil(escribir, tmp_path, perfil_kingdom):
    origen = escribir('ep.en.ass', [('Default', 'Hello.')])
    trabajo = tmp_path / 'trabajo'
    partes.preparar(origen, trabajo)
    texto = partes.escribir_instrucciones(trabajo, origen, tmp_path / 'ep.es.ass', perfil_kingdom).read_text(encoding='utf-8')

    assert 'Duke Hyou' in texto
    assert 'NUNCA voseo' in texto
    assert '-m subtrad insertar' in texto
    assert '{IDIOMA}' not in texto
