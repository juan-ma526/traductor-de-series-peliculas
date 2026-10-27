"""Motor de traduccion por API compatible con OpenAI (OpenAI, OpenRouter, DeepSeek, Ollama, etc.).

Configuracion (entorno o .env):
- SUBTRAD_API_URL: base de la API (por defecto https://api.openai.com/v1).
  OpenRouter: https://openrouter.ai/api/v1 - Ollama local: http://localhost:11434/v1
- SUBTRAD_API_KEY: clave del proveedor (si falta se usa OPENAI_API_KEY; Ollama no necesita).
- SUBTRAD_MODELO: modelo a usar (ej. gpt-4o-mini, deepseek/deepseek-chat, qwen2.5:14b).

Traduce parte por parte, con las mismas reglas que el agente.
Cada respuesta se valida (ids, tags, etiquetas) y si falla se le devuelven los errores al modelo para que corrija.
"""
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from subtrad import config, partes
from subtrad.archivos import cargar
from subtrad.perfil import Perfil

URL_POR_DEFECTO = 'https://api.openai.com/v1'
INTENTOS = 3


class ErrorAPI(Exception):
    """La API fallo o la traduccion no paso la validacion despues de varios intentos."""


@dataclass
class Uso:
    """Tokens consumidos, para informar al usuario."""
    entrada : int = 0
    salida : int = 0


class MotorAPI:
    """Cliente minimo de /chat/completions."""

    def __init__(self, modelo : str|None = None, url : str|None = None, clave : str|None = None, temperatura : float = 0.2):
        self.url = (url or config.valor('SUBTRAD_API_URL', URL_POR_DEFECTO)).rstrip('/')
        self.clave = clave if clave is not None else (config.valor('SUBTRAD_API_KEY') or config.valor('OPENAI_API_KEY'))
        self.modelo = modelo or config.valor('SUBTRAD_MODELO')
        self.temperatura = temperatura
        self.uso = Uso()
        if not self.modelo:
            raise ErrorAPI('Falta el modelo: --modelo o SUBTRAD_MODELO en .env')

    def completar(self, mensajes : list[dict]) -> str:
        """Una llamada a la API; reintenta ante errores temporales (429, 5xx)."""
        cuerpo = json.dumps({'model': self.modelo, 'messages': mensajes, 'temperature': self.temperatura}).encode()
        cabeceras = {'Content-Type': 'application/json'}
        if self.clave:
            cabeceras['Authorization'] = f'Bearer {self.clave}'

        for espera in (0, 10, 20, 40, 60, 90, 120):
            time.sleep(espera)
            pedido = urllib.request.Request(f'{self.url}/chat/completions', data=cuerpo, headers=cabeceras, method='POST')
            try:
                with urllib.request.urlopen(pedido, timeout=300) as respuesta:
                    datos = json.loads(respuesta.read())
                break
            except urllib.error.HTTPError as error:
                if error.code in (429, 500, 502, 503, 504):
                    continue
                raise ErrorAPI(f'HTTP {error.code}: {error.read()[:300].decode("utf-8", "replace")}') from error
            except urllib.error.URLError as error:
                raise ErrorAPI(f'Sin conexion con {self.url}: {error.reason}') from error
        else:
            raise ErrorAPI('La API sigue respondiendo con error temporal despues de varios reintentos')

        uso = datos.get('usage') or {}
        self.uso.entrada += uso.get('prompt_tokens', 0)
        self.uso.salida += uso.get('completion_tokens', 0)
        return datos['choices'][0]['message']['content'] or ''


def crear_motor(modelo : str|None = None, url : str|None = None, formato : str|None = None):
    """Motor segun SUBTRAD_API_FORMATO: 'openai' (por defecto) o 'anthropic'."""
    formato = (formato or config.valor('SUBTRAD_API_FORMATO', 'openai')).lower()
    if formato == 'anthropic':
        try:
            from subtrad.motor_anthropic import MotorAnthropic
        except ImportError as error:
            raise ErrorAPI('Falta el SDK de Anthropic: pip install -e ".[anthropic]"') from error
        return MotorAnthropic(modelo, url)
    if formato != 'openai':
        raise ErrorAPI(f"SUBTRAD_API_FORMATO desconocido: {formato} (usar 'openai' o 'anthropic')")
    return MotorAPI(modelo, url)


def _limpiar_respuesta(texto : str) -> str:
    """Algunos modelos envuelven la respuesta en un bloque de codigo."""
    lineas = [l for l in texto.strip().splitlines() if not l.strip().startswith('```')]
    return '\n'.join(lineas)


def _ultimo_recurso(subs, esperados : dict[int, str], traducciones : dict[int, str], errores : list[str]) -> tuple[dict[int, str], list[str]]:
    """Tras el ultimo intento, si solo quedan problemas de tags: cursivas se toleran y los demas tags se rearman
    con partes.forzar_tags. Perder el color de una palabra o un enfasis es menor que perder el capitulo
    (caso real: Escaflowne, 12 capitulos fallaban solo por tags)."""
    solo_tags = all(e.endswith(partes.ERROR_CURSIVAS) or e.endswith(partes.ERROR_TAGS) for e in errores)
    if not solo_tags:
        return traducciones, errores
    arregladas = dict(traducciones)
    for error in errores:
        if error.endswith(partes.ERROR_TAGS):
            i = int(error[1:error.index(']')])
            arregladas[i] = partes.forzar_tags(subs.events[i].text, arregladas[i])
    return arregladas, partes.validar(subs, set(esperados), arregladas, tolerar_cursivas=True)


def traducir_capitulo(motor, trabajo : Path, perfil : Perfil) -> None:
    """Traduce todas las partes de una carpeta de trabajo (preparada con partes.preparar) y escribe los NNN.out.txt."""
    manifiesto = json.loads((trabajo / 'manifiesto.json').read_text(encoding='utf-8'))
    subs = cargar(Path(manifiesto['archivo']))
    sistema = partes.prompt_api(perfil)

    for nombre in manifiesto['partes']:
        salida = trabajo / f'{nombre}.out.txt'
        if salida.exists():
            continue

        original = (trabajo / f'{nombre}.txt').read_text(encoding='utf-8')
        esperados, _ = partes.leer_lineas(original)
        mensajes = [{'role': 'system', 'content': sistema}, {'role': 'user', 'content': original}]

        for intento in range(INTENTOS):
            respuesta = _limpiar_respuesta(motor.completar(mensajes))
            traducciones, errores = partes.leer_lineas(respuesta)
            traducciones = partes.reparar(subs, {i: t for i, t in traducciones.items() if i < len(subs.events)})
            errores += partes.validar(subs, set(esperados), traducciones)
            if not errores:
                break

            if intento == INTENTOS - 1:
                traducciones, errores = _ultimo_recurso(subs, esperados, traducciones, errores)
                if not errores:
                    manifiesto['tolerar_cursivas'] = True
                    (trabajo / 'manifiesto.json').write_text(json.dumps(manifiesto, indent=1), encoding='utf-8')
                    break
                # Se guarda la ultima respuesta para poder ver que hizo el modelo
                (trabajo / f'{nombre}.fallido.txt').write_text(respuesta, encoding='utf-8')

            # Se le devuelven los errores al modelo para que corrija sobre su propia respuesta
            mensajes += [{'role': 'assistant', 'content': respuesta},
                         {'role': 'user', 'content': 'Corregi estos errores y responde de nuevo TODAS las lineas:\n' + '\n'.join(errores[:20])}]
        if errores:
            raise ErrorAPI(f'{trabajo.name}/{nombre}: la traduccion no paso la validacion: {errores[:5]}')

        texto = '\n'.join(f'[{i}] {traducciones[i]}' for i in esperados)
        salida.write_text(texto + '\n', encoding='utf-8')
