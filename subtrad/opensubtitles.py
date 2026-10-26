"""Cliente minimo de la API REST de OpenSubtitles (api.opensubtitles.com).

Necesita OPENSUBTITLES_API_KEY en el entorno o en .env.
Con OPENSUBTITLES_USERNAME y OPENSUBTITLES_PASSWORD inicia sesion y el limite diario de descargas sube (5 -> 20 en cuentas gratis).
"""
import json
import struct
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from subtrad import __version__, config

API = 'https://api.opensubtitles.com/api/v1'
AGENTE = f'subtrad v{__version__}'


class ErrorOpenSubtitles(Exception):
    """Fallo de la API (clave invalida, limite de descargas, red...)."""


class LimiteAgotado(ErrorOpenSubtitles):
    """Se agoto el limite diario de descargas."""


@dataclass
class Resultado:
    """Un subtitulo encontrado."""
    file_id : int
    release : str
    descargas : int
    coincide_hash : bool
    titulo : str


def hash_video(ruta : Path) -> str:
    """Hash de OpenSubtitles: tamaño + suma de los primeros y ultimos 64 KB en bloques de 8 bytes."""
    bloque = 65536
    tamaño = ruta.stat().st_size
    total = tamaño
    with ruta.open('rb') as f:
        for posicion in (0, max(tamaño - bloque, 0)):
            f.seek(posicion)
            datos = f.read(bloque)
            for (n,) in struct.iter_unpack('<Q', datos[:len(datos) // 8 * 8]):
                total = (total + n) & 0xFFFFFFFFFFFFFFFF
    return f'{total:016x}'


class Cliente:
    """Busqueda y descarga de subtitulos."""

    def __init__(self, clave : str|None = None):
        self.clave = clave or config.valor('OPENSUBTITLES_API_KEY')
        if not self.clave:
            raise ErrorOpenSubtitles('Falta OPENSUBTITLES_API_KEY (en el entorno o en .env)')
        self.token = ''
        self.restantes : int|None = None
        self.agotado = False

    def _pedir(self, metodo : str, ruta : str, parametros : dict|None = None, cuerpo : dict|None = None) -> dict:
        url = f'{API}/{ruta}'
        if parametros:
            url += '?' + urllib.parse.urlencode(sorted(parametros.items()))
        cabeceras = {'Api-Key': self.clave, 'User-Agent': AGENTE, 'Accept': 'application/json'}
        datos = None
        if cuerpo is not None:
            cabeceras['Content-Type'] = 'application/json'
            datos = json.dumps(cuerpo).encode()
        if self.token:
            cabeceras['Authorization'] = f'Bearer {self.token}'

        pedido = urllib.request.Request(url, data=datos, headers=cabeceras, method=metodo)
        try:
            with urllib.request.urlopen(pedido, timeout=30) as respuesta:
                return json.loads(respuesta.read())
        except urllib.error.HTTPError as error:
            detalle = error.read()[:200].decode('utf-8', 'replace')
            raise ErrorOpenSubtitles(f'HTTP {error.code} en {ruta}: {detalle}') from error
        except urllib.error.URLError as error:
            raise ErrorOpenSubtitles(f'Sin conexion con OpenSubtitles: {error.reason}') from error

    def iniciar_sesion(self) -> bool:
        """Inicia sesion si hay usuario y contraseña configurados."""
        usuario, contraseña = config.valor('OPENSUBTITLES_USERNAME'), config.valor('OPENSUBTITLES_PASSWORD')
        if not usuario or not contraseña:
            return False
        self.token = self._pedir('POST', 'login', cuerpo={'username': usuario, 'password': contraseña}).get('token', '')
        return bool(self.token)

    def buscar(self, consulta : str, temporada : int|None, episodio : int|None, idioma : str = 'en',
               video : Path|None = None) -> list[Resultado]:
        """Subtitulos de un episodio, los que coinciden con el hash del video primero y despues los mas descargados."""
        parametros : dict = {'query': consulta, 'languages': idioma}
        if temporada is not None:
            parametros['season_number'] = temporada
        if episodio is not None:
            parametros['episode_number'] = episodio
        if video is not None:
            parametros['moviehash'] = hash_video(video)

        resultados = []
        for item in self._pedir('GET', 'subtitles', parametros).get('data', []):
            atributos = item['attributes']
            for archivo in atributos.get('files', [])[:1]:
                resultados.append(Resultado(
                    file_id=archivo['file_id'],
                    release=atributos.get('release', ''),
                    descargas=atributos.get('download_count', 0),
                    coincide_hash=bool(atributos.get('moviehash_match')),
                    titulo=atributos.get('feature_details', {}).get('title', ''),
                ))
        return sorted(resultados, key=lambda r: (not r.coincide_hash, -r.descargas))

    def descargar(self, resultado : Resultado, carpeta : Path) -> Path:
        """Descarga un subtitulo a la carpeta indicada (cuenta para el limite diario)."""
        if self.agotado:
            raise LimiteAgotado('Se agotaron las descargas de hoy en OpenSubtitles')
        try:
            datos = self._pedir('POST', 'download', cuerpo={'file_id': resultado.file_id})
        except ErrorOpenSubtitles as error:
            # 406: limite diario agotado; no tiene sentido seguir intentando con otros videos
            if 'HTTP 406' in str(error):
                self.agotado = True
                raise LimiteAgotado(str(error)) from error
            raise
        self.restantes = datos.get('remaining')
        pedido = urllib.request.Request(datos['link'], headers={'User-Agent': AGENTE})
        with urllib.request.urlopen(pedido, timeout=60) as respuesta:
            contenido = respuesta.read()
        nombre = Path(datos.get('file_name') or f'{resultado.file_id}.srt').name
        ruta = carpeta / f'{resultado.file_id}_{nombre}'
        ruta.write_bytes(contenido)
        return ruta
