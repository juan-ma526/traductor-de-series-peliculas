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
        ('romajied5', 'yakusoku wa iranai'),        # Escaflowne: letra del ending
        ('Edward', 'Brother!'),                     # un personaje, no una cancion
        ('Default', '{\\k20}la{\\k30}la'),
        ('Default', '{\\p1}m 0 0 l 10 10{\\p0}'),
    ])
    manifiesto = partes.preparar(origen, tmp_path / 'trabajo')
    assert manifiesto.eventos == [0, 3]


def test_karaoke_silabico_y_copias_de_carteles(escribir, tmp_path):
    # Caso real (Eminence in Shadow): karaoke silaba por silaba en estilos sin nombre de cancion,
    # y un cartel que sigue a la camara repetido cuadro por cuadro
    silabas = [('neo shadow OR', s) for s in ['ko', 'no', 'su', 'be', 'te'] * 5]
    silabas += [('neo shadow OR2', 'me'), ('neo shadow OR2', 'mae ni biru yo')]
    cartel = [('Sign', f'{{\\pos(100,{y})}}Deceased ~ Kageno Minoru') for y in (10, 12, 14)]
    origen = escribir('ep.en.ass', [('Main', 'Hello.')] + silabas + cartel)
    trabajo = tmp_path / 'trabajo'
    manifiesto = partes.preparar(origen, trabajo)

    primero = 1 + len(silabas)
    assert manifiesto.eventos == [0, primero]
    assert manifiesto.duplicados == {str(primero + 1): primero, str(primero + 2): primero}

    traducir(trabajo, {0: 'Hola.', primero: '{\\pos(100,10)}Fallecido ~ Kageno Minoru'})
    partes.insertar(origen, trabajo, tmp_path / 'ep.es.ass')
    eventos = cargar(tmp_path / 'ep.es.ass').events
    assert [e.text for e in eventos[-3:]] == [f'{{\\pos(100,{y})}}Fallecido ~ Kageno Minoru' for y in (10, 12, 14)]


def test_comentarios_no_van_al_traductor(escribir, tmp_path):
    # Caso real (Eminence in Shadow S2): comentarios con el texto ingles alternativo en cada linea
    origen = escribir('ep.en.ass', [('Default', '{\\an8}Aww, man...{Aww, man, really...}')])
    trabajo = tmp_path / 'trabajo'
    partes.preparar(origen, trabajo)
    assert '{Aww' not in (trabajo / '001.txt').read_text(encoding='utf-8')

    traducir(trabajo, {0: '{\\an8}Ay, no...'})
    partes.insertar(origen, trabajo, tmp_path / 'ep.es.ass')
    assert cargar(tmp_path / 'ep.es.ass').events[0].text == '{\\an8}Ay, no...'


def test_rechaza_tags_perdidos(escribir, tmp_path):
    # Cursiva parcial: no se puede rearmar sola
    origen = escribir('ep.en.ass', [('Default', '{\\i1}Hello{\\i0} friend')])
    trabajo = tmp_path / 'trabajo'
    partes.preparar(origen, trabajo)
    traducir(trabajo, {0: 'Hola amigo'})

    with pytest.raises(partes.ErrorInsercion):
        partes.insertar(origen, trabajo, tmp_path / 'ep.es.ass')
    assert not (tmp_path / 'ep.es.ass').exists()


def test_repara_cursivas_por_renglon(escribir, tmp_path):
    # Error frecuente (Kingdom, Escaflowne E23): linea toda en cursiva y el modelo deja un solo par de tags
    origen = escribir('ep.en.ass', [('Default', "{\\i1}Folken's arrival{\\i}\\N{\\i1}changed everything.{\\i}")])
    trabajo = tmp_path / 'trabajo'
    partes.preparar(origen, trabajo)
    traducir(trabajo, {0: '{\\i1}La llegada de Folken\\Nlo cambió todo.{\\i}'})

    partes.insertar(origen, trabajo, tmp_path / 'ep.es.ass')
    assert cargar(tmp_path / 'ep.es.ass').events[0].text == '{\\i1}La llegada de Folken{\\i}\\N{\\i1}lo cambió todo.{\\i}'


def test_rechaza_caracteres_de_otro_alfabeto(escribir, tmp_path):
    # Error real (Escaflowne E18): "con el que se顶层 mi padre"
    origen = escribir('ep.en.ass', [('Default', 'That my father met?')])
    trabajo = tmp_path / 'trabajo'
    partes.preparar(origen, trabajo)
    traducir(trabajo, {0: '¿Con el que se顶层 mi padre?'})
    with pytest.raises(partes.ErrorInsercion):
        partes.insertar(origen, trabajo, tmp_path / 'ep.es.ass')


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
