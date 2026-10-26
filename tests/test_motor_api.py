import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from subtrad import motor_api, partes
from subtrad.archivos import cargar
from subtrad.perfil import Perfil


class ServidorFalso(BaseHTTPRequestHandler):
    """Imita /chat/completions: la primera respuesta pierde un tag, la segunda viene bien."""
    respuestas : list[str] = []
    pedidos : list[dict] = []

    def do_POST(self):
        cuerpo = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        ServidorFalso.pedidos.append(cuerpo)
        contenido = ServidorFalso.respuestas.pop(0)
        datos = {'choices': [{'message': {'content': contenido}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(datos).encode())

    def log_message(self, *_args):
        pass


@pytest.fixture
def servidor():
    http = HTTPServer(('127.0.0.1', 0), ServidorFalso)
    hilo = threading.Thread(target=http.serve_forever, daemon=True)
    hilo.start()
    ServidorFalso.pedidos = []
    yield f'http://127.0.0.1:{http.server_port}/v1'
    http.shutdown()


def test_traduce_y_corrige_cuando_falla_la_validacion(escribir, tmp_path, servidor):
    origen = escribir('ep.en.ass', [('Default', '{\\i1}Hello{\\i0}'), ('Default', 'Goodbye.')])
    trabajo = tmp_path / 'trabajo'
    partes.preparar(origen, trabajo)
    ServidorFalso.respuestas = [
        '```\n[0] Hola\n[1] Adiós.\n```',          # pierde el tag de cursiva
        '[0] {\\i1}Hola{\\i0}\n[1] Adiós.',        # corregida
    ]

    motor = motor_api.MotorAPI('modelo-prueba', servidor, clave='')
    motor_api.traducir_capitulo(motor, trabajo, Perfil(serie='Prueba'))
    partes.insertar(origen, trabajo, tmp_path / 'ep.es.ass')

    assert [e.text for e in cargar(tmp_path / 'ep.es.ass').events] == ['{\\i1}Hola{\\i0}', 'Adiós.']
    assert len(ServidorFalso.pedidos) == 2
    assert 'tags de estilo' in ServidorFalso.pedidos[1]['messages'][-1]['content']
    assert motor.uso.entrada == 20


def test_falla_si_no_logra_corregir(escribir, tmp_path, servidor):
    origen = escribir('ep.en.ass', [('Default', 'One.'), ('Default', 'Two.')])
    trabajo = tmp_path / 'trabajo'
    partes.preparar(origen, trabajo)
    ServidorFalso.respuestas = ['[0] Uno y dos.'] * motor_api.INTENTOS

    with pytest.raises(motor_api.ErrorAPI):
        motor_api.traducir_capitulo(motor_api.MotorAPI('modelo-prueba', servidor, clave=''), trabajo, Perfil(serie='Prueba'))


class AnthropicFalso(BaseHTTPRequestHandler):
    """Imita /v1/messages de Anthropic con las mismas respuestas encoladas."""
    respuestas : list[str] = []
    pedidos : list[dict] = []

    def do_POST(self):
        cuerpo = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        AnthropicFalso.pedidos.append(cuerpo)
        datos = {
            'id': 'msg_prueba', 'type': 'message', 'role': 'assistant', 'model': cuerpo['model'],
            'content': [{'type': 'text', 'text': AnthropicFalso.respuestas.pop(0)}],
            'stop_reason': 'end_turn', 'stop_sequence': None,
            'usage': {'input_tokens': 7, 'output_tokens': 3},
        }
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(datos).encode())

    def log_message(self, *_args):
        pass


def test_motor_anthropic_con_gateway(escribir, tmp_path):
    pytest.importorskip('anthropic')
    from subtrad.motor_anthropic import MotorAnthropic

    http = HTTPServer(('127.0.0.1', 0), AnthropicFalso)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        origen = escribir('ep.en.ass', [('Default', '{\\i1}Hello{\\i0}')])
        trabajo = tmp_path / 'trabajo'
        partes.preparar(origen, trabajo)
        AnthropicFalso.pedidos = []
        AnthropicFalso.respuestas = ['[0] Hola', '[0] {\\i1}Hola{\\i0}']

        motor = MotorAnthropic('claude-haiku-5-5', f'http://127.0.0.1:{http.server_port}', clave='prueba')
        motor_api.traducir_capitulo(motor, trabajo, Perfil(serie='Prueba'))
    finally:
        http.shutdown()

    primero = AnthropicFalso.pedidos[0]
    assert primero['model'] == 'claude-haiku-5-5'
    assert 'temperature' not in primero                       # la API ya no la acepta
    assert 'SOLO con las lineas traducidas' in primero['system']
    assert [m['role'] for m in AnthropicFalso.pedidos[1]['messages']] == ['user', 'assistant', 'user']
    assert (trabajo / '001.out.txt').read_text(encoding='utf-8').strip() == '[0] {\\i1}Hola{\\i0}'
    assert motor.uso.entrada == 14


def test_prompt_api_tiene_las_mismas_reglas_que_el_agente(perfil_kingdom):
    prompt = partes.prompt_api(perfil_kingdom)
    assert 'Duke Hyou' in prompt and 'NUNCA voseo' in prompt and 'SOLO con las lineas traducidas' in prompt
    assert '{' + 'REGLAS' + '}' not in prompt
