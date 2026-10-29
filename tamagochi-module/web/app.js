/* Independent, local-first companion UI. All data is obtained from the pet engine. */
'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const labels = {
  mood: {CALM:'Tranquilo', HAPPY:'Feliz', CURIOUS:'Curioso', EXCITED:'Empolgado', TIRED:'Cansado', FOCUSED:'Concentrado', BORED:'Entediado', PROUD:'Orgulhoso', RESTING:'Descansando'},
  trait: {PLAYFUL:'Brincalhão', CURIOUS:'Curioso', CREATIVE:'Criativo', ORGANIZED:'Organizado', SOCIAL:'Sociável', REFLECTIVE:'Reflexivo', HELPFUL:'Prestativo'},
  specialty: {EXPLORER:'Explorador', CREATOR:'Criador', RESEARCHER:'Pesquisador', ORGANIZER:'Organizador', COMPANION:'Companheiro'},
  xp: {FIRST_INTERACTION:'Primeira interação do dia', CONVERSATION:'Conversa significativa', TASK:'Tarefa concluída', GOAL:'Meta concluída', SKILL:'Nova habilidade', LEARN:'Atividade de aprendizado', CREATIVE:'Atividade criativa', MILESTONE:'Marco especial'},
  activity: {DREAM:'Sonhar', EXPLORE:'Explorar', EXPERIMENT:'Experimentar', JOURNAL:'Diário'},
  memory: {INTERACTION:'Interação', PREFERENCE:'Preferência', EVOLUTION:'Evolução', ACTIVITY:'Atividade', DIARY:'Diário', ACHIEVEMENT:'Conquista', DISCOVERY:'Descoberta', MOOD:'Humor'},
  stage: {AWAKENING:'Toda jornada começa aqui.', DISCOVERY:'Um mundo de possibilidades se abre.', LEARNING:'Cada descoberta constrói uma história.', COMPANION:'A convivência deixa suas marcas.', EXPLORER:'Novos horizontes para descobrir.', EVOLVED:'Uma jornada de muitos momentos.'},
  media: {idle_video:'Vídeo · repouso', idle_poster:'Poster · repouso', happy_video:'Vídeo · feliz', happy_poster:'Poster · feliz', thinking_video:'Vídeo · pensando', thinking_poster:'Poster · pensando', resting_video:'Vídeo · descanso', resting_poster:'Poster · descanso', milestone_video:'Vídeo · milestone', milestone_poster:'Poster · milestone'}
};
let state = null, memories = [], awards = [], history = [], media = {}, eventCursor = 0, eventsInitialized = false;
let memoryTotal = 0, hasMoreMemories = false, hasMoreAwards = false, hasMoreHistory = false;
let renderedAwardMarkup = null;
let milestonePlaying = false, failedVideo = null;
let authenticated = false, activeView = 'home';
// Only pagination counts, never event contents or credentials, are kept per tab.
const AWARD_PAGE_SIZE = 20, AWARD_API_LIMIT = 500, AWARD_POSITION_KEY = 'muse.sl001.journey.pagination.v1';
let awardTotal = 0, awardPosition = readAwardPosition();
// Local writes and snapshots must not paint responses in an older order.
let snapshotRevision = 0, refreshTail = Promise.resolve(), pendingRefresh = null, mutationTail = Promise.resolve();
let chatGeneration = 0;
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
const eventId = prefix => `${prefix}-${globalThis.crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
function readAwardPosition() {
  try {
    const value = JSON.parse(sessionStorage.getItem(AWARD_POSITION_KEY) || 'null');
    if (value && Number.isSafeInteger(value.loaded) && value.loaded > AWARD_PAGE_SIZE &&
        Number.isSafeInteger(value.total) && value.total >= value.loaded) return {loaded:value.loaded, total:value.total};
  } catch { /* storage may be disabled or contain invalid data */ }
  return null;
}
function rememberAwardPosition() {
  awardPosition = awards.length > AWARD_PAGE_SIZE ? {loaded:awards.length, total:awardTotal} : null;
  try {
    if (awardPosition) sessionStorage.setItem(AWARD_POSITION_KEY, JSON.stringify(awardPosition));
    else sessionStorage.removeItem(AWARD_POSITION_KEY);
  } catch { /* in-memory pagination still works when storage is unavailable */ }
}
const formatDate = value => {
  const d = new Date(value);
  return Number.isNaN(d.valueOf()) ? '—' : new Intl.DateTimeFormat('pt-BR', {day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}).format(d).replace('.', '');
};
function showLogin() {
  authenticated = false;
  const dialog = $('#dialog-login');
  if (!dialog.open) dialog.showModal();
}
async function api(path, options={}) {
  const request = {method: options.method || 'GET', headers: {'X-Pet-Request':'1',...(options.headers || {})}, cache:'no-store', credentials:'same-origin'};
  if (options.json !== undefined) { request.headers['Content-Type'] = 'application/json'; request.body = JSON.stringify(options.json); }
  else if (options.body !== undefined) request.body = options.body;
  const response = await fetch(path, request);
  let data = {};
  try { data = await response.json(); } catch { /* preserve the HTTP status */ }
  if (!response.ok) {
    const error = new Error(data.error || `Não foi possível concluir (HTTP ${response.status}).`);
    if (response.status === 401 && path !== '/api/session') { error.authRequired = true; showLogin(); }
    throw error;
  }
  return data;
}
function toast(message, isError=false) {
  const el = document.createElement('div'); el.className = `toast${isError ? ' error' : ''}`; el.textContent = message;
  const region = $('#toast-region');
  while (region.children.length >= 3) region.firstElementChild.remove();
  region.append(el); setTimeout(() => el.remove(), 6000);
}
function showError(error) { if (error.authRequired) return; console.error(error); toast(error.message || 'Algo não saiu como esperado.', true); }
// Keep focus on active controls while blocking repeated activation in code.
function beginButtonOperation(button) {
  if (button.getAttribute('aria-disabled') === 'true') return false;
  button.setAttribute('aria-disabled','true');
  return true;
}
function endButtonOperation(button) { button.removeAttribute('aria-disabled'); }
function setView(name) {
  if (!['home','evolution','diary','memory'].includes(name)) return;
  const previousView = document.activeElement?.closest('.view');
  activeView = name;
  $$('.view').forEach(el => { el.hidden = el.id !== `view-${name}`; });
  $$('.nav-item[data-view]').forEach(el => { const selected = el.dataset.view === name; el.classList.toggle('active', selected); if (selected) el.setAttribute('aria-current','page'); else el.removeAttribute('aria-current'); });
  $('#breadcrumb').textContent = {home:'MEU SLIME',evolution:'MINHA JORNADA',diary:'DIÁRIO',memory:'MEMÓRIAS'}[name];
  window.scrollTo({top:0, behavior:'auto'});
  // A shortcut inside the old view is now hidden; do not leave focus there.
  if (previousView?.hidden) {
    const heading = $(`#view-${name} h1`);
    if (heading) { heading.tabIndex = -1; heading.focus({preventScroll:true}); }
  }
}
function setBar(id, number) { $(id).style.width = `${Math.max(0,Math.min(100, Number(number) || 0))}%`; }
function renderState() {
  if (!state) return;
  $('#level').textContent = String(state.level).padStart(2,'0');
  $('#stage-name').textContent = state.stage.name;
  $('#stage-subtitle').textContent = labels.stage[state.stage.key] || 'Uma nova etapa começa.';
  $('#habitat-mood').textContent = labels.mood[state.mood] || state.mood;
  const {intoLevel, neededInLevel, nextThreshold, percent} = state.progress;
  const formatXP = number => number.toLocaleString('pt-BR');
  const remaining = neededInLevel - intoLevel;
  $('#xp-level-current').textContent = formatXP(intoLevel);
  $('#xp-level-needed').textContent = formatXP(neededInLevel);
  $('#xp-current').textContent = formatXP(state.xp);
  $('#xp-next').textContent = formatXP(nextThreshold);
  $('#xp-remaining').textContent = `${formatXP(remaining)} XP para o próximo nível`;
  const progressBar = $('#xp-progress');
  progressBar.setAttribute('aria-valuenow', String(intoLevel));
  progressBar.setAttribute('aria-valuemax', String(neededInLevel));
  progressBar.setAttribute('aria-valuetext', `${formatXP(intoLevel)} de ${formatXP(neededInLevel)} XP neste nível; ${formatXP(percent)}% concluído; faltam ${formatXP(remaining)} XP para o próximo nível`);
  setBar('#bar-xp',percent);
  for (const key of ['happiness','energy','bond']) { $(`#${key}-value`).textContent = Math.round(state[key]); setBar(`#bar-${key}`,state[key]); }
  $('#trait-list').innerHTML = state.leadingTraits.map(key => `<span class="trait-chip">${escapeHtml(labels.trait[key] || key)}</span>`).join('');
  $('#habitat-card').dataset.theme = state.habitat.theme;
  $('#habitat-card').dataset.decoration = state.habitat.decoration;
  const stageIndex = state.stages.findIndex(item => item.key === state.stage.key);
  $('#habitat-card').dataset.stageIndex = String(stageIndex);
  $('#habitat-stage-badge').hidden = stageIndex < 2;
  $('#habitat-stage-label').textContent = state.stage.name;
  $('#habitat-center').dataset.fit = state.habitat.playerFit;
  $('#journey-stage').textContent = state.stage.name;
  $('#journey-description').textContent = labels.stage[state.stage.key] || 'Uma nova etapa começa.';
  $('#journey-level').textContent = String(state.level).padStart(2,'0');
  $('#stage-timeline').innerHTML = state.stages.map(stage => {
    const unlocked = state.level >= stage.start, current = state.stage.key === stage.key;
    return `<div class="stage-row ${unlocked?'unlocked':''} ${current?'current':''}"><div class="stage-dot">${icon(unlocked?'check':'lock')}</div><div><strong>${escapeHtml(stage.name)}</strong><p>${escapeHtml(stage.reward)}</p></div><small>Nível ${stage.start}${current?' · atual':''}</small></div>`;
  }).join('');
  $('#specialization-name').textContent = labels.specialty[state.specialization] || 'Em formação';
  $('#specialization-scores').innerHTML = Object.entries(state.specializationScores).map(([key,value]) => `<div class="score-row"><span>${escapeHtml(labels.specialty[key] || key)}</span><strong>${value} ${value === 1 ? 'atividade' : 'atividades'}</strong></div>`).join('');
  $('#autonomy-status').textContent = state.autonomy.enabled ? `Autonomia ativada · a cada ${state.autonomy.intervalMinutes} min` : 'Autonomia desativada';
  const details = [['happiness','Felicidade','Bem-estar do slime'],['energy','Energia','Disposição para atividades'],['curiosity','Curiosidade','Vontade de explorar'],['knowledge','Conhecimento','Progresso de aprendizado'],['bond','Vínculo','Histórico de convivência'],['trust','Confiança','Segurança nas interações']];
  $('#all-stats').innerHTML = details.map(([key,label,description]) => `<div class="detail-stat"><div><span>${label}</span><strong>${Math.round(state[key])}</strong></div><div class="bar"><span data-stat-width="${Math.max(0,Math.min(100,state[key]))}"></span></div><small>${description}</small></div>`).join('');
  $$('#all-stats [data-stat-width]').forEach(el => {el.style.width = `${el.dataset.statWidth}%`;});
  updatePlayer();
}
function displayMemoryBody(entry) {
  // Translate only exact engine templates with known codes. Other content is
  // left unchanged, and the persisted record is never rewritten.
  const mood = entry.kind === 'MOOD' && /^O humor do SL-001 agora é ([A-Z_]+)\.$/.exec(entry.body);
  if (mood && labels.mood[mood[1]]) return `O humor do SL-001 agora é ${labels.mood[mood[1]].toLocaleLowerCase('pt-BR')}.`;
  const specialty = entry.kind === 'EVOLUTION' && /^A tendência ([A-Z_]+) se destacou nas atividades locais\.$/.exec(entry.body);
  if (specialty && labels.specialty[specialty[1]]) return `A tendência ${labels.specialty[specialty[1]].toLocaleLowerCase('pt-BR')} se destacou nas atividades locais.`;
  return entry.body;
}
function entryHtml(entry, canDelete=false) {
  const name = labels.memory[entry.kind] || entry.kind;
  const symbol = entry.kind === 'EVOLUTION' || entry.kind === 'ACHIEVEMENT' ? 'sparkle' : (entry.kind === 'DISCOVERY' ? 'compass' : 'book');
  return `<div class="entry"><div class="entry-icon">${icon(symbol)}</div><div><strong>${escapeHtml(entry.title)}</strong><p>${escapeHtml(displayMemoryBody(entry))}</p><small>${escapeHtml(name)} · ${escapeHtml(formatDate(entry.createdAt))}</small></div>${canDelete ? `<button class="delete-entry" data-delete-memory="${escapeHtml(entry.id)}" aria-label="Apagar registro ${escapeHtml(entry.title)}">${icon('trash')}</button>` : ''}</div>`;
}
function renderAwardList() {
  const list = $('#award-list');
  const markup = awards.length ? awards.map(item => `<div class="award-row" role="group" aria-label="${escapeHtml(labels.xp[item.reason] || item.reason)}, ${escapeHtml(item.day)}, mais ${item.amount} XP" data-award-event="${escapeHtml(item.eventId)}" data-award-reason="${escapeHtml(item.reason)}"><span>${escapeHtml(labels.xp[item.reason] || item.reason)}<br><small>${escapeHtml(item.day)}</small></span><strong>+${item.amount} XP</strong></div>`).join('') : '<div class="empty-state">As concessões de XP vão aparecer aqui.</div>';
  if (renderedAwardMarkup === markup) return;
  const focused = document.activeElement;
  const key = focused?.matches('.award-row') && list.contains(focused)
    ? {eventId:focused.dataset.awardEvent, reason:focused.dataset.awardReason} : null;
  list.innerHTML = markup; renderedAwardMarkup = markup;
  // Do not leave an old count in the live region when the ledger changes.
  $('#award-announcement').textContent = '';
  if (key && !$('#view-evolution').hidden) {
    const replacement = $$('.award-row', list).find(row => row.dataset.awardEvent === key.eventId && row.dataset.awardReason === key.reason);
    if (replacement) { replacement.tabIndex = -1; replacement.focus({preventScroll:true}); }
    else $('#award-heading').focus({preventScroll:true});
  }
}
function renderLists() {
  $('#recent-memories').innerHTML = memories.length ? memories.slice(0,2).map(entry => `<div class="recent-item"><span class="recent-icon">${icon(entry.kind==='EVOLUTION'?'sparkle':'book')}</span><div><strong>${escapeHtml(entry.title)}</strong><small>${escapeHtml(formatDate(entry.createdAt))}</small></div></div>`).join('') : '<div class="empty-state">Os primeiros momentos vão aparecer aqui.</div>';
  $('#diary-list').innerHTML = memories.length ? memories.map(entry => entryHtml(entry)).join('') : '<div class="empty-state">Ainda não há páginas por aqui. Cada momento pode se tornar uma lembrança.</div>';
  $('#memory-list').innerHTML = memories.length ? memories.map(entry => entryHtml(entry,true)).join('') : '<div class="empty-state">Nenhum registro guardado no momento.</div>';
  $('#memory-count').textContent = String(memoryTotal);
  $('#load-more-memories').hidden = !hasMoreMemories;
  renderAwardList();
  $('#autonomy-history').innerHTML = history.length ? history.map(item => `<div class="history-row"><span>${escapeHtml(labels.activity[item.activity] || 'Ciclo local')} · ${item.status === 'COMPLETED'?'concluído':item.status === 'SKIPPED'?'adiado':'falhou'}${item.scheduled?' · agendado':' · manual'}</span><span>${escapeHtml(formatDate(item.createdAt))}</span></div>`).join('') : '<div class="empty-state">Nenhuma atividade local executada ainda.</div>';
  $('#delete-all').disabled = memoryTotal === 0;
  $('#load-more-awards').hidden = !hasMoreAwards;
  $('#load-more-history').hidden = !hasMoreHistory;
}
function renderMediaList() {
  const entries = Object.entries(media);
  $('#media-list').innerHTML = entries.length ? entries.map(([slot,meta]) => `<div class="media-row"><div>${escapeHtml(labels.media[slot] || slot)}<small>SHA-256 ${escapeHtml(meta.sha256.slice(0,16))}… · ${(meta.size/1024/1024).toFixed(1)} MiB</small></div><button type="button" class="delete-entry" data-remove-media="${escapeHtml(slot)}" aria-label="Remover ${escapeHtml(labels.media[slot] || slot)}">${icon('trash')}</button></div>`).join('') : '<div class="empty-state">Nenhuma mídia original foi importada.</div>';
}
function mediaUrl(slot) { return media[slot] ? `/media/${slot}?sha=${encodeURIComponent(media[slot].sha256)}` : null; }
function baseMediaState() {
  if (['HAPPY','EXCITED','PROUD'].includes(state?.mood)) return 'happy';
  if (['TIRED','RESTING'].includes(state?.mood)) return 'resting';
  if (['CURIOUS','FOCUSED'].includes(state?.mood)) return 'thinking';
  return 'idle';
}
function updatePlayer() {
  if (!state) return;
  const video = $('#pet-video'), poster = $('#pet-poster'), placeholder = $('#media-placeholder');
  const wanted = milestonePlaying ? 'milestone' : baseMediaState();
  let videoSlot = media[`${wanted}_video`] ? `${wanted}_video` : 'idle_video';
  let posterSlot = media[`${wanted}_poster`] ? `${wanted}_poster` : 'idle_poster';
  let url = mediaUrl(videoSlot), posterUrl = mediaUrl(posterSlot);
  if (failedVideo === url) url = null;
  if (url) {
    placeholder.hidden = true; poster.hidden = true; video.hidden = false;
    video.loop = !milestonePlaying;
    if (posterUrl) video.poster = posterUrl; else video.removeAttribute('poster');
    if (video.getAttribute('src') !== url) {
      video.src = url; video.load();
      const playing = video.play();
      if (playing && typeof playing.catch === 'function') playing.catch(() => { /* browser may require a gesture; poster remains */ });
    }
  } else if (posterUrl) {
    video.pause(); video.hidden = true; placeholder.hidden = true; poster.hidden = false;
    if (poster.getAttribute('src') !== posterUrl) poster.src = posterUrl;
  } else {
    video.pause(); video.hidden = true; poster.hidden = true; placeholder.hidden = false;
  }
}
function celebrate() {
  if (!media.milestone_video) return;
  milestonePlaying = true; failedVideo = null; updatePlayer();
}
$('#pet-video').addEventListener('ended', () => { if (milestonePlaying) { milestonePlaying = false; updatePlayer(); } });
$('#pet-video').addEventListener('error', () => {
  const video = $('#pet-video'); if (!video.getAttribute('src') || video.hidden) return;
  failedVideo = video.getAttribute('src'); milestonePlaying = false; updatePlayer();
  toast('Não foi possível reproduzir esta mídia; o poster disponível será usado.', true);
});
async function refreshEvents() {
  let more = true, celebrateNow = false;
  // Process only events after the opening boundary, in bounded batches.
  for (let page=0; more && page<20; page++) {
    const result = await api(`/api/ui/events?after=${eventCursor}&limit=500`);
    for (const event of result.events) {
      eventCursor = Math.max(eventCursor,event.seq);
      if (event.eventType === 'PET_LEVEL_UP') { toast(`Novo nível: ${event.payload.level}! Uma etapa a mais na jornada.`); celebrateNow = true; }
      if (event.eventType === 'PET_EVOLUTION_UNLOCKED' && event.payload.axis === 'LEVEL') { toast(`Nova evolução: ${event.payload.name}. ${event.payload.reward}.`); celebrateNow = true; }
      if (event.eventType === 'PET_REWARD_UNLOCKED' && event.payload.mediaKey === 'milestone_video') celebrateNow = true;
    }
    more = result.events.length === 500;
  }
  if (celebrateNow) celebrate();
}
function serializeMutation(work) {
  const operation = mutationTail.then(work);
  // An error belongs to its caller; it must not poison later operations.
  mutationTail = operation.catch(() => {});
  return operation;
}
function applyMutationState(nextState) {
  snapshotRevision++;
  state = nextState;
  renderState();
}
async function readAwardWindow(position, extra=0) {
  // The ledger is append-only. A newer total means new entries appeared at the
  // front; include them without pushing the previously loaded tail off screen.
  for (;;) {
    const size = Math.min(AWARD_API_LIMIT, Math.max(AWARD_PAGE_SIZE, (position?.loaded ?? AWARD_PAGE_SIZE) + extra));
    const first = await api(`/api/awards?limit=${size}`);
    const desired = Math.min(first.total, position
      ? position.loaded + Math.max(0, first.total - position.total) + extra
      : AWARD_PAGE_SIZE + extra);
    const items = first.awards.slice(0, desired);
    let changed = false;
    while (items.length < desired) {
      const limit = Math.min(AWARD_API_LIMIT, desired - items.length);
      const next = await api(`/api/awards?limit=${limit}&offset=${items.length}`);
      if (next.total !== first.total) { changed = true; break; }
      if (!next.awards.length) throw new Error('Não foi possível completar o histórico de XP.');
      items.push(...next.awards);
    }
    // Page totals are read transactionally. Retry if another writer changed
    // the append-only ledger between requests rather than mixing two windows.
    if (!changed) return {awards:items, total:first.total, hasMore:items.length < first.total};
  }
}
function queueAwardRead(work) {
  // A load-more and a refresh share the same list; order them on the read tail.
  const operation = refreshTail.then(work);
  refreshTail = operation.catch(() => {});
  return operation;
}
async function refreshSnapshot(includeMedia) {
  // Take one opening boundary BEFORE reading state. Old events are not replayed,
  // while a milestone committed during the initial read remains after the cursor.
  if (!eventsInitialized) {
    const {cursor} = await api('/api/ui/events/cursor');
    if (!Number.isSafeInteger(cursor) || cursor < 0) throw new Error('Cursor local de eventos inválido.');
    eventCursor = cursor;
    eventsInitialized = true;
  }
  // If a local write completes during a read, retry the entire snapshot rather
  // than mixing an old state with newer lists or overwriting the action result.
  for (;;) {
    const revision = snapshotRevision;
    const nextState = (await api('/api/state')).state;
    if (revision !== snapshotRevision) continue;
    const requests = [api('/api/memories'), readAwardWindow(awardPosition), api('/api/autonomy/history')];
    if (includeMedia) requests.push(api('/api/media'));
    const results = await Promise.all(requests);
    if (revision !== snapshotRevision) continue;
    state = nextState;
    memories = results[0].memories; memoryTotal = results[0].total; hasMoreMemories = results[0].hasMore;
    awards = results[1].awards; awardTotal = results[1].total; hasMoreAwards = results[1].hasMore;
    history = results[2].history; hasMoreHistory = results[2].hasMore;
    rememberAwardPosition();
    if (includeMedia) { media = results[3].media; renderMediaList(); }
    renderState(); renderLists(); await refreshEvents();
    return;
  }
}
function refresh({includeMedia=false}={}) {
  // Coalesce requests waiting behind a refresh, without dropping a later read
  // or losing a request to include media. Every caller awaits that batch.
  if (pendingRefresh) {
    pendingRefresh.includeMedia ||= includeMedia;
    return pendingRefresh.promise;
  }
  const batch = {includeMedia, promise: null};
  batch.promise = refreshTail.then(() => {
    if (pendingRefresh === batch) pendingRefresh = null;
    return refreshSnapshot(batch.includeMedia);
  });
  refreshTail = batch.promise.catch(() => {});
  pendingRefresh = batch;
  return batch.promise;
}
async function action(name, button) {
  if (!beginButtonOperation(button)) return;
  try {
    await serializeMutation(async () => {
      const result = await api('/api/actions',{method:'POST',json:{action:name,eventId:eventId('ui')}});
      applyMutationState(result.state);
      toast(`${result.message}${result.xpAwarded ? ` +${result.xpAwarded} XP.` : ''}`);
      await refresh();
    });
  } catch (error) { showError(error); }
  finally { endButtonOperation(button); }
}
async function autoActivity(name,button) {
  button.disabled = true;
  try {
    await serializeMutation(async () => {
      const result = await api('/api/autonomy/run',{method:'POST',json:{activity:name,eventId:eventId('local')}});
      applyMutationState(result.state);
      toast(`${result.message}${result.xpAwarded ? ` +${result.xpAwarded} XP.` : ''}`);
      await refresh();
    });
  } catch(error) { showError(error); } finally { button.disabled = false; }
}
function renderBridgeConsent(consent) {
  $('#bridge-receive').checked = consent.receiveEvents;
  $('#bridge-share').checked = consent.shareData;
  const granted = [consent.receiveEvents && 'recebimento', consent.shareData && 'compartilhamento'].filter(Boolean);
  $('#bridge-status').textContent = granted.length ? `Permitido nesta execução: ${granted.join(' e ')}. Expira após 8 horas.` : 'Nenhuma permissão concedida.';
}
async function openDialog(name) {
  const dialog = $(`#dialog-${name}`); if (!dialog) return;
  if (name === 'settings') {
    const config = (await api('/api/config')).config;
    renderBridgeConsent((await api('/api/bridge/consent')).consent);
    $('#config-json').value = JSON.stringify(config,null,2);
    $('#auto-enabled').checked = config.autonomy.enabled;
    $('#auto-interval').value = config.autonomy.intervalMinutes;
    $('#rest-start').value = config.autonomy.restStartHour;
    $('#rest-end').value = config.autonomy.restEndHour;
    $('#time-zone').value = config.autonomy.timeZone;
    media = (await api('/api/media')).media; renderMediaList();
  }
  if (name === 'customize' && state) {
    const form = $('#customize-form');
    form.elements.theme.value = state.habitat.theme; form.elements.decoration.value = state.habitat.decoration; form.elements.playerFit.value = state.habitat.playerFit;
    const stageLevel = key => state.stages.find(item => item.key === key).start;
    for (const [value,key,label] of [['AURORA','EXPLORER','#lock-aurora'],['HALO','COMPANION','#lock-halo'],['CONSTELLATION','EVOLVED','#lock-constellation']]) {
      const input = $(`input[value="${value}"]`,form), required = stageLevel(key);
      input.disabled = state.level < required;
      $(label).textContent = input.disabled ? `· nível ${required}` : '· desbloqueado';
    }
  }
  if (!dialog.open) dialog.showModal();
}
document.addEventListener('click', async event => {
  const button = event.target.closest('button'); if (!button) return;
  try {
    if (button.dataset.view || button.dataset.go) setView(button.dataset.view || button.dataset.go);
    else if (button.dataset.open) await openDialog(button.dataset.open);
    else if (button.hasAttribute('data-close')) button.closest('dialog')?.close();
    else if (button.dataset.action) await action(button.dataset.action,button);
    else if (button.dataset.auto) await autoActivity(button.dataset.auto,button);
    else if (button.dataset.deleteMemory) {
      if (!confirm('Apagar este registro do pet?')) return;
      await api(`/api/memories/${encodeURIComponent(button.dataset.deleteMemory)}`,{method:'DELETE'}); snapshotRevision++; await refresh(); toast('Registro apagado.');
    } else if (button.dataset.removeMedia) {
      if (!confirm('Remover esta mídia local importada?')) return;
      await api(`/api/media/${button.dataset.removeMedia}`,{method:'DELETE'}); snapshotRevision++; failedVideo=null; await refresh({includeMedia:true}); toast('Mídia removida do armazenamento do protótipo.');
    }
  } catch(error) { showError(error); }
});
$('#load-more-memories').addEventListener('click', async event => {
  const button=event.currentTarget; button.disabled=true;
  try {
    const previous = memories, revision = snapshotRevision;
    const page = await api(`/api/memories?limit=100&offset=${previous.length}`);
    // A local mutation or refresh can replace this list while the page is in flight.
    // Do not resurrect deleted entries or append to a different snapshot.
    if (revision !== snapshotRevision || memories !== previous) return;
    memories.push(...page.memories); memoryTotal=page.total; hasMoreMemories=page.hasMore; renderLists();
  } catch(error) { showError(error); } finally { button.disabled=false; }
});
$('#load-more-awards').addEventListener('click', async event => {
  const button=event.currentTarget;
  // Native disabled would eject keyboard focus; guard re-entry while keeping it focusable.
  if (!beginButtonOperation(button)) return;
  try {
    await queueAwardRead(async () => {
      for (;;) {
        if (!hasMoreAwards) return;
        const revision = snapshotRevision, previous = {loaded:awards.length, total:awardTotal};
        const previousLast = awards.at(-1);
        const page = await api(`/api/awards?limit=${AWARD_PAGE_SIZE}&offset=${previous.loaded}`);
        if (revision !== snapshotRevision) continue;
        // Rebuild the window if new grants appeared ahead of the old offset.
        const result = page.total === previous.total
          ? {awards:[...awards,...page.awards], total:page.total, hasMore:page.hasMore}
          : await readAwardWindow(previous, AWARD_PAGE_SIZE);
        if (revision !== snapshotRevision) continue;
        const moveFocus = document.activeElement === button && !$('#view-evolution').hidden;
        awards=result.awards; awardTotal=result.total; hasMoreAwards=result.hasMore;
        const oldLastIndex = previousLast ? awards.findIndex(item => item.eventId === previousLast.eventId && item.reason === previousLast.reason) : -1;
        const firstNewIndex = oldLastIndex >= 0 ? oldLastIndex + 1 : previous.loaded;
        rememberAwardPosition(); renderLists();
        const added = Math.max(0, awards.length - previous.loaded);
        $('#award-announcement').textContent = !hasMoreAwards
          ? `Todos os ${awardTotal} registros de XP foram carregados.`
          : added ? `${added} registros de XP carregados. Mostrando ${awards.length} de ${awardTotal}.`
          : `Nenhum registro adicional encontrado. Mostrando ${awards.length} de ${awardTotal}.`;
        if (moveFocus) {
          const firstNew = $$('#award-list .award-row')[firstNewIndex];
          if (firstNew) { firstNew.tabIndex = -1; firstNew.focus(); }
          else if (!hasMoreAwards) $('#award-heading').focus();
        }
        return;
      }
    });
  } catch(error) { showError(error); } finally { endButtonOperation(button); }
});
$('#load-more-history').addEventListener('click', async event => {
  const button=event.currentTarget; button.disabled=true;
  try {
    const previous = history, revision = snapshotRevision;
    const page = await api(`/api/autonomy/history?limit=20&offset=${previous.length}`);
    // Avoid mixing an old offset with a refreshed history after an activity.
    if (revision !== snapshotRevision || history !== previous) return;
    history.push(...page.history); hasMoreHistory=page.hasMore; renderLists();
  } catch(error) { showError(error); } finally { button.disabled=false; }
});
$('#delete-all').addEventListener('click', async () => {
  if (!confirm('Apagar todas as memórias do pet? O histórico técnico de XP e deduplicação será preservado.')) return;
  try { await api('/api/memories',{method:'DELETE'}); snapshotRevision++; await refresh(); toast('Registros do pet apagados.'); } catch(error) { showError(error); }
});
$('#customize-form').addEventListener('submit', async event => {
  event.preventDefault(); const form = event.currentTarget, submit = $('button[type="submit"]',form); submit.disabled=true;
  try {
    const data = {theme:form.elements.theme.value,decoration:form.elements.decoration.value,playerFit:form.elements.playerFit.value};
    await serializeMutation(async () => {
      const result = await api('/api/customization',{method:'POST',json:data});
      applyMutationState(result.state);
      $('#dialog-customize').close(); toast('Habitat atualizado sem alterar o personagem.'); await refresh();
    });
  } catch(error) { showError(error); } finally { submit.disabled=false; }
});
$('#settings-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = $('button[type="submit"]',event.currentTarget); button.disabled=true;
  try {
    let config; try { config=JSON.parse($('#config-json').value); } catch { throw new Error('O JSON de regras avançadas é inválido.'); }
    if (!config.autonomy || typeof config.autonomy !== 'object') throw new Error('A seção autonomy é obrigatória.');
    config.autonomy = {...config.autonomy,enabled:$('#auto-enabled').checked,intervalMinutes:Number($('#auto-interval').value),restStartHour:Number($('#rest-start').value),restEndHour:Number($('#rest-end').value),timeZone:$('#time-zone').value.trim()};
    await serializeMutation(async () => {
      const result = await api('/api/config',{method:'POST',json:config});
      applyMutationState(result.state);
      $('#config-json').value=JSON.stringify(result.config,null,2); toast('Configurações salvas.'); await refresh();
    });
  } catch(error) { showError(error); } finally { button.disabled=false; }
});
$('#bridge-save').addEventListener('click', async event => {
  const button = event.currentTarget; button.disabled = true;
  try {
    const consent = {receiveEvents:$('#bridge-receive').checked,shareData:$('#bridge-share').checked};
    renderBridgeConsent((await api('/api/bridge/consent',{method:'POST',json:consent})).consent);
    toast('Permissões da ponte atualizadas.');
  } catch(error) { showError(error); } finally { button.disabled = false; }
});
$('#owner-logout').addEventListener('click', async () => {
  try { await api('/api/session',{method:'DELETE'}); location.reload(); } catch(error) { showError(error); }
});
$('#media-upload').addEventListener('click', async event => {
  const file = $('#media-file').files[0], slot = $('#media-slot').value; if (!file) return toast('Selecione um arquivo original aprovado.',true);
  if (file.size > 50*1024*1024) return toast('A mídia deve ter no máximo 50 MiB.',true);
  const button = event.currentTarget; button.disabled=true;
  try { await api(`/api/media/${slot}`,{method:'POST',body:file}); snapshotRevision++; $('#media-file').value=''; failedVideo=null; await refresh({includeMedia:true}); toast('Mídia original importada sem modificações.'); }
  catch(error) { showError(error); } finally { button.disabled=false; }
});
$('#chat-form').addEventListener('submit', async event => {
  event.preventDefault(); const input=$('#chat-input'), text=input.value.trim(), button=$('button',event.currentTarget);
  if (!text || !beginButtonOperation(button)) return;
  const generation = chatGeneration;
  try {
    await serializeMutation(async () => {
      // Only a length-derived boolean leaves the browser. Never send or persist the text.
      const result=await api('/api/actions',{method:'POST',json:{action:'CHAT',eventId:eventId('chat'),meaningful:text.length>=(state?.rules?.meaningfulChatMinChars ?? 30)}});
      // A queued reply must not restore text after this dialog was closed.
      if (generation === chatGeneration && $('#dialog-chat').open) {
        const output=$('#chat-output'); const own=document.createElement('div'); own.className='chat-bubble user'; own.textContent=text; output.append(own);
        const reply=document.createElement('div'); reply.className='chat-bubble';
        reply.textContent=`Estou ${String(labels.mood[result.state.mood] || 'tranquilo').toLowerCase()} e tenho ${Math.round(result.state.energy)} de energia. Obrigado por este momento! Esta é uma resposta local pré-definida.`;
        output.append(reply); output.scrollTop=output.scrollHeight;
        if (input.value.trim() === text) input.value='';
      }
      applyMutationState(result.state);
      if(result.xpAwarded) toast(`Momento registrado. +${result.xpAwarded} XP.`);
      await refresh();
    });
  } catch(error) { showError(error); } finally { endButtonOperation(button); }
});
// Retain no conversation text when the local dialog closes.
$('#dialog-chat').addEventListener('close', () => { chatGeneration++; $('#chat-input').value=''; $('#chat-output').innerHTML='<div class="chat-bubble">Olá! Que bom compartilhar este momento com você. ✦</div>'; });
$('#dialog-login').addEventListener('cancel', event => event.preventDefault());
$('#login-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = $('button[type="submit"]',event.currentTarget), input = $('#owner-token'), errorNode = $('#login-error');
  button.disabled = true; errorNode.hidden = true;
  try {
    await api('/api/session',{method:'POST',json:{token:input.value.trim()}});
    input.value = ''; authenticated = true;
    await refresh({includeMedia:true}); $('#dialog-login').close();
  } catch(error) {
    input.value = ''; errorNode.textContent = error.message; errorNode.hidden = false;
  } finally { button.disabled = false; }
});
document.addEventListener('visibilitychange', () => { if (authenticated && !document.hidden) refresh().catch(showError); });
setInterval(() => { if (authenticated && !document.hidden) refresh().catch(showError); }, 60000);
(async () => {
  try {
    authenticated = (await api('/api/session')).authenticated;
    if (authenticated) await refresh({includeMedia:true}); else showLogin();
  } catch(error) { showError(error); }
})();
