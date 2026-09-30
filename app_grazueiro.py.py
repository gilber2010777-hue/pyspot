from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import base64
import io
import json
import os
import random
import re
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unicodedata
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from duckduckgo_search import DDGS
from PIL import Image
import requests
import streamlit as st
import streamlit.components.v1 as components

try:
  from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
except Exception:
  try:
    from streamlit.report_thread import add_report_ctx as add_script_run_ctx
    from streamlit.report_thread import get_report_ctx as get_script_run_ctx
  except Exception:
    def get_script_run_ctx():
      return None

    def add_script_run_ctx(thread=None, ctx=None):
      return thread


load_dotenv()
GROQ_API_KEY_ENV = os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")


_chave_groq_compartilhada_lock = threading.Lock()
_CHAVE_GROQ_COMPARTILHADA = GROQ_API_KEY_ENV or ""


def _definir_chave_groq_compartilhada(chave):
  global _CHAVE_GROQ_COMPARTILHADA
  with _chave_groq_compartilhada_lock:
    _CHAVE_GROQ_COMPARTILHADA = (chave or "").strip()


def _obter_chave_groq_compartilhada():
  with _chave_groq_compartilhada_lock:
    return _CHAVE_GROQ_COMPARTILHADA


LOG_FILE = ".telemetria_sistema.log"
BAN_FILE = ".usuarios_banidos.txt"

BRAIN_STATE_DIR = ".brain_states"
BRAIN_SERVER_HOST = "127.0.0.1"
BRAIN_SERVER_PORT = 8765
os.makedirs(BRAIN_STATE_DIR, exist_ok=True)


ROBLOX_AI_DIR = ".roblox_ai_state"
ROBLOX_QTABLE_PATH = os.path.join(ROBLOX_AI_DIR, "tabela_q.json")
os.makedirs(ROBLOX_AI_DIR, exist_ok=True)
ROBLOX_ACOES = ["frente", "tras", "pular", "correr", "nada"]



RESPONSE_STATE_DIR = ".response_states"
os.makedirs(RESPONSE_STATE_DIR, exist_ok=True)


def _brain_state_path(token):
  seguro = re.sub(r"[^a-zA-Z0-9_-]", "_", str(token or "SES-0000"))
  return os.path.join(BRAIN_STATE_DIR, f"{seguro}.json")


def _response_state_path(token):
  seguro = re.sub(r"[^a-zA-Z0-9_-]", "_", str(token or "SES-0000"))
  return os.path.join(RESPONSE_STATE_DIR, f"{seguro}.json")


def _ler_estado_resposta(token):
  try:
    with open(_response_state_path(token), "r", encoding="utf-8") as f:
      return json.load(f)
  except Exception:
    return {"generation_id": "", "status": "idle", "texto": ""}


def _gravar_estado_resposta(token, estado):
  caminho = _response_state_path(token)
  temporario = caminho + ".tmp"
  try:
    with open(temporario, "w", encoding="utf-8") as f:
      json.dump(estado, f, ensure_ascii=False)
    os.replace(temporario, caminho)
  except Exception:
    try:
      if os.path.exists(temporario):
        os.remove(temporario)
    except Exception:
      pass


def _ler_estado_cerebro(token):
  try:
    with open(_brain_state_path(token), "r", encoding="utf-8") as f:
      return json.load(f)
  except Exception:
    return {
      "generation_id": "",
      "status": "idle",
      "started_at": 0,
      "finished_at": 0,
      "events": [],
    }


def _gravar_estado_cerebro(token, estado):
  caminho = _brain_state_path(token)
  temporario = caminho + ".tmp"
  try:
    with open(temporario, "w", encoding="utf-8") as f:
      json.dump(estado, f, ensure_ascii=False)
    os.replace(temporario, caminho)
  except Exception:
    try:
      if os.path.exists(temporario):
        os.remove(temporario)
    except Exception:
      pass



def _roblox_carregar_tabela_q():
  try:
    with open(ROBLOX_QTABLE_PATH, "r", encoding="utf-8") as f:
      tabela = json.load(f)
  except Exception:
    return {}
  
  for linha in tabela.values():
    for acao in ROBLOX_ACOES:
      linha.setdefault(acao, 0.0)
  return tabela


def _roblox_salvar_tabela_q(tabela):
  caminho = ROBLOX_QTABLE_PATH
  temporario = caminho + ".tmp"
  try:
    with open(temporario, "w", encoding="utf-8") as f:
      json.dump(tabela, f, ensure_ascii=False)
    os.replace(temporario, caminho)
  except Exception:
    try:
      if os.path.exists(temporario):
        os.remove(temporario)
    except Exception:
      pass


_ROBLOX_TABELA_Q = _roblox_carregar_tabela_q()
_roblox_lock = threading.Lock()
_roblox_ultimo_estado = {} 
_roblox_contador_ticks = 0
_roblox_comando_forcado = {}  
ROBLOX_DURACAO_COMANDO_MOVIMENTO = 3.0  
ROBLOX_CHAT_NOME_NPC = "Grazueiro"


def _roblox_chave_estado(estado):
   obstaculo = bool(estado.get("obstaculo"))
  distancia = estado.get("distancia_obstaculo", 999)
  try:
    distancia = float(distancia)
  except Exception:
    distancia = 999.0
  if distancia < 4:
    faixa_distancia = "perto"
  elif distancia < 10:
    faixa_distancia = "medio"
  else:
    faixa_distancia = "longe"
  no_chao = bool(estado.get("no_chao", True))
  caindo = bool(estado.get("caindo"))
  return f"{obstaculo}|{faixa_distancia}|{no_chao}|{caindo}"


def _roblox_calcular_recompensa(estado):
  
  recompensa = 0.0
  try:
    avancou = float(estado.get("avancou", 0.0))
  except Exception:
    avancou = 0.0
  recompensa += max(-1.0, min(1.0, avancou))
  if estado.get("caindo"):
    recompensa -= 5.0
  if estado.get("colidiu"):
    recompensa -= 1.0
  if not estado.get("no_chao", True):
    recompensa -= 0.05
  return recompensa


def _roblox_escolher_acao(chave, epsilon=0.15):
  linha = _ROBLOX_TABELA_Q.get(chave)
  if not linha or random.random() < epsilon:
    return random.choice(ROBLOX_ACOES)
  return max(linha, key=linha.get)


def _roblox_atualizar_q(chave_anterior, acao_anterior, recompensa, chave_atual, alpha=0.3, gamma=0.9):
  linha_anterior = _ROBLOX_TABELA_Q.setdefault(chave_anterior, {a: 0.0 for a in ROBLOX_ACOES})
  linha_atual = _ROBLOX_TABELA_Q.get(chave_atual, {a: 0.0 for a in ROBLOX_ACOES})
  melhor_futuro = max(linha_atual.values()) if linha_atual else 0.0
  atual = linha_anterior.get(acao_anterior, 0.0)
  linha_anterior[acao_anterior] = atual + alpha * (recompensa + gamma * melhor_futuro - atual)


def _roblox_processar_tick(token, estado):

  global _roblox_contador_ticks
  with _roblox_lock:
    chave_atual = _roblox_chave_estado(estado)
    anterior = _roblox_ultimo_estado.get(token)
    if anterior is not None:
      chave_anterior, acao_anterior = anterior
      recompensa = _roblox_calcular_recompensa(estado)
      _roblox_atualizar_q(chave_anterior, acao_anterior, recompensa, chave_atual)
    comando_forcado = _roblox_comando_forcado.get(token)
    if comando_forcado and comando_forcado[1] > time.time():
      acao = comando_forcado[0]
      if acao == "pular":
     
        _roblox_comando_forcado.pop(token, None)
    else:
      if comando_forcado:
        _roblox_comando_forcado.pop(token, None)
      acao = _roblox_escolher_acao(chave_atual)
    _roblox_ultimo_estado[token] = (chave_atual, acao)
    _roblox_contador_ticks += 1
    if _roblox_contador_ticks % 20 == 0:
      _roblox_salvar_tabela_q(_ROBLOX_TABELA_Q)
    return acao


def _roblox_normalizar_texto(texto):

  texto = (texto or "").lower()
  texto = unicodedata.normalize("NFKD", texto)
  return "".join(c for c in texto if not unicodedata.combining(c))


def _roblox_detectar_comando_por_palavra(mensagem):

  texto = _roblox_normalizar_texto(mensagem)
  if re.search(r"\b(pula|pule|pular|pulo|salta|salte|saltar|jump)\b", texto):
    return "pular"
  if "para tras" in texto or "pra tras" in texto or re.search(r"\b(re|volta|voltar|recua|recue|recuar)\b", texto):
    return "tras"
  if re.search(r"\b(corre|corra|correr|correndo|disparada|rapido|rapida|run)\b", texto):
    return "correr"
  if re.search(r"\b(anda|andar|vai|va|caminha|caminhar|avanca|avance|avancar|segue|siga)\b", texto) or "frente" in texto:
    return "frente"
  if re.search(r"\b(para|pare|parado|parada|stop|quieto|quieta)\b", texto):
    return "nada"
  return None


def _roblox_definir_comando_chat(token, acao):
 
  if acao not in ROBLOX_ACOES:
    return
  duracao = 0.6 if acao == "pular" else ROBLOX_DURACAO_COMANDO_MOVIMENTO
  with _roblox_lock:
    _roblox_comando_forcado[token] = (acao, time.time() + duracao)


def _roblox_chamar_groq_simples(mensagens, instrucao_sistema, timeout=20):
 
  chave = _obter_chave_groq_compartilhada() or GROQ_API_KEY_ENV
  if not chave:
    return None
  payload = [{"role": "system", "content": instrucao_sistema}] + mensagens
  for modelo in ("openai/gpt-oss-120b", "openai/gpt-oss-20b"):
    try:
      resp = requests.post(
          "https://api.groq.com/openai/v1/chat/completions",
          headers={
              "Authorization": f"Bearer {chave}",
              "Content-Type": "application/json",
          },
          json={"model": modelo, "messages": payload, "temperature": 0.6},
          timeout=timeout,
      )
      if resp.status_code == 200:
        return resp.json()["choices"][0]["message"]["content"]
    except Exception:
      continue
  return None


def _roblox_chamar_ollama_simples(mensagens, instrucao_sistema, timeout=20):

  payload = [{"role": "system", "content": instrucao_sistema}] + mensagens
  for host in ("http://127.0.0.1:11434", "http://localhost:11434"):
    try:
      resp_tags = requests.get(f"{host}/api/tags", timeout=3)
      if resp_tags.status_code != 200:
        continue
      modelos_disponiveis = [m.get("name") for m in resp_tags.json().get("models", [])]
    except Exception:
      continue
    preferenciais = ["qwen2.5-coder:1.5b", "qwen2.5-coder:3b", "qwen2.5-coder:7b", "llama3.2", "llama3"]
    candidatos = [m for m in preferenciais if m in modelos_disponiveis] or modelos_disponiveis
    for modelo in candidatos:
      try:
        resp = requests.post(
            f"{host}/api/chat",
            json={"model": modelo, "messages": payload, "stream": False},
            timeout=timeout,
        )
        if resp.status_code == 200:
          return resp.json().get("message", {}).get("content", "")
      except Exception:
        continue
  return None


def _roblox_processar_chat(token, jogador, mensagem):
  
  mensagem = (mensagem or "").strip()
  if not mensagem:
    return {"resposta": "..."}

  instrucao = (
      f'Voce e {ROBLOX_CHAT_NOME_NPC}, um NPC simpatico, esperto e bem-humorado dentro de um jogo '
      'do Roblox -- tao afiado quanto a mesma IA quando conversa no chat web, so que em personagem '
      'e com respostas curtas. Voce esta conversando com jogadores pelo chat do jogo: responda '
      'SEMPRE em portugues, em no maximo 1 ou 2 frases curtas, sem markdown (isso vai aparecer num '
      'balao de chat e para todos os jogadores verem). Alem de conversar, voce tambem decide como '
      'se mover: andar para frente, andar para tras, correr (mais rapido que andar), pular ou '
      'ficar parada -- escolha livremente o que fizer mais sentido pro que o jogador pediu, e nao '
      'mexa nisso se ele so quiser bater papo. Se o jogador pedir claramente pra voce fazer algo '
      'desse tipo (ex: "pula", "corre", "anda pra frente", "para", "volta"), aceite o pedido com '
      'naturalidade na fala. Responda ESTRITAMENTE em JSON valido, sem nada fora do JSON, no '
      'formato exato: {"resposta": "sua fala em portugues", "acao": '
      '"frente|tras|pular|correr|nada|nenhuma"}. So use um valor de "acao" diferente de "nenhuma" '
      'quando o jogador pediu explicitamente pra voce se mover, correr ou parar.'
  )
  mensagens = [{"role": "user", "content": f"{jogador} disse: {mensagem}"}]

  bruto = _roblox_chamar_groq_simples(mensagens, instrucao)
  if not bruto:
    bruto = _roblox_chamar_ollama_simples(mensagens, instrucao)

  resposta_texto = ""
  acao = None
  if bruto:
    candidato = bruto.strip()
    if candidato.startswith("```"):
      candidato = candidato.strip("`")
      if "\n" in candidato:
        candidato = candidato.split("\n", 1)[1]
    try:
      dados = json.loads(candidato)
      resposta_texto = str(dados.get("resposta") or "").strip()
      acao_bruta = str(dados.get("acao") or "").strip().lower()
      if acao_bruta in ROBLOX_ACOES:
        acao = acao_bruta
    except Exception:
      resposta_texto = candidato

  if not resposta_texto:
    resposta_texto = "Desculpa, nao consegui pensar em nada agora."

  if acao is None:
    acao = _roblox_detectar_comando_por_palavra(mensagem)
  if acao:
    _roblox_definir_comando_chat(token, acao)

  return {"resposta": resposta_texto}


class _BrainStateHandler(BaseHTTPRequestHandler):
  def do_GET(self):
    try:
      rota, _, query = self.path.partition("?")
      if rota not in ("/brain_state", "/response_state"):
        self.send_response(404)
        self.end_headers()
        return

      params = parse_qs(query)
      token = params.get("token", ["SES-0000"])[0]
      if rota == "/brain_state":
        estado = _ler_estado_cerebro(token)
      else:
        estado = _ler_estado_resposta(token)
      body = json.dumps(estado, ensure_ascii=False).encode("utf-8")

      self.send_response(200)
      self.send_header("Content-Type", "application/json; charset=utf-8")
      self.send_header("Content-Length", str(len(body)))
      self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
      self.send_header("Pragma", "no-cache")
      self.send_header("Access-Control-Allow-Origin", "*")
      self.end_headers()
      self.wfile.write(body)
    except Exception:
      try:
        self.send_response(500)
        self.end_headers()
      except Exception:
        pass

  def do_POST(self):
    try:
      rota, _, query = self.path.partition("?")
      if rota not in ("/roblox_tick", "/roblox_chat"):
        self.send_response(404)
        self.end_headers()
        return

      tamanho = int(self.headers.get("Content-Length", 0) or 0)
      corpo = self.rfile.read(tamanho) if tamanho else b"{}"
      try:
        estado = json.loads(corpo.decode("utf-8"))
      except Exception:
        estado = {}

      params = parse_qs(query)
      token = estado.get("token") or params.get("token", ["BOT-0000"])[0]

      if rota == "/roblox_chat":
        jogador = estado.get("player") or estado.get("jogador") or "Jogador"
        mensagem = estado.get("message") or estado.get("mensagem") or ""
        resultado = _roblox_processar_chat(token, jogador, mensagem)
      else:
        acao = _roblox_processar_tick(token, estado)
        resultado = {"acao": acao}

      body = json.dumps(resultado, ensure_ascii=False).encode("utf-8")
      self.send_response(200)
      self.send_header("Content-Type", "application/json; charset=utf-8")
      self.send_header("Content-Length", str(len(body)))
      self.send_header("Access-Control-Allow-Origin", "*")
      self.end_headers()
      self.wfile.write(body)
    except Exception:
      try:
        self.send_response(500)
        self.end_headers()
      except Exception:
        pass

  def log_message(self, *_args):
    return


def _iniciar_servidor_cerebro():
  if getattr(_iniciar_servidor_cerebro, "_started", False):
    return
  try:
    servidor = ThreadingHTTPServer((BRAIN_SERVER_HOST, BRAIN_SERVER_PORT), _BrainStateHandler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
  except OSError:
    pass
  _iniciar_servidor_cerebro._started = True


_iniciar_servidor_cerebro()



is_admin_mode = st.query_params.get("ver") == "admin67"


if is_admin_mode:
  st.set_page_config(
      page_title="Grazueiro",
      page_icon="",
      layout="wide",
  )
else:
  st.set_page_config(
      page_title="Grazueiro", page_icon="", layout="centered"
  )


st.markdown("""
<style>
    /* Fundo Preto Absoluto Geral */
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"], [data-testid="stSidebar"], header, footer {
        background-color: #000000 !important;
        color: #ffffff !important;
    }

    /* Remoção completa de fundos cinzas no rodapé e caixa de perguntas */
    [data-testid="stBottom"],
    [data-testid="stBottom"] *,
    [data-testid="stBottomBlockContainer"],
    [data-testid="stBottomBlockContainer"] *,
    [data-testid="stChatInput"],
    [data-testid="stChatInput"] *,
    [data-testid="stChatInputContainer"],
    [data-testid="stChatInputContainer"] *,
    .stChatInputContainer,
    .stChatInputContainer *,
    [data-testid="stFileUploader"],
    [data-testid="stFileUploaderDropzone"],
    section[data-testid="stFileUploaderDropzone"],
    div[data-baseweb="base-input"],
    div[data-baseweb="input"],
    div[data-baseweb="textarea"] {
        background-color: #000000 !important;
    }

    /* Textos gerais e Títulos */
    h1, h2, h3, h4, h5, h6, p, span, label, div, small {
        color: #ffffff !important;
    }

    /* Espaçamento para garantir que a parte de baixo não seja cortada */
    [data-testid="stBottomBlockContainer"] {
        padding-bottom: 20px !important;
        background-color: #000000 !important;
    }

    /* Bordas brancas minimalistas em caixas, inputs, containers e cards */
    [data-testid="stSidebar"],
    [data-testid="stChatMessage"],
    [data-testid="stForm"],
    .stButton > button,
    .stSelectbox,
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stChatInput,
    .stChatInput > div,
    [data-testid="stExpander"],
    [data-testid="stContainer"],
    [data-testid="stVerticalBlock"] > div[style*="border"] {
        border: 1px solid #ffffff !important;
        border-radius: 6px !important;
        background-color: #000000 !important;
    }

    /* Estilização dos Botões */
    .stButton > button {
        background-color: #000000 !important;
        color: #ffffff !important;
        border: 1px solid #ffffff !important;
        transition: all 0.2s ease-in-out;
    }

    .stButton > button:hover {
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 1px solid #ffffff !important;
    }

    /* Campos de Entrada de Texto e Áreas de Texto */
    input, textarea {
        background-color: #000000 !important;
        color: #ffffff !important;
        border: 1px solid #ffffff !important;
    }

    /* Linhas Divisórias */
    hr {
        border-color: #ffffff !important;
    }

    /* Popups e Notificações */
    [data-testid="stToast"] {
        background-color: #000000 !important;
        color: #ffffff !important;
        border: 1px solid #ffffff !important;
    }
</style>
""", unsafe_allow_html=True)


if "historico" not in st.session_state:
  st.session_state["historico"] = []
if "fontes_ultima_busca" not in st.session_state:
  st.session_state["fontes_ultima_busca"] = []
if "raw_ua" not in st.session_state:
  st.session_state["raw_ua"] = "Não capturado"
if "token_sessao_oculto" not in st.session_state:
  st.session_state["token_sessao_oculto"] = f"SES-{random.randint(1000, 9999)}"
if "modo_exibicao" not in st.session_state:
  st.session_state["modo_exibicao"] = "Chat Normal"
if "brain_events" not in st.session_state:
  st.session_state["brain_events"] = []
if "resposta_pendente_generation_id" not in st.session_state:
  st.session_state["resposta_pendente_generation_id"] = ""


def registrar_evento_cerebro(etapa, detalhe=""):
  try:
    agora = time.time()
    token = st.session_state.get("token_sessao_oculto", "SES-0000")
    eventos = st.session_state.setdefault("brain_events", [])

  
    if etapa == "resposta" and eventos and eventos[-1].get("etapa") == "resposta":
      eventos[-1]["detalhe"] = str(detalhe)
      eventos[-1]["timestamp"] = agora
    else:
      eventos.append({
        "id": f"{agora:.6f}-{len(eventos)}",
        "etapa": str(etapa),
        "detalhe": str(detalhe),
        "timestamp": agora,
      })

    st.session_state["brain_events"] = eventos[-40:]

    estado = _ler_estado_cerebro(token)
    estado["generation_id"] = st.session_state.get("brain_generation_id", "")
    estado["status"] = st.session_state.get("brain_status", "idle")
    estado["started_at"] = st.session_state.get("brain_started_at", 0)
    estado["finished_at"] = st.session_state.get("brain_finished_at", 0)
    estado["events"] = st.session_state["brain_events"]
    _gravar_estado_cerebro(token, estado)
  except Exception:
    pass



if "contexto_local" not in st.session_state:
  try:
    st.session_state["contexto_local"] = requests.get(
        "https://ipinfo.io/json", timeout=2
    ).json()
  except:
    st.session_state["contexto_local"] = {}


if "temperatura_ambiente" not in st.session_state:
  st.session_state["temperatura_ambiente"] = "Não detectada"
  resp_loc = st.session_state.get("contexto_local", {})
  if resp_loc and "loc" in resp_loc:
    try:
      coords = resp_loc["loc"].split(",")
      clima_api = requests.get(
          f"https://api.open-meteo.com/v1/forecast?latitude={coords[0]}&longitude={coords[1]}&current=temperature_2m,relative_humidity_2m,wind_speed_10m&timezone=auto",
          timeout=2,
      ).json()
      curr = clima_api["current"]
      st.session_state["temperatura_ambiente"] = (
          f"{curr['temperature_2m']}°C, Umidade: {curr['relative_humidity_2m']}%,"
          f" Vento: {curr['wind_speed_10m']} km/h"
      )
    except:
      pass


def checar_se_banido(ip, token):
  if not os.path.exists(BAN_FILE):
    return False
  with open(BAN_FILE, "r", encoding="utf-8") as f:
    banidos = [linha.strip() for linha in f if linha.strip()]
  return ip in banidos or token in banidos


def carregar_lista_banidos():
  if not os.path.exists(BAN_FILE):
    return []
  with open(BAN_FILE, "r", encoding="utf-8") as f:
    return [linha.strip() for linha in f if linha.strip()]


def aplicar_banimento(identificador):
  banidos = carregar_lista_banidos()
  if identificador not in banidos:
    with open(BAN_FILE, "a", encoding="utf-8") as f:
      f.write(f"{identificador}\n")
    st.toast(f"{identificador} foi banido com sucesso!")


def revogar_banimento(identificador):
  banidos = carregar_lista_banidos()
  if identificador in banidos:
    banidos.remove(identificador)
    with open(BAN_FILE, "w", encoding="utf-8") as f:
      for b in banidos:
        f.write(f"{b}\n")
    st.toast(f"Banimento de {identificador} foi revertido!")


def ler_logs_estruturados():
  if not os.path.exists(LOG_FILE) or os.path.getsize(LOG_FILE) == 0:
    return {}
  sessoes = {}
  with open(LOG_FILE, "r", encoding="utf-8") as f:
    for linha in f:
      linha = linha.strip()
      if not linha or " ||| " not in linha:
        continue
      partes = linha.split(" ||| ")
      if len(partes) < 4:
        continue
      timestamp, usuario_id, role, texto = (
          partes[0],
          partes[1],
          partes[2],
          partes[3].replace(" [BR] ", "\n"),
      )

      token = "SES-0000"
      ip = "Não detectado"
      local = "Desconhecido"
      try:
        if " (" in usuario_id and " - " in usuario_id:
          token = usuario_id.split(" (")[0].strip()
          resto = usuario_id.split(" (")[1].rstrip(")")
          sub_partes = resto.split(" - ")
          ip = sub_partes[0].strip()
          local = (
              sub_partes[1].strip() if len(sub_partes) > 1 else "Desconhecido"
          )
        else:
          token = usuario_id
      except:
        pass

      if usuario_id not in sessoes:
        sessoes[usuario_id] = {
            "token": token,
            "ip": ip,
            "local": local,
            "ultima_atividade": timestamp,
            "interacoes": [],
        }
      sessoes[usuario_id]["interacoes"].append(
          {"timestamp": timestamp, "role": role, "texto": texto}
      )
      sessoes[usuario_id]["ultima_atividade"] = timestamp
  return sessoes


def registrar_log_invisivel(role, texto):
  try:
    (
        _horario,
        local,
        ip_usuario,
        _,
        _,
        _,
        _,
        _,
        email_usuario,
    ) = obter_contexto_usuario()
    timestamp = datetime.now().strftime("%d/%m %H:%M:%S")
    token = st.session_state.get("token_sessao_oculto", "SES-0000")

    usuario_id = f"{token} ({ip_usuario} - {local} - {email_usuario})"
    texto_seguro = str(texto).replace("\n", " [BR] ")

    dados_formatados = (
        f"{timestamp} ||| {usuario_id} ||| {role} ||| {texto_seguro}\n"
    )

    with open(LOG_FILE, "a", encoding="utf-8") as f:
      f.write(dados_formatados)
  except:
    pass


def obter_contexto_usuario():
  horario = datetime.now()
  dias_semana = [
      "Segunda-feira",
      "Terça-feira",
      "Quarta-feira",
      "Quinta-feira",
      "Sexta-feira",
      "Sábado",
      "Domingo",
  ]
  dia_semana = dias_semana[horario.weekday()]
  horario_formatated = (
      f"{dia_semana}, {horario.strftime('%d/%m/%Y às %H:%M:%S')}"
  )

  resp = st.session_state.get("contexto_local", {})
  if resp:
    cidade = (
        f"{resp.get('city', 'Desconhecida')},"
        f" {resp.get('region', '')}, {resp.get('country', '')}"
    )
    ip_usuario = resp.get("ip", "Não detectado")
  else:
    cidade = "Não detectada"
    ip_usuario = "Não detectado"

  ip_celular = "Não detectado"
  try:
    headers = st.context.headers
    if "X-Forwarded-For" in headers:
      ip_celular = headers["X-Forwarded-For"].split(",")[0].strip()
    elif "X-Real-Ip" in headers:
      ip_celular = headers["X-Real-Ip"]
    elif hasattr(st.context, "ip_address") and st.context.ip_address:
      ip_celular = st.context.ip_address
  except:
    pass

  informacoes_celular = "Desconhecido"
  plataforma_sistema = ""
  try:
    headers = st.context.headers
    for k, v in headers.items():
      if k.lower() == "user-agent":
        informacoes_celular = v
        st.session_state["raw_ua"] = v
      elif k.lower() in ["sec-ch-ua-platform", "x-device-os"]:
        plataforma_sistema = v.replace('"', "").strip()
  except:
    pass

  if plataforma_sistema:
    informacoes_celular += f" [Plataforma Reportada: {plataforma_sistema}]"

  temp_ambiente = st.session_state.get("temperatura_ambiente", "Não detectada")

  pct_bateria = st.query_params.get("bat_pct", "Não detectado")
  status_bateria = st.query_params.get("bat_status", "Não detectado")

  email_usuario = "Não autenticado"
  try:
    if hasattr(st, "user") and getattr(st.user, "email", None):
      email_usuario = st.user.email
    elif hasattr(st, "experimental_user") and getattr(
        st.experimental_user, "email", None
    ):
      email_usuario = st.experimental_user.email
    else:
      for k, v in st.context.headers.items():
        if k.lower() in [
            "x-user-email",
            "x-forwarded-user",
            "x-auth-username",
            "remote-user",
        ]:
          email_usuario = v
          break
  except:
    pass

  return (
      horario_formatated,
      cidade,
      ip_usuario,
      ip_celular,
      informacoes_celular,
      temp_ambiente,
      pct_bateria,
      status_bateria,
      email_usuario,
  )


def get_system_prompt():
  (
      horario,
      local,
      ip_usuario,
      ip_celular,
      informacoes_celular,
      temp_ambiente,
      pct_bateria,
      status_bateria,
      email_usuario,
  ) = obter_contexto_usuario()
  return f"""Você é o Alemão, um assistente brasileiro de elite: inteligente, detalhista, focado em soluções estruturadas e um especialista sênior de nível Principal/Staff em Engenharia de Software e Programação.
Você possui domínio técnico avançado em arquitetura de código, desenvolvimento de jogos (especialmente Roblox Luau), algoritmos, estruturas de dados, otimização de performance, padrões de projeto (Design Patterns), concorrência, tratamento rigoroso de erros e debugging avançado.

DIRETRIZES RIGOROSAS DE PROGRAMAÇÃO E ENGENHARIA DE SOFTWARE:
1. PADRÕES MODERNOS EM ROBLOX (LUAU):
   - Nunca utilize métodos ou funções obsoletas/descontinuadas. Use `task.wait()`, `task.spawn()` e `task.delay()` em vez de `wait()`, `spawn()` ou `delay()`.
   - NUNCA altere o `game.StarterGui` diretamente via script do servidor para tentar exibir uma GUI para um jogador no jogo. O `StarterGui` serve apenas como modelo inicial ao entrar. Para manipular a interface em tempo real de um jogador, encontre o jogador (`game.Players:GetPlayerFromCharacter()`) e modifique a pasta `PlayerGui` dele.
   - Use propriedades modernas de interface de usuário, como `TextSize` em vez da obsoleta `FontSize`.
   - Sempre utilize mecanismos de Debounce (cooldown) em eventos repetitivos como `.Touched` para evitar bugs de execução acelerada ou disparo múltiplo inadvertido.
   - Respeite estritamente a separação entre Script (Servidor), LocalScript (Cliente) e ModuleScript (Módulos compartilhados/utilitários).
2. QUALIDADE DE CÓDIGO E EXCELÊNCIA TÉCNICA GERAL:
   - Escreva códigos completos, limpos, highly seguros, modulares e prontos para produção. Evite reticências (`...`) ou trechos omitidos dentro dos blocos de código.
   - Trate todos os cenários de erro, validações de entrada, concorrência e tipos nulos/indefinidos antes de executar qualquer operação principal.
   - Inclua comentários explicativos e claros em português brasileiro diretamente no código para facilitar o entendimento técnico.

Contexto Técnico Real do Usuário:
- Localização: {local}
- Horário: {horario}
- IP da Rede: {ip_usuario}
- IP do Dispositivo: {ip_celular}
- Temperatura Ambiente Local: {temp_ambiente}
- Assinatura do Dispositivo (User-Agent/Plataforma): {informacoes_celular}
- Nível de Bateria Atual: {pct_bateria}% (Status: {status_bateria})
- E-mail Identificado: {email_usuario}

Diretrizes Rigorosas de Identificação de Hardware:
1. ANÁLISE DO USER-AGENT E PLATAFORMA: Examine a assinatura técnica fornecida. 
   - Se houver 'Plataforma Reportada', priorize essa informação sobre o User-Agent padrão (pois navegadores modernos costumam congelar o User-Agent para proteção de privacidade).
   - Se o User-Agent ou a Plataforma indicar Windows, Linux, Macintosh ou Android, descreva o sistema correspondente de forma precisa.
2. PROIBIÇÃO DE ALUCINAÇÃO: Não invente marcas. Se os dados forem insuficientes ou ambíguos, declare o que consegue ler na assinatura técnica e peça para o usuário confirmar o modelo.
3. MONITORAMENTO DE BATERIA E ABAS: Se o usuário perguntar sobre o nível de bateria ou status de carga, use diretamente os dados reais fornecidos no contexto técnico ({pct_bateria}% e {status_bateria}) para responder com precisão e clareza. Se ele perguntar sobre guias abertas do Chrome, explique pacientemente as restrições de segurança do Sandbox da Web que impedem aplicativos de espionar outros navegadores ou abas externas."""


def url_valida(url: str) -> bool:
  try:
    parsed = urlparse(url)
    return all([parsed.scheme, parsed.netloc])
  except:
    return False


def extrair_texto_html(html_puro: str, limite_caracteres: int = 10000) -> str:
  soup = BeautifulSoup(html_puro, "html.parser")
  for tag in soup([
      "script",
      "style",
      "noscript",
      "header",
      "footer",
      "svg",
      "img",
      "nav",
      "aside",
      "form",
  ]):
    tag.extract()
  corpo = soup.find("article") or soup.find(id="content") or soup
  return re.sub(r"\s+", " ", corpo.get_text(separator=" ", strip=True))[
      :limite_caracteres
  ]


def extrair_texto_da_url(url: str):
  headers_padrao = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          " (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
      )
  }

  if "twitter.com" in url or "x.com" in url:
    try:
      match = re.search(r"/(?:status|statuses)/(\d+)", url)
      if match:
        tweet_id = match.group(1)
        fx_resp = requests.get(
            f"https://api.fxtwitter.com/status/{tweet_id}", timeout=6
        )
        if fx_resp.status_code == 200:
          dados = fx_resp.json().get("tweet", {})
          texto_tweet = dados.get("text", "")
          autor = dados.get("author", {}).get("name", "")
          username = dados.get("author", {}).get("screen_name", "")
          curtidas = dados.get("likes", 0)
          reposts = dados.get("retweets", 0)
          respostas = dados.get("replies", 0)
          views = dados.get("views", 0)
          data_hora = dados.get("created_at", "Não informada")

          views_str = f"{views:,}" if isinstance(views, int) and views > 0 else (str(views) if views else "Não informada")

          conteudo_formatado = (
              f"=== DETALHES DO POST DO TWITTER / X ===\n"
              f"Autor: {autor} (@{username})\n"
              f"Data e Hora do Post: {data_hora}\n"
              f"Texto do Post: {texto_tweet}\n\n"
              f"--- MÉTRICAS DE ENGAJAMENTO ---\n"
              f"Visualizações / Impressões: {views_str}\n"
              f"Curtidas: {curtidas:,}\n"
              f"Republicações / Retweets: {reposts:,}\n"
              f"Comentários / Respostas: {respostas:,}\n"
          )
          return {"ok": True, "conteudo": conteudo_formatado}
    except Exception:
      pass

  if "reddit.com" in url:
    try:
      clean_url = url.split("?")[0].rstrip("/")
      json_url = f"{clean_url}.json"
      resp = requests.get(json_url, headers=headers_padrao, timeout=6)
      if resp.status_code == 200:
        data = resp.json()
        post_data = data[0]["data"]["children"][0]["data"]
        titulo = post_data.get("title", "")
        autor = post_data.get("author", "")
        subreddit = post_data.get("subreddit_name_prefixed", "")
        texto = post_data.get("selftext", "")
        ups = post_data.get("ups", 0)
        num_comments = post_data.get("num_comments", 0)
        upvote_ratio = post_data.get("upvote_ratio", 0)
        created_utc = post_data.get("created_utc")
        data_hora = datetime.fromtimestamp(created_utc).strftime("%d/%m/%Y %H:%M:%S") if created_utc else "Não informada"
        view_count = post_data.get("view_count")
        
        views_str = f"{view_count:,}" if view_count is not None else "Restrito pela API do Reddit"

        conteudo_formatado = (
            f"=== DETALHES DA PUBLICAÇÃO DO REDDIT ===\n"
            f"Subreddit: {subreddit}\n"
            f"Autor: u/{autor}\n"
            f"Título: {titulo}\n"
            f"Data e Hora: {data_hora}\n"
            f"Texto: {texto if texto else '[Publicação de Mídia/Link]'}\n\n"
            f"--- MÉTRICAS DE ENGAJAMENTO ---\n"
            f"Visualizações / Impressões: {views_str}\n"
            f"Upvotes (Curtidas): {ups:,}\n"
            f"Taxa de Aprovação: {int(upvote_ratio * 100)}%\n"
            f"Comentários: {num_comments:,}\n"
        )
        return {"ok": True, "conteudo": conteudo_formatado}
    except Exception:
      pass

  if "youtube.com" in url or "youtu.be" in url:
    try:
      resp = requests.get(url, headers=headers_padrao, timeout=6)
      if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        titulo = soup.find("meta", property="og:title")
        titulo_str = titulo["content"] if titulo else "Não informado"
        
        views_meta = soup.find("meta", itemprop="interactionCount") or soup.find("meta", property="og:video:tag")
        vis_str = views_meta["content"] if views_meta and views_meta.get("content") else "Detectada no player/HTML"
        
        desc_meta = soup.find("meta", property="og:description")
        desc_str = desc_meta["content"] if desc_meta else ""
        
        channel_meta = soup.find("link", itemprop="name")
        channel_str = channel_meta["content"] if channel_meta else "Não informado"

        conteudo_formatado = (
            f"=== DETALHES DO VÍDEO DO YOUTUBE ===\n"
            f"Título: {titulo_str}\n"
            f"Canal: {channel_str}\n"
            f"Descrição: {desc_str}\n\n"
            f"--- MÉTRICAS DE ENGAJAMENTO ---\n"
            f"Visualizações / Impressões: {vis_str}\n"
        )
        return {"ok": True, "conteudo": conteudo_formatado}
    except Exception:
      pass

  if "tiktok.com" in url:
    try:
      vx_url = url.replace("tiktok.com", "vxtiktok.com")
      resp = requests.get(vx_url, headers=headers_padrao, timeout=6)
      if resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "html.parser")
        og_desc = soup.find("meta", property="og:description")
        og_title = soup.find("meta", property="og:title")
        
        desc_texto = og_desc["content"] if og_desc else ""
        titulo_texto = og_title["content"] if og_title else ""

        conteudo_formatado = (
            f"=== DETALHES DO POST DO TIKTOK ===\n"
            f"Título / Autor: {titulo_texto}\n"
            f"Descrição e Métricas: {desc_texto}\n\n"
            f"--- MÉTRICAS DE ENGAJAMENTO ---\n"
            f"Visualizações / Impressões e Curtidas: Incluídas na descrição dos metadados\n"
        )
        return {"ok": True, "conteudo": conteudo_formatado}
    except Exception:
      pass

  try:
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        ),
        "X-With-Generated-Alt": "true",
        "X-With-Images-Summary": "true",
        "X-With-Links-Summary": "true",
    }
    resp = requests.get(jina_url, headers=headers, timeout=12)
    if resp.status_code == 200 and len(resp.text.strip()) > 50:
      return {"ok": True, "conteudo": resp.text[:10000]}
  except Exception:
    pass

  try:
    resp = requests.get(url, headers=headers_padrao, timeout=6)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    og_desc = soup.find("meta", property="og:description") or soup.find(
        "meta", attrs={"name": "description"}
    )
    og_title = soup.find("meta", property="og:title")
    pub_time = (
        soup.find("meta", property="article:published_time")
        or soup.find("meta", property="og:updated_time")
        or soup.find("time")
    )

    data_hora_str = (
        pub_time.get("datetime") or pub_time.get_text()
        if pub_time
        else "Não identificada no HTML"
    )
    desc_texto = (
        og_desc["content"] if og_desc and og_desc.get("content") else ""
    )
    titulo_texto = (
        og_title["content"] if og_title and og_title.get("content") else ""
    )

    texto_extraido = extrair_texto_html(resp.text)

    metadados = [
        "=== METADADOS E ENGAJAMENTO DA PÁGINA ===",
        f"Título: {titulo_texto}",
        (
            "Resumo de Engajamento (Visualizações/Impressões, Curtidas, Comentários e Descrição):"
            f" {desc_texto}"
        ),
        f"Data e Hora Publicada: {data_hora_str}",
    ]

    resultado_final = "\n".join(metadados) + "\n\n" + texto_extraido
    return {"ok": True, "conteudo": resultado_final}
  except Exception:
    return {"ok": False, "conteudo": ""}


def analisar_imagem_local(bytes_imagem, prompt="Descreva esta imagem em português."):
  try:
    img = Image.open(io.BytesIO(bytes_imagem)).convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    bytes_imagem = buffer.getvalue()
  except Exception:
    pass

  if not prompt or prompt.strip() == "":
    prompt = "Descreva esta imagem em detalhes."

  imagem_b64 = base64.b64encode(bytes_imagem).decode("utf-8")
  
  hosts = ["http://127.0.0.1:11434", "http://localhost:11434"]
  host_ativo = None
  modelos_disponiveis = []

  for host in hosts:
    try:
      resp_tags = requests.get(f"{host}/api/tags", timeout=3)
      if resp_tags.status_code == 200:
        host_ativo = host
        modelos_disponiveis = [m.get("name") for m in resp_tags.json().get("models", [])]
        break
    except Exception:
      continue

  if not host_ativo:
    yield "O Ollama não parece estar ativo em 127.0.0.1:11434 ou localhost:11434."
    return

  modelos_visao = [m for m in ["moondream:1.8b", "moondream", "llava", "llama3.2-vision"] if m in modelos_disponiveis]
  if not modelos_visao:
    modelos_visao = modelos_disponiveis if modelos_disponiveis else ["moondream:1.8b"]

  url_chat = f"{host_ativo}/api/chat"
  url_gen = f"{host_ativo}/api/generate"

  for modelo in modelos_visao:
    payload_chat = {
        "model": modelo,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [imagem_b64],
            }
        ],
        "stream": True,
    }
    try:
      resp = requests.post(url_chat, json=payload_chat, timeout=90, stream=True)
      if resp.status_code == 200:
        for line in resp.iter_lines():
          if line:
            try:
              data = json.loads(line.decode("utf-8"))
              content = data.get("message", {}).get("content", "")
              if content:
                registrar_evento_cerebro("resposta", f"Token: {content[:10]}")
                yield content
            except Exception:
              pass
        return
    except Exception:
      pass

    payload_gen = {
        "model": modelo,
        "prompt": prompt,
        "images": [imagem_b64],
        "stream": True,
    }
    try:
      resp = requests.post(url_gen, json=payload_gen, timeout=90, stream=True)
      if resp.status_code == 200:
        for line in resp.iter_lines():
          if line:
            try:
              data = json.loads(line.decode("utf-8"))
              content = data.get("response", "")
              if content:
                registrar_evento_cerebro("resposta", f"Token: {content[:10]}")
                yield content
            except Exception:
              pass
        return
    except Exception:
      pass

  yield "Erro ao processar imagem no Ollama."


def detectar_pedido_imagem(pergunta: str) -> bool:

  texto = pergunta.lower()

  verbos_diretos = r"\b(desenh\w*|ilustr\w*|renderiz\w*)\b"
  if re.search(verbos_diretos, texto):
    return True

  verbos_criacao = r"\b(gera|gere|gerar|cri[ae]|criar|monta|montar|fa[çc]a|fazer|faz)\b"
  substantivos_imagem = (
      r"\b(imagem|imagens|foto|fotos|figura|figuras|wallpaper|logo|logotipo|"
      r"banner|capa|thumbnail|arte|ilustra[çc][ãa]o)\b"
  )
  if re.search(verbos_criacao, texto) and re.search(substantivos_imagem, texto):
    return True

  return False


def gerar_imagem_ia(prompt: str, largura: int = 1024, altura: int = 1024):

  if not prompt or not prompt.strip():
    return None

  prompt_codificado = requests.utils.quote(prompt.strip()[:800])
  semente = random.randint(0, 999999)

  for modelo in ["flux", "turbo"]:
    try:
      url = (
          f"https://image.pollinations.ai/prompt/{prompt_codificado}"
          f"?width={largura}&height={altura}&model={modelo}"
          f"&seed={semente}&nologo=true"
      )
      resp = requests.get(url, timeout=90)
      tipo_conteudo = resp.headers.get("content-type", "")
      if resp.status_code == 200 and tipo_conteudo.startswith("image"):
        return resp.content
    except Exception:
      continue

  return None


def detectar_nicho_e_queries(pergunta: str, historico: list) -> tuple:
  texto = pergunta.lower()
  queries = [f"{pergunta} 2026"]
  nicho = "GERAL"
  ano_atual = 2026

  termos_atuais = [
      "atual",
      "atualmente",
      "hoje",
      "quem é",
      "quem e",
      "joga",
      "time",
      "clube",
      "papa",
      "presidente",
      "campeao",
      "campeão",
      "elenco",
      "contratou",
      "transferência",
  ]
  if any(k in texto for k in termos_atuais):
    queries.append(f"{pergunta} {ano_atual} notícias recentes")

  if any(
      k in texto
      for k in ["clima", "tempo", "chover", "temperatura", "previsão", "previsao"]
  ):
    nicho = "CLIMA_E_MAPAS"
    queries.append(f"{pergunta} coordenadas latitude longitude 2026")

    texto_filtrado = texto
    for termo in [
        "clima",
        "tempo",
        "chover",
        "temperatura",
        "previsão",
        "previsao",
        "pra",
        "hoje",
        "em",
        "de",
        "para",
        "no",
        "na",
    ]:
      texto_filtrado = re.sub(rf"\b{termo}\b", "", texto_filtrado)
    texto_filtrado = texto_filtrado.strip()
    texto_filtrado = re.sub(r"\b[a-z]{2}\b", "", texto_filtrado).strip()

    resp = st.session_state.get("contexto_local", {})
    cit_padrao = resp.get("city")

    if texto_filtrado and len(texto_filtrado) > 2:
      cidade_alvo = texto_filtrado
    else:
      cidade_alvo = cit_padrao

    if cidade_alvo:

      def normalizar_slug(t):
        return re.sub(
            r"[\s-]+",
            "-",
            unicodedata.normalize("NFKD", t)
            .encode("ascii", "ignore")
            .decode("utf-8")
            .lower()
            .strip(),
        )

      query_accuweather = (
          f"site:accuweather.com/pt/br/ {normalizar_slug(cidade_alvo)} weather"
          " forecast 2026"
      )
      queries.append(query_accuweather)

  elif any(k in texto for k in ["onde fica", "cidade", "mapa", "turismo"]):
    nicho = "CLIMA_E_MAPAS"
    queries.append(f"{pergunta} wikipedia turismo 2026")
  elif any(k in texto for k in ["roblox", "luau"]):
    nicho = "ROBLOX"
    queries.append(f"{pergunta} site:devforum.roblox.com 2026")
  elif any(k in texto for k in ["fifa", "ea fc", "futbin"]):
    nicho = "FIFA"
    queries.append(f"{pergunta} {ano_atual}")

  return nicho, queries


def pesquisar_web_avancado(pergunta: str):
  st.session_state["fontes_ultima_busca"] = []
  nicho, queries = detectar_nicho_e_queries(
      pergunta, st.session_state["historico"]
  )
  resultados_busca = []

  try:
    with DDGS() as ddgs:
      for q in queries:
        resultados_busca.extend(list(ddgs.text(q, max_results=3)))
  except:
    pass

  if not resultados_busca:
    return {"ok": False, "contexto": ""}

  links_validos = [
      r["href"] for r in resultados_busca if url_valida(r["href"])
  ][:3]
  st.session_state["fontes_ultima_busca"] = [
      {"titulo": r["title"], "link": r["href"]} for r in resultados_busca[:3]
  ]

  contexto_paginas = []
  with ThreadPoolExecutor(max_workers=3) as executor:
    futuros = {
        executor.submit(extrair_texto_da_url, url): url for url in links_validos
    }
    for futuro in as_completed(futuros):
      res = futuro.result()
      if res["ok"] and res["conteudo"].strip():
        contexto_paginas.append(res["conteudo"])

  if contexto_paginas:
    contexto = "\n\n--- NOVA FONTE RASPADA PROFUNDA ---\n\n".join(
        contexto_paginas
    )
  else:
    contexto = "\n".join(
        [f"Fonte: {r['title']}\nTexto: {r['body']}" for r in resultados_busca[:3]]
    )

  if nicho == "CLIMA_E_MAPAS":
    coords = re.findall(r"([-?]\d+\.\d+)", contexto)
    if len(coords) >= 2:
      try:
        clima = requests.get(
            f"https://api.open-meteo.com/v1/forecast?latitude={coords[0]}&longitude={coords[1]}&current=temperature_2m,relative_humidity_2m,wind_speed_10m&timezone=auto",
            timeout=3,
        ).json()
        curr = clima["current"]
        contexto += (
            f"\nClima da cidade pesquisada: {curr['temperature_2m']}°C, Umidade:"
            f" {curr['relative_humidity_2m']}%, Vento:"
            f" {curr['wind_speed_10m']} km/h"
        )
      except:
        pass

  return {"ok": True, "contexto": contexto}


def enviar_requisicao_ollama_local(messages, system_instruction):
  payload = [{"role": "system", "content": system_instruction}] + messages
  
  hosts = ["http://127.0.0.1:11434", "http://localhost:11434"]
  host_ativo = None
  modelos_disponiveis = []

  for host in hosts:
    try:
      resp_tags = requests.get(f"{host}/api/tags", timeout=3)
      if resp_tags.status_code == 200:
        host_ativo = host
        modelos_disponiveis = [m.get("name") for m in resp_tags.json().get("models", [])]
        break
    except Exception:
      continue

  if not host_ativo:
    yield "O Ollama local não está acessível em 127.0.0.1:11434. Verifique se o aplicativo Ollama está em execução no Windows."
    return

  modelos_preferenciais = [
      "qwen2.5-coder:1.5b",
      "qwen2.5-coder:3b",
      "qwen2.5-coder:7b",
      "llama3.2",
      "llama3",
  ]

  modelos_para_tentar = [m for m in modelos_preferenciais if m in modelos_disponiveis]
  if not modelos_para_tentar:
    modelos_para_tentar = modelos_disponiveis if modelos_disponiveis else modelos_preferenciais

  for modelo in modelos_para_tentar:
    try:
      resp = requests.post(
          f"{host_ativo}/api/chat",
          json={"model": modelo, "messages": payload, "stream": True},
          timeout=120,
          stream=True,
      )
      if resp.status_code == 200:
        for line in resp.iter_lines():
          if line:
            try:
              data = json.loads(line.decode("utf-8"))
              content = data.get("message", {}).get("content", "")
              if content:
                registrar_evento_cerebro("resposta", f"Token: {content[:10]}")
                yield content
            except Exception:
              pass
        return
    except Exception:
      continue

  yield "O Ollama local não respondeu a tempo ao carregar o modelo. Tente novamente em alguns segundos."


def enviar_requisicao_groq(messages, system_instruction):
  chave = st.session_state.get("api_key")

  if chave:
    payload = [{"role": "system", "content": system_instruction}] + messages
    modelos = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
    ]

    for modelo in modelos:
      try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {chave}",
                "Content-Type": "application/json",
            },
            json={"model": modelo, "messages": payload, "temperature": 0.25, "stream": True},
            timeout=25,
            stream=True,
        )
        if resp.status_code == 200:
          for line in resp.iter_lines():
            if line:
              line_str = line.decode("utf-8")
              if line_str.startswith("data: "):
                data_str = line_str[6:].strip()
                if data_str == "[DONE]":
                  break
                try:
                  data = json.loads(data_str)
                  content = data["choices"][0]["delta"].get("content", "")
                  if content:
                    registrar_evento_cerebro("resposta", f"Token: {content[:10]}")
                    yield content
                except Exception:
                  pass
          return
      except Exception:
        continue

  yield from enviar_requisicao_ollama_local(messages, system_instruction)


def iniciar_geracao_cerebro():

  token = st.session_state.get("token_sessao_oculto", "SES-0000")
  generation_id = f"{time.time_ns()}-{random.randint(1000, 9999)}"
  started = time.time()

  st.session_state["brain_generation_id"] = generation_id
  st.session_state["brain_started_at"] = started
  st.session_state["brain_finished_at"] = 0
  st.session_state["brain_status"] = "running"
  st.session_state["brain_events"] = []

  _gravar_estado_cerebro(token, {
    "generation_id": generation_id,
    "status": "running",
    "started_at": started,
    "finished_at": 0,
    "events": [],
  })


def finalizar_geracao_cerebro():
  token = st.session_state.get("token_sessao_oculto", "SES-0000")
  finished = time.time()

  st.session_state["brain_finished_at"] = finished
  st.session_state["brain_status"] = "complete"

  estado = _ler_estado_cerebro(token)
  estado["generation_id"] = st.session_state.get("brain_generation_id", "")
  estado["status"] = "complete"
  estado["started_at"] = st.session_state.get("brain_started_at", 0)
  estado["finished_at"] = finished
  estado["events"] = st.session_state.get("brain_events", [])
  _gravar_estado_cerebro(token, estado)


def renderizar_cerebro_ia(num_nos=120, altura_canvas=950):
 
  token_js = json.dumps(
    st.session_state.get("token_sessao_oculto", "SES-0000"),
    ensure_ascii=False,
  )

  components.html(f"""
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: 100%; height: 100%; overflow: hidden; background: #000; font-family: monospace; }}
      #brainGraphCanvas {{ width: 100%; height: 100%; display: block; background: #000; }}
      #brainStatus {{
        position: fixed; left: 12px; top: 10px; z-index: 10;
        color: rgba(255,255,255,.58); font: 10px monospace;
        letter-spacing: .7px; pointer-events: none;
      }}
    </style>

    <div id="brainStatus">CÉREBRO • AGUARDANDO PROCESSAMENTO</div>
    <canvas id="brainGraphCanvas"></canvas>

    <script>
      (function() {{
        const canvas = document.getElementById('brainGraphCanvas');
        const ctx = canvas.getContext('2d');
        const statusEl = document.getElementById('brainStatus');
        const token = {token_js};
        const endpoint = 'http://127.0.0.1:8765/brain_state?token=' + encodeURIComponent(token);

        const etapas = [
          {{chave:"entrada", label:"Prompt do Usuário"}},
          {{chave:"historico", label:"Histórico de Conversa"}},
          {{chave:"url", label:"Análise de URL"}},
          {{chave:"rag", label:"Consulta RAG Web"}},
          {{chave:"fontes", label:"Fontes Integradas"}},
          {{chave:"system", label:"System Prompt"}},
          {{chave:"motor", label:"Motor LLM — Groq / Ollama"}},
          {{chave:"resposta", label:"Resposta Gerada"}},
          {{chave:"visao", label:"Modelo de Visão — Ollama"}}
        ];

        const nodes = [];
        const pulsos = [];
        const numNodes = {num_nos};

        let generationId = "";
        let previousEventIds = new Set();
        let firstSuccessfulPoll = false;

        function resizeCanvas() {{
          const rect = canvas.getBoundingClientRect();
          const dpr = Math.max(1, window.devicePixelRatio || 1);
          canvas.width = Math.max(1, Math.floor(rect.width * dpr));
          canvas.height = Math.max(1, Math.floor(rect.height * dpr));
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        }}

        function createNodes() {{
          nodes.length = 0;
          const width = Math.max(1, canvas.clientWidth);
          const height = Math.max(1, canvas.clientHeight);

          for (let i = 0; i < numNodes; i++) {{
            const temInfo = i < etapas.length || Math.random() < .25;
            nodes.push({{
              id: i,
              x: Math.random() * width,
              y: Math.random() * height,
              vx: (Math.random() - .5) * .35,
              vy: (Math.random() - .5) * .35,
              radius: temInfo ? Math.random() * 2 + 3 : Math.random() * 1.5 + 1,
              alphaBase: Math.random() * .30 + .56,
              pulseSpeed: Math.random() * .02 + .006,
              info: i < etapas.length ? etapas[i].label : "No #" + (i + 1) + " [contexto]",
              temInfo: temInfo,
              brilho: 0
            }});
          }}
        }}

        function localizarNo(etapa) {{
          const texto = String(etapa || '').toLowerCase();
          if (texto.includes('url')) return 2;
          if (texto.includes('rag')) return 3;
          if (texto.includes('fonte')) return 4;
          if (texto.includes('hist')) return 1;
          if (texto.includes('system')) return 5;
          if (texto.includes('motor') || texto.includes('llm') || texto.includes('ollama') || texto.includes('groq')) return 6;
          if (texto.includes('resposta')) return 7;
          if (texto.includes('vis')) return 8;
          return 0;
        }}

        function addPulse(evento, origemEtapa) {{
          const origem = nodes[Math.max(0, Math.min(8, localizarNo(origemEtapa)))];
          const destino = nodes[Math.max(0, Math.min(8, localizarNo(evento.etapa)))];

          if (!origem || !destino) return;

          pulsos.push({{
            origem,
            destino,
            progresso: 0,
            chegouEm: 0,
            velocidade: .045
          }});

          origem.brilho = 1;
          destino.brilho = 1;
        }}

        async function pollState() {{
          try {{
            const response = await fetch(endpoint + '&_=' + Date.now(), {{cache:'no-store'}});
            if (response.ok) {{
              const state = await response.json();
              const events = Array.isArray(state.events) ? state.events : [];

              if (generationId !== state.generation_id) {{
                generationId = state.generation_id || "";
                previousEventIds = new Set();

                // Ao abrir o cérebro depois de uma geração concluída,
                // não fazemos replay: mostramos apenas o estado final.
                if (state.status === "complete") {{
                  for (const ev of events) {{
                    if (ev && ev.id) previousEventIds.add(ev.id);
                  }}
                }}
              }}

              if (!firstSuccessfulPoll) {{
                firstSuccessfulPoll = true;
                if (state.status === "complete") {{
                  for (const ev of events) {{
                    if (ev && ev.id) previousEventIds.add(ev.id);
                  }}
                }}
              }}

              for (let i = 0; i < events.length; i++) {{
                const ev = events[i];
                if (!ev || !ev.id || previousEventIds.has(ev.id)) continue;

                const previous = i > 0 ? events[i - 1] : null;
                addPulse(ev, previous ? previous.etapa : "entrada");
                previousEventIds.add(ev.id);
              }}

              if (state.status === "running") {{
                statusEl.textContent = "CÉREBRO • PROCESSANDO EM TEMPO REAL";
              }} else if (state.status === "complete") {{
                statusEl.textContent = "CÉREBRO • PROCESSAMENTO CONCLUÍDO";
              }} else {{
                statusEl.textContent = "CÉREBRO • AGUARDANDO PROCESSAMENTO";
              }}
            }}
          }} catch (e) {{}}

          setTimeout(pollState, 220);
        }}

        function drawPulse(p, now) {{
          if (p.progresso < 1) {{
            p.progresso = Math.min(1, p.progresso + p.velocidade);
          }}

          if (p.progresso >= 1 && p.chegouEm === 0) {{
            p.chegouEm = now;
          }}

          let alpha = 1;
          if (p.chegouEm > 0) {{
            alpha = Math.max(0, 1 - ((now - p.chegouEm) / 700));
          }}

          const x = p.origem.x + (p.destino.x - p.origem.x) * p.progresso;
          const y = p.origem.y + (p.destino.y - p.origem.y) * p.progresso;

          ctx.beginPath();
          ctx.moveTo(p.origem.x, p.origem.y);
          ctx.lineTo(x, y);
          ctx.strokeStyle = 'rgba(255,255,255,' + (.85 * alpha) + ')';
          ctx.lineWidth = 1.6;
          ctx.stroke();

          ctx.beginPath();
          ctx.arc(x, y, 3.2, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(255,255,255,' + alpha + ')';
          ctx.shadowBlur = 10 * alpha;
          ctx.shadowColor = '#fff';
          ctx.fill();
          ctx.shadowBlur = 0;

          return alpha > 0;
        }}

        function draw() {{
          const width = canvas.clientWidth;
          const height = canvas.clientHeight;
          const now = performance.now();

          ctx.clearRect(0, 0, width, height);
          ctx.fillStyle = '#000';
          ctx.fillRect(0, 0, width, height);

          // Distância de conexão adaptada ao tamanho real do canvas, para que
          // a mesma densidade de linhas apareça tanto na tela dividida quanto
          // na tela cheia (onde a área é bem maior).
          const areaAtual = Math.max(1, width * height);
          const distanciaConexao = Math.sqrt((20 * areaAtual) / (Math.max(1, numNodes) * Math.PI));

          for (let i = 0; i < nodes.length; i++) {{
            const n = nodes[i];

            n.x += n.vx;
            n.y += n.vy;

            if (n.x < 0 || n.x > width) {{
              n.vx *= -1;
              n.x = Math.max(0, Math.min(width, n.x));
            }}

            if (n.y < 0 || n.y > height) {{
              n.vy *= -1;
              n.y = Math.max(0, Math.min(height, n.y));
            }}

            n.brilho *= .965;

            const breathing = Math.sin(now * n.pulseSpeed) * .04;
            const alpha = Math.max(.36, Math.min(.92, n.alphaBase + breathing));

            for (let j = i + 1; j < nodes.length; j++) {{
              const n2 = nodes[j];
              const dx = n.x - n2.x;
              const dy = n.y - n2.y;
              const dist = Math.sqrt(dx * dx + dy * dy);

              if (dist < distanciaConexao) {{
                ctx.beginPath();
                ctx.moveTo(n.x, n.y);
                ctx.lineTo(n2.x, n2.y);
                ctx.strokeStyle = 'rgba(255,255,255,' + ((1 - dist / distanciaConexao) * .25) + ')';
                ctx.lineWidth = .8;
                ctx.stroke();
              }}
            }}

            ctx.beginPath();
            ctx.arc(n.x, n.y, n.radius + n.brilho * 1.7, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(255,255,255,' + Math.min(1, alpha + n.brilho * .30) + ')';

            // Brilho constante por padrão nas bolinhas; quando uma resposta
            // chega se conectando, o brilho aumenta e some suavemente de volta
            // ao normal (graças ao decaimento de n.brilho logo acima).
            ctx.shadowBlur = 4 + n.brilho * 10;
            ctx.shadowColor = '#fff';

            ctx.fill();
            ctx.shadowBlur = 0;
          }}

          for (let i = pulsos.length - 1; i >= 0; i--) {{
            if (!drawPulse(pulsos[i], now)) {{
              pulsos.splice(i, 1);
            }}
          }}

          // Rótulos independentes do alpha: nunca piscam.
          for (const n of nodes) {{
            if (!n.temInfo) continue;

            const label = '• ' + n.info;
            ctx.font = '10px monospace';
            ctx.fillStyle = 'rgba(255,255,255,.62)';
            ctx.fillText(label, n.x + 8, n.y + 3);

            if (n.brilho > .08) {{
              const widthText = ctx.measureText(label).width;
              ctx.beginPath();
              ctx.strokeStyle = 'rgba(255,255,255,' + (.13 * n.brilho) + ')';
              ctx.lineWidth = .5;
              ctx.strokeRect(n.x + 5, n.y - 9, widthText + 6, 14);
            }}
          }}

          requestAnimationFrame(draw);
        }}

        resizeCanvas();
        createNodes();
        window.addEventListener('resize', resizeCanvas);
        pollState();
        draw();
      }})();
    </script>
  """, height=altura_canvas)



def gerar_resposta_alemao(pergunta_usuario):
  iniciar_geracao_cerebro()
  registrar_evento_cerebro("entrada", "Prompt recebido")
  registrar_evento_cerebro("historico", f"{len(st.session_state['historico'])} mensagens no contexto")
  historico_api = [
      {"role": item["role"], "content": str(item["content"])}
      for item in st.session_state["historico"]
      if "role" in item and "content" in item
  ]

  prompt_final = pergunta_usuario
  urls_diretas = re.findall(r"https?://[^\s]+", pergunta_usuario)

  termos_codigo = [
      "script",
      "código",
      "codigo",
      "python",
      "roblox",
      "luau",
      "html",
      "css",
      "javascript",
      "js",
      "função",
      "funcao",
      "def ",
      "class ",
  ]
  eh_pedido_codigo = any(t in pergunta_usuario.lower() for t in termos_codigo)

  detalhes_pensamento = []

  if urls_diretas:
    registrar_evento_cerebro("url", f"{len(urls_diretas)} URL(s) detectada(s)")
    contexto_links = []
    st.session_state["fontes_ultima_busca"] = []

    for url in urls_diretas:
      res_link = extrair_texto_da_url(url)
      if res_link["ok"] and res_link["conteudo"].strip():
        contexto_links.append(
            f"Conteúdo e Análise Visual extraídos de ({url}):\n"
            f"{res_link['conteudo']}"
        )
        st.session_state["fontes_ultima_busca"].append(
            {"titulo": f"Link/Imagem Analisado ({url})", "link": url}
        )

    if contexto_links:
      detalhes_pensamento.append("-> URLs identificadas no prompt do usuário.")
      detalhes_pensamento.append("-> Raspagem profunda ativada (Jina AI / Metadados HTML).")
      prompt_final = (
          "O usuário forneceu estes links/imagens específicos para você"
          " analisar:\n\n"
          + "\n\n---\n\n".join(contexto_links)
          + f"\n\nInstrução ou Pergunta do Usuário: {pergunta_usuario}"
      )
  elif not eh_pedido_codigo:
    registrar_evento_cerebro("rag", "RAG Web iniciado")
    detalhes_pensamento.append("-> Pergunta geral/informativa identificada. Iniciando RAG na Web.")
    busca = pesquisar_web_avancado(pergunta_usuario)
    if busca["ok"]:
      registrar_evento_cerebro("fontes", "Fontes encontradas e integradas")
      detalhes_pensamento.append("-> Fontes encontradas e integradas ao contexto.")
      prompt_final = (
          "Baseie-se nestes dados em tempo real extraídos da internet"
          f" atualizados para o ano de 2026: {busca['contexto']}\n\nPergunta:"
          f" {pergunta_usuario}"
      )
  else:
    detalhes_pensamento.append("-> Pedido direto de código/engenharia de software detectado.")

  sys_prompt = get_system_prompt()
  registrar_evento_cerebro("system", "System Prompt carregado")
  detalhes_pensamento.append("-> System Prompt carregado com telemetria local e contexto real.")
  detalhes_pensamento.append(f"-> Histórico de conversação ativo: {len(historico_api)} mensagens.")
  detalhes_pensamento.append("-> Enviando requisição para motor LLM (Groq / Ollama)...")

  payload = historico_api + [{"role": "user", "content": prompt_final}]
  registrar_evento_cerebro("motor", "Requisição enviada ao Groq/Ollama em streaming")
  
  yield from enviar_requisicao_groq(payload, sys_prompt)
  registrar_evento_cerebro("resposta", "Motor LLM concluiu a geração")
  finalizar_geracao_cerebro()


def _rodar_geracao_texto_em_background(pergunta_usuario, generation_id, token):

  texto_acumulado = ""
  _gravar_estado_resposta(token, {
    "generation_id": generation_id,
    "status": "running",
    "texto": "",
  })

  try:
    for pedaco in gerar_resposta_alemao(pergunta_usuario):
      texto_acumulado += pedaco
      _gravar_estado_resposta(token, {
        "generation_id": generation_id,
        "status": "running",
        "texto": texto_acumulado,
      })
  except Exception as e:
    if not texto_acumulado.strip():
      texto_acumulado = f"Ocorreu um erro ao gerar a resposta: {e}"

  _gravar_estado_resposta(token, {
    "generation_id": generation_id,
    "status": "complete",
    "texto": texto_acumulado,
  })


  try:
    if st.session_state.get("resposta_pendente_generation_id") == generation_id:
      st.session_state["historico"].append(
          {"role": "assistant", "content": texto_acumulado, "pensamento": ""}
      )
      st.session_state["resposta_pendente_generation_id"] = ""
  except Exception:
    pass

  registrar_log_invisivel("SISTEMA", texto_acumulado)


def iniciar_resposta_texto_em_background(pergunta_usuario):

  token = st.session_state.get("token_sessao_oculto", "SES-0000")
  generation_id = f"{time.time_ns()}-{random.randint(1000, 9999)}"
  st.session_state["resposta_pendente_generation_id"] = generation_id

  ctx = get_script_run_ctx()
  thread = threading.Thread(
      target=_rodar_geracao_texto_em_background,
      args=(pergunta_usuario, generation_id, token),
      daemon=True,
  )
  add_script_run_ctx(thread, ctx)
  thread.start()
  return generation_id


def renderizar_resposta_ao_vivo(token, generation_id, altura_canvas=260):

  token_js = json.dumps(token, ensure_ascii=False)
  gen_js = json.dumps(generation_id, ensure_ascii=False)

  components.html(f"""
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ background: transparent; font-family: sans-serif; }}
      #respostaAoVivo {{
        color: #ffffff; white-space: pre-wrap; line-height: 1.55;
        font-size: 15px; padding: 2px 0;
      }}
      #respostaAoVivo .cursor {{
        display: inline-block; width: 7px; height: 15px;
        background: rgba(255,255,255,.75); margin-left: 2px;
        animation: piscarCursor 1s step-end infinite; vertical-align: text-bottom;
      }}
      @keyframes piscarCursor {{ 50% {{ opacity: 0; }} }}
    </style>
    <div id="respostaAoVivo">Gerando resposta...</div>
    <script>
      (function() {{
        const el = document.getElementById('respostaAoVivo');
        const token = {token_js};
        const generationId = {gen_js};
        const endpoint = 'http://127.0.0.1:8765/response_state?token=' + encodeURIComponent(token);

        async function poll() {{
          let terminou = false;
          try {{
            const r = await fetch(endpoint + '&_=' + Date.now(), {{cache:'no-store'}});
            if (r.ok) {{
              const estado = await r.json();
              if (estado.generation_id === generationId) {{
                const texto = estado.texto || '';
                el.innerHTML = (texto ? texto.replace(/&/g,'&amp;').replace(/</g,'&lt;') : 'Gerando resposta...') + '<span class="cursor"></span>';
                if (estado.status === 'complete') {{
                  el.querySelector('.cursor')?.remove();
                  terminou = true;
                }}
              }}
            }}
          }} catch (e) {{}}
          if (!terminou) setTimeout(poll, 250);
        }}
        poll();
      }})();
    </script>
  """, height=altura_canvas)


if is_admin_mode:

  st.title("Central Suprema de Moderação e Telemetria")
  st.caption("Modo de Exibição Administrativo Secreto Ativo via Token de URL")
  st.write("---")

  dados_sessoes = ler_logs_estruturados()
  lista_banidos = carregar_lista_banidos()

  tab_monitor, tab_banidos = st.tabs(
      ["Tráfego e Históricos", "Lista Negra (Banimentos)"]
  )

  with tab_monitor:
    if not dados_sessoes:
      st.info("Nenhum sinal telemétrico de tráfego recebido até o momento.")
    else:
      col_lista, col_chat = st.columns([1, 2], gap="large")
      with col_lista:
        st.subheader("Usuários Ativos")
        if st.button("Resetar Logs do Sistema"):
          if os.path.exists(LOG_FILE):
            open(LOG_FILE, "w").close()
            st.rerun()
        st.write("---")
        lista_ids_reais = list(dados_sessoes.keys())
        opcoes_menu = []
        for uid in lista_ids_reais:
          status_ban = (
              "(BANIDO)"
              if (
                  dados_sessoes[uid]["ip"] in lista_banidos
                  or dados_sessoes[uid]["token"] in lista_banidos
              )
              else ""
          )
          opcoes_menu.append(f"{status_ban} {uid}".strip())

        selecionado = st.radio(
            "Selecione um alvo para inspecionar:", options=opcoes_menu, index=0
        )
        idx = opcoes_menu.index(selecionado)
        alvo_id_real = lista_ids_reais[idx]
        alvo_dados = dados_sessoes[alvo_id_real]

      with col_chat:
        st.subheader("Painel de Moderação Visual")
        with st.container(border=True):
          st.write(f"**Identificação Telemétrica Completa:** `{alvo_id_real}`")
          st.write(f"**Token da Sessão:** `{alvo_dados['token']}`")
          st.write(f"**IP da Rede:** `{alvo_dados['ip']}`")
          st.write(f"**Localização:** {alvo_dados['local']}")
          st.write(f"**Último Sinal:** `{alvo_dados['ultima_atividade']}`")

          c1, c2 = st.columns(2)
          with c1:
            is_ip_ban = alvo_dados["ip"] in lista_banidos
            if not is_ip_ban:
              if st.button(
                  "Banir por IP da Rede",
                  type="primary",
                  use_container_width=True,
              ):
                aplicar_banimento(alvo_dados["ip"])
                st.rerun()
            else:
              if st.button(
                  "Reverter Ban por IP",
                  type="secondary",
                  use_container_width=True,
              ):
                revogar_banimento(alvo_dados["ip"])
                st.rerun()
          with c2:
            is_tok_ban = alvo_dados["token"] in lista_banidos
            if not is_tok_ban:
              if st.button(
                  "Banir Sessão (Aba)",
                  type="secondary",
                  use_container_width=True,
              ):
                aplicar_banimento(alvo_dados["token"])
                st.rerun()
            else:
              if st.button(
                  "Reverter Ban da Sessão",
                  type="secondary",
                  use_container_width=True,
              ):
                revogar_banimento(alvo_dados["token"])
                st.rerun()

        st.write("---")
        box_mensagens = st.container(height=400)
        with box_mensagens:
          for msg in alvo_dados["interacoes"]:
            if "USUÁRIO" in msg["role"]:
              with st.chat_message("user"):
                st.markdown(f"**Usuário** • `{msg['timestamp']}`")
                st.write(msg["texto"])
            else:
              with st.chat_message("assistant"):
                st.markdown(f"**Alemão (Engine)** • `{msg['timestamp']}`")
                w = msg["texto"]
                st.write(w)
        if st.button("Recarregar Conversa"):
          st.rerun()

  with tab_banidos:
    st.subheader("Gerenciamento Geral de Lista Negra")
    if not lista_banidos:
      st.info("Nenhum usuário ou endereço IP encontra-se banido atualmente.")
    else:
      for item_banido in lista_banidos:
        col_b, col_a = st.columns([3, 1])
        with col_b:
          st.code(f"Identificador Bloqueado: {item_banido}")
        with col_a:
          if st.button("Reverter Punição", key=f"rev_{item_banido}"):
            revogar_banimento(item_banido)
            st.rerun()

else:

  (
      _horario,
      _local,
      current_ip,
      _ipc,
      _infoc,
      _temp,
      _pct,
      _stat,
      _email,
  ) = obter_contexto_usuario()
  current_token = st.session_state.get("token_sessao_oculto", "")

  if checar_se_banido(current_ip, current_token):
    st.error(
        "Erro de Conexão: O acesso a este servidor foi restrito pelo"
        " administrador do sistema."
    )
    st.stop()

  with st.sidebar:
    st.markdown("# Grazueiro")
    st.caption("RAG Híbrido: Web + YouTube + Maps + Clima + Local Ollama")
    st.write("---")

    st.markdown("### Modo de Exibição")
    st.radio(
        "Escolha o modo:",
        ["Chat Normal", "Chat + Cérebro", "Tela Cheia"],
        key="modo_exibicao",
    )

    st.write("---")

    if GROQ_API_KEY_ENV:
      st.session_state["api_key"] = GROQ_API_KEY_ENV
      st.success("Chave Groq carregada!")
    else:
      st.text_input(
          "GroqCloud API Key (gsk_...):",
          type="password",
          placeholder="gsk_... (opcional se Ollama estiver ativo)",
          key="api_key",
      )


 
    _definir_chave_groq_compartilhada(st.session_state.get("api_key"))

    st.write("---")
    st.markdown("### Status do Sistema")
    st.info(f"Conversa activa: {len(st.session_state['historico'])} interações")
    st.caption("Ollama Local (`qwen2.5-coder:1.5b`) pronto como engine offline!")
    st.caption("Geração de Imagens: Pollinations.AI (gratuito, sem chave)")

    st.markdown("### Diagnóstico de Hardware")
    st.caption("Dados brutos enviados pelo seu navegador:")
    st.text_area(
        "Assinatura (User-Agent):",
        value=st.session_state["raw_ua"],
        height=70,
        disabled=True,
    )

    st.markdown("**Status de Energia do Dispositivo:**")
    components.html(
        """
            <div id="bat-box" style="font-family: monospace; font-size: 13px; color: #ffffff; background-color: #000000; padding: 10px; border-radius: 6px; border: 1px solid #ffffff;">
                 Lendo sensores do dispositivo...
            </div>
            <script>
                if ('getBattery' in navigator) {
                    navigator.getBattery().then(function(battery) {
                        function updateBatteryDisplay() {
                            const level = Math.round(battery.level * 100);
                            const charging = battery.charging ? "Carregando" : "Desconectado";
                            document.getElementById('bat-box').innerHTML = `<b>Nível:</b> ${level}% <br><b>Estado:</b> ${charging}`;
                            if(battery.charging) {
                                document.getElementById('bat-box').style.color = "#34d399";
                            } else if (level < 20) {
                                document.getElementById('bat-box').style.color = "#f87171";
                            } else {
                                document.getElementById('bat-box').style.color = "#ffffff";
                            }
                            
                            try {
                                const url = new URL(window.parent.location.href);
                                url.searchParams.set('bat_pct', level);
                                url.searchParams.set('bat_status', battery.charging ? 'carregando' : 'desconectado');
                                window.parent.history.replaceState({}, '', url);
                            } catch(e) {}
                        }
                        updateBatteryDisplay();
                        battery.addEventListener('chargingchange', updateBatteryDisplay);
                        battery.addEventListener('levelchange', updateBatteryDisplay);
                    });
                } else {
                    document.getElementById('bat-box').innerHTML = "API de bateria não suportada neste navegador.";
                    document.getElementById('bat-box').style.color = "#fbbf24";
                }
            </script>
        """,
        height=65,
    )

    st.write("---")
    st.markdown("### Configurações de Áudio")
    ouvir_audio = st.toggle(
        "Ouvir resposta por voz automaticamente", value=True, key="ouvir_audio"
    )

    if st.button("Limpar Memória"):
      st.session_state["historico"] = []
      st.session_state["fontes_ultima_busca"] = []
      st.rerun()

  obter_contexto_usuario()

  
  modo_atual = st.session_state.get("modo_exibicao")

  if modo_atual == "Chat + Cérebro":
    st.markdown("""
      <style>
        .brain-split-label {
          font: 11px monospace;
          letter-spacing: 1px;
          margin: 0 0 8px 2px;
          opacity: .7;
        }
      </style>
    """, unsafe_allow_html=True)

    col_chat, col_brain = st.columns([1, 1], gap="medium")

    with col_chat:
      st.title("Grazueiro")
      area_chat_split = st.container(height=650)
      with area_chat_split:
        for msg in st.session_state["historico"]:
          with st.chat_message(msg["role"]):
            if msg.get("tipo") == "imagem" and msg.get("imagem_bytes"):
              st.image(msg["imagem_bytes"])
              if msg.get("content"):
                st.caption(msg["content"])
            else:
              st.write(msg["content"])

        _gid_pendente_split = st.session_state.get("resposta_pendente_generation_id", "")
        if _gid_pendente_split:
          _token_split = st.session_state.get("token_sessao_oculto", "SES-0000")
          _estado_pendente_split = _ler_estado_resposta(_token_split)
          if _estado_pendente_split.get("generation_id") == _gid_pendente_split:
            with st.chat_message("assistant"):
              renderizar_resposta_ao_vivo(_token_split, _gid_pendente_split)

      if st.session_state["fontes_ultima_busca"]:
        with st.expander("Fontes consultadas"):
          for f in st.session_state["fontes_ultima_busca"]:
            st.markdown(f"- [{f['titulo']}]({f['link']})")

    with col_brain:
      st.markdown('<div class="brain-split-label">CÉREBRO DA IA • MONITORAMENTO EM TEMPO REAL</div>', unsafe_allow_html=True)
      renderizar_cerebro_ia(num_nos=120, altura_canvas=650)

    imagem_upload_split = st.file_uploader(
      "Anexar imagem para o Ollama analisar junto com a mensagem",
      type=["png", "jpg", "jpeg", "webp"],
      label_visibility="collapsed",
      key="imagem_upload_split",
    )

    pergunta = st.chat_input("Pergunte algo ou cole um link para analisar...")

    if pergunta:
      if detectar_pedido_imagem(pergunta) and not imagem_upload_split:
        st.session_state["historico"].append({"role": "user", "content": pergunta})
        registrar_log_invisivel("USUÁRIO", pergunta)

        with st.chat_message("user"):
          st.write(pergunta)

        with st.chat_message("assistant"):
          iniciar_geracao_cerebro()
          registrar_evento_cerebro("entrada", "Pedido de geração de imagem recebido")
          registrar_evento_cerebro("imagem", "Gerando imagem com IA (Pollinations)...")
          with st.spinner("Gerando imagem..."):
            imagem_gerada = gerar_imagem_ia(pergunta)
          if imagem_gerada:
            st.image(imagem_gerada)
            registrar_evento_cerebro("resposta", "Imagem gerada com sucesso")
            legenda_imagem = f"[Imagem Gerada]: {pergunta}"
            st.session_state["historico"].append({
                "role": "assistant",
                "content": legenda_imagem,
                "pensamento": "-> Pedido de imagem detectado. Geração via API de imagem (Pollinations.AI).",
                "tipo": "imagem",
                "imagem_bytes": imagem_gerada,
            })
            registrar_log_invisivel("SISTEMA", legenda_imagem)
          else:
            erro_imagem = "Não consegui gerar a imagem agora. O serviço pode estar temporariamente indisponível, tente novamente em instantes."
            st.write(erro_imagem)
            registrar_evento_cerebro("resposta", "Falha ao gerar imagem")
            st.session_state["historico"].append(
                {"role": "assistant", "content": erro_imagem, "pensamento": ""}
            )
            registrar_log_invisivel("SISTEMA", erro_imagem)
          finalizar_geracao_cerebro()
      elif imagem_upload_split:
        texto_usuario = f"[Imagem Anexada]: {pergunta}"
        st.session_state["historico"].append({"role": "user", "content": texto_usuario})
        registrar_log_invisivel("USUÁRIO", texto_usuario)

        with st.chat_message("user"):
          st.write(texto_usuario)

        with st.chat_message("assistant"):
          iniciar_geracao_cerebro()
          registrar_evento_cerebro("entrada", "Imagem e prompt recebidos")
          registrar_evento_cerebro("visao", "Modelo de visão local iniciado")
          bytes_img = imagem_upload_split.getvalue()
          resposta_visio = st.write_stream(analisar_imagem_local(bytes_img, prompt=pergunta))
          registrar_evento_cerebro("resposta", "Análise visual concluída")
          finalizar_geracao_cerebro()
          finalizar_geracao_cerebro()

          st.session_state["historico"].append(
            {"role": "assistant", "content": resposta_visio, "pensamento": "-> Análise visual ativada no modelo de visão local (Ollama/Llama)."}
          )
          registrar_log_invisivel("SISTEMA", resposta_visio)
      else:
        st.session_state["historico"].append({"role": "user", "content": pergunta})
        registrar_log_invisivel("USUÁRIO", pergunta)

        with st.chat_message("user"):
          st.write(pergunta)

        with st.chat_message("assistant"):
          resposta = st.write_stream(gerar_resposta_alemao(pergunta))
          st.session_state["historico"].append(
              {"role": "assistant", "content": resposta, "pensamento": ""}
          )
          registrar_log_invisivel("SISTEMA", resposta)

      st.rerun()

  elif modo_atual == "Tela Cheia":
    st.markdown("""
        <style>
            [data-testid="stSidebar"] { display: none !important; }
            [data-testid="stHeader"] { display: none !important; }
            [data-testid="stFooter"] { display: none !important; }
            .block-container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; height: 100vh !important; overflow: hidden !important; }
            iframe { border: none !important; display: block !important; }
            
            /* Posiciona o botão de sair flutuando no canto superior direito */
            div[data-testid="stButton"] {
                position: fixed !important;
                top: 20px !important;
                right: 20px !important;
                z-index: 999999 !important;
            }
        </style>
    """, unsafe_allow_html=True)

    def sair_tela_cheia():
      st.session_state["modo_exibicao"] = "Chat Normal"

    st.button("Voltar ao Chat Normal", key="btn_sair_tc", on_click=sair_tela_cheia)

   
    renderizar_cerebro_ia(num_nos=120, altura_canvas=950)

  else:
   
    st.title("Grazueiro")

    area_chat = st.container(height=500)
    with area_chat:
      for msg in st.session_state["historico"]:
        with st.chat_message(msg["role"]):
          if msg.get("tipo") == "imagem" and msg.get("imagem_bytes"):
            st.image(msg["imagem_bytes"])
            if msg.get("content"):
              st.caption(msg["content"])
          else:
            st.write(msg["content"])

      _gid_pendente_normal = st.session_state.get("resposta_pendente_generation_id", "")
      if _gid_pendente_normal:
        _token_normal = st.session_state.get("token_sessao_oculto", "SES-0000")
        _estado_pendente_normal = _ler_estado_resposta(_token_normal)
        if _estado_pendente_normal.get("generation_id") == _gid_pendente_normal:
          with st.chat_message("assistant"):
            renderizar_resposta_ao_vivo(_token_normal, _gid_pendente_normal)

    if st.session_state["fontes_ultima_busca"]:
      with st.expander("Fontes consultadas"):
        for f in st.session_state["fontes_ultima_busca"]:
          st.markdown(f"- [{f['titulo']}]({f['link']})")

    st.markdown("### Controle por Voz")

    components.html(
        """
          <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 5px;">
              <button id="start-mic" style="background-color: #000000; color: #ffffff; border: 1px solid #ffffff; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: bold; font-family: sans-serif;">
                  Ligar Microfone
              </button>
              <span id="mic-status" style="font-family: sans-serif; font-size: 13px; color: #ffffff;">Pronto para ouvir</span>
          </div>
          <script>
              const btn = document.getElementById('start-mic');
              const status = document.getElementById('mic-status');
              
              if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
                  status.innerText = "Reconhecimento de voz não suportado neste navegador.";
                  btn.disabled = true;
                  btn.style.backgroundColor = '#000000';
              } else {
                  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                  const recognition = new SpeechRecognition();
                  recognition.lang = 'pt-BR';
                  recognition.interimResults = false;
                  
                  let gravando = false;
                  
                  btn.addEventListener('click', () => {
                      if(!gravando) {
                          recognition.start();
                      } else {
                          recognition.stop();
                      }
                  });
                  
                  recognition.onstart = () => {
                      gravando = true;
                      btn.style.backgroundColor = '#ffffff';
                      btn.style.color = '#000000';
                      btn.innerText = 'Parar Gravação';
                      status.innerText = 'Ouvindo microfone... fale agora';
                  };
                  
                  recognition.onresult = (event) => {
                      const textoCapturado = event.results[0][0].transcript;
                      status.innerText = 'Transcrevendo...';
                      
                      const targetInput = window.parent.document.querySelector('.stChatInput textarea');
                      if(targetInput) {
                          targetInput.value = textoCapturado;
                          targetInput.dispatchEvent(new Event('input', { bubbles: true }));
                          status.innerText = 'Voz inserida com sucesso no campo de texto!';
                      } else {
                          status.innerText = 'Clique na caixa de texto abaixo para colar: "' + textoCapturado + '"';
                      }
                  };
                  
                  recognition.onerror = (e) => {
                      status.innerText = 'Erro no microfone: ' + e.error;
                  };
                  
                  recognition.onend = () => {
                      gravando = false;
                      btn.style.backgroundColor = '#000000';
                      btn.style.color = '#ffffff';
                      btn.innerText = 'Ligar Microfone';
                  };
              }
          </script>
      """,
        height=65,
    )

    if (
        st.session_state.get("ouvir_audio", True)
        and st.session_state["historico"]
        and st.session_state["historico"][-1]["role"] == "assistant"
    ):
      texto_fala = (
          st.session_state["historico"][-1]["content"]
          .replace('"', '\\"')
          .replace("\n", " ")
      )
      components.html(
          f"""
              <script>
                  if ('speechSynthesis' in window) {{
                      window.speechSynthesis.cancel();
                      const msg = new SpeechSynthesisUtterance("{texto_fala}");
                      msg.lang = "pt-BR";
                      msg.rate = 1.0; 
                      window.speechSynthesis.speak(msg);
                  }}
              </script>
          """,
          height=0,
          width=0,
      )

    imagem_upload = st.file_uploader(
        "Anexar imagem para o Ollama analisar junto com a mensagem",
        type=["png", "jpg", "jpeg", "webp"],
        label_visibility="collapsed",
        key="imagem_upload_normal",
    )

    pergunta = st.chat_input("Pergunte algo ou cole um link para analisar...")

    if pergunta:
      if detectar_pedido_imagem(pergunta) and not imagem_upload:
        st.session_state["historico"].append({"role": "user", "content": pergunta})
        registrar_log_invisivel("USUÁRIO", pergunta)

        with st.chat_message("user"):
          st.write(pergunta)

        with st.chat_message("assistant"):
          iniciar_geracao_cerebro()
          registrar_evento_cerebro("entrada", "Pedido de geração de imagem recebido")
          registrar_evento_cerebro("imagem", "Gerando imagem com IA (Pollinations)...")
          with st.spinner("Gerando imagem..."):
            imagem_gerada = gerar_imagem_ia(pergunta)
          if imagem_gerada:
            st.image(imagem_gerada)
            registrar_evento_cerebro("resposta", "Imagem gerada com sucesso")
            legenda_imagem = f"[Imagem Gerada]: {pergunta}"
            st.session_state["historico"].append({
                "role": "assistant",
                "content": legenda_imagem,
                "pensamento": "-> Pedido de imagem detectado. Geração via API de imagem (Pollinations.AI).",
                "tipo": "imagem",
                "imagem_bytes": imagem_gerada,
            })
            registrar_log_invisivel("SISTEMA", legenda_imagem)
          else:
            erro_imagem = "Não consegui gerar a imagem agora. O serviço pode estar temporariamente indisponível, tente novamente em instantes."
            st.write(erro_imagem)
            registrar_evento_cerebro("resposta", "Falha ao gerar imagem")
            st.session_state["historico"].append(
                {"role": "assistant", "content": erro_imagem, "pensamento": ""}
            )
            registrar_log_invisivel("SISTEMA", erro_imagem)
          finalizar_geracao_cerebro()
      elif imagem_upload:
        texto_usuario = f"[Imagem Anexada]: {pergunta}"
        st.session_state["historico"].append({"role": "user", "content": texto_usuario})
        registrar_log_invisivel("USUÁRIO", texto_usuario)

        with st.chat_message("user"):
          st.write(texto_usuario)
        with st.chat_message("assistant"):
          iniciar_geracao_cerebro()
          registrar_evento_cerebro("entrada", "Imagem e prompt recebidos")
          registrar_evento_cerebro("visao", "Modelo de visão local iniciado")
          bytes_img = imagem_upload.getvalue()
          resposta_visio = st.write_stream(analisar_imagem_local(bytes_img, prompt=pergunta))
          registrar_evento_cerebro("resposta", "Análise visual concluída")
          
          pensamento_img = "-> Análise visual ativada no modelo de visão local (Ollama/Llama)."

          st.session_state["historico"].append(
              {"role": "assistant", "content": resposta_visio, "pensamento": pensamento_img}
          )
          registrar_log_invisivel("SISTEMA", resposta_visio)
      else:
        st.session_state["historico"].append({"role": "user", "content": pergunta})
        registrar_log_invisivel("USUÁRIO", pergunta)

        with st.chat_message("user"):
          st.write(pergunta)

        with st.chat_message("assistant"):
          resposta = st.write_stream(gerar_resposta_alemao(pergunta))
          st.session_state["historico"].append(
              {"role": "assistant", "content": resposta, "pensamento": ""}
          )
          registrar_log_invisivel("SISTEMA", resposta)

      st.rerun()