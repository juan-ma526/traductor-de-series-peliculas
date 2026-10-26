"""Linea de comandos: subtrad <comando> ...

  conseguir    consigue el original de cada video (pistas o descarga) verificado contra el audio
  extraer      saca los subtitulos de los videos de una carpeta
  pendientes   lista originales y si ya tienen traduccion
  nombres      nombres propios de los originales que el perfil no cubre
  preparar     divide subtitulos en partes para el traductor
  insertar     reinserta la traduccion validandola
  limpiar      borra las carpetas de trabajo terminadas
  postproceso  aplica el perfil de la serie (nombres, unidades)
  revisar      controles de calidad de los traducidos
"""
import argparse
import collections
import json
import shutil
import sys
from pathlib import Path

from subtrad import archivos, conseguir, nombres, opensubtitles, partes, postproceso, revisar, sincronizar, video
from subtrad.perfil import Perfil, cargar_perfil

CARPETA_TRABAJO = '.traduccion'


def _perfil(ruta : str|None) -> Perfil|None:
    return cargar_perfil(Path(ruta)) if ruta else None


def _traducidos(objetivo : Path, codigo : str) -> list[Path]:
    """Un archivo traducido o todos los de una carpeta."""
    if objetivo.is_file():
        return [objetivo]
    return sorted(f for f in objetivo.iterdir() if f.is_file() and archivos.codigo_idioma(f) == codigo
                  and f.suffix.lower() in archivos.EXTENSIONES_SUBTITULOS)


def cmd_extraer(args : argparse.Namespace) -> int:
    lista = video.videos(Path(args.carpeta))
    if not lista:
        print(f"No hay videos en {args.carpeta}")
        return 1

    if args.listar:
        for v in lista:
            pistas = video.pistas_subtitulos(v)
            print(f"{v.name}: " + ('; '.join(video.describir(p) for p in pistas) or 'sin subtitulos'))
        return 0

    estados : collections.Counter = collections.Counter()
    for v in lista:
        resultado = video.extraer_video(v, args.idioma, args.sobrescribir)
        estados[resultado.estado] += 1
        nombre = resultado.salida.name if resultado.salida else v.name
        print(f"{resultado.estado.upper():13} {nombre} {resultado.detalle}")

    print(f"Resumen: {dict(estados)}")
    return 1 if estados['error'] or estados['sin_pista'] or estados['no_extraible'] else 0


def cmd_conseguir(args : argparse.Namespace) -> int:
    carpeta = Path(args.carpeta)
    consulta = args.serie or carpeta.name
    cliente = None
    if not args.sin_descargas:
        try:
            cliente = opensubtitles.Cliente()
            if cliente.iniciar_sesion():
                print("OpenSubtitles: sesion iniciada")
        except opensubtitles.ErrorOpenSubtitles as error:
            print(f"Aviso: sin descargas ({error})")

    fallidos = 0
    for v in video.videos(carpeta):
        try:
            resultado = conseguir.conseguir_video(v, args.idioma, consulta, cliente, args.max_descargas)
        except opensubtitles.ErrorOpenSubtitles as error:
            print(f"ERROR     {v.name}: {error}")
            fallidos += 1
            continue

        for c in resultado.candidatos:
            ver = c.verificacion
            marca = '*' if c is resultado.elegido else ' '
            if ver:
                print(f"   {marca} {c.origen}{' (SDH)' if c.sdh else ''}: {ver.estado}, mueve {ver.corrimiento_ms / 1000:+.1f}s, quietas {ver.quietas:.0%}")
        if resultado.salida:
            print(f"OK        {resultado.salida.name}  <- {resultado.elegido.origen}")
        else:
            print(f"SIN SUBS  {v.name}: {resultado.detalle}")
            fallidos += 1

    if cliente is not None and cliente.restantes is not None:
        print(f"OpenSubtitles: quedan {cliente.restantes} descargas hoy")
    return 1 if fallidos else 0


def cmd_pendientes(args : argparse.Namespace) -> int:
    for p in archivos.pendientes(Path(args.carpeta), args.destino):
        estado = 'TRADUCIDO (revisar)' if p.ya_traducido else 'PENDIENTE'
        print(f"{estado:20}\t{p.origen}\t{p.salida}")
    return 0


def cmd_preparar(args : argparse.Namespace) -> int:
    objetivo = Path(args.objetivo)
    perfil = _perfil(args.perfil)

    # Carpeta: prepara todos los originales que todavia no tienen traduccion
    if objetivo.is_dir():
        if perfil is None:
            print("ERROR: para preparar una carpeta hace falta --perfil")
            return 1
        base = Path(args.trabajo) if args.trabajo else objetivo / CARPETA_TRABAJO
        for pendiente in archivos.pendientes(objetivo, perfil.codigo):
            if pendiente.ya_traducido and not args.rehacer:
                continue
            trabajo = base / pendiente.origen.stem
            partes.preparar(pendiente.origen, trabajo, args.lineas)
            print(f"INSTRUCCIONES\t{partes.escribir_instrucciones(trabajo, pendiente.origen, pendiente.salida, perfil)}")
        return 0

    trabajo = Path(args.trabajo) if args.trabajo else objetivo.parent / CARPETA_TRABAJO / objetivo.stem
    manifiesto = partes.preparar(objetivo, trabajo, args.lineas)
    print(f"{objetivo.name}: {len(manifiesto.eventos)} lineas en {len(manifiesto.partes)} partes -> {trabajo}")
    if perfil:
        salida = Path(args.salida) if args.salida else archivos.ruta_salida(objetivo, perfil.codigo)
        print(f"INSTRUCCIONES\t{partes.escribir_instrucciones(trabajo, objetivo, salida, perfil)}")
    return 0


def cmd_limpiar(args : argparse.Namespace) -> int:
    """Borra las carpetas de trabajo cuyo subtitulo traducido ya existe."""
    base = Path(args.carpeta) / CARPETA_TRABAJO
    if not base.is_dir():
        return 0

    quedan = []
    for trabajo in sorted(base.iterdir()):
        manifiesto = trabajo / 'manifiesto.json'
        salida = json.loads(manifiesto.read_text(encoding='utf-8')).get('salida') if manifiesto.exists() else None
        if salida and Path(salida).exists():
            shutil.rmtree(trabajo)
        else:
            quedan.append(trabajo.name)

    if not quedan:
        base.rmdir()
    print(f"Quedan sin terminar: {quedan}" if quedan else "Carpeta de trabajo eliminada")
    return 0


def cmd_nombres(args : argparse.Namespace) -> int:
    objetivo = Path(args.objetivo)
    originales = [objetivo] if objetivo.is_file() else [p.origen for p in archivos.pendientes(objetivo, args.destino)]
    for nombre, n in nombres.candidatos(originales, _perfil(args.perfil), args.minimo):
        print(f"{n:5}  {nombre}")
    return 0


def cmd_insertar(args : argparse.Namespace) -> int:
    try:
        n = partes.insertar(Path(args.archivo), Path(args.trabajo), Path(args.salida))
    except partes.ErrorInsercion as error:
        print("ERROR - no se genero la salida:")
        for detalle in error.errores:
            print(f"  {detalle}")
        return 1
    print(f"OK {args.salida} ({n} lineas, tiempos y estilos sin cambios)")
    return 0


def cmd_postproceso(args : argparse.Namespace) -> int:
    perfil = cargar_perfil(Path(args.perfil))
    total : collections.Counter = collections.Counter()
    for archivo in _traducidos(Path(args.objetivo), perfil.codigo):
        conteo = postproceso.aplicar_perfil(archivo, perfil, args.temporada)
        total.update(conteo)
        print(f"{sum(conteo.values()):5} cambios  {archivo.name}")
    for reemplazo, n in total.most_common(30):
        print(f"   {n:5} -> {reemplazo}")
    print(f"Total: {sum(total.values())} cambios")
    return 0


def cmd_revisar(args : argparse.Namespace) -> int:
    perfil = _perfil(args.perfil)
    codigo = perfil.codigo if perfil else args.destino
    graves = 0
    for archivo in _traducidos(Path(args.objetivo), codigo):
        problemas = revisar.revisar_archivo(archivo, perfil, args.origen)
        graves += sum(1 for p in problemas if p.gravedad == revisar.GRAVE)
        estado = 'OK' if not problemas else ('GRAVE' if any(p.gravedad == revisar.GRAVE for p in problemas) else 'AVISOS')
        print(f"{estado:7} {archivo.name}")
        for p in problemas:
            linea = f" (linea {p.linea})" if p.linea is not None else ''
            print(f"        [{p.gravedad}] {p.tipo}: {p.detalle}{linea}")
    return 1 if graves else 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='subtrad', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    comandos = parser.add_subparsers(dest='comando', required=True)

    p = comandos.add_parser('extraer', help='saca los subtitulos de los videos de una carpeta')
    p.add_argument('carpeta')
    p.add_argument('--idioma', default='en')
    p.add_argument('--sobrescribir', action='store_true')
    p.add_argument('--listar', action='store_true', help='solo mostrar las pistas de cada video')
    p.set_defaults(funcion=cmd_extraer)

    p = comandos.add_parser('conseguir', help='consigue el original de cada video y verifica que corresponda al audio')
    p.add_argument('carpeta')
    p.add_argument('--idioma', default='en')
    p.add_argument('--serie', help='nombre para buscar en OpenSubtitles (por defecto, el de la carpeta)')
    p.add_argument('--max-descargas', type=int, default=2, help='descargas maximas por video')
    p.add_argument('--sin-descargas', action='store_true', help='solo verificar lo que ya hay')
    p.set_defaults(funcion=cmd_conseguir)

    p = comandos.add_parser('pendientes', help='lista originales y si ya tienen traduccion')
    p.add_argument('carpeta')
    p.add_argument('--destino', default='es')
    p.set_defaults(funcion=cmd_pendientes)

    p = comandos.add_parser('preparar', help='divide subtitulos en partes para el traductor')
    p.add_argument('objetivo', help='un subtitulo original o una carpeta (prepara todos los pendientes)')
    p.add_argument('--perfil', help='perfil YAML; escribe INSTRUCCIONES.txt para el agente')
    p.add_argument('--trabajo', help=f'carpeta de trabajo (por defecto <carpeta>/{CARPETA_TRABAJO}/<nombre>)')
    p.add_argument('--salida', help='archivo traducido final (por defecto <nombre>.<codigo>.<ext>)')
    p.add_argument('--lineas', type=int, default=partes.LINEAS_POR_PARTE)
    p.add_argument('--rehacer', action='store_true', help='incluir capitulos que ya tienen traduccion')
    p.set_defaults(funcion=cmd_preparar)

    p = comandos.add_parser('limpiar', help='borra las carpetas de trabajo de capitulos terminados')
    p.add_argument('carpeta')
    p.set_defaults(funcion=cmd_limpiar)

    p = comandos.add_parser('nombres', help='nombres propios de los originales que el perfil no cubre')
    p.add_argument('objetivo', help='subtitulo original o carpeta')
    p.add_argument('--perfil')
    p.add_argument('--destino', default='es')
    p.add_argument('--minimo', type=int, default=4, help='apariciones minimas')
    p.set_defaults(funcion=cmd_nombres)

    p = comandos.add_parser('insertar', help='reinserta la traduccion validandola')
    p.add_argument('archivo')
    p.add_argument('trabajo')
    p.add_argument('salida')
    p.set_defaults(funcion=cmd_insertar)

    p = comandos.add_parser('postproceso', help='aplica el perfil de la serie a los traducidos')
    p.add_argument('objetivo', help='archivo traducido o carpeta')
    p.add_argument('--perfil', required=True)
    p.add_argument('--temporada', type=int, help='por defecto se deduce del nombre del archivo')
    p.set_defaults(funcion=cmd_postproceso)

    p = comandos.add_parser('revisar', help='controles de calidad de los traducidos')
    p.add_argument('objetivo', help='archivo traducido o carpeta')
    p.add_argument('--perfil')
    p.add_argument('--origen', default='en', help='codigo del original con el que comparar')
    p.add_argument('--destino', default='es', help='codigo de los traducidos si no hay perfil')
    p.set_defaults(funcion=cmd_revisar)
    return parser


def main(argv : list[str]|None = None) -> int:
    args = construir_parser().parse_args(argv)
    try:
        return args.funcion(args)
    except (video.FfmpegNoEncontrado, sincronizar.AlassNoEncontrado) as error:
        print(f"ERROR: {error}")
        return 2


if __name__ == '__main__':
    sys.exit(main())
