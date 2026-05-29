let audioCtx, audioSource, pannerNode, gainNode;
let playlist = [];
let currentIndex = 0;
let isPlaying = false;
let is8D = false, isTremolo = false, isSurround = false;
let angle8d = 0;

const audioEl = new Audio();

// Elementos da Interface
const btnPlay = document.getElementById('btnPlay');
const btn8d = document.getElementById('btn8d');
const btnTremolo = document.getElementById('btnTremolo');
const btnSurround = document.getElementById('btnSurround');
const trackTitle = document.getElementById('trackTitle');
const progress = document.getElementById('progress');
const currTimeEl = document.getElementById('currTime');
const totalTimeEl = document.getElementById('totalTime');
const fileInput = document.getElementById('audioFiles');

// Inicializa o Contexto de Áudio Web (Segurança dos navegadores exige clique do usuário)
function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        audioSource = audioCtx.createMediaElementSource(audioEl);
        
        // Nó do Panner Estéreo (Controla Esquerda/Direita para o 8D)
        pannerNode = audioCtx.createStereoPanner();
        // Nó de Ganho (Volume dinâmico para o Tremolo)
        gainNode = audioCtx.createGain();

        // Conexões: Fonte -> Efeito Espacial -> Efeito Volume -> Saída do Celular
        audioSource.connect(pannerNode);
        pannerNode.connect(gainNode);
        gainNode.connect(audioCtx.destination);
    }
}

// Carregar fila de músicas do aparelho
fileInput.addEventListener('change', (e) => {
    initAudio();
    const files = Array.from(e.target.files);
    if (files.length === 0) return;

    playlist = files.map(file => ({
        name: file.name.replace(/\.[^/.]+$/, ""), // Remove a extensão (.mp3, etc)
        url: URL.createObjectURL(file)
    }));

    currentIndex = 0;
    loadTrack(currentIndex);
    playTrack();
});

function loadTrack(index) {
    if (!playlist[index]) return;
    audioEl.src = playlist[index].url;
    trackTitle.innerText = playlist[index].name;
    progress.value = 0;
}

function playTrack() {
    if (!audioEl.src) return;
    audioCtx.resume();
    audioEl.play();
    btnPlay.innerText = "⏸";
    isPlaying = true;
}

function pauseTrack() {
    audioEl.pause();
    btnPlay.innerText = "▶";
    isPlaying = false;
}

// Controles Globais
btnPlay.addEventListener('click', () => {
    if (isPlaying) { pauseTrack(); } else { playTrack(); }
});

document.getElementById('btnNext').addEventListener('click', () => {
    if (playlist.length === 0) return;
    currentIndex = (currentIndex + 1) % playlist.length;
    loadTrack(currentIndex);
    playTrack();
});

document.getElementById('btnPrev').addEventListener('click', () => {
    if (playlist.length === 0) return;
    currentIndex = (currentIndex - 1 + playlist.length) % playlist.length;
    loadTrack(currentIndex);
    playTrack();
});

// Alternadores de Efeitos (Ativa/Desativa)
btn8d.addEventListener('click', () => {
    is8D = !is8D;
    btn8d.classList.toggle('active', is8D);
    btn8d.innerText = is8D ? "🎧 8D: Ativo" : "🎧 8D: Off";
    if (!is8D && pannerNode) pannerNode.pan.setValueAtTime(0, audioCtx.currentTime);
});

btnTremolo.addEventListener('click', () => {
    isTremolo = !isTremolo;
    btnTremolo.classList.toggle('active', isTremolo);
    btnTremolo.innerText = isTremolo ? "🌊 Tremolo: Ativo" : "🌊 Tremolo: Off";
    if (!isTremolo && gainNode) gainNode.gain.setValueAtTime(1, audioCtx.currentTime);
});

btnSurround.addEventListener('click', () => {
    isSurround = !isSurround;
    btnSurround.classList.toggle('active', isSurround);
    btnSurround.innerText = isSurround ? "📻 Surround: Ativo" : "📻 Surround: Off";
});

// Atualização de Linha do Tempo / Seek
audioEl.addEventListener('timeupdate', () => {
    if (isNaN(audioEl.duration)) return;
    progress.max = audioEl.duration;
    progress.value = audioEl.currentTime;
    
    currTimeEl.innerText = formatTime(audioEl.currentTime);
    totalTimeEl.innerText = formatTime(audioEl.duration);
});

progress.addEventListener('input', () => {
    audioEl.currentTime = progress.value;
});

audioEl.addEventListener('ended', () => {
    document.getElementById('btnNext').click();
});

function formatTime(secs) {
    let min = Math.floor(secs / 60);
    let sec = Math.floor(secs % 60);
    return `${min}:${sec < 10 ? '0' : ''}${sec}`;
}

// LOOP DO PROCESSADOR DE ÁUDIO (Mapeado direto do seu script Python)
// Roda a cada 30ms garantindo transições perfeitamente fluidas e sem ruídos
setInterval(() => {
    if (!isPlaying || !audioCtx) return;

    let now = audioCtx.currentTime;

    // 1. Processamento do Efeito 8D (Rotação 360 Graus suave)
    if (is8D && pannerNode) {
        angle8d += 0.04;
        let panValue = Math.sin(angle8d); // Oscila entre -1 (Esquerda) e 1 (Direita)
        pannerNode.pan.setValueAtTime(panValue, now);
    }

    // 2. Processamento do Efeito Tremolo (Modulação senoidal de Volume)
    if (isTremolo && gainNode) {
        // Oscilação rápida e sutil de volume imitando caixas de som clássicas
        let modVol = 0.85 + 0.15 * Math.sin(audioEl.currentTime * 2 * Math.PI * 4.0);
        gainNode.gain.setValueAtTime(modVol, now);
    }

    // 3. Processamento do Efeito Surround (Simulação de Fase/Eco leve)
    if (isSurround && pannerNode && is8D === false) {
        // Adiciona um balanço tridimensional estático expandindo o palco sonoro
        let surroundValue = 0.3 * Math.cos(audioEl.currentTime * 1.5);
        pannerNode.pan.setValueAtTime(surroundValue, now);
    }
}, 30);