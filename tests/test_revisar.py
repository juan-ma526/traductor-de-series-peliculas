from subtrad.revisar import GRAVE, revisar_archivo

ORIGINAL = [
    ('Default', 'A sudden strike at the very heart of Zhao'),
    ('Default', "is something out of a child's daydream."),
    ('Default', 'But such an outlandish strategy is the only way'),
    ('Default', "we'll ever manage to outmaneuver Li Mu."),
    ('Default', 'Still, the very idea of it is terrifying...'),
]


def tipos(problemas) -> set[str]:
    return {p.tipo for p in problemas}


def test_traduccion_correcta_no_tiene_problemas(escribir):
    escribir('ep.en.ass', ORIGINAL)
    es = escribir('ep.es.ass', [
        ('Default', 'Un golpe repentino al mismo corazón de Zhao'),
        ('Default', 'es algo sacado de la fantasía de un niño.'),
        ('Default', 'Pero una estrategia tan descabellada es la única forma'),
        ('Default', 'en que lograremos superar a Riboku.'),
        ('Default', 'Aun así, la sola idea da miedo...'),
    ])
    assert revisar_archivo(es) == []


LARGO = [
    ('Default', 'Yes.'),
    ('Default', 'If we manage to take Ye, Your Highness, we can conquer the capital.'),
    ('Default', 'Really?'),
    ('Default', 'And Zhao along with it, in three years at most, if everything goes to plan.'),
    ('Default', 'Three years...!'),
    ('Default', 'Of course, as you have gathered, even if we make it to Ye,'),
    ('Default', 'No.'),
    ('Default', 'we will inevitably be besieged by the powerful security forces of Handan.'),
    ('Default', 'Go!'),
    ('Default', 'We are likely to suffer an unparalleled number of casualties.'),
]


def test_detecta_corrimiento(escribir):
    # Error real (Kingdom S6E02): una frase de mas al principio corrio todo lo que sigue una posicion
    escribir('ep.en.ass', LARGO)
    es = escribir('ep.es.ass', [
        ('Default', 'Sí, y si logramos tomar Gyou, Su Alteza, conquistaremos la capital.'),
        ('Default', '¿En serio?'),
        ('Default', 'Y Zhao con ella, en tres años como mucho, si todo sale según lo previsto.'),
        ('Default', '¡Tres años...!'),
        ('Default', 'Por supuesto, como habrás notado, aunque lleguemos a Gyou,'),
        ('Default', 'No.'),
        ('Default', 'nos sitiarán sin remedio las poderosas fuerzas de seguridad de Kantan.'),
        ('Default', '¡Vamos!'),
        ('Default', 'Es probable que suframos una cantidad de bajas sin precedentes.'),
        ('Default', 'Sí.'),
    ])
    problemas = revisar_archivo(es)
    assert 'corrimiento' in tipos(problemas)
    assert any(p.gravedad == GRAVE for p in problemas)


def test_sin_corrimiento_en_traduccion_alineada(escribir):
    escribir('ep.en.ass', LARGO)
    es = escribir('ep.es.ass', [
        ('Default', 'Sí.'),
        ('Default', 'Si logramos tomar Gyou, Su Alteza, conquistaremos la capital.'),
        ('Default', '¿En serio?'),
        ('Default', 'Y Zhao con ella, en tres años como mucho, si todo sale según lo previsto.'),
        ('Default', '¡Tres años...!'),
        ('Default', 'Por supuesto, como habrás notado, aunque lleguemos a Gyou,'),
        ('Default', 'No.'),
        ('Default', 'nos sitiarán sin remedio las poderosas fuerzas de seguridad de Kantan.'),
        ('Default', '¡Vamos!'),
        ('Default', 'Es probable que suframos una cantidad de bajas sin precedentes.'),
    ])
    assert 'corrimiento' not in tipos(revisar_archivo(es))


def test_detecta_bloque_sin_traducir(escribir):
    escribir('ep.en.ass', ORIGINAL)
    es = escribir('ep.es.ass', [ORIGINAL[0], ORIGINAL[1], ORIGINAL[2], ('Default', 'en que superaremos a Riboku.'), ('Default', 'Aun así...')])
    assert 'sin_traducir' in tipos(revisar_archivo(es))


def test_detecta_etiquetas_voseo_y_nombres(escribir, perfil_kingdom):
    escribir('[HGS]_Kingdom_S2E01.en.ass', [('Default', 'Hello.'), ('Default', 'You know.'), ('Default', 'Xin!')])
    es = escribir('[HGS]_Kingdom_S2E01.es.ass', [
        ('Default', 'Original\\NHello.\\NTranslation\\NHola.'),
        ('Default', 'Vos sabés.'),
        ('Default', '¡Xin!'),
    ])
    encontrados = tipos(revisar_archivo(es, perfil_kingdom))
    assert {'etiquetas', 'voseo', 'nombres'} <= encontrados


def test_sin_original_revisa_solo_el_texto(escribir):
    es = escribir('ep.es.ass', [('Default', 'Hola.')])
    assert tipos(revisar_archivo(es)) == {'sin_original'}
