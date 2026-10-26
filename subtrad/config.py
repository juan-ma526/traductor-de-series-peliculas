"""Configuracion local: variables de entorno y archivo .env (nunca se sube al repo)."""
import os
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parent.parent


def _leer_env(ruta : Path) -> dict[str, str]:
    valores = {}
    if ruta.is_file():
        for linea in ruta.read_text(encoding='utf-8').splitlines():
            linea = linea.strip()
            if linea and not linea.startswith('#') and '=' in linea:
                clave, valor = linea.split('=', 1)
                valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def valor(clave : str, por_defecto : str = '') -> str:
    """Busca la clave en el entorno, despues en .env del directorio actual y del repo."""
    if os.environ.get(clave):
        return os.environ[clave]
    for ruta in (Path.cwd() / '.env', RAIZ_REPO / '.env'):
        encontrado = _leer_env(ruta).get(clave)
        if encontrado:
            return encontrado
    return por_defecto
