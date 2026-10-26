"""Linea de comandos: subtrad <comando> ...

  extraer      saca los subtitulos de los videos de una carpeta
  pendientes   lista originales y si ya tienen traduccion
  preparar     divide un subtitulo en partes para el traductor
  insertar     reinserta la traduccion validandola
  postproceso  aplica el perfil de la serie (nombres, unidades)
  revisar      controles de calidad de los traducidos
"""
import argparse
import collections
import sys
from pathlib import Path

from subtrad import archivos, partes, postproceso, revisar, video
from subtrad.perfil import Perfil, cargar_perfil


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


def cmd_pendientes(args : argparse.Namespace) -> int:
    for p in archivos.pendientes(Path(args.carpeta), args.destino):
        estado = 'TRADUCIDO (revisar)' if p.ya_traducido else 'PENDIENTE'
        print(f"{estado:20}\t{p.origen}\t{p.salida}")
    return 0


def cmd_preparar(args : argparse.Namespace) -> int:
    origen, trabajo = Path(args.archivo), Path(args.trabajo)
    manifiesto = partes.preparar(origen, trabajo, args.lineas)
    print(f"{origen.name}: {len(manifiesto.eventos)} lineas en {len(manifiesto.partes)} partes -> {trabajo}")

    perfil = _perfil(args.perfil)
    if perfil:
        salida = Path(args.salida) if args.salida else archivos.ruta_salida(origen, perfil.codigo)
        print(f"Instrucciones: {partes.escribir_instrucciones(trabajo, origen, salida, perfil)}")
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

    p = comandos.add_parser('pendientes', help='lista originales y si ya tienen traduccion')
    p.add_argument('carpeta')
    p.add_argument('--destino', default='es')
    p.set_defaults(funcion=cmd_pendientes)

    p = comandos.add_parser('preparar', help='divide un subtitulo en partes para el traductor')
    p.add_argument('archivo')
    p.add_argument('trabajo', help='carpeta de trabajo')
    p.add_argument('--perfil', help='perfil YAML; si se indica, escribe INSTRUCCIONES.txt')
    p.add_argument('--salida', help='archivo traducido final (por defecto <nombre>.<codigo>.<ext>)')
    p.add_argument('--lineas', type=int, default=partes.LINEAS_POR_PARTE)
    p.set_defaults(funcion=cmd_preparar)

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
    except video.FfmpegNoEncontrado as error:
        print(f"ERROR: {error}")
        return 2


if __name__ == '__main__':
    sys.exit(main())
