"""Cliente de Gestdown (api.gestdown.info), que sirve los subtitulos de Addic7ed: solo series, sin clave.

Addic7ed tiene muy buenos subtitulos en ingles de series de TV, sincronizados con los releases comunes.
"""
import urllib.parse
from pathlib import Path

from subtrad.fuentes import ErrorFuente, Resultado, guardar, pedir, pedir_json, titulo_y_año

API = 'https://api.gestdown.info'
IDIOMAS = {'en': 'English', 'es': 'Spanish', 'fr': 'French', 'it': 'Italian', 'pt': 'Portuguese', 'de': 'German'}


def _normalizar(texto : str) -> str:
    return ''.join(c for c in texto.lower() if c.isalnum())


class Cliente:
    """Busqueda y descarga de subtitulos de series en Gestdown."""
    nombre = 'gestdown'

    def __init__(self):
        self._series : dict[str, str|None] = {}

    def _serie(self, titulo : str) -> str|None:
        """Id de la serie en Gestdown; se busca una sola vez por titulo."""
        if titulo not in self._series:
            datos = pedir_json(f'{API}/shows/search/' + urllib.parse.quote(titulo))
            series = datos.get('shows', [])
            exacta = [s for s in series if _normalizar(s.get('name', '')) == _normalizar(titulo)]
            elegida = (exacta or series or [None])[0]
            self._series[titulo] = elegida['id'] if elegida else None
        return self._series[titulo]

    def buscar(self, consulta : str, temporada : int|None, episodio : int|None, idioma : str = 'en',
               video : Path|None = None) -> list[Resultado]:
        """Subtitulos completos del episodio, sin SDH primero y despues los mas descargados."""
        if temporada is None or episodio is None or idioma not in IDIOMAS:
            return []
        titulo, _año = titulo_y_año(consulta)
        serie = self._serie(titulo)
        if serie is None:
            return []

        try:
            datos = pedir_json(f'{API}/subtitles/get/{serie}/{temporada}/{episodio}/{IDIOMAS[idioma]}')
        except ErrorFuente as error:
            # 404: la serie existe pero ese episodio no tiene subtitulos
            if 'HTTP 404' in str(error):
                return []
            raise

        resultados = [Resultado(id=s['downloadUri'], release=s.get('version', ''), descargas=s.get('downloadCount', 0),
                                datos={'sdh': bool(s.get('hearingImpaired'))})
                      for s in datos.get('matchingSubtitles', []) if s.get('completed') and s.get('downloadUri')]
        return sorted(resultados, key=lambda r: (r.datos['sdh'], -r.descargas))

    def descargar(self, resultado : Resultado, carpeta : Path) -> Path:
        contenido = pedir(API + resultado.id, timeout=60)
        return guardar(contenido, Path(resultado.id).name + '.srt', carpeta, 'gestdown')
