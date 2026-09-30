import os
import sys
import time
from yt_dlp import YoutubeDL
import pygame

class MusicEngine:
    def __init__(self):
        self.music_dir = "musicas"
        self.current_track = None
        self.is_paused = False
        
        # Garante a existência do diretório de músicas
        if not os.path.exists(self.music_dir):
            os.makedirs(self.music_dir)
            
        # Inicializa o player de áudio
        pygame.mixer.init()

    def download_audio(self, search_query):
        """Busca e baixa o áudio do YouTube baseado no nome ou link."""
        print(f"\n[🔍] Buscando por: '{search_query}'...")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{self.music_dir}/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True
        }

        try:
            with YoutubeDL(ydl_opts) as ydl:
                # O prefixo ytsearch: faz a busca automática se não for uma URL direta
                info = ydl.extract_info(f"ytsearch1:{search_query}", download=True)
                if 'entries' in info and len(info['entries']) > 0:
                    video_title = info['entries'][0]['title']
                    filename = f"{video_title}.mp3"
                    print(f"[✅] Sucesso! Baixado: {filename}")
                    return filename
                else:
                    print("[❌] Nenhum resultado encontrado.")
                    return None
        except Exception as e:
            print(f"[❌] Erro no download: {e}")
            return None

    def list_local_songs(self):
        """Retorna uma lista de todas as músicas baixadas na pasta."""
        files = [f for f in os.listdir(self.music_dir) if f.endswith('.mp3')]
        return files

    def play(self, filename):
        """Carrega e reproduz uma música."""
        filepath = os.path.join(self.music_dir, filename)
        if os.path.exists(filepath):
            try:
                pygame.mixer.music.load(filepath)
                pygame.mixer.music.play()
                self.current_track = filename
                self.is_paused = False
                print(f"\n[🎶] Tocando agora: {filename}")
            except Exception as e:
                print(f"[❌] Erro ao reproduzir o arquivo: {e}")
        else:
            print("[❌] Arquivo não encontrado.")

    def pause_resume(self):
        """Alterna entre Pause e Resume."""
        if self.current_track:
            if self.is_paused:
                pygame.mixer.music.unpause()
                self.is_paused = False
                print("[▶] Música retomada.")
            else:
                pygame.mixer.music.pause()
                self.is_paused = True
                print("[⏸] Música pausada.")
        else:
            print("[⚠] Nenhuma música tocando no momento.")

    def stop(self):
        """Para a reprodução atual."""
        pygame.mixer.music.stop()
        self.current_track = None
        self.is_paused = False
        print("[⏹] Reprodução parada.")

    def set_volume(self, volume_level):
        """Ajusta o volume (0.0 a 1.0)."""
        # Garante que o input fique dentro do limite do pygame
        vol = max(0.0, min(1.0, volume_level))
        pygame.mixer.music.set_volume(vol)
        print(f"[🔊] Volume definido para: {int(vol * 100)}%")


# --- Interface de Controle via Terminal ---
def main():
    engine = MusicEngine()
    
    while True:
        print("\n" + "="*40)
        print(f" PYSPOTIFY ENGINE (Core Mode) ")
        print("="*40)
        if engine.current_track:
            status = "PAUSADO" if engine.is_paused else "TOCANDO"
            print(f"Status: [{status}] -> {engine.current_track}")
        else:
            print("Status: [PARADO]")
        print("-"*40)
        print("1. Buscar e Baixar Música")
        print("2. Listar Biblioteca Local")
        print("3. Play em Música Local")
        print("4. Pausar / Retomar")
        print("5. Parar")
        print("6. Ajustar Volume")
        print("0. Sair")
        print("="*40)
        
        opcao = input("Escolha uma opção: ").strip()

        if opcao == "1":
            busca = input("\nDigite o nome da música ou link do YT: ")
            if busca:
                engine.download_audio(busca)
                
        elif opcao == "2":
            musicas = engine.list_local_songs()
            print("\n--- SUA BIBLIOTECA ---")
            if not musicas:
                print("Nenhuma música baixada ainda.")
            for idx, musica in enumerate(musicas, start=1):
                print(f"{idx}. {musica}")
                
        elif opcao == "3":
            musicas = engine.list_local_songs()
            if not musicas:
                print("\n[⚠] Baixe alguma música primeiro!")
                continue
                
            print("\n--- SELECIONE A MÚSICA ---")
            for idx, musica in enumerate(musicas, start=1):
                print(f"{idx}. {musica}")
                
            try:
                escolha = int(input("\nDigite o número da música: "))
                if 1 <= escolha <= len(musicas):
                    engine.play(musicas[escolha - 1])
                else:
                    print("[❌] Índice inválido.")
            except ValueError:
                print("[❌] Digite um número válido.")
                
        elif opcao == "4":
            engine.pause_resume()
            
        elif opcao == "5":
            engine.stop()
            
        elif opcao == "6":
            try:
                vol = float(input("\nDigite o volume de 0 a 100: "))
                engine.set_volume(vol / 100.0)
            except ValueError:
                print("[❌] Entrada inválida.")
                
        elif opcao == "0":
            engine.stop()
            print("\nEncerrando o PySpotify. Até logo!")
            sys.exit()
        else:
            print("[❌] Opção inválida.")

        time.sleep(1)

if __name__ == "__main__":
    main()
