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
const trackCount = document.getElementById('trackCount');
const progress = document.getElementById('progress');
const currTimeEl = document.getElementById('currTime');
const totalTimeEl = document.getElementById('totalTime');
const fileInput = document.getElementById('audioFiles');
const playlistTracksContainer = document.getElementById('playlistTracks');

function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        audioSource = audioCtx.createMediaElementSource(audioEl);
        pannerNode = audioCtx.createStereoPanner();
        gainNode = audioCtx.createGain();

        audioSource.connect(pannerNode);
        pannerNode.connect(gainNode);
        gainNode.connect(audioCtx.destination);
    }
}

// Carregar arquivos e montar a lista visual
fileInput.addEventListener('change', (e) => {
    initAudio();
    const files = Array.from(e.target.files);
    if (files.length === 0) return;

    playlist = files.map(file => ({
        name: file.name.replace(/\.[^/.]+$/, ""),
        url: URL.createObjectURL(file)
    }));

    trackCount.innerText = `${playlist.length} músicas adicionadas`;
    renderPlaylist();
    
    currentIndex = 0;
    loadTrack(currentIndex);
    playTrack();
});

// Renderiza a lista de músicas na tela igual ao app Desktop
function renderPlaylist() {
    playlistTracksContainer.innerHTML = '';
    playlist.forEach((track, index) => {
        const item = document.createElement('div');
        item.className = `track-item ${index === currentIndex ? 'playing' : ''}`;
        item.innerHTML = `
            <div class="track-item-index">${index + 1}</div>
            <div class="track-item-name">${track.name}</div>
        `;
        
        // Se clicar na música da lista, ela toca direto!
        item.addEventListener('click', () => {
            currentIndex = index;
            loadTrack(currentIndex);
            playTrack();
        });
        
        playlistTracksContainer.appendChild(item);
    });
}

function loadTrack(index) {
    if (!playlist[index]) return;
    audioEl.src = playlist[index].url;
    trackTitle.innerText = playlist[index].name;
    progress.value = 0;
    
    // Atualiza qual música está marcada como "tocando agora" na lista
    const items = document.querySelectorAll('.track-item');
    items.forEach((item, idx) => {
        if (idx === index) {
            item.classList.add('playing');
            item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
            item.classList.remove('playing');
        }
    });
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

// Efeitos
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

// Loop do processador
setInterval(() => {
    if (!isPlaying || !audioCtx) return;
    let now = audioCtx.currentTime;

    if (is8D && pannerNode) {
        angle8d += 0.04;
        pannerNode.pan.setValueAtTime(Math.sin(angle8d), now);
    }
    if (isTremolo && gainNode) {
        let modVol = 0.85 + 0.15 * Math.sin(audioEl.currentTime * 2 * Math.PI * 4.0);
        gainNode.gain.setValueAtTime(modVol, now);
    }
    if (isSurround && pannerNode && is8D === false) {
        let surroundValue = 0.3 * Math.cos(audioEl.currentTime * 1.5);
        pannerNode.pan.setValueAtTime(surroundValue, now);
    }
}, 30);
