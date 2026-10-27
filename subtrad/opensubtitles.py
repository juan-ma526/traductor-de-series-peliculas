"""Cliente minimo de la API REST de OpenSubtitles (api.opensubtitles.com).

Necesita OPENSUBTITLES_API_KEY en el entorno o en .env.
Con OPENSUBTITLES_USERNAME y OPENSUBTITLES_PASSWORD inicia sesion y el limite diario de descargas sube (5 -> 20 en cuentas gratis).
El cupo se renueva a las 00:00 UTC.
"""
import json
import struct
import urllib.parse
from pathlib import Path

from subtrad import config
from subtrad.fuentes import ErrorFuente, LimiteAgotado, Resultado, guardar, pedir, pedir_json, titulo_y_año

API = 'https://api.opensubtitles.com/api/v1'


class ErrorOpenSubtitles(ErrorFuente):
    """Fallo de la API (clave invalida, limite de descargas, red...)."""


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
    nombre = 'opensubtitles'

    def __init__(self, clave : str|None = None):
        self.clave = clave or config.valor('OPENSUBTITLES_API_KEY')
        if not self.clave:
            raise ErrorOpenSubtitles('Falta OPENSUBTITLES_API_KEY (en el entorno o en .env)')
        self.token = ''
        self.restantes : int|None = None
        self.agotado = False

    def _cabeceras(self) -> dict:
        cabeceras = {'Api-Key': self.clave}
        if self.token:
            cabeceras['Authorization'] = f'Bearer {self.token}'
        return cabeceras

    def _enviar(self, ruta : str, cuerpo : dict) -> dict:
        try:
            respuesta = pedir(f'{API}/{ruta}', {**self._cabeceras(), 'Content-Type': 'application/json',
                                                'Accept': 'application/json'}, json.dumps(cuerpo).encode(), 'POST')
        except ErrorFuente as error:
            raise ErrorOpenSubtitles(f'{ruta}: {error}') from error
        return json.loads(respuesta)

    def iniciar_sesion(self) -> bool:
        """Inicia sesion si hay usuario y contraseña configurados."""
        usuario, contraseña = config.valor('OPENSUBTITLES_USERNAME'), config.valor('OPENSUBTITLES_PASSWORD')
        if not usuario or not contraseña:
            return False
        self.token = self._enviar('login', {'username': usuario, 'password': contraseña}).get('token', '')
        return bool(self.token)

    def buscar(self, consulta : str, temporada : int|None, episodio : int|None, idioma : str = 'en',
               video : Path|None = None) -> list[Resultado]:
        """Subtitulos de un episodio o pelicula, los que coinciden con el hash del video primero y despues los mas descargados."""
        titulo, año = titulo_y_año(consulta)
        parametros : dict = {'query': titulo, 'languages': idioma}
        if año is not None:
            parametros['year'] = año
        if temporada is not None:
            parametros['season_number'] = temporada
        if episodio is not None:
            parametros['episode_number'] = episodio
        if video is not None:
            parametros['moviehash'] = hash_video(video)

        url = f'{API}/subtitles?' + urllib.parse.urlencode(sorted(parametros.items()))
        try:
            datos = pedir_json(url, self._cabeceras())
        except ErrorFuente as error:
            raise ErrorOpenSubtitles(f'subtitles: {error}') from error

        resultados = []
        for item in datos.get('data', []):
            atributos = item['attributes']
            for archivo in atributos.get('files', [])[:1]:
                resultados.append(Resultado(
                    id=str(archivo['file_id']),
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
            datos = self._enviar('download', {'file_id': int(resultado.id)})
        except ErrorOpenSubtitles as error:
            # 406: limite diario agotado; no tiene sentido seguir intentando con otros videos
            if 'HTTP 406' in str(error):
                self.agotado = True
                raise LimiteAgotado(str(error)) from error
            raise
        self.restantes = datos.get('remaining')
        contenido = pedir(datos['link'], timeout=60)
        return guardar(contenido, datos.get('file_name') or f'{resultado.id}.srt', carpeta, resultado.id)
