"""Linea de comandos: subtrad <comando> ...

  identificar  que serie es (perfil existente, o candidatos de AniList/TVmaze/TMDB)
  conseguir    consigue el original de cada video (pistas o descarga) verificado contra el audio
  extraer      saca los subtitulos de los videos de una carpeta
  incluidos    videos que ya traen subtitulos en el idioma destino
  pendientes   lista originales y si ya tienen traduccion
  nombres      nombres propios de los originales que el perfil no cubre
  traducir     traduce por API (OpenAI, OpenRouter, Ollama...) de punta a punta
  preparar     divide subtitulos en partes para el traductor (agentes)
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import regex

from subtrad import (archivos, config, conseguir, fuentes, gestdown, identificar, motor_api, nombres, opensubtitles, partes,
                     postproceso, revisar, sincronizar, subdl, video)
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


def cmd_identificar(args : argparse.Namespace) -> int:
    """Identifica la serie de una carpeta. Codigo de salida 0 si queda claro, 3 si hay que preguntarle al usuario."""
    perfiles = Path(args.perfiles)
    resultado = identificar.identificar(Path(args.carpeta), perfiles)
    pistas = resultado.pistas
    print(f"Carpeta: titulo '{pistas.titulo}', año {pistas.año or '?'}, {pistas.videos} videos")

    if resultado.perfil:
        print(f"PERFIL EXISTENTE\t{resultado.perfil}")
        return 0
    if not resultado.candidatos:
        print("SIN CANDIDATOS: preguntar al usuario el titulo exacto y el año")
        return 3

    if args.crear is not None:
        elegido = resultado.candidatos[args.crear - 1]
        print(f"PERFIL CREADO\t{identificar.crear_perfil(elegido, perfiles)}")
        return 0

    for n, c in enumerate(resultado.candidatos[:8], 1):
        ids = ', '.join(f'{k} {v}' for k, v in c.ids.items())
        episodios = f", {c.episodios} episodios" if c.episodios else ''
        print(f"{n}. {c.titulo} ({c.año or '?'}) - {c.tipo}{episodios} - {c.detalle} [{ids}] (puntaje {c.puntaje})")
    if resultado.claro:
        print("CLARO\t1  (crear el perfil con --crear 1)")
        return 0
    print("AMBIGUO: preguntar al usuario cual es; despues --crear N")
    return 3


def cmd_conseguir(args : argparse.Namespace) -> int:
    carpeta = Path(args.carpeta)
    # "Serie/Season 2": el nombre para buscar es el de la serie
    nombre_carpeta = carpeta.parent.name if regex.fullmatch(r'(?i)(season|temporada)\s*\d+', carpeta.name) else carpeta.name
    consulta = args.serie or nombre_carpeta
    descargas = [] if args.sin_descargas else _fuentes_de_descarga()

    fallidos = 0
    for v in video.videos(carpeta):
        resultado = conseguir.conseguir_video(v, args.idioma, consulta, descargas, args.max_descargas, args.audio)

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

    for fuente in descargas:
        if isinstance(fuente, opensubtitles.Cliente) and fuente.restantes is not None:
            print(f"OpenSubtitles: quedan {fuente.restantes} descargas hoy")
    return 1 if fallidos else 0


def _fuentes_de_descarga() -> list[fuentes.Fuente]:
    """Las fuentes disponibles, en orden: OpenSubtitles, Subdl (si hay clave) y Gestdown (series, sin clave)."""
    disponibles : list[fuentes.Fuente] = []
    try:
        cliente = opensubtitles.Cliente()
        if cliente.iniciar_sesion():
            print("OpenSubtitles: sesion iniciada")
        disponibles.append(cliente)
    except fuentes.ErrorFuente as error:
        print(f"Aviso: sin OpenSubtitles ({error})")
    try:
        disponibles.append(subdl.Cliente())
    except fuentes.ErrorFuente as error:
        print(f"Aviso: sin Subdl ({error})")
    disponibles.append(gestdown.Cliente())
    return disponibles


def cmd_incluidos(args : argparse.Namespace) -> int:
    """Videos que ya traen subtitulos de texto en el idioma destino: normalmente no hace falta traducirlos."""
    con, sin = 0, 0
    for v in video.videos(Path(args.carpeta)):
        pistas = video.pistas_en_idioma(v, args.destino)
        if pistas:
            con += 1
            print(f"INCLUIDO\t{v.name}\t{', '.join(video.describir(p) for p in pistas)}")
        else:
            sin += 1
            print(f"SIN\t{v.name}")
    print(f"Total: {con} con subtitulos '{args.destino}' incluidos, {sin} sin")
    return 0


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


def cmd_traducir(args : argparse.Namespace) -> int:
    """Flujo completo por API: preparar, traducir, insertar, limpiar, postproceso y revisar."""
    objetivo = Path(args.objetivo)
    perfil = cargar_perfil(Path(args.perfil))
    try:
        motor = motor_api.crear_motor(args.modelo, args.url, args.formato)
    except motor_api.ErrorAPI as error:
        print(f"ERROR: {error}")
        return 2

    carpeta = objetivo if objetivo.is_dir() else objetivo.parent
    base = carpeta / CARPETA_TRABAJO
    if objetivo.is_dir():
        capitulos = [p for p in archivos.pendientes(objetivo, perfil.codigo) if args.rehacer or not p.ya_traducido]
    else:
        capitulos = [archivos.Pendiente(objetivo, archivos.ruta_salida(objetivo, perfil.codigo))]
    if not capitulos:
        print("No hay capitulos pendientes")
        return 0

    def traducir_uno(pendiente : archivos.Pendiente) -> str:
        trabajo = base / pendiente.origen.stem
        if not (trabajo / 'manifiesto.json').exists():
            partes.preparar(pendiente.origen, trabajo, args.lineas)
        partes.escribir_instrucciones(trabajo, pendiente.origen, pendiente.salida, perfil)
        motor_api.traducir_capitulo(motor, trabajo, perfil)
        n = partes.insertar(pendiente.origen, trabajo, pendiente.salida)
        return f"OK      {pendiente.salida.name} ({n} lineas)"

    print(f"Traduciendo {len(capitulos)} capitulos con {motor.modelo} ({motor.url}), {args.paralelo} a la vez")
    fallidos = 0
    with ThreadPoolExecutor(max_workers=args.paralelo) as grupo:
        futuros = {grupo.submit(traducir_uno, p): p for p in capitulos}
        for futuro in as_completed(futuros):
            try:
                print(futuro.result())
            except (motor_api.ErrorAPI, partes.ErrorInsercion) as error:
                fallidos += 1
                print(f"ERROR   {futuros[futuro].origen.name}: {str(error)[:300]}")

    print(f"Tokens usados: {motor.uso.entrada} de entrada, {motor.uso.salida} de salida")
    cmd_limpiar(argparse.Namespace(carpeta=str(carpeta)))
    cmd_postproceso(argparse.Namespace(objetivo=str(objetivo if objetivo.is_dir() else capitulos[0].salida), perfil=args.perfil, temporada=None))
    graves = cmd_revisar(argparse.Namespace(objetivo=str(objetivo if objetivo.is_dir() else capitulos[0].salida),
                                            perfil=args.perfil, origen='en', destino=perfil.codigo))
    return 1 if fallidos or graves else 0


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

    p = comandos.add_parser('identificar', help='identifica la serie de una carpeta (AniList, TVmaze, TMDB opcional)')
    p.add_argument('carpeta')
    p.add_argument('--perfiles', default=str(config.RAIZ_REPO / 'series'), help='carpeta de perfiles')
    p.add_argument('--crear', type=int, help='crear el perfil base del candidato N')
    p.set_defaults(funcion=cmd_identificar)

    p = comandos.add_parser('conseguir', help='consigue el original de cada video y verifica que corresponda al audio')
    p.add_argument('carpeta')
    p.add_argument('--idioma', default='en')
    p.add_argument('--serie', help='nombre para buscar en OpenSubtitles (por defecto, el de la carpeta)')
    p.add_argument('--max-descargas', type=int, default=2, help='descargas maximas por video')
    p.add_argument('--sin-descargas', action='store_true', help='solo verificar lo que ya hay')
    p.add_argument('--audio', help='idioma del audio contra el que verificar (por defecto japones/coreano/chino si hay, si no el primero)')
    p.set_defaults(funcion=cmd_conseguir)

    p = comandos.add_parser('incluidos', help='videos que ya traen subtitulos de texto en el idioma destino')
    p.add_argument('carpeta')
    p.add_argument('--destino', default='es')
    p.set_defaults(funcion=cmd_incluidos)

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

    p = comandos.add_parser('traducir', help='traduce por API (compatible con OpenAI) de punta a punta')
    p.add_argument('objetivo', help='carpeta con los originales o un subtitulo original')
    p.add_argument('--perfil', required=True)
    p.add_argument('--modelo', help='por defecto SUBTRAD_MODELO del .env')
    p.add_argument('--url', help='base de la API, por defecto SUBTRAD_API_URL o la oficial del formato')
    p.add_argument('--formato', choices=['openai', 'anthropic'], help='por defecto SUBTRAD_API_FORMATO (openai)')
    p.add_argument('--paralelo', type=int, default=3, help='capitulos a la vez')
    p.add_argument('--lineas', type=int, default=partes.LINEAS_POR_PARTE)
    p.add_argument('--rehacer', action='store_true', help='incluir capitulos que ya tienen traduccion')
    p.set_defaults(funcion=cmd_traducir)

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
    # La consola de Windows no puede mostrar algunos caracteres (titulos en japones): se reemplazan en vez de fallar
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, 'reconfigure'):
            flujo.reconfigure(errors='replace')
    args = construir_parser().parse_args(argv)
    try:
        return args.funcion(args)
    except (video.FfmpegNoEncontrado, sincronizar.AlassNoEncontrado) as error:
        print(f"ERROR: {error}")
        return 2


if __name__ == '__main__':
    sys.exit(main())
