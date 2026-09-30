import os
import sys
import threading
import math
import json
import ctypes
import shutil
import random
import time
import subprocess
import customtkinter as ctk
import pygame
from tkinter import filedialog, colorchooser
from PIL import Image, ImageDraw, ImageFilter

# --- CORREÇÃO: Oculta a janela do console nativamente para não quebrar os atalhos de teclado ---
try:
    hwnd_console = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd_console:
        ctypes.windll.user32.ShowWindow(hwnd_console, 0) # 0 = SW_HIDE (Esconde o CMD instantaneamente)
except Exception:
    pass

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

EXTENSOES_VALIDAS = ('.mp3', '.wav', '.ogg', '.opus', '.m4a')
EXTENSOES_IMAGEM = ('.jpg', '.jpeg', '.png', '.webp', '.JPG', '.JPEG', '.PNG', '.WEBP')

ctk.set_appearance_mode("Dark")

class PySpotifyApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Grazueiro - Aura 67 Pro")
        self.geometry("1100x750")
        self.minsize(1000, 650)
        self.resizable(True, True)

        # Força a renderização inicial e captura o HWND real do topo da janela através do Root Ancestor do Windows
        self.update()
        try:
            self.hwnd = ctypes.windll.user32.GetAncestor(self.winfo_id(), 2) # GA_ROOT robusto
        except Exception:
            try:
                self.hwnd = int(self.wm_frame(), 16)
            except Exception:
                self.hwnd = None

        # CORREÇÃO DE ÁUDIO: Frequência ajustada e buffer otimizado para eliminar chiados/ruídos de resampling
        pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=2048)
        pygame.mixer.init()
        self.channel = pygame.mixer.Channel(0) 

        self.music_dir = "musicas"
        self.metadata_file = os.path.join(self.music_dir, "metadata.json")
        if not os.path.exists(self.music_dir):
            os.makedirs(self.music_dir)
            
        self.metadata = self.load_metadata()

        # Ícone profissional da janela / barra de tarefas
        self._ensure_app_icon()

        # Estados de controle
        self.current_track = None
        self.is_paused = False
        self.previous_files = []
        self.track_length = 0.0
        self.current_time = 0.0
        self.track_ended_check = False
        self.repeat_mode = 0 
        self.repeat_labels = ["🔁 Off", "🔂 Música", "🔁 Todas"]
        
        # Cor de destaque padrão (Modificada dinamicamente ao tocar músicas)
        self.current_accent_color = "#1DB954"
        
        # Controle de Interatividade do Seeker
        self.is_seeking = False
        
        # Estados de processing avançado de som
        self.is_8d_enabled = False
        self.is_surround_enabled = False
        self.audio_angle = 0.0
        
        # Referência de cache para o fundo dinâmico
        self.current_pil_blur = None

        # --- MONITORAMENTO DE BLUETOOTH ---
        self.bt_connected = False
        self.bt_thread = threading.Thread(target=self._monitor_bluetooth, daemon=True)
        self.bt_thread.start()

        # --- ESTRUTURA DE LAYOUT ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 1. Barra Lateral Esquerda
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color="#000000")
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.pack_propagate(False)

        self.logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.logo_frame.pack(pady=(30, 4), padx=22, fill="x")

        self.logo = ctk.CTkLabel(self.logo_frame, text="🎧 Grazueiro", text_color="#1DB954", font=ctk.CTkFont(size=22, weight="bold"))
        self.logo.pack(anchor="w")

        self.logo_subtitle = ctk.CTkLabel(self.logo_frame, text="PREMIUM PLAYER", text_color="#5a5a5a", font=ctk.CTkFont(size=10, weight="bold"))
        self.logo_subtitle.pack(anchor="w", pady=(2, 0))

        self.sidebar_divider = ctk.CTkFrame(self.sidebar, fg_color="#1a1a1a", height=1)
        self.sidebar_divider.pack(fill="x", padx=22, pady=(22, 16))

        self.btn_view_library = ctk.CTkButton(self.sidebar, text="  🎵  Minha Biblioteca", anchor="w", height=44, corner_radius=10, fg_color="#1c1c1c", hover_color="#2b2b2b", font=ctk.CTkFont(size=13, weight="bold"), command=self.show_library_view)
        self.btn_view_library.pack(fill="x", padx=15, pady=4)
        self.apply_button_effects(self.btn_view_library)

        self.btn_view_player = ctk.CTkButton(self.sidebar, text="  📺  Tela de Reprodução", anchor="w", height=44, corner_radius=10, fg_color="transparent", hover_color="#2b2b2b", font=ctk.CTkFont(size=13, weight="bold"), command=self.show_player_view)
        self.btn_view_player.pack(fill="x", padx=15, pady=4)
        self.apply_button_effects(self.btn_view_player)

        self.sidebar_footer = ctk.CTkLabel(self.sidebar, text="Grazueiro Aura 67 • v3.0", text_color="#3d3d3d", font=ctk.CTkFont(size=10))
        self.sidebar_footer.pack(side="bottom", pady=16)

        # 2. Container Central
        self.content_container = ctk.CTkFrame(self, fg_color="#121212", corner_radius=0)
        self.content_container.grid(row=0, column=1, sticky="nsew")
        
        self.setup_library_view()
        self.setup_player_view()

        self.show_library_view()

        # Ajuste dinâmico do borrão
        self.player_frame.bind("<Configure>", self.on_player_resize)

        # --- CONFIGURAÇÃO DE ATALHOS MODIFICADA ---
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.add_hotkey('ctrl+shift', lambda: self.after(0, self.pause_resume))
                keyboard.add_hotkey('shift+right', lambda: self.after(0, self.handle_next_forced))
                keyboard.add_hotkey('shift+left', lambda: self.after(0, self.play_previous))
            except Exception:
                pass
                
        self.audio_processor_loop()
        self.auto_refresh_loop()

    def _ensure_app_icon(self):
        """Gera (uma única vez) e aplica um ícone profissional para a janela e a barra de tarefas."""
        try:
            assets_dir = os.path.join(self.music_dir, ".assets")
            os.makedirs(assets_dir, exist_ok=True)
            icon_path = os.path.join(assets_dir, "icon.ico")

            if not os.path.exists(icon_path):
                size = 256
                icon_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                draw = ImageDraw.Draw(icon_img)
                draw.ellipse((4, 4, size - 4, size - 4), fill="#1DB954")
                note_color = "#0b0b0b"
                draw.rectangle((118, 55, 130, 190), fill=note_color)
                draw.rectangle((188, 40, 200, 175), fill=note_color)
                draw.polygon([(118, 55), (200, 40), (200, 65), (118, 80)], fill=note_color)
                draw.ellipse((70, 150, 128, 205), fill=note_color)
                draw.ellipse((140, 132, 198, 187), fill=note_color)
                icon_img.save(icon_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

            self.iconbitmap(icon_path)
        except Exception:
            pass

    def apply_button_effects(self, btn):
        """Aplica animação suave de subir no hover e pressionar no clique (mantendo layout estável)."""
        # Captura os valores de pady reais no momento em que o efeito é atribuído ao botão
        try:
            info = btn.pack_info()
            py = info.get("pady", 0)
            if isinstance(py, (tuple, list)):
                top, bot = py[0], py[1]
            else:
                top = bot = int(py) if isinstance(py, str) else py
            btn._orig_pady = (max(3, int(top)), max(3, int(bot)))
        except Exception:
            btn._orig_pady = (5, 5)

        btn._anim_target_dy = 0.0
        btn._anim_curr_dy = 0.0

        def animate():
            if btn.winfo_manager() != "pack":
                return

            target = btn._anim_target_dy
            curr = btn._anim_curr_dy
            diff = target - curr

            if abs(diff) < 0.05:
                btn._anim_curr_dy = target
                curr = target
            else:
                btn._anim_curr_dy += diff * 0.35
                curr = btn._anim_curr_dy
                self.after(12, animate)

            if btn._orig_pady is not None:
                top, bot = btn._orig_pady
                total_py = top + bot
                new_top = max(0, min(total_py, int(round(top + curr))))
                new_bot = total_py - new_top
                try:
                    btn.pack_configure(pady=(new_top, new_bot))
                except Exception:
                    pass

        def set_target(target_dy):
            btn._anim_target_dy = float(target_dy)
            animate()

        def on_enter(e):
            set_target(-3)

        def on_leave(e):
            try:
                focused = btn.winfo_containing(*btn.winfo_pointerxy())
                if focused and (focused == btn or focused in btn.winfo_children()):
                    return
            except Exception:
                pass
            set_target(0)

        def on_press(e):
            set_target(2)

        def on_release(e):
            on_enter(e)

        def bind_events(w):
            w.bind("<Enter>", on_enter, add="+")
            w.bind("<Leave>", on_leave, add="+")
            w.bind("<Button-1>", on_press, add="+")
            w.bind("<ButtonRelease-1>", on_release, add="+")
            for child in w.winfo_children():
                bind_events(child)

        bind_events(btn)

    def _check_bluetooth_connected(self):
        """Verifica conexão de áudio Bluetooth e retorna (conectado, nome_dispositivo, nivel_bateria)."""
        try:
            if sys.platform == "win32":
                flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                ps_script = (
                    "$eps = @(Get-PnpDevice -Class AudioEndpoint -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.Status -eq 'OK' }); "
                    "$bts = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { ($_.InstanceId -like '*BTHENUM*' -or $_.InstanceId -like '*BTHLE*') -and $_.FriendlyName -notmatch 'Adapter|Enumerator|Controller|Radio|Generic' }); "
                    "$found = $false; "
                    "foreach ($ep in $eps) { "
                    "  foreach ($bt in $bts) { "
                    "    if (($ep.ContainerId -and $bt.ContainerId -and ($ep.ContainerId -eq $bt.ContainerId)) -or ($ep.FriendlyName -and $bt.FriendlyName -and $ep.FriendlyName -like \"*$($bt.FriendlyName)*\")) { "
                    "      $name = $ep.FriendlyName; "
                    "      $batt = ''; "
                    "      try { $b = (Get-ItemProperty -Path \"HKLM:\\SYSTEM\\CurrentSet\\Enum\\$($bt.InstanceId)\\Device Parameters\" -ErrorAction SilentlyContinue).BatteryLevel; if ($b) { $batt = \"$b%\" } } catch {}; "
                    "      if ($batt) { Write-Output \"CONNECTED|$name|$batt\" } else { Write-Output \"CONNECTED|$name\" }; "
                    "      $found = $true; "
                    "      break; "
                    "    } "
                    "  } "
                    "  if ($found) { break } "
                    "}"
                )
                output = subprocess.check_output(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                    text=True,
                    creationflags=flags
                ).strip()
                if "CONNECTED" in output:
                    parts = output.split("|")
                    name = parts[1] if len(parts) > 1 else "Dispositivo Bluetooth"
                    batt = parts[2] if len(parts) > 2 else ""
                    return True, name, batt
                return False, "", ""
            elif sys.platform == "darwin":
                output = subprocess.check_output(["system_profiler", "SPBluetoothDataType"], text=True)
                if "Connected: Yes" in output:
                    return True, "Dispositivo Bluetooth", ""
                return False, "", ""
            else:
                output = subprocess.check_output(["bluetoothctl", "devices", "Connected"], text=True)
                if len(output.strip()) > 0:
                    return True, "Dispositivo Bluetooth", ""
                return False, "", ""
        except Exception:
            return False, "", ""

    def _monitor_bluetooth(self):
        """Monitora o estado da conexão Bluetooth em segundo plano."""
        while True:
            time.sleep(2)
            currently_connected, dev_name, dev_batt = self._check_bluetooth_connected()
            
            # Se estava conectado e desconectou/acabou a bateria durante a reprodução
            if self.bt_connected and not currently_connected:
                if self.channel.get_busy() and not self.is_paused:
                    self.after(0, self.pause_resume)

            self.bt_connected = currently_connected
            
            # Atualiza o indicador de status na interface
            if currently_connected:
                batt_info = f" ({dev_batt})" if dev_batt else ""
                status_text = f"🎧 Bluetooth: {dev_name}{batt_info}"
                status_color = self.current_accent_color
            else:
                status_text = "🎧 Bluetooth: Desconectado"
                status_color = "#ff5555"

            if hasattr(self, 'lbl_bt_status'):
                self.after(0, lambda t=status_text, c=status_color: self.lbl_bt_status.configure(text=t, text_color=c))

    def load_metadata(self):
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_metadata(self):
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Erro ao salvar metadados: {e}")

    def show_library_view(self):
        self.player_frame.pack_forget()
        self.library_frame.pack(fill="both", expand=True)
        self.btn_view_library.configure(fg_color="#1c1c1c")
        self.btn_view_player.configure(fg_color="transparent")

    def show_player_view(self):
        self.library_frame.pack_forget()
        self.player_frame.pack(fill="both", expand=True)
        self.btn_view_player.configure(fg_color="#1c1c1c")
        self.btn_view_library.configure(fg_color="transparent")
        self.update_blur_background_ui()

    def setup_library_view(self):
        self.library_frame = ctk.CTkFrame(self.content_container, fg_color="transparent")
        
        # --- INDICADOR BLUETOOTH (Posicionado em cima da barra de pesquisa) ---
        self.lbl_bt_status = ctk.CTkLabel(
            self.library_frame, 
            text="🎧 Bluetooth: Verificando...", 
            font=ctk.CTkFont(size=12, weight="bold"), 
            text_color="#b3b3b3"
        )
        self.lbl_bt_status.pack(anchor="w", padx=30, pady=(20, 0))

        search_card = ctk.CTkFrame(self.library_frame, fg_color="#1a1a1a", corner_radius=25, height=54)
        search_card.pack(fill="x", padx=30, pady=(14, 28))
        search_card.pack_propagate(False)

        self.entry_search = ctk.CTkEntry(search_card, placeholder_text="🔎  Buscar música ou colar link do YouTube...", height=54, corner_radius=25, border_width=0, fg_color="transparent", font=ctk.CTkFont(size=13))
        self.entry_search.pack(side="left", fill="both", expand=True, padx=(18, 8), pady=4)

        self.btn_download = ctk.CTkButton(search_card, text="＋ Baixar", width=110, height=44, corner_radius=22, fg_color="#1DB954", hover_color="#14833B", text_color="black", font=ctk.CTkFont(size=13, weight="bold"), command=self.start_download_thread)
        self.btn_download.pack(side="right", padx=(0, 5), pady=4)
        self.apply_button_effects(self.btn_download)

        header_row = ctk.CTkFrame(self.library_frame, fg_color="transparent")
        header_row.pack(fill="x", padx=30, pady=(0, 8))

        lbl_title = ctk.CTkLabel(header_row, text="Minha Playlist", font=ctk.CTkFont(size=26, weight="bold"))
        lbl_title.pack(side="left", anchor="w")

        self.lbl_track_count = ctk.CTkLabel(header_row, text="0 músicas", font=ctk.CTkFont(size=12), text_color="#8a8a8a")
        self.lbl_track_count.pack(side="left", anchor="s", padx=(12, 0), pady=(0, 4))

        self.scroll_tracks = ctk.CTkScrollableFrame(self.library_frame, fg_color="transparent")
        self.scroll_tracks.pack(fill="both", expand=True, padx=20, pady=10)

    def setup_player_view(self):
        self.player_frame = ctk.CTkFrame(self.content_container, fg_color="#121212", corner_radius=0)
        
        # Camada de fundo (Borrão Estilo Spotify/Vignette)
        self.bg_blur_label = ctk.CTkLabel(self.player_frame, text="")
        self.bg_blur_label.place(x=0, y=0, relwidth=1, relheight=1)

        # HUD Principal
        self.center_hud = ctk.CTkFrame(self.player_frame, fg_color="transparent")
        self.center_hud.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Ferramentas Superiores
        self.custom_tools_frame = ctk.CTkFrame(self.center_hud, fg_color="transparent")
        self.custom_tools_frame.pack(anchor="n", fill="x", padx=30, pady=15)

        self.btn_custom_cover = ctk.CTkButton(self.custom_tools_frame, text="🖼️ Mudar Capa", width=110, height=32, fg_color="#1f1f1f", hover_color="#2a2a2a", font=ctk.CTkFont(size=12), command=self.select_custom_cover)
        self.btn_custom_cover.pack(side="right", padx=5)
        self.apply_button_effects(self.btn_custom_cover)

        self.btn_custom_color = ctk.CTkButton(self.custom_tools_frame, text="🎨 Mudar Cor", width=110, height=32, fg_color="#1f1f1f", hover_color="#2a2a2a", font=ctk.CTkFont(size=12), command=self.select_custom_color)
        self.btn_custom_color.pack(side="right", padx=5)
        self.apply_button_effects(self.btn_custom_color)

        # Capa com cantos arredondados
        self.cover_label = ctk.CTkLabel(self.center_hud, text="", width=300, height=300)
        self.cover_label.pack(pady=(10, 15))
        self.generate_default_cover()

        # Títulos
        self.label_eyebrow = ctk.CTkLabel(self.center_hud, text="", font=ctk.CTkFont(size=11, weight="bold"), text_color="#9a9a9a")
        self.label_eyebrow.pack(pady=(0, 2))

        self.label_title = ctk.CTkLabel(self.center_hud, text="Nenhuma música tocando", font=ctk.CTkFont(size=26, weight="bold"), text_color="white")
        self.label_title.pack(pady=(0, 2))
        
        self.label_artist = ctk.CTkLabel(self.center_hud, text="Grazueiro Premium", font=ctk.CTkFont(size=15), text_color="#d3d3d3")
        self.label_artist.pack(pady=(0, 15))

        # --- MONITOR DE ÁUDIO ESTÉREO (VU METER) ---
        self.vu_frame = ctk.CTkFrame(self.center_hud, fg_color="transparent")
        self.vu_frame.pack(pady=(0, 15))

        self.lbl_vu_left = ctk.CTkLabel(self.vu_frame, text="Esquerda", font=ctk.CTkFont(size=12, weight="bold"), text_color="#b3b3b3")
        self.lbl_vu_left.pack(side="left", padx=(0, 5))

        self.bar_vu_left = ctk.CTkProgressBar(self.vu_frame, width=120, height=10, progress_color="#1DB954", fg_color="#282828")
        self.bar_vu_left.set(0.0)
        self.bar_vu_left.pack(side="left", padx=(0, 15))

        self.bar_vu_right = ctk.CTkProgressBar(self.vu_frame, width=120, height=10, progress_color="#1DB954", fg_color="#282828")
        self.bar_vu_right.set(0.0)
        self.bar_vu_right.pack(side="left", padx=(15, 0))

        self.lbl_vu_right = ctk.CTkLabel(self.vu_frame, text="Direita", font=ctk.CTkFont(size=12, weight="bold"), text_color="#b3b3b3")
        self.lbl_vu_right.pack(side="left", padx=(5, 0))

        # Barra de Progresso ATIVADA e INTERATIVA
        self.timeline_frame = ctk.CTkFrame(self.center_hud, fg_color="transparent")
        self.timeline_frame.pack(fill="x", padx=120, pady=5)

        self.label_time_current = ctk.CTkLabel(self.timeline_frame, text="00:00", font=ctk.CTkFont(size=12), text_color="#e0e0e0")
        self.label_time_current.pack(side="left")

        self.timeline_slider = ctk.CTkSlider(self.timeline_frame, from_=0, to=100, height=14, button_color="#1DB954", button_hover_color="#1ed760")
        self.timeline_slider.set(0)
        self.timeline_slider.pack(side="left", fill="x", expand=True, padx=15)
        
        self.timeline_slider.bind("<ButtonPress-1>", lambda e: self.set_seeking_flag(True))
        self.timeline_slider.bind("<ButtonRelease-1>", self.on_slider_release)

        self.label_time_max = ctk.CTkLabel(self.timeline_frame, text="00:00", font=ctk.CTkFont(size=12), text_color="#e0e0e0")
        self.label_time_max.pack(side="right")

        # Controles Multimídia Inferiores
        self.controls_wrapper = ctk.CTkFrame(self.center_hud, fg_color="transparent")
        self.controls_wrapper.pack(pady=15, fill="x", padx=120)

        self.btn_repeat = ctk.CTkButton(self.controls_wrapper, text="🔁 Off", width=75, height=35, corner_radius=17, font=ctk.CTkFont(size=12), fg_color="#1c1c1c", hover_color="#2b2b2b", command=self.toggle_repeat)
        self.btn_repeat.pack(side="left", padx=6)
        self.apply_button_effects(self.btn_repeat)

        # Botões de Processamento de Áudio Avançado
        self.btn_8d = ctk.CTkButton(self.controls_wrapper, text="🎧 8D: Off", width=85, height=35, corner_radius=17, font=ctk.CTkFont(size=12), fg_color="#1c1c1c", hover_color="#2b2b2b", command=self.toggle_8d)
        self.btn_8d.pack(side="left", padx=6)
        self.apply_button_effects(self.btn_8d)

        self.btn_surround = ctk.CTkButton(self.controls_wrapper, text="📻 Surround: Off", width=95, height=35, corner_radius=17, font=ctk.CTkFont(size=12), fg_color="#1c1c1c", hover_color="#2b2b2b", command=self.toggle_surround)
        self.btn_surround.pack(side="left", padx=6)
        self.apply_button_effects(self.btn_surround)

        self.controls_divider = ctk.CTkFrame(self.controls_wrapper, width=1, fg_color="#2b2b2b")
        self.controls_divider.pack(side="left", fill="y", padx=12, pady=4)

        self.btn_prev = ctk.CTkButton(self.controls_wrapper, text="⏮", width=45, height=45, corner_radius=22, font=ctk.CTkFont(size=20), fg_color="transparent", hover_color="#2b2b2b", text_color="white", command=self.play_previous)
        self.btn_prev.pack(side="left", padx=8)
        self.apply_button_effects(self.btn_prev)

        self.btn_play = ctk.CTkButton(self.controls_wrapper, text="▶", width=62, height=62, corner_radius=31, text_color="black", fg_color="white", hover_color="#e0e0e0", font=ctk.CTkFont(size=20, weight="bold"), command=self.pause_resume)
        self.btn_play.pack(side="left", padx=8)
        self.apply_button_effects(self.btn_play)

        self.btn_next = ctk.CTkButton(self.controls_wrapper, text="⏭", width=45, height=45, corner_radius=22, font=ctk.CTkFont(size=20), fg_color="transparent", hover_color="#2b2b2b", text_color="white", command=self.handle_next_forced)
        self.btn_next.pack(side="left", padx=8)
        self.apply_button_effects(self.btn_next)

        self.volume_slider = ctk.CTkSlider(self.controls_wrapper, from_=0, to=1, width=110, height=14, button_color="#1DB954", command=self.update_volume_direct)
        self.volume_slider.set(0.6)
        self.volume_slider.pack(side="right", padx=10)
        
        self.label_vol_icon = ctk.CTkLabel(self.controls_wrapper, text="🔊", font=ctk.CTkFont(size=14))
        self.label_vol_icon.pack(side="right")

        self.fx_sliders_wrapper = ctk.CTkFrame(self.center_hud, fg_color="transparent")
        self.fx_sliders_wrapper.pack(pady=5)
        
        self.label_8d_speed = ctk.CTkLabel(self.fx_sliders_wrapper, text="⚡ Velocidade 8D: 1.0x", font=ctk.CTkFont(size=12), text_color="white")
        self.label_8d_speed.pack(side="left", padx=(0, 10))
        
        self.slider_8d_speed = ctk.CTkSlider(self.fx_sliders_wrapper, from_=0.1, to=3.0, width=150, height=14, button_color="#1DB954", command=self.update_8d_speed_label)
        self.slider_8d_speed.set(1.0)
        self.slider_8d_speed.pack(side="left")

    def update_library_view(self):
        for widget in self.scroll_tracks.winfo_children():
            widget.destroy()

        if os.path.exists(self.music_dir):
            musicas = sorted([f for f in os.listdir(self.music_dir) if f.lower().endswith(EXTENSOES_VALIDAS)])
        else:
            musicas = []
        
        self.previous_files = musicas

        if hasattr(self, 'lbl_track_count'):
            total = len(musicas)
            self.lbl_track_count.configure(text=f"{total} música" + ("s" if total != 1 else ""))

        if not musicas:
            lbl = ctk.CTkLabel(self.scroll_tracks, text="🎵  Sua biblioteca está vazia.\nBusque uma música acima para começar.", text_color="#6b6b6b", font=ctk.CTkFont(size=13), justify="center")
            lbl.pack(pady=60)
            return

        for idx, musica in enumerate(musicas, start=1):
            nome_limpo = os.path.splitext(musica)[0]
            
            cover_path = None
            if musica in self.metadata and "custom_cover" in self.metadata[musica]:
                if os.path.exists(self.metadata[musica]["custom_cover"]):
                    cover_path = self.metadata[musica]["custom_cover"]
            if not cover_path:
                for ext in EXTENSOES_IMAGEM:
                    test_path = os.path.join(self.music_dir, nome_limpo + ext)
                    if os.path.exists(test_path):
                        cover_path = test_path
                        break
            
            try:
                if cover_path:
                    pil_thumb = Image.open(cover_path).convert("RGBA").resize((38, 38), Image.Resampling.LANCZOS)
                else:
                    pil_thumb = Image.new("RGBA", (38, 38), "#282828")
                pil_thumb = self.apply_rounded_corners(pil_thumb, 6)
                ctk_thumb = ctk.CTkImage(light_image=pil_thumb, dark_image=pil_thumb, size=(38, 38))
            except Exception:
                pil_thumb = Image.new("RGBA", (38, 38), "#282828")
                pil_thumb = self.apply_rounded_corners(pil_thumb, 6)
                ctk_thumb = ctk.CTkImage(light_image=pil_thumb, dark_image=pil_thumb, size=(38, 38))

            is_playing = (musica == self.current_track)
            if is_playing:
                row_fg = self.current_accent_color
                row_hover = self.get_darker_color(self.current_accent_color)
                row_text_color = "black"
                prefix = "▶  "
            else:
                row_fg = "#1a1a1a"
                row_hover = "#262626"
                row_text_color = "white"
                prefix = f"{idx:02d}   "

            btn = ctk.CTkButton(
                self.scroll_tracks, 
                text=f"{prefix}{nome_limpo[:70]}",
                image=ctk_thumb,
                compound="left",
                anchor="w", 
                fg_color=row_fg, 
                hover_color=row_hover,
                text_color=row_text_color,
                height=54,
                corner_radius=10,
                font=ctk.CTkFont(size=13, weight="bold" if is_playing else "normal"),
                command=lambda m=musica: self.select_and_play(m)
            )
            btn._img_ref = ctk_thumb
            btn.pack(fill="x", pady=5, padx=10)
            self.apply_button_effects(btn)

    def auto_refresh_loop(self):
        if os.path.exists(self.music_dir):
            current_files = sorted([f for f in os.listdir(self.music_dir) if f.lower().endswith(EXTENSOES_VALIDAS)])
        else:
            current_files = []

        if current_files != self.previous_files:
            self.update_library_view()

        self.after(2000, self.auto_refresh_loop)

    def select_and_play(self, filename):
        self.play_music(filename)
        self.show_player_view()

    def apply_rounded_corners(self, image, radius):
        mask = Image.new("L", image.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0, image.size[0], image.size[1]), radius=radius, fill=255)
        rounded_image = Image.new("RGBA", image.size, (0, 0, 0, 0))
        rounded_image.paste(image, (0, 0), mask=mask)
        return rounded_image

    def extract_dominant_color(self, pil_img):
        try:
            img_rgba = pil_img.convert("RGBA")
            img = img_rgba.copy().resize((1, 1), resample=Image.Resampling.BILINEAR)
            color = img.getpixel((0, 0))
            
            if isinstance(color, (tuple, list)):
                r_raw, g_raw, b_raw = color[0], color[1], color[2]
            else:
                r_raw = g_raw = b_raw = color
        except Exception:
            r_raw = g_raw = b_raw = 40 

        r = max(18, min(255, int(r_raw * 0.45)))
        g = max(18, min(255, int(g_raw * 0.45)))
        b = max(18, min(255, int(b_raw * 0.45)))
        return f"#{r:02d}{g:02d}{b:02d}"

    def update_windows_system_theme(self, hex_color):
        try:
            self.configure(fg_color=hex_color)
            self.content_container.configure(fg_color=hex_color)
            self.sidebar.configure(fg_color=hex_color)
            self.library_frame.configure(fg_color=hex_color)
            
            if self.hwnd:
                dwmapi = ctypes.WinDLL("dwmapi")
                dwmapi.DwmSetWindowAttribute(self.hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
                
                r = int(hex_color[1:3], 16)
                g = int(hex_color[3:5], 16)
                b = int(hex_color[5:7], 16)
                win_color = (b << 16) | (g << 8) | r
                
                try:
                    dwmapi.DwmSetWindowAttribute(self.hwnd, 35, ctypes.byref(ctypes.c_int(win_color)), 4)
                    dwmapi.DwmSetWindowAttribute(self.hwnd, 34, ctypes.byref(ctypes.c_int(win_color)), 4)
                except Exception:
                    pass

            # --- CÓDIGO ATUALIZADO: ALTERAÇÃO DA BARRA DE TAREFAS E BARRAS DO WINDOWS 11 ---
            try:
                import winreg
                clean_hex = hex_color.lstrip('#')
                r_t = int(clean_hex[0:2], 16)
                g_t = int(clean_hex[2:4], 16)
                b_t = int(clean_hex[4:6], 16)
                # Formato DWORD nativo do Windows: 0xFFBBGGRR
                cor_dw = (0xFF << 24) | (b_t << 16) | (g_t << 8) | r_t

                # 1. Atualiza no Gerenciador de Janelas do Windows (DWM) - Cor e Prevalência de bordas
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key, "AccentColor", 0, winreg.REG_DWORD, cor_dw)
                winreg.SetValueEx(key, "ColorPrevalence", 0, winreg.REG_DWORD, 1)
                winreg.CloseKey(key)

                # 2. Atualiza nas propriedades de Acentuação do Explorer (Menu Iniciar / Taskbar)
                key2 = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key2, "AccentColorMenu", 0, winreg.REG_DWORD, cor_dw)
                winreg.CloseKey(key2)

                # 3. Força a ativação da opção de vinculação de cor nativa na Barra de Tarefas (Themes/Personalize)
                key3 = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", 0, winreg.KEY_SET_VALUE)
                winreg.SetValueEx(key3, "ColorPrevalence", 0, winreg.REG_DWORD, 1)
                winreg.CloseKey(key3)

                # 4. Notifica o subsistema shell síncronamente sobre a mudança no conjunto imersivo
                ctypes.windll.user32.PostMessageW(0xFFFF, 0x001A, 0, 0)
                ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 2, 100, None)
            except Exception as e:
                print(f"Erro ao injetar cor na barra de tarefas do Windows: {e}")

        except Exception as e:
            print(f"Erro ao injetar tema no Windows DWM: {e}")

    def get_accent_color(self, bg_hex):
        try:
            hex_str = bg_hex.lstrip('#')
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            
            max_c = max(r, g, b, 1)
            if max_c < 30:
                return "#1DB954"
                
            factor = 200 / max_c
            factor = max(1.5, min(3.5, factor))
            
            ra = max(30, min(255, int(r * factor)))
            ga = max(30, min(255, int(g * factor)))
            ba = max(30, min(255, int(b * factor)))
            return f"#{ra:02d}{ga:02d}{ba:02d}"
        except Exception:
            return "#1DB954"

    def get_darker_color(self, hex_color):
        try:
            hex_str = hex_color.lstrip('#')
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            return f"#{int(r * 0.75):02d}{int(g * 0.75):02d}{int(b * 0.75):02d}"
        except Exception:
            return "#2b2b2b"

    def update_widget_accents(self, accent_color):
        hover_accent = self.get_darker_color(accent_color)
        
        self.logo.configure(text_color=accent_color)
        self.entry_search.configure(border_color=accent_color)
        self.btn_download.configure(fg_color=accent_color, hover_color=hover_accent)
        self.bar_vu_left.configure(progress_color=accent_color)
        self.bar_vu_right.configure(progress_color=accent_color)
        self.timeline_slider.configure(button_color=accent_color, button_hover_color=accent_color)
        self.volume_slider.configure(button_color=accent_color)
        self.slider_8d_speed.configure(button_color=accent_color)
        
        # Atualiza a cor do indicador Bluetooth dinamicamente de acordo com a música
        if hasattr(self, 'lbl_bt_status') and self.bt_connected:
            self.lbl_bt_status.configure(text_color=accent_color)

        if self.is_8d_enabled:
            self.btn_8d.configure(fg_color=accent_color, hover_color=hover_accent)
        else:
            self.btn_8d.configure(fg_color="#1c1c1c", hover_color="#2b2b2b")
            
        if self.is_surround_enabled:
            self.btn_surround.configure(fg_color=accent_color, hover_color=hover_accent)
        else:
            self.btn_surround.configure(fg_color="#1c1c1c", hover_color="#2b2b2b")

    def generate_default_cover(self):
        img = Image.new("RGBA", (300, 300), "#282828")
        img = self.apply_rounded_corners(img, 15)
        self.ctk_cover = ctk.CTkImage(light_image=img, dark_image=img, size=(300, 300))
        self.cover_label.configure(image=self.ctk_cover)

    def on_player_resize(self, event):
        if self.current_pil_blur:
            self.update_blur_background_ui()

    def update_blur_background_ui(self):
        if not self.current_pil_blur:
            return
        
        w = max(10, self.player_frame.winfo_width())
        h = max(10, self.player_frame.winfo_height())
        
        try:
            resized_bg = self.current_pil_blur.resize((w, h), Image.Resampling.LANCZOS)
            ctk_blur = ctk.CTkImage(light_image=resized_bg, dark_image=resized_bg, size=(w, h))
            self.bg_blur_label.configure(image=ctk_blur)
        except Exception as e:
            print(f"Erro no redimensionamento do borrão: {e}")

    def load_cover_art_and_background(self, track_filename):
        base_name = os.path.splitext(track_filename)[0]
        cover_path = None
        
        if track_filename in self.metadata and "custom_cover" in self.metadata[track_filename]:
            stored_path = self.metadata[track_filename]["custom_cover"]
            if os.path.exists(stored_path):
                cover_path = stored_path

        if not cover_path:
            for ext in EXTENSOES_IMAGEM:
                test_path = os.path.join(self.music_dir, base_name + ext)
                if os.path.exists(test_path):
                    cover_path = test_path
                    break
                    
        if cover_path:
            try:
                pil_img = Image.open(cover_path).convert("RGBA")
                
                bg_blur_img = pil_img.copy().resize((800, 800), Image.Resampling.LANCZOS)
                bg_blur_img = bg_blur_img.filter(ImageFilter.GaussianBlur(radius=55)).convert("RGBA")
                
                dark_overlay = Image.new("RGBA", bg_blur_img.size, (0, 0, 0, 135))
                bg_blur_img = Image.alpha_composite(bg_blur_img, dark_overlay)
                
                self.current_pil_blur = bg_blur_img
                cover_center = pil_img.resize((300, 300), Image.Resampling.LANCZOS)
                
                if track_filename in self.metadata and "custom_color" in self.metadata[track_filename]:
                    dom_color = self.metadata[track_filename]["custom_color"]
                else:
                    dom_color = self.extract_dominant_color(cover_center)
                
                cover_center = self.apply_rounded_corners(cover_center, 15)
                self.ctk_cover = ctk.CTkImage(light_image=cover_center, dark_image=cover_center, size=(300, 300))
                self.cover_label.configure(image=self.ctk_cover)
                
                self.player_frame.configure(fg_color=dom_color)
                self.update_blur_background_ui()
                self.update_windows_system_theme(dom_color)
                
                accent_color = self.get_accent_color(dom_color)
                self.current_accent_color = accent_color
                self.update_widget_accents(accent_color)
                return
            except Exception as e:
                print(f"Erro ao processar imagem: {e}")

        if track_filename in self.metadata and "custom_color" in self.metadata[track_filename]:
            fallback_color = self.metadata[track_filename]["custom_color"]
        else:
            fallback_color = "#121212"

        self.current_pil_blur = None
        self.bg_blur_label.configure(image="")
        self.generate_default_cover()
        self.player_frame.configure(fg_color=fallback_color)
        self.update_windows_system_theme(fallback_color)
        
        accent_color = self.get_accent_color(fallback_color) if fallback_color != "#121212" else "#1DB954"
        self.current_accent_color = accent_color
        self.update_widget_accents(accent_color)

    def select_custom_cover(self):
        if not self.current_track: return
        file_path = filedialog.askopenfilename(filetypes=[("Imagens", "*.jpg *.jpeg *.png *.webp *.JPG *.JPEG *.PNG *.WEBP")])
        if file_path:
            base_name = os.path.splitext(self.current_track)[0]
            ext = os.path.splitext(file_path)[1]
            dest_path = os.path.join(self.music_dir, base_name + ext)
            
            try:
                shutil.copy(file_path, dest_path)
                if self.current_track not in self.metadata:
                    self.metadata[self.current_track] = {}
                self.metadata[self.current_track]["custom_cover"] = dest_path
                self.save_metadata()
                self.load_cover_art_and_background(self.current_track)
                self.update_library_view()
            except Exception as e:
                print(f"Erro ao salvar capa customizada: {e}")

    def select_custom_color(self):
        if not self.current_track: return
        color_data = colorchooser.askcolor(title="Escolha a cor dessa música")
        if color_data and color_data[1]:
            chosen_hex = color_data[1]
            if self.current_track not in self.metadata:
                self.metadata[self.current_track] = {}
            self.metadata[self.current_track]["custom_color"] = chosen_hex
            self.save_metadata()
            self.load_cover_art_and_background(self.current_track)

    def toggle_8d(self):
        self.is_8d_enabled = not self.is_8d_enabled
        if self.is_8d_enabled:
            hover_accent = self.get_darker_color(self.current_accent_color)
            self.btn_8d.configure(text="🎧 8D: Ativo", fg_color=self.current_accent_color, hover_color=hover_accent, text_color="black")
        else:
            self.btn_8d.configure(text="🎧 8D: Off", fg_color="#1c1c1c", hover_color="#2b2b2b", text_color="white")
        self.update_volume_direct(self.volume_slider.get())

    def toggle_surround(self):
        self.is_surround_enabled = not self.is_surround_enabled
        if self.is_surround_enabled:
            hover_accent = self.get_darker_color(self.current_accent_color)
            self.btn_surround.configure(text="📻 Surround: Ativo", fg_color=self.current_accent_color, hover_color=hover_accent, text_color="black")
        else:
            self.btn_surround.configure(text="📻 Surround: Off", fg_color="#1c1c1c", hover_color="#2b2b2b", text_color="white")
        self.update_volume_direct(self.volume_slider.get())

    def play_music(self, filename):
        filepath = os.path.join(self.music_dir, filename)
        if self.channel.get_busy():
            self.channel.stop()

        try:
            self.base_sound = pygame.mixer.Sound(filepath)
            self.audio_raw_bytes = self.base_sound.get_raw()
            self.track_length = self.base_sound.get_length()
            self.bytes_per_second = len(self.audio_raw_bytes) / self.track_length
            
            self.current_time = 0.0
            self.timeline_slider.configure(to=self.track_length)
            self.label_time_max.configure(text=self.format_time(self.track_length))
            self.label_time_current.configure(text="00:00")
            
            self.channel.play(self.base_sound)
            self.current_track = filename
            self.is_paused = False
            self.track_ended_check = True
            
            nome_limpo = os.path.splitext(filename)[0]
            self.label_title.configure(text=nome_limpo[:45])
            self.btn_play.configure(text="⏸")
            if hasattr(self, 'label_eyebrow'):
                self.label_eyebrow.configure(text="TOCANDO AGORA")
            
            self.load_cover_art_and_background(filename)
            self.update_volume_direct(self.volume_slider.get())

            if hasattr(self, 'scroll_tracks'):
                self.update_library_view()
        except Exception as e:
            print(f"Erro ao iniciar áudio: {e}")

    def pause_resume(self):
        if not self.current_track:
            musicas = sorted([f for f in os.listdir(self.music_dir) if f.lower().endswith(EXTENSOES_VALIDAS)])
            if musicas: self.select_and_play(musicas[0])
            return
            
        if self.is_paused:
            self.channel.unpause()
            self.is_paused = False
            self.btn_play.configure(text="⏸")
        else:
            self.channel.pause()
            self.is_paused = True
            self.btn_play.configure(text="▶")

    def update_volume_direct(self, val):
        if not (self.is_8d_enabled or self.is_surround_enabled):
            self.channel.set_volume(float(val), float(val))

    def toggle_repeat(self):
        self.repeat_mode = (self.repeat_mode + 1) % 3
        self.btn_repeat.configure(text=self.repeat_labels[self.repeat_mode])

    def format_time(self, seconds):
        if math.isnan(seconds) or seconds < 0: return "00:00"
        return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"

    def set_seeking_flag(self, state):
        self.is_seeking = state

    def on_slider_release(self, event):
        target_time = self.timeline_slider.get()
        self.seek_to(target_time)
        self.is_seeking = False

    def seek_to(self, target_time):
        if not self.current_track or not hasattr(self, 'audio_raw_bytes'): 
            return
            
        self.channel.stop()
        target_time = max(0.0, min(target_time, self.track_length - 0.1))
        
        start_byte = int(target_time * self.bytes_per_second)
        start_byte = (start_byte // 4) * 4
        
        try:
            sliced_bytes = self.audio_raw_bytes[start_byte:]
            seeked_sound = pygame.mixer.Sound(buffer=sliced_bytes)
            
            self.channel.play(seeked_sound)
            self.current_time = target_time
            self.track_ended_check = True
            
            if self.is_paused:
                self.channel.pause()
        except Exception as e:
            print(f"Erro ao redefinir ponteiro de áudio: {e}")

    def update_8d_speed_label(self, val):
        self.label_8d_speed.configure(text=f"⚡ Velocidade 8D: {float(val):.1f}x")

    def audio_processor_loop(self):
        if self.channel.get_busy() and not self.is_paused:
            self.current_time += 0.040
            
            if not self.is_seeking:
                self.timeline_slider.set(self.current_time)
                self.label_time_current.configure(text=self.format_time(self.current_time))

            master_vol = float(self.volume_slider.get())
            
            left_pan = 1.0
            right_pan = 1.0
            profundidade = 1.0

            if self.is_8d_enabled:
                velocidade_base = 0.033
                multiplicador = float(self.slider_8d_speed.get())
                self.audio_angle += velocidade_base * multiplicador
                
                sin_val = math.sin(self.audio_angle)
                cos_val = math.cos(self.audio_angle)
                
                angle_pan = (sin_val + 1) / 2
                left_pan = math.cos(angle_pan * (math.pi / 2))
                right_pan = math.sin(angle_pan * (math.pi / 2))
                
                profundidade = 0.70 + 0.30 * ((cos_val + 1) / 2)

            surround_l = 1.0
            surround_r = 1.0
            if self.is_surround_enabled:
                surround_l = 0.94 + 0.06 * math.sin(self.current_time * 7.5)
                surround_r = 0.94 + 0.06 * math.cos(self.current_time * 7.5)

            vol_l = max(0.0, min(1.0, left_pan * master_vol * profundidade * surround_l))
            vol_r = max(0.0, min(1.0, right_pan * master_vol * profundidade * surround_r))
            
            self.channel.set_volume(vol_l, vol_r)

            v_l = vol_l * random.uniform(0.7, 1.0) if vol_l > 0.01 else 0.0
            v_r = vol_r * random.uniform(0.7, 1.0) if vol_r > 0.01 else 0.0
            self.bar_vu_left.set(v_l)
            self.bar_vu_right.set(v_r)
        else:
            if hasattr(self, 'bar_vu_left'):
                self.bar_vu_left.set(0.0)
            if hasattr(self, 'bar_vu_right'):
                self.bar_vu_right.set(0.0)

        if self.track_ended_check and not self.channel.get_busy() and not self.is_paused:
            self.track_ended_check = False
            self.handle_playlist_logic()

        self.after(40, self.audio_processor_loop)

    def handle_playlist_logic(self):
        if not os.path.exists(self.music_dir): return
        musicas = sorted([f for f in os.listdir(self.music_dir) if f.lower().endswith(EXTENSOES_VALIDAS)])
        if not musicas or not self.current_track: return

        if self.repeat_mode == 1:
            self.play_music(self.current_track)
        else:
            try:
                idx_atual = musicas.index(self.current_track)
                if idx_atual + 1 < len(musicas):
                    self.play_music(musicas[idx_atual + 1])
                elif self.repeat_mode == 2:
                    self.play_music(musicas[0])
                else:
                    self.current_track = None
                    self.label_title.configure(text="Fim da playlist")
                    if hasattr(self, 'label_eyebrow'):
                        self.label_eyebrow.configure(text="")
                    self.btn_play.configure(text="▶")
                    self.timeline_slider.set(0)
                    self.label_time_current.configure(text="00:00")
                    if hasattr(self, 'scroll_tracks'):
                        self.update_library_view()
            except ValueError:
                pass

    def handle_next_forced(self):
        self.track_ended_check = False
        if not os.path.exists(self.music_dir): return
        musicas = sorted([f for f in os.listdir(self.music_dir) if f.lower().endswith(EXTENSOES_VALIDAS)])
        if not musicas or not self.current_track: return
        try:
            idx = musicas.index(self.current_track)
            self.play_music(musicas[(idx + 1) % len(musicas)])
        except ValueError:
            self.play_music(musicas[0])

    def play_previous(self):
        self.track_ended_check = False
        if not os.path.exists(self.music_dir): return
        musicas = sorted([f for f in os.listdir(self.music_dir) if f.lower().endswith(EXTENSOES_VALIDAS)])
        if not musicas or not self.current_track: return
        try:
            idx = musicas.index(self.current_track)
            self.play_music(musicas[(idx - 1) % len(musicas)])
        except ValueError:
            self.play_music(musicas[0])

    def download_audio(self, query):
        if not query: return
        
        from yt_dlp import YoutubeDL
        
        query_clean = query.strip()
        if "youtube.com" in query_clean.lower() or "youtu.be" in query_clean.lower() or query_clean.startswith("http"):
            url = query_clean
        else:
            url = f"ytsearch1:{query_clean}"

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{self.music_dir}/%(title)s.%(ext)s',
            'writethumbnail': True,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True
        }

        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
        except Exception as e:
            print(f"Falha no download: {e}")
        
        self.after(0, lambda: self.btn_download.configure(state="normal", text="Baixar"))
        self.after(0, lambda: self.entry_search.delete(0, 'end'))

    def start_download_thread(self):
        query = self.entry_search.get()
        if not query: return
        
        self.btn_download.configure(state="disabled", text="Baixando...")
        threading.Thread(target=self.download_audio, args=(query,), daemon=True).start()

if __name__ == "__main__":
    app = PySpotifyApp()
    app.mainloop()