"""Cliente de la API de Subdl (subdl.com): peliculas y series, sin limite diario conocido.

Necesita SUBDL_API_KEY en el entorno o en .env (gratis, registrandose en subdl.com).
Las descargas son zip; los de temporada completa traen un archivo por episodio.
Los enlaces que devuelve la API incluyen la clave: nunca se imprimen.
"""
import urllib.parse
from pathlib import Path

from subtrad import config
from subtrad.fuentes import ErrorFuente, Resultado, elegir_de_zip, guardar, pedir, pedir_json, titulo_y_año

API = 'https://api.subdl.com/api/v1/subtitles'
DESCARGAS = 'https://dl.subdl.com'
POR_PAGINA = 30


class Cliente:
    """Busqueda y descarga de subtitulos en Subdl."""
    nombre = 'subdl'

    def __init__(self, clave : str|None = None):
        self.clave = clave or config.valor('SUBDL_API_KEY')
        if not self.clave:
            raise ErrorFuente('Falta SUBDL_API_KEY (en el entorno o en .env)')

    def buscar(self, consulta : str, temporada : int|None, episodio : int|None, idioma : str = 'en',
               video : Path|None = None) -> list[Resultado]:
        """Subtitulos del episodio (o paquetes de su temporada) o de la pelicula.
        Primero los del episodio exacto, despues los de temporada completa; dentro de cada grupo, sin SDH primero."""
        titulo, año = titulo_y_año(consulta)
        serie = episodio is not None
        parametros : dict = {'film_name': titulo, 'type': 'tv' if serie else 'movie', 'languages': idioma.upper(),
                             'subs_per_page': POR_PAGINA}
        if año is not None and not serie:
            parametros['year'] = año
        if temporada is not None and serie:
            parametros['season_number'] = temporada
        if serie:
            parametros['episode_number'] = episodio

        datos = pedir_json(f'{API}?' + urllib.parse.urlencode({'api_key': self.clave, **parametros}))
        if not datos.get('status'):
            raise ErrorFuente(f"Subdl: {datos.get('error', 'busqueda rechazada')}")

        resultados = []
        for item in datos.get('subtitles', []):
            exacto = item.get('episode') == episodio
            if serie and not exacto and not item.get('full_season'):
                continue
            resultados.append(Resultado(
                id=item['url'],
                release=item.get('release_name', ''),
                titulo=item.get('name', ''),
                datos={'exacto': exacto, 'sdh': bool(item.get('hi')), 'temporada': temporada, 'episodio': episodio},
            ))
        return sorted(resultados, key=lambda r: (not r.datos['exacto'], r.datos['sdh']))

    def descargar(self, resultado : Resultado, carpeta : Path) -> Path:
        contenido = pedir(DESCARGAS + resultado.id, timeout=60)
        nombre, subtitulo = elegir_de_zip(contenido, resultado.datos.get('temporada'), resultado.datos.get('episodio'))
        return guardar(subtitulo, nombre, carpeta, 'subdl')
