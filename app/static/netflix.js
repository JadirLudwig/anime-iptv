let animeData = [];
let currentIndex = -1;
let currentHls = null;
let lastFocusedElement = null;

// Storage for playback progress
const PROGRESS_KEY = 'anime_playback_progress';

document.addEventListener('DOMContentLoaded', () => {
    fetchAnimes();
    
    // Navbar scroll effect
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            document.getElementById('navbar').classList.add('scrolled');
        } else {
            document.getElementById('navbar').classList.remove('scrolled');
        }
    });

    document.getElementById('closeModalBtn').addEventListener('click', closeModal);
    document.getElementById('closePlayerBtn').addEventListener('click', closePlayer);

    // D-PAD Navigation Support
    document.addEventListener('keydown', handleKeyDown);

    // Video Progress Tracking
    const video = document.getElementById('videoPlayer');
    video.addEventListener('timeupdate', () => {
        if (video.dataset.epId && video.currentTime > 5) {
            saveProgress(video.dataset.epId, video.currentTime, video.duration);
        }
    });
});

function handleKeyDown(e) {
    const focusable = Array.from(document.querySelectorAll('[tabindex], button, video'));
    let current = document.activeElement;
    
    if (e.key === 'Enter') {
        if (current.onclick) current.onclick();
        else if (current.tagName === 'BUTTON') current.click();
        return;
    }

    if (e.key === 'Escape' || e.key === 'Back' || e.key === 'Backspace') {
        if (document.getElementById('playerPanel').style.display === 'block') {
            closePlayer();
        } else if (document.getElementById('detailsModal').style.display === 'flex') {
            closeModal();
        }
        return;
    }

    // Basic spatial navigation (very simple version)
    // In a real TV app, we'd use a grid-based spatial lib, 
    // but here we can just do basic tab navigation for simplicity or more complex logic.
    // For standard TV behavior, we usually just let the browser handle focus with Arrow keys 
    // if we add the right CSS and tabindexes.
}

async function fetchAnimes() {
    try {
        const res = await fetch('/api/animes');
        animeData = await res.json();
        renderHome();
        setupHero();
    } catch (err) {
        console.error("Error fetching animes:", err);
    }
}

function renderHome() {
    renderAnimesGrid(animeData, 'animeGrid');
    
    // Recently Added (Sort by ID or Sync Date)
    const recent = [...animeData].sort((a,b) => b.id - a.id).slice(0, 10);
    renderAnimesGrid(recent, 'recentGrid');

    // Continue Watching
    renderContinueWatching();
}

function renderAnimesGrid(data, containerId) {
    const grid = document.getElementById(containerId);
    grid.innerHTML = '';
    data.forEach(anime => {
        const card = document.createElement('div');
        card.className = 'anime-card';
        card.tabIndex = 0;
        card.innerHTML = `
            <img src="${anime.poster_url || 'https://via.placeholder.com/300x450?text=No+Poster'}" alt="${anime.name}">
            <div class="anime-info">
                <div class="anime-name">${anime.name}</div>
                <div style="font-size:0.7rem; color:var(--text-muted)">${anime.episodes.length} episódios</div>
            </div>
        `;
        card.onclick = () => showDetails(anime);
        grid.appendChild(card);
    });
}

function renderContinueWatching() {
    const progress = JSON.parse(localStorage.getItem(PROGRESS_KEY) || '{}');
    const row = document.getElementById('continueWatchingRow');
    const grid = document.getElementById('continueGrid');
    grid.innerHTML = '';

    const items = Object.values(progress).sort((a,b) => b.timestamp - a.timestamp);
    
    if (items.length > 0) {
        row.style.display = 'block';
        items.forEach(item => {
            // Find episode in animeData
            let ep = null;
            let targetAnime = null;
            for(const a of animeData) {
                ep = a.episodes.find(e => e.id == item.epId);
                if(ep) { targetAnime = a; break; }
            }

            if(ep) {
                const card = document.createElement('div');
                card.className = 'anime-card';
                card.tabIndex = 0;
                const percent = (item.time / item.duration) * 100;
                
                card.innerHTML = `
                    <img src="${targetAnime.poster_url}" alt="${targetAnime.name}">
                    <div style="position:absolute; bottom:0; left:0; width:100%; height:4px; background:#444;">
                        <div style="width:${percent}%; height:100%; background:var(--netflix-red);"></div>
                    </div>
                    <div class="anime-info">
                        <div class="anime-name">${targetAnime.name}</div>
                        <div style="font-size:0.7rem;">Episódio ${ep.number}</div>
                    </div>
                `;
                card.onclick = () => playEpisode(ep.id, targetAnime.name, ep.number, ep.media_type, item.time);
                grid.appendChild(card);
            }
        });
    } else {
        row.style.display = 'none';
    }
}

function setupHero() {
    if (animeData.length === 0) return;
    const hero = animeData[Math.floor(Math.random() * animeData.length)];
    if (hero.poster_url) {
        document.getElementById('hero').style.backgroundImage = `url('${hero.poster_url}')`;
    }
    document.getElementById('heroTitle').textContent = hero.name;
    document.getElementById('heroSynopsis').textContent = hero.description || "Nenhuma descrição disponível.";
    
    currentIndex = animeData.indexOf(hero);
    document.querySelector('.btn-primary').focus();
}

function showDetails(anime) {
    lastFocusedElement = document.activeElement;
    const modal = document.getElementById('detailsModal');
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    document.getElementById('modalAnimeTitle').textContent = anime.name;
    document.getElementById('modalHeaderBanner').style.backgroundImage = `url('${anime.poster_url}')`;
    
    // Meta Info
    const addedDate = new Date(anime.last_sync_date).toLocaleDateString('pt-BR');
    document.getElementById('modalAnimeMeta').textContent = `Adicionado em: ${addedDate} • ${anime.episodes.length} episódios`;
    document.getElementById('modalAnimeSynopsis').textContent = anime.description || "Nenhuma sinopse disponível.";

    const seasonGroups = document.getElementById('seasonGroups');
    seasonGroups.innerHTML = '';

    const seasons = {};
    anime.episodes.forEach(ep => {
        if (!seasons[ep.season]) seasons[ep.season] = [];
        seasons[ep.season].push(ep);
    });

    const sortedSeasons = Object.keys(seasons).sort((a,b) => a - b);
    sortedSeasons.forEach(s => {
        const group = document.createElement('div');
        group.className = 'season-group';
        group.innerHTML = `<h3 class="season-title">Temporada ${s}</h3>`;
        const epList = document.createElement('div');
        epList.className = 'ep-list';
        
        seasons[s].sort((a,b) => parseFloat(a.number) - parseFloat(b.number)).forEach(ep => {
            const item = document.createElement('div');
            item.className = 'ep-item';
            item.tabIndex = 0;
            const canPlay = ep.status === 'Online' || ep.status === 'Pending' || ep.status === 'Renovating';

            item.innerHTML = `
                <div class="ep-thumb">
                    ${ep.thumb_url ? `<img src="${ep.thumb_url}" style="width:100%;height:100%;object-fit:cover">` : '<i class="ph ph-image-square" style="font-size:2rem; opacity:0.3"></i>'}
                </div>
                <div class="ep-info">
                    <div class="ep-num">Episódio ${ep.number} ${ep.title ? '- ' + ep.title : ''}</div>
                    <div style="font-size: 0.8rem; color: #aaa; margin: 4px 0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                        ${ep.description || 'Sem descrição.'}
                    </div>
                    <div class="ep-status">${ep.status}</div>
                </div>
                ${canPlay ? '<i class="ph ph-play-fill" style="font-size:1.5rem"></i>' : ''}
            `;
            if (canPlay) item.onclick = () => playEpisode(ep.id, anime.name, ep.number, ep.media_type);
            epList.appendChild(item);
        });
        group.appendChild(epList);
        seasonGroups.appendChild(group);
    });

    // Focus first ep item
    const firstEp = seasonGroups.querySelector('.ep-item');
    if (firstEp) firstEp.focus();
}

function playEpisode(epId, animeName, epNumber, mediaType, resumeTime = 0) {
    const lastFocus = document.activeElement;
    const panel = document.getElementById('playerPanel');
    panel.style.display = 'block';
    
    const video = document.getElementById('videoPlayer');
    video.dataset.epId = epId;
    video.tabIndex = 0;
    
    const streamUrl = `/stream/${epId}`;
    if (currentHls) currentHls.destroy();

    if (mediaType === 'youtube') {
        const container = document.getElementById('videoContainer');
        const existingIframe = container.querySelector('iframe');
        if (existingIframe) existingIframe.remove();
        video.style.display = 'none';
        const iframe = document.createElement('iframe');
        iframe.src = streamUrl;
        iframe.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture";
        iframe.allowFullscreen = true;
        container.appendChild(iframe);
        iframe.focus();
    } else {
        video.style.display = 'block';
        if (Hls.isSupported()) {
            currentHls = new Hls();
            currentHls.loadSource(streamUrl);
            currentHls.attachMedia(video);
            currentHls.on(Hls.Events.MANIFEST_PARSED, () => {
                if (resumeTime > 0) video.currentTime = resumeTime;
                video.play();
            });
        } else {
            video.src = streamUrl;
            video.oncanplay = () => {
                if (resumeTime > 0) video.currentTime = resumeTime;
                video.play();
            };
        }
        video.focus();
    }
}

function saveProgress(epId, time, duration) {
    const progress = JSON.parse(localStorage.getItem(PROGRESS_KEY) || '{}');
    progress[epId] = {
        epId,
        time,
        duration,
        timestamp: Date.now()
    };
    // Keep only last 20 items
    const keys = Object.keys(progress).sort((a,b) => progress[b].timestamp - progress[a].timestamp);
    if(keys.length > 20) {
        keys.slice(20).forEach(k => delete progress[k]);
    }
    localStorage.setItem(PROGRESS_KEY, JSON.stringify(progress));
}

function closeModal() {
    document.getElementById('detailsModal').style.display = 'none';
    document.body.style.overflow = 'auto';
    if (lastFocusedElement) lastFocusedElement.focus();
}

function closePlayer() {
    document.getElementById('playerPanel').style.display = 'none';
    const video = document.getElementById('videoPlayer');
    video.pause();
    if (currentHls) {
        currentHls.destroy();
        currentHls = null;
    }
    renderContinueWatching();
    if (lastFocusedElement) lastFocusedElement.focus();
}

function playRandom() {
    if (currentIndex !== -1) showDetails(animeData[currentIndex]);
}
