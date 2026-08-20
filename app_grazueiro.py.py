import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import io
import os
import random
import re
import time
import unicodedata
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from duckduckgo_search import DDGS
from PIL import Image
import requests
import streamlit as st
import streamlit.components.v1 as components


load_dotenv()
GROQ_API_KEY_ENV = os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")


LOG_FILE = ".telemetria_sistema.log"
BAN_FILE = ".usuarios_banidos.txt"


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

# Injeção de CSS para interface 100% preta com bordas brancas minimalistas
st.markdown("""
<style>
    /* Fundo Preto Absoluto Geral */
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"], [data-testid="stSidebar"], header, footer {
        background-color: #000000 !important;
        color: #ffffff !important;
    }

    /* Remoção de fundos cinzas no rodapé, caixa de chat, inputs e upload */
    [data-testid="stBottom"],
    [data-testid="stBottomBlockContainer"],
    [data-testid="stChatInput"],
    [data-testid="stChatInput"] *,
    [data-testid="stChatInputContainer"],
    .stChatInputContainer,
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
  return f"""Você é grazueiro, um assistente: inteligente, detalhista, focado em soluções estruturadas e um especialista sênior de nível Principal/Staff em Engenharia de Software e Programação.
Você possui domínio técnico avançado em arquitetura de código, desenvolvimento de jogos (especialmente Roblox Luau), algoritmos, estruturas de dados, otimização de performance, padrões de projeto (Design Patterns), concorrência, tratamento rigoroso de erros e debugging avançado.

DIRETRIZES RIGOROSAS DE PROGRAMAÇÃO E ENGENHARIA DE SOFTWARE:
1. PADRÕES MODERNOS EM ROBLOX (LUAU):
   - Nunca utilize métodos ou funções obsoletas/descontinuadas. Use `task.wait()`, `task.spawn()` e `task.delay()` em vez de `wait()`, `spawn()` ou `delay()`.
   - NUNCA altere o `game.StarterGui` diretamente via script do servidor para tentar exibir uma GUI para um jogador no jogo. O `StarterGui` serve apenas como modelo inicial ao entrar. Para manipular a interface em tempo real de um jogador, encontre o jogador (`game.Players:GetPlayerFromCharacter()`) e modifique a pasta `PlayerGui` dele.
   - Use propriedades modernas de interface de usuário, como `TextSize` em vez da obsoleta `FontSize`.
   - Sempre utilize mecanismos de Debounce (cooldown) em eventos repetitivos como `.Touched` para evitar bugs de execução acelerada ou disparo múltiplo inadvertido.
   - Respeite estritamente a separação entre Script (Servidor), LocalScript (Cliente) e ModuleScript (Módulos compartilhados/utilitários).
2. QUALIDADE DE CÓDIGO E EXCELÊNCIA TÉCNICA GERAL:
   - Escreva códigos completos, limpos, altamente seguros, modulares e prontos para produção. Evite reticências (`...`) ou trechos omitidos dentro dos blocos de código.
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
  """Extrai conteúdo de qualquer link, com suporte avançado a redes sociais
  (Twitter/X, Reddit, YouTube, TikTok, Instagram, etc.), capturando métricas de engajamento
  (curtidas, comentários, reposts e visualizações/impressões) e data/hora.
  """
  headers_padrao = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          " (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
      )
  }

  # 1. Suporte Avançado para Twitter / X (Extrai métricas exatas, visualizações/impressões e Data/Hora via API aberta)
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

  # 2. Suporte Avançado para Reddit (Extrai dados do post, Upvotes, Comentários e Visualizações via endpoint JSON)
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

  # 3. Suporte Avançado para YouTube (Extrai Título, Canal, Visualizações/Impressões e Descrição)
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

  # 4. Suporte Avançado para TikTok (Extrai metadados de engajamento e visualizações)
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

  # 5. Leitura via Jina AI Reader (Fallback principal)
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

  # 6. Fallback com BeautifulSoup (Instagram / Outros) para extrair Metadados de Engajamento, Visualizações e Data/Hora
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
    return "O Ollama não parece estar ativo em 127.0.0.1:11434 ou localhost:11434."

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
        "stream": False,
    }
    try:
      resp = requests.post(url_chat, json=payload_chat, timeout=90)
      if resp.status_code == 200:
        return resp.json()["message"]["content"]
    except Exception:
      pass

    payload_gen = {
        "model": modelo,
        "prompt": prompt,
        "images": [imagem_b64],
        "stream": False,
    }
    try:
      resp = requests.post(url_gen, json=payload_gen, timeout=90)
      if resp.status_code == 200:
        return resp.json().get("response", "Sem resposta.")
    except Exception:
      pass

  return "Erro ao processar imagem no Ollama."


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
  """Executa a geração de texto localmente via Ollama com suporte a resiliência no Windows."""
  payload = [{"role": "system", "content": system_instruction}] + messages
  
  hosts = ["http://127.0.0.1:11434", "http://localhost:11434"]
  host_ativo = None
  modelos_disponiveis = []

  # Detecta host ativo e lê os modelos que o usuário REALMENTE baixou
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
    return {
        "ok": False,
        "resposta": (
            "O Ollama local não está acessível em 127.0.0.1:11434. Verifique se o"
            " aplicativo Ollama está em execução no Windows."
        ),
    }

  # Modelos de programação leves e genéricos priorizados
  modelos_preferenciais = [
      "qwen2.5-coder:1.5b",
      "qwen2.5-coder:3b",
      "qwen2.5-coder:7b",
      "llama3.2",
      "llama3",
  ]

  # Prioriza os modelos preferenciais presentes no sistema
  modelos_para_tentar = [m for m in modelos_preferenciais if m in modelos_disponiveis]
  if not modelos_para_tentar:
    modelos_para_tentar = modelos_disponiveis if modelos_disponiveis else modelos_preferenciais

  for modelo in modelos_para_tentar:
    try:
      resp = requests.post(
          f"{host_ativo}/api/chat",
          json={"model": modelo, "messages": payload, "stream": False},
          timeout=120, # Aumentado para dar tempo do modelo carregar na memória VRAM
      )
      if resp.status_code == 200:
        res_json = resp.json()
        if "message" in res_json and "content" in res_json["message"]:
          return {"ok": True, "resposta": res_json["message"]["content"]}
    except Exception:
      continue

  return {
      "ok": False,
      "resposta": (
          "O Ollama local não respondeu a tempo ao carregar o modelo. Tente novamente em alguns segundos."
      ),
  }


def enviar_requisicao_groq(messages, system_instruction):
  """Envia para a Groq Cloud se houver API Key; caso contrário ou se falhar, alterna para o Ollama local."""
  chave = st.session_state.get("api_key")

  if chave:
    payload = [{"role": "system", "content": system_instruction}] + messages
    modelos = [
        "llama-3.3-70b-versatile",
        "llama-3.2-11b-vision-preview",
        "llama-3.1-8b-instant",
    ]

    for modelo in modelos:
      try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {chave}",
                "Content-Type": "application/json",
            },
            json={"model": modelo, "messages": payload, "temperature": 0.25},
            timeout=25,
        )
        if resp.status_code == 200:
          return {
              "ok": True,
              "resposta": resp.json()["choices"][0]["message"]["content"],
          }
      except Exception:
        continue

  # Fallback automático para o Ollama local
  return enviar_requisicao_ollama_local(messages, system_instruction)


def gerar_resposta_alemao(pergunta_usuario):
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

  if urls_diretas:
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
      prompt_final = (
          "O usuário forneceu estes links/imagens específicos para você"
          " analisar:\n\n"
          + "\n\n---\n\n".join(contexto_links)
          + f"\n\nInstrução ou Pergunta do Usuário: {pergunta_usuario}"
      )
  elif not eh_pedido_codigo:
    busca = pesquisar_web_avancado(pergunta_usuario)
    if busca["ok"]:
      prompt_final = (
          "Baseie-se nestes dados em tempo real extraídos da internet"
          f" atualizados para o ano de 2026: {busca['contexto']}\n\nPergunta:"
          f" {pergunta_usuario}"
      )

  payload = historico_api + [{"role": "user", "content": prompt_final}]
  res = enviar_requisicao_groq(payload, get_system_prompt())
  return res


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

    st.write("---")
    st.markdown("### Status do Sistema")
    st.info(f"Conversa activa: {len(st.session_state['historico'])} interações")
    st.caption("Ollama Local (`qwen2.5-coder:1.5b`) pronto como engine offline!")

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

  st.title("Grazueiro")

  obter_contexto_usuario()

  area_chat = st.container(height=500)
  with area_chat:
    for msg in st.session_state["historico"]:
      with st.chat_message(msg["role"]):
        st.write(msg["content"])

  if st.session_state["fontes_ultima_busca"]:
    with st.expander("Fontes consultadas"):
      for f in st.session_state["fontes_ultima_busca"]:
        st.markdown(f"- [{f['titulo']}]({f['link']})")

  # --- INÍCIO DA PARTE DE BAIXO CORRIGIDA ---
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
  )

  pergunta = st.chat_input("Pergunte algo ou cole um link para analisar...")
  # --- FIM DA PARTE DE BAIXO CORRIGIDA ---

  if pergunta:
    if imagem_upload:
      texto_usuario = f"[Imagem Anexada]: {pergunta}"
      st.session_state["historico"].append({"role": "user", "content": texto_usuario})
      registrar_log_invisivel("USUÁRIO", texto_usuario)

      with area_chat:
        with st.chat_message("user"):
          st.write(texto_usuario)
        with st.chat_message("assistant"):
          with st.spinner("Ollama/Llama analisando a imagem anexada..."):
            bytes_img = imagem_upload.getvalue()
            resposta_visio = analisar_imagem_local(bytes_img, prompt=pergunta)
            st.write(resposta_visio)

            st.session_state["historico"].append(
                {"role": "assistant", "content": resposta_visio}
            )
            registrar_log_invisivel("SISTEMA", resposta_visio)
    else:
      st.session_state["historico"].append({"role": "user", "content": pergunta})
      registrar_log_invisivel("USUÁRIO", pergunta)

      with area_chat:
        with st.chat_message("user"):
          st.write(pergunta)
        with st.chat_message("assistant"):
          with st.spinner("Pensando e analisando conteúdo..."):
            resp = gerar_resposta_alemao(pergunta)
            st.write(resp["resposta"])

            st.session_state["historico"].append(
                {"role": "assistant", "content": resp["resposta"]}
            )
            registrar_log_invisivel("SISTEMA", resp["resposta"])

    st.rerun()