from subtrad.cli import main
from subtrad.nombres import candidatos


def test_preparar_carpeta_solo_pendientes_y_limpiar(escribir, tmp_path, perfil_kingdom, capsys):
    escribir('a.en.ass', [('Default', 'Hello.')])
    escribir('b.en.ass', [('Default', 'Bye.')])
    escribir('b.es.ass', [('Default', 'Chau.')])
    perfil = str(tmp_path.parent / 'perfil.yaml')
    (tmp_path.parent / 'perfil.yaml').write_text('serie: Prueba\ncodigo: es\n', encoding='utf-8')

    assert main(['preparar', str(tmp_path), '--perfil', perfil]) == 0
    salida = capsys.readouterr().out
    assert sum(1 for linea in salida.splitlines() if linea.startswith('INSTRUCCIONES\t')) == 1
    trabajo = tmp_path / '.traduccion' / 'a.en'
    assert (trabajo / 'INSTRUCCIONES.txt').exists()

    # Sin traducir todavia: limpiar no borra nada
    main(['limpiar', str(tmp_path)])
    assert trabajo.exists()

    # Traducido e insertado: limpiar borra la carpeta de trabajo
    (trabajo / '001.out.txt').write_text('[0] Hola.\n', encoding='utf-8')
    assert main(['insertar', str(tmp_path / 'a.en.ass'), str(trabajo), str(tmp_path / 'a.es.ass')]) == 0
    main(['limpiar', str(tmp_path)])
    assert not (tmp_path / '.traduccion').exists()


def test_nombres_propone_los_que_faltan_en_el_perfil(escribir, perfil_kingdom):
    ruta = escribir('ep.en.ass', [('Default', 'Xin and Bai Lao attack!'), ('Default', 'Bai Lao, wait!')] * 3)
    encontrados = dict(candidatos([ruta], perfil_kingdom, minimo=2))
    assert 'Bai Lao' in encontrados
    assert 'Xin' not in encontrados          # ya esta en el perfil
    assert 'Wait' not in encontrados
