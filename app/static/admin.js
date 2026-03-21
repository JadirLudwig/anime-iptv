document.addEventListener('DOMContentLoaded', () => {
    fetchAnimes();

    document.getElementById('addAnimeForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const targetUrl = document.getElementById('targetUrl').value;
        
        try {
            showToast('Adding anime and fetching episode list...');
            const res = await fetch('/api/animes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ base_url: targetUrl })
            });
            
            if (res.ok) {
                showToast(`Tracked successfuly. Running background sync...`);
                document.getElementById('addAnimeForm').reset();
                setTimeout(fetchAnimes, 3000);
            } else {
                const data = await res.json();
                showToast(`Error: ${data.detail}`, true);
            }
        } catch (err) {
            showToast('Network error while adding.', true);
        }
    });

    document.getElementById('refreshListBtn').addEventListener('click', fetchAnimes);
});

let globalAnimes = [];
let hlsInstance = null;

function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.style.background = isError ? 'var(--status-expired)' : 'var(--primary)';
    toast.classList.remove('hidden');
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 4000);
}

async function fetchAnimes() {
    try {
        const res = await fetch('/api/animes');
        globalAnimes = await res.json();
        
        const tbody = document.getElementById('animeListBody');
        tbody.innerHTML = '';
        
        globalAnimes.forEach(anime => {
            const onlineEps = anime.episodes.filter(e => e.status === 'Online').length;
            const episodeStr = `${anime.episodes.length} (${onlineEps} Online)`;

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${anime.name}</strong></td>
                <td><span class="status-badge status-Online">${episodeStr}</span></td>
                <td>
                    <button class="action-btn" onclick="viewEpisodes(${anime.id})">📺 View Episodes</button>
                    <button class="action-btn" onclick="forceSync(${anime.id})">🔄 Sync</button>
                    <button class="action-btn" style="background:#e53e3e" onclick='deleteAnime(${anime.id}, ${JSON.stringify(anime.name)})' title="Remove anime">🗑️ Delete</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error("Error fetching animes:", err);
    }
}

async function forceSync(id) {
    try {
        const res = await fetch(`/api/animes/${id}/sync`, { method: 'POST' });
        if (res.ok) {
            showToast('Anime sync triggered. Checking for new episodes...');
            setTimeout(fetchAnimes, 3000);
        } else {
            showToast('Error triggering sync.', true);
        }
    } catch (err) {
        showToast('Network error.', true);
    }
}

async function deleteAnime(id, name) {
    if (!confirm(`Remover "${name}" e todos os seus episódios?`)) return;
    try {
        const res = await fetch(`/api/animes/${id}`, { method: 'DELETE' });
        if (res.ok) {
            showToast(`"${name}" removido com sucesso!`);
            // Hide episodes panel if it was showing this anime
            document.getElementById('episodesPanel').style.display = 'none';
            fetchAnimes();
        } else {
            showToast('Erro ao remover o anime.', true);
        }
    } catch (err) {
        showToast('Erro de rede.', true);
    }
}

function viewEpisodes(animeId) {
    const anime = globalAnimes.find(a => a.id === animeId);
    if (!anime) return;

    document.getElementById('episodesPanel').style.display = 'block';
    document.getElementById('selectedAnimeName').textContent = anime.name;

    const tbody = document.getElementById('episodeListBody');
    tbody.innerHTML = '';

    // Sort episodes by season then number
    let eps = [...anime.episodes];
    eps.sort((a,b) => {
        let sA = parseInt(a.season) || 1;
        let sB = parseInt(b.season) || 1;
        if (sA !== sB) return sA - sB;
        let n1 = parseFloat(a.number.replace('.','')) || 0;
        let n2 = parseFloat(b.number.replace('.','')) || 0;
        return n1 - n2;
    });

    let currentSeason = -1;
    eps.forEach(ep => {
        // Add season header
        if (ep.season !== currentSeason) {
            currentSeason = ep.season;
            const seasonTr = document.createElement('tr');
            seasonTr.style.background = 'rgba(255,255,255,0.05)';
            seasonTr.innerHTML = `<td colspan="3" style="font-weight:bold; color:var(--primary); padding-top: 15px;">Temporada ${currentSeason}</td>`;
            tbody.appendChild(seasonTr);
        }

        const tr = document.createElement('tr');
        const canPlay = ep.status === 'Online' || ep.status === 'Pending' || ep.status === 'Renovating';
        tr.innerHTML = `
            <td style="padding-left: 20px;"><strong>Ep ${ep.number}</strong></td>
            <td><span class="status-badge status-${ep.status}">${ep.status}</span></td>
            <td>
                ${canPlay ? `<button class="action-btn" style="background:var(--primary)" onclick="playEpisode(${ep.id}, '${anime.name.replace(/'/g, "\\'")}', '${ep.number}', '${ep.media_type || ""}')">▶ Play</button>` : 'N/A'}
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function playEpisode(epId, animeName, epNumber, mediaType) {
    const playerPanel = document.getElementById('playerPanel');
    playerPanel.style.display = 'block';
    playerPanel.scrollIntoView({ behavior: 'smooth' });

    document.getElementById('nowPlayingTitle').textContent = `${animeName} - Ep ${epNumber}`;
    document.getElementById('playerPlaceholder').classList.remove('show');

    if (hlsInstance) {
        hlsInstance.destroy();
        hlsInstance = null;
    }

    const container = document.querySelector('.video-container');

    // Remove any existing youtube iframe
    const existingIframe = container.querySelector('iframe.yt-player');
    if (existingIframe) existingIframe.remove();

    const video = document.getElementById('internalPlayer');

    if (mediaType === 'youtube') {
        // For YouTube embeds, use an iframe directly
        video.style.display = 'none';
        const iframe = document.createElement('iframe');
        iframe.className = 'yt-player';
        iframe.style.cssText = 'width:100%;height:100%;min-height:400px;border:0;border-radius:12px;';
        iframe.src = `/stream/${epId}`;
        iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture';
        iframe.allowFullscreen = true;
        container.appendChild(iframe);
    } else {
        video.style.display = 'block';
        const streamUrl = `/stream/${epId}`;
        if (Hls.isSupported()) {
            hlsInstance = new Hls();
            hlsInstance.loadSource(streamUrl);
            hlsInstance.attachMedia(video);
            hlsInstance.on(Hls.Events.MANIFEST_PARSED, function() {
                video.play().catch(e => console.log('Autoplay blocked', e));
            });
        } else {
            video.src = streamUrl;
            video.play().catch(e => console.log('Autoplay blocked', e));
        }
    }
}
