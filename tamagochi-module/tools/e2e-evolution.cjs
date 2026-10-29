/* Browser regression for XP display and evolution, using ONLY local disposable
 * data. Optional EVIDENCE_DIR saves screenshots; no real pet media is imported.
 * Requires Node 22, puppeteer-core and CHROME_BIN. */
'use strict';
const assert = require('node:assert/strict');
const {spawn, spawnSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const puppeteer = require('puppeteer-core');
const {holdOneResponse} = require('./browser-test-helpers.cjs');

const root = path.resolve(__dirname, '..');
const chrome = process.env.CHROME_BIN;
if (!chrome) throw new Error('Defina CHROME_BIN para um Chromium/Chrome local.');
const evidenceDir = process.env.EVIDENCE_DIR ? path.resolve(process.env.EVIDENCE_DIR) : null;
if (evidenceDir) fs.mkdirSync(evidenceDir, {recursive: true});
const errors = [], external = [], running = new Set();
let browser;

async function serverFor(target, existingDirectory = null) {
  if (target && existingDirectory) throw new Error('Não semear um diretório de dados já existente.');
  const directory = existingDirectory || fs.mkdtempSync(path.join(os.tmpdir(), 'sl001-evolution-ui-'));
  const accessDir = path.join(directory, '.access');
  const oldSessions = new Set(fs.existsSync(accessDir) ? fs.readdirSync(accessDir) : []);
  if (target) {
    const seed = spawnSync(process.env.PYTHON || 'python3', ['tests/evolution_scenario.py', '--seed-dir', directory, '--target', target],
      {cwd: root, env: {...process.env, PYTHONPATH: '.'}, encoding: 'utf8'});
    if (seed.status !== 0) {
      fs.rmSync(directory, {recursive: true, force: true});
      throw new Error(`Falha ao criar cenário descartável: ${seed.stderr || seed.stdout}`);
    }
    if (target === 'level50-edge') console.log(seed.stdout.trim());
  }
  const server = spawn(process.env.PYTHON || 'python3', ['app.py', '--host', '127.0.0.1', '--port', '0', '--data-dir', directory],
    {cwd: root, stdio: ['ignore', 'pipe', 'pipe']});
  const entry = {server, directory};
  running.add(entry);
  const port = await new Promise((resolve, reject) => {
    let output = '', diagnostics = '';
    const timeout = setTimeout(() => reject(new Error(`Servidor não iniciou: ${diagnostics}`)), 10000);
    server.stderr.on('data', data => { diagnostics += data.toString(); });
    server.stdout.on('data', data => {
      output += data.toString();
      const match = output.match(/:(\d+) \(modo local/);
      if (match) { clearTimeout(timeout); resolve(Number(match[1])); }
    });
    server.once('error', error => { clearTimeout(timeout); reject(error); });
    server.once('exit', code => { clearTimeout(timeout); reject(new Error(`Servidor saiu (${code}): ${diagnostics}`)); });
  });
  const sessionName = fs.readdirSync(accessDir).find(name => !oldSessions.has(name));
  if (!sessionName) throw new Error('A sessão local do novo servidor não foi criada.');
  const sessionDir = path.join(accessDir, sessionName);
  entry.ownerToken = fs.readFileSync(path.join(sessionDir, 'owner.token'), 'utf8').trim();
  entry.port = port;
  return entry;
}

async function closeServer(entry, {preserveData = false} = {}) {
  if (!running.has(entry)) return;
  if (entry.server.exitCode === null && entry.server.signalCode === null) {
    await new Promise(resolve => {
      const timeout = setTimeout(() => { entry.server.kill('SIGKILL'); resolve(); }, 3000);
      entry.server.once('exit', () => { clearTimeout(timeout); resolve(); });
      // A clean stop allows a second server process to reopen the same database.
      entry.server.kill(preserveData ? 'SIGINT' : 'SIGTERM');
    });
  }
  if (!preserveData) fs.rmSync(entry.directory, {recursive: true, force: true});
  running.delete(entry);
  if (preserveData && entry.server.exitCode !== 0) throw new Error('O servidor de teste não encerrou normalmente antes da reinicialização.');
}

async function loginPage(page, token) {
  await page.waitForSelector('#dialog-login[open]');
  await page.$eval('#owner-token', el => { el.value = ''; });
  await page.type('#owner-token', token);
  await page.click('#login-form button[type="submit"]');
  await page.waitForFunction(() => !document.querySelector('#dialog-login').open);
  await page.waitForFunction(() => document.querySelector('#habitat-card').dataset.stageIndex !== undefined);
}

async function withPage(target, callback) {
  const entry = await serverFor(target);
  const context = await browser.createBrowserContext();
  try {
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
    page.on('request', req => {
      const url = new URL(req.url());
      if (['http:', 'https:'].includes(url.protocol) && url.hostname !== '127.0.0.1') external.push(req.url());
    });
    await page.setViewport({width: 1440, height: 1000, deviceScaleFactor: 1});
    // Remove progress-bar transition while capturing evidence, not the values.
    await page.emulateMediaFeatures([{name: 'prefers-reduced-motion', value: 'reduce'}]);
    await page.goto(`http://127.0.0.1:${entry.port}/`, {waitUntil: 'networkidle0'});
    await loginPage(page, entry.ownerToken);
    await callback(page, context, entry);
  } finally {
    await context.close();
    await closeServer(entry);
  }
}

async function screenshot(page, filename, fullPage = true) {
  if (evidenceDir) await page.screenshot({path: path.join(evidenceDir, filename), fullPage});
}

async function tabTo(page, selector, reverse=false) {
  for (let i = 0; i < 80; i++) {
    if (await page.evaluate(s => document.activeElement.matches(s), selector)) return;
    if (reverse) await page.keyboard.down('Shift');
    await page.keyboard.press('Tab');
    if (reverse) await page.keyboard.up('Shift');
  }
  throw new Error(`O teclado não alcançou ${selector}.`);
}

// Observe the same returned state in the habitat, attributes dialog and journey.
async function sharedState(page) {
  await page.evaluate(() => refresh());
  const observed = await page.evaluate(() => ({
    state: structuredClone(state),
    home: {xp:Number(document.querySelector('#xp-current').textContent.replace(/\D/g, '')), level:Number(document.querySelector('#level').textContent), stage:document.querySelector('#stage-name').textContent, mood:document.querySelector('#habitat-mood').textContent},
    journey: {level:Number(document.querySelector('#journey-level').textContent), stage:document.querySelector('#journey-stage').textContent},
    attributes: [...document.querySelectorAll('#all-stats .detail-stat strong')].map(el => Number(el.textContent)),
    expectedMood: labels.mood[state.mood],
  }));
  const s = observed.state;
  assert.deepEqual([observed.home.xp, observed.home.level, observed.home.stage, observed.home.mood], [s.xp, s.level, s.stage.name, observed.expectedMood], 'habitat acompanha estado local');
  assert.deepEqual([observed.journey.level, observed.journey.stage], [s.level, s.stage.name], 'jornada acompanha o mesmo nível e estágio');
  assert.deepEqual(observed.attributes, ['happiness','energy','curiosity','knowledge','bond','trust'].map(key => Math.round(s[key])), 'diálogo de atributos usa o mesmo estado');
  const fromAPI = await page.evaluate(() => api('/api/state').then(result => result.state));
  assert.deepEqual([fromAPI.xp, fromAPI.level, fromAPI.stage.key, fromAPI.mood], [s.xp, s.level, s.stage.key, s.mood]);
  for (const key of ['happiness','curiosity','knowledge','bond','trust','specialization','recentSignal','traits','specializationScores']) {
    assert.deepEqual(fromAPI[key], s[key], `${key}: estado renderizado confere com API`);
  }
  assert.ok(Math.abs(fromAPI.energy - s.energy) < 0.05, 'energia pode recuperar um pouco durante as leituras');
  return fromAPI;
}

function assertContinuous(before, after) {
  for (const key of ['xp','level','mood','recentSignal','activity','happiness','curiosity','knowledge','bond','trust','specialization','traits','specializationScores']) {
    assert.deepEqual(after[key], before[key], `${key}: preservado no mesmo banco`);
  }
  assert.equal(after.stage.key, before.stage.key, 'estágio derivado do XP preservado');
  assert.ok(after.energy >= before.energy - 0.0001 && after.energy - before.energy < 0.05, 'energia preservada com recuperação passiva limitada ao tempo decorrido');
}

function summaryState(s) {
  return {xp:s.xp, level:s.level, stage:s.stage.name, mood:s.mood,
    attributes:['happiness','energy','curiosity','knowledge','bond','trust'].map(key => Math.round(s[key])), specialty:s.specialization};
}

async function submitChat(page, text) {
  const before = await page.$$eval('#chat-output .chat-bubble', nodes => nodes.length);
  await page.type('#chat-input', text);
  await page.click('#chat-form button[type="submit"]');
  await page.waitForFunction(count => document.querySelectorAll('#chat-output .chat-bubble').length === count + 2 && document.querySelector('#chat-form button[type="submit"]').getAttribute('aria-disabled') !== 'true', {}, before);
}

async function traceState(page, label, expectedStats, expectedMood, expectedXP) {
  const observed = await page.evaluate(() => ({
    stats: [...document.querySelectorAll('#all-stats .detail-stat strong')].map(el => Number(el.textContent)),
    mood: document.querySelector('#habitat-mood').textContent,
    xp: Number(document.querySelector('#xp-current').textContent.replace(/\D/g, '')),
    level: Number(document.querySelector('#level').textContent),
    stage: document.querySelector('#stage-name').textContent,
  }));
  assert.deepEqual(observed.stats, expectedStats, `${label}: atributos`);
  assert.equal(observed.mood, expectedMood, `${label}: humor`);
  assert.equal(observed.xp, expectedXP, `${label}: XP`);
  console.log(`${label}: XP=${observed.xp}; nível=${observed.level}; estágio=${observed.stage}; humor=${observed.mood}; atributos [felicidade,energia,curiosidade,conhecimento,vínculo,confiança]=${observed.stats.join(',')}`);
}

async function traceFeedback(page, label, expected) {
  const notifications = await page.$$eval('#toast-region .toast', nodes => nodes.map(node => node.textContent));
  assert.ok(notifications.includes(expected), `${label}: aviso esperado ausente: ${notifications.join(' | ')}`);
  console.log(`Feedback ${label}: ${expected}`);
}

async function assertXP(page, expected) {
  const observed = await page.evaluate(() => {
    const value = selector => Number(document.querySelector(selector).textContent.replace(/\D/g, ''));
    const bar = document.querySelector('#xp-progress');
    return {
      total: value('#xp-current'), next: value('#xp-next'), into: value('#xp-level-current'),
      needed: value('#xp-level-needed'), remaining: value('#xp-remaining'),
      percent: Number.parseFloat(document.querySelector('#bar-xp').style.width),
      role: bar.getAttribute('role'), min: Number(bar.getAttribute('aria-valuemin')),
      max: Number(bar.getAttribute('aria-valuemax')), now: Number(bar.getAttribute('aria-valuenow')),
      label: bar.getAttribute('aria-labelledby'), text: bar.getAttribute('aria-valuetext'),
    };
  });
  assert.equal(observed.total, expected.total, 'XP acumulado');
  assert.equal(observed.next, expected.next, 'limiar acumulado seguinte');
  assert.equal(observed.into, expected.into, 'XP dentro do nível');
  assert.equal(observed.needed, expected.needed, 'XP necessário dentro do nível');
  assert.equal(observed.remaining, expected.needed - expected.into, 'XP que falta');
  assert.equal(observed.percent, expected.percent, 'largura corresponde à fração do nível');
  assert.equal(observed.role, 'progressbar');
  assert.equal(observed.label, 'xp-progress-label');
  assert.equal(observed.min, 0);
  assert.equal(observed.max, expected.needed);
  assert.equal(observed.now, expected.into);
  const text = `${expected.into.toLocaleString('pt-BR')} de ${expected.needed.toLocaleString('pt-BR')} XP neste nível; ${expected.percent.toLocaleString('pt-BR')}% concluído; faltam ${(expected.needed - expected.into).toLocaleString('pt-BR')} XP para o próximo nível`;
  assert.equal(observed.text, text, 'leitura acessível acompanha a barra');
  const state = await page.evaluate(() => fetch('/api/state', {headers: {'X-Pet-Request': '1'}}).then(r => r.json()).then(r => r.state));
  assert.deepEqual([state.xp, state.progress.nextThreshold, state.progress.intoLevel, state.progress.neededInLevel, state.progress.percent],
    [expected.total, expected.next, expected.into, expected.needed, expected.percent], 'interface usa o estado do motor');
}

(async () => {
  browser = await puppeteer.launch({executablePath: chrome, headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']});

  await withPage(null, async page => {
    // Persist real mood and specialization memories, then check the labels in
    // both views without changing or migrating their stored event codes.
    await page.click('[data-action="PLAY"]');
    await page.waitForFunction(() => document.querySelector('#habitat-mood').textContent === 'Empolgado' && document.querySelector('[data-action="PLAY"]').getAttribute('aria-disabled') !== 'true');
    for (let count = 1; count <= 3; count++) {
      await page.click('[data-action="LEARN"]');
      await page.waitForFunction(count => state.specializationScores.RESEARCHER === count && document.querySelector('[data-action="LEARN"]').getAttribute('aria-disabled') !== 'true', {}, count);
    }
    const stored = (await page.evaluate(() => api('/api/memories'))).memories;
    assert.ok(stored.some(item => item.kind === 'MOOD' && item.body === 'O humor do SL-001 agora é EXCITED.'));
    assert.ok(stored.some(item => item.kind === 'MOOD' && item.body === 'O humor do SL-001 agora é FOCUSED.'));
    assert.ok(stored.some(item => item.kind === 'EVOLUTION' && item.body === 'A tendência RESEARCHER se destacou nas atividades locais.'));
    assert.equal(await page.$eval('#specialization-name', el => el.textContent), 'Pesquisador');
    for (const [view, selector] of [['diary','#diary-list'], ['memory','#memory-list']]) {
      await page.click(`[data-view="${view}"]`);
      const bodies = await page.$$eval(`${selector} .entry p`, nodes => nodes.map(node => node.textContent));
      console.log(`${view} · registros exibidos: ${bodies.filter(body => body.includes('humor do SL-001') || body.includes('tendência')).join(' | ')}`);
      assert.ok(bodies.includes('O humor do SL-001 agora é empolgado.'), 'humor antigo usa o mesmo rótulo português do habitat');
      assert.ok(bodies.includes('O humor do SL-001 agora é concentrado.'), 'humor atual usa o mesmo rótulo português do habitat');
      assert.ok(bodies.includes('A tendência pesquisador se destacou nas atividades locais.'), 'tendência usa o mesmo rótulo português da jornada');
      await screenshot(page, view === 'diary' ? '13-diario-rotulos.png' : '14-memorias-rotulos.png', false);
    }
    // Exercise every built-in label and preserve unknown templates/codes.
    const rendered = await page.evaluate(() => {
      const moodCodes = ['CALM','HAPPY','CURIOUS','EXCITED','TIRED','FOCUSED','BORED','PROUD','RESTING'];
      const specialtyCodes = ['EXPLORER','CREATOR','RESEARCHER','ORGANIZER','COMPANION'];
      return {
        moods:moodCodes.map(code => displayMemoryBody({kind:'MOOD', body:`O humor do SL-001 agora é ${code}.`})),
        specialties:specialtyCodes.map(code => displayMemoryBody({kind:'EVOLUTION', body:`A tendência ${code} se destacou nas atividades locais.`})),
        unknown:displayMemoryBody({kind:'MOOD', body:'O humor do SL-001 agora é FUTURE.'}),
        otherKind:displayMemoryBody({kind:'ACTIVITY', body:'O humor do SL-001 agora é EXCITED.'}),
        custom:entryHtml({kind:'MOOD', title:'Exemplo', body:'Texto genérico EXCITED & <teste>', createdAt:'2026-10-28T12:00:00Z'}),
      };
    });
    assert.deepEqual(rendered.moods, ['tranquilo','feliz','curioso','empolgado','cansado','concentrado','entediado','orgulhoso','descansando'].map(label => `O humor do SL-001 agora é ${label}.`));
    assert.deepEqual(rendered.specialties, ['explorador','criador','pesquisador','organizador','companheiro'].map(label => `A tendência ${label} se destacou nas atividades locais.`));
    assert.equal(rendered.unknown, 'O humor do SL-001 agora é FUTURE.');
    assert.equal(rendered.otherKind, 'O humor do SL-001 agora é EXCITED.');
    assert.ok(rendered.custom.includes('Texto genérico EXCITED &amp; &lt;teste&gt;'));
    await page.reload({waitUntil:'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#level').textContent === '01' && document.querySelector('#xp-current').textContent === '29');
    await page.click('[data-view="memory"]');
    const afterReload = await page.$eval('#memory-list', el => el.textContent);
    assert.ok(afterReload.includes('O humor do SL-001 agora é empolgado.'));
    assert.ok(afterReload.includes('A tendência pesquisador se destacou nas atividades locais.'));
    console.log('OK · Diário e Memórias apresentam rótulos locais, preservam os códigos no banco e persistem após recarga.');
  });
  if (process.env.MEMORY_LABELS_ONLY === '1') {
    assert.deepEqual(errors, [], 'nenhum erro de console ou de página');
    assert.deepEqual(external, [], 'nenhuma solicitação externa');
    return;
  }

  await withPage(null, async page => {
    assert.equal(await page.$eval('#level', el => el.textContent), '01');
    assert.equal(await page.$eval('#stage-name', el => el.textContent), 'Despertar');
    assert.equal(await page.$eval('#media-placeholder', el => !el.hidden), true, 'sem mídia aprovada há placeholder');
    assert.equal(await page.$eval('#pet-video', el => el.hidden), true);
    assert.deepEqual(await page.$$eval('.action-card strong', nodes => nodes.map(n => n.textContent)),
      ['Brincar', 'Descansar', 'Explorar', 'Aprender', 'Criar', 'Conversar']);
    assert.deepEqual(await page.evaluate(() => ['happiness', 'energy', 'bond'].map(key => document.querySelector(`#${key}-value`).textContent)), ['75', '80', '20']);
    assert.equal(await page.$eval('#habitat-mood', el => el.textContent), 'Tranquilo');
    await assertXP(page, {total: 0, next: 100, into: 0, needed: 100, percent: 0});
    await traceState(page, 'Inicial', [75, 80, 50, 10, 20, 50], 'Tranquilo', 0);
    await screenshot(page, '01-visao-inicial.png');
    await page.evaluate(() => document.activeElement.blur());
    await tabTo(page, '[data-go="evolution"]');
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => document.activeElement === document.querySelector('#view-evolution h1')), true, 'atalho por teclado move foco para a jornada');
    assert.equal(await page.$eval('[data-view="evolution"]', el => el.getAttribute('aria-current')), 'page');
    assert.equal(await page.$eval('#journey-stage', el => el.textContent), 'Despertar');
    assert.equal(await page.$eval('#journey-level', el => el.textContent), '01');
    assert.equal(await page.$eval('#specialization-name', el => el.textContent), 'Em formação');
    assert.ok((await page.$eval('#award-list', el => el.textContent)).includes('As concessões de XP vão aparecer aqui.'));
    assert.equal(await page.$eval('#load-more-awards', el => el.hidden), true);
    console.log('Jornada vazia: atalho por teclado → título; nível 01, Despertar, Em formação, histórico vazio e sem Mostrar mais.');
    await tabTo(page, '[data-view="home"]', true);
    await page.keyboard.press('Enter');
    assert.equal(await page.$eval('#view-home', el => !el.hidden), true);
    await tabTo(page, '[data-go="diary"]');
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => document.activeElement === document.querySelector('#view-diary h1')), true, 'atalho ao diário também não deixa foco no controle oculto');
    await tabTo(page, '[data-view="home"]', true);
    await page.keyboard.press('Enter');
    assert.equal(await page.$eval('#view-home', el => !el.hidden), true);
    await page.click('[data-open="stats"]');
    assert.deepEqual(await page.$$eval('#all-stats .detail-stat strong', nodes => nodes.map(n => n.textContent)), ['75', '80', '50', '10', '20', '50']);
    await page.click('#dialog-stats [data-close]');
    await tabTo(page, '[data-action="PLAY"]');
    let playRequests = 0;
    const countPlay = req => { if (new URL(req.url()).pathname === '/api/actions' && req.method() === 'POST') playRequests++; };
    page.on('request', countPlay);
    const delayedPlay = await holdOneResponse(page, '*/api/actions');
    await page.keyboard.press('Enter');
    const playResponse = await delayedPlay.paused.catch(async error => {
      const diagnostic = await page.evaluate(() => ({focus:document.activeElement.outerHTML.slice(0,200), busy:document.querySelector('[data-action="PLAY"]').getAttribute('aria-disabled'), view:document.querySelector('.view:not([hidden])')?.id}));
      throw new Error(`${error.message}; estado=${JSON.stringify(diagnostic)}; pedidos=${playRequests}`);
    });
    assert.equal(await page.evaluate(() => document.activeElement.matches('[data-action="PLAY"]')), true, 'Brincar mantém foco durante a ação');
    assert.equal(await page.$eval('[data-action="PLAY"]', el => el.getAttribute('aria-disabled')), 'true');
    await page.keyboard.press('Enter');
    assert.equal(playRequests, 1, 'Brincar não duplica o pedido enquanto ocupado');
    await delayedPlay.release(playResponse);
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '5' && document.querySelector('[data-action="PLAY"]').getAttribute('aria-disabled') !== 'true');
    assert.equal(playRequests, 1);
    assert.equal(await page.evaluate(() => document.activeElement.matches('[data-action="PLAY"]')), true, 'Brincar mantém foco após concluir');
    page.off('request', countPlay);
    assert.deepEqual(await page.evaluate(() => ['happiness', 'energy', 'bond'].map(key => document.querySelector(`#${key}-value`).textContent)), ['83', '70', '23']);
    assert.equal(await page.$eval('#habitat-mood', el => el.textContent), 'Empolgado');
    await assertXP(page, {total: 5, next: 100, into: 5, needed: 100, percent: 5});
    await traceState(page, 'Brincar', [83, 70, 50, 10, 23, 51], 'Empolgado', 5);
    await traceFeedback(page, 'Brincar', 'Um momento de brincadeira deixou o habitat mais alegre. +5 XP.');
    await screenshot(page, '02-apos-brincar.png');
    await page.waitForFunction(() => document.querySelector('[data-action="PLAY"]').getAttribute('aria-disabled') !== 'true' && document.querySelectorAll('#award-list .award-row').length === 1);
    await page.click('[data-go="evolution"]');
    assert.equal(await page.evaluate(() => document.activeElement === document.querySelector('#view-evolution h1')), true);
    const firstGrant = await page.$eval('#award-list .award-row', el => ({label:el.querySelector('span').childNodes[0].textContent, day:el.querySelector('small').textContent, amount:el.querySelector('strong').textContent}));
    assert.equal(firstGrant.label, 'Primeira interação do dia');
    assert.equal(firstGrant.amount, '+5 XP');
    assert.equal(await page.$eval('#load-more-awards', el => el.hidden), true);
    console.log(`Jornada com registro após Brincar: ${firstGrant.label} / ${firstGrant.day} / ${firstGrant.amount}; Mostrar mais oculto.`);
    await page.click('[data-view="home"]');
    await page.click('[data-open="stats"]');
    assert.deepEqual(await page.$$eval('#all-stats .detail-stat strong', nodes => nodes.map(n => n.textContent)), ['83', '70', '50', '10', '23', '51']);
    await page.click('#dialog-stats [data-close]');
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '5');
    await assertXP(page, {total: 5, next: 100, into: 5, needed: 100, percent: 5});
    // Verify the remaining UI actions with Tab/Enter and the default rules.
    await tabTo(page, '[data-action="REST"]');
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('#energy-value').textContent === '90' && document.querySelector('[data-action="REST"]').getAttribute('aria-disabled') !== 'true');
    assert.equal(await page.evaluate(() => document.activeElement.matches('[data-action="REST"]')), true);
    assert.equal(await page.$eval('#habitat-mood', el => el.textContent), 'Descansando');
    await traceState(page, 'Descansar', [83, 90, 50, 10, 23, 51], 'Descansando', 5);
    await traceFeedback(page, 'Descansar', 'SL-001 descansou e recuperou energia.');
    await tabTo(page, '[data-action="EXPLORE"]');
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('#energy-value').textContent === '82' && document.querySelector('[data-action="EXPLORE"]').getAttribute('aria-disabled') !== 'true');
    assert.equal(await page.evaluate(() => document.activeElement.matches('[data-action="EXPLORE"]')), true);
    assert.equal(await page.$eval('#happiness-value', el => el.textContent), '85');
    assert.equal(await page.$eval('#habitat-mood', el => el.textContent), 'Curioso');
    await traceState(page, 'Explorar', [85, 82, 55, 10, 23, 51], 'Curioso', 5);
    await traceFeedback(page, 'Explorar', 'Descoberta local: Jardins de luz. Uma coleção local de ideias sobre brilho, folhas e sombras.');
    await tabTo(page, '[data-action="LEARN"]');
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '13' && document.querySelector('[data-action="LEARN"]').getAttribute('aria-disabled') !== 'true');
    assert.equal(await page.evaluate(() => document.activeElement.matches('[data-action="LEARN"]')), true);
    assert.equal(await page.$eval('#energy-value', el => el.textContent), '75');
    await traceState(page, 'Aprender', [85, 75, 57, 14, 23, 51], 'Concentrado', 13);
    await traceFeedback(page, 'Aprender', 'Aprendizado local — Luz do Sol: A luz do Sol leva cerca de oito minutos para chegar à Terra. +8 XP.');
    await tabTo(page, '[data-action="CREATE"]');
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '21' && document.querySelector('[data-action="CREATE"]').getAttribute('aria-disabled') !== 'true');
    assert.equal(await page.evaluate(() => document.activeElement.matches('[data-action="CREATE"]')), true);
    assert.equal(await page.$eval('#energy-value', el => el.textContent), '68');
    assert.equal(await page.$eval('#happiness-value', el => el.textContent), '88');
    await traceState(page, 'Criar', [88, 68, 59, 14, 23, 51], 'Concentrado', 21);
    await traceFeedback(page, 'Criar', 'Ideia local: um jardim lilás iluminado por estrelas de papel. +8 XP.');
    await tabTo(page, '[data-open="chat"]');
    await page.keyboard.press('Enter');
    await page.type('#chat-input', 'Uma mensagem de teste com mais de trinta caracteres.');
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement.matches('#chat-form button[type="submit"]')), true);
    let chatRequests = 0;
    const countChat = req => { if (new URL(req.url()).pathname === '/api/actions' && req.method() === 'POST') chatRequests++; };
    page.on('request', countChat);
    const delayedChat = await holdOneResponse(page, '*/api/actions');
    await page.keyboard.press('Enter');
    const chatResponse = await delayedChat.paused;
    assert.equal(await page.evaluate(() => document.activeElement.matches('#chat-form button[type="submit"]')), true, 'envio de conversa mantém foco no diálogo');
    assert.equal(await page.$eval('#chat-form button[type="submit"]', el => el.getAttribute('aria-disabled')), 'true');
    await page.keyboard.press('Enter');
    assert.equal(chatRequests, 1, 'conversa não envia duas vezes enquanto ocupada');
    await delayedChat.release(chatResponse);
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '23' && document.querySelector('#chat-form button[type="submit"]').getAttribute('aria-disabled') !== 'true');
    assert.equal(chatRequests, 1);
    assert.equal(await page.evaluate(() => document.activeElement.matches('#chat-form button[type="submit"]')), true);
    page.off('request', countChat);
    assert.equal(await page.$$eval('#chat-output .chat-bubble', nodes => nodes.length), 3);
    await traceState(page, 'Conversar (significativa)', [90, 68, 59, 14, 25, 52], 'Concentrado', 23);
    await traceFeedback(page, 'Conversar', 'Momento registrado. +2 XP.');
    const reply = await page.$eval('#chat-output .chat-bubble:last-child', el => el.textContent);
    assert.equal(reply, 'Estou concentrado e tenho 68 de energia. Obrigado por este momento! Esta é uma resposta local pré-definida.');
    console.log(`Resposta da conversa: ${reply}`);
    await screenshot(page, '10-conversa-local.png', false);
    await page.click('#dialog-chat [data-close]');
    await page.click('[data-open="stats"]');
    assert.deepEqual(await page.$$eval('#all-stats .detail-stat strong', nodes => nodes.map(n => n.textContent)), ['90', '68', '59', '14', '25', '52']);
    await screenshot(page, '05-atributos-apos-acoes.png', false);
    await page.click('#dialog-stats [data-close]');
    await assertXP(page, {total: 23, next: 100, into: 23, needed: 100, percent: 23});
    for (const view of ['evolution', 'diary', 'memory', 'home']) {
      await page.click(`.nav-item[data-view="${view}"]`);
      assert.equal(await page.$eval(`#view-${view}`, el => !el.hidden), true, `navegação para ${view}`);
      assert.equal(await page.$eval(`.nav-item[data-view="${view}"]`, el => el.getAttribute('aria-current')), 'page');
      assert.equal(await page.$$eval('.view:not([hidden])', nodes => nodes.length), 1);
      if (view === 'evolution') {
        const list = await page.$eval('#award-list', el => el.textContent);
        for (const label of ['Primeira interação do dia', 'Atividade de aprendizado', 'Atividade criativa', 'Conversa significativa']) assert.ok(list.includes(label));
      }
      if (view === 'diary') {
        assert.ok((await page.$eval('#diary-list', el => el.textContent)).includes('Aprendizado do dia'));
        await screenshot(page, '06-diario-local.png', false);
      }
      if (view === 'memory') {
        const privacy = await page.$eval('#view-memory .privacy-banner', el => el.textContent);
        assert.ok(privacy.includes('registros genéricos ficam no banco local'));
        assert.equal(privacy.includes('preview'), false, 'a interface não oferece preview remoto');
        assert.ok(Number(await page.$eval('#memory-count', el => el.textContent)) > 0);
        assert.ok(await page.$$eval('#memory-list [data-delete-memory]', nodes => nodes.length) > 0);
        await screenshot(page, '07-memorias-locais.png', false);
      }
    }
    console.log('Navegação: Minha jornada → Diário → Memórias → Meu slime; históricos e registros presentes.');
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '23');
    await assertXP(page, {total: 23, next: 100, into: 23, needed: 100, percent: 23});
    await traceState(page, 'Após recarga', [90, 68, 59, 14, 25, 52], 'Concentrado', 23);
    const persistedStats = await page.evaluate(() => fetch('/api/state', {headers: {'X-Pet-Request': '1'}}).then(r => r.json()).then(({state}) =>
      ['happiness', 'energy', 'curiosity', 'knowledge', 'bond', 'trust'].map(key => Math.round(state[key]))));
    assert.deepEqual(persistedStats, [90, 68, 59, 14, 25, 52], 'atributos recarregados correspondem ao estado persistido');
    await page.click('[data-open="stats"]');
    assert.deepEqual(await page.$$eval('#all-stats .detail-stat strong', nodes => nodes.map(n => n.textContent)), ['90', '68', '59', '14', '25', '52']);
    await page.click('#dialog-stats [data-close]');
    await page.setViewport({width: 390, height: 844, deviceScaleFactor: 1});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'sem overflow no celular');
    console.log('OK · seis ações, seis atributos, navegação entre quatro telas e persistência após recarga.');
    console.log('OK · Tab/Enter nas ações e na conversa: foco mantido; Brincar e envio não duplicam durante a resposta atrasada.');
  });

  await withPage(null, async (page, context, entry) => {
    // An isolated browser conversation, followed by distinct login sessions
    // and an actual new server process using the SAME disposable SQLite file.
    const marker = 'PRIVATE_SESSION_TEST_MESSAGE_DO_NOT_STORE';
    const bodies = [];
    page.on('request', req => {
      if (req.method() === 'POST' && new URL(req.url()).pathname === '/api/actions') bodies.push(req.postData());
    });
    const initial = await sharedState(page);
    assert.deepEqual(summaryState(initial), {xp:0, level:1, stage:'Despertar', mood:'CALM', attributes:[75,80,50,10,20,50], specialty:null});
    await page.click('[data-open="chat"]');
    await submitChat(page, 'Oi!');
    const afterShort = await sharedState(page);
    assert.deepEqual(summaryState(afterShort), {xp:5, level:1, stage:'Despertar', mood:'CALM', attributes:[77,80,50,10,22,51], specialty:null});
    await submitChat(page, marker);
    assert.equal(bodies.length, 2);
    const chatPayloads = bodies.map(body => JSON.parse(body));
    assert.deepEqual(chatPayloads.map(item => item.meaningful), [false, true]);
    for (const payload of chatPayloads) {
      assert.deepEqual(Object.keys(payload).sort(), ['action','eventId','meaningful']);
      assert.equal(payload.action, 'CHAT');
    }
    assert.equal(bodies.some(body => body.includes(marker)), false, 'conteúdo não vai para o servidor');
    const replies = await page.$$eval('#chat-output .chat-bubble:not(.user)', nodes => nodes.map(node => node.textContent));
    assert.equal(replies.length, 3);
    assert.equal(replies[1], replies[2], 'resposta é um modelo local para o mesmo humor/energia');
    assert.ok(replies[2].includes('Estou tranquilo e tenho 80 de energia'));
    assert.ok(await page.$eval('#chat-output', (el, value) => el.textContent.includes(value), marker));
    await page.click('#dialog-chat [data-close]');
    await page.waitForFunction(() => !document.querySelector('#dialog-chat').open && document.querySelectorAll('#chat-output .chat-bubble').length === 1);
    await page.click('[data-open="chat"]');
    assert.equal(await page.$eval('#chat-input', el => el.value), '');
    assert.equal(await page.$eval('#chat-output', (el, value) => el.textContent.includes(value), marker), false, 'conteúdo não retorna ao reabrir');
    await page.click('#dialog-chat [data-close]');
    const afterChat = await sharedState(page);
    assert.deepEqual(summaryState(afterChat), {xp:7, level:1, stage:'Despertar', mood:'CALM', attributes:[79,80,50,10,24,52], specialty:null});
    console.log('Conversa local · inicial:', JSON.stringify(summaryState(initial)));
    console.log('Conversa local · após curta:', JSON.stringify(summaryState(afterShort)));
    console.log('Conversa local · após curta e significativa:', JSON.stringify(summaryState(afterChat)));
    await page.click('[data-view="evolution"]');
    assert.equal(await page.$eval('#journey-level', el => el.textContent), '01');
    const awardText = await page.$eval('#award-list', el => el.textContent);
    assert.ok(awardText.includes('Primeira interação do dia') && awardText.includes('Conversa significativa'));
    await page.click('[data-view="diary"]');
    assert.ok((await page.$eval('#diary-list', el => el.textContent)).includes('Um momento juntos'));
    await page.click('[data-view="memory"]');
    const memoryText = await page.$eval('#memory-list', el => el.textContent);
    assert.ok(memoryText.includes('Um momento juntos'));
    assert.equal(memoryText.includes(marker), false);
    const returnedRecords = await page.evaluate(async () => ({memories:await api('/api/memories?limit=500'), awards:await api('/api/awards?limit=500'), events:await api('/api/ui/events?limit=500')}));
    assert.equal(JSON.stringify(returnedRecords).includes(marker), false, 'texto não aparece nas memórias, XP ou eventos');
    await page.click('[data-view="home"]');
    await page.click('[data-action="PLAY"]');
    await page.waitForFunction(() => document.querySelector('[data-action="PLAY"]').getAttribute('aria-disabled') !== 'true' && document.querySelector('#happiness-value').textContent === '87');
    let beforeNewSession = await sharedState(page);
    assert.deepEqual(summaryState(beforeNewSession), {xp:7, level:1, stage:'Despertar', mood:'EXCITED', attributes:[87,70,50,10,27,53], specialty:'COMPANION'});
    assert.equal(beforeNewSession.recentSignal.type, 'EXCITED');
    console.log('Após Brincar, antes da nova sessão:', JSON.stringify(summaryState(beforeNewSession)));

    await page.click('[data-open="settings"]');
    await page.waitForSelector('#dialog-settings[open]');
    await Promise.all([page.waitForNavigation({waitUntil:'networkidle0'}), page.click('#owner-logout')]);
    await loginPage(page, entry.ownerToken);
    const afterLogin = await sharedState(page);
    assertContinuous(beforeNewSession, afterLogin);
    console.log('Após bloquear e entrar novamente:', JSON.stringify(summaryState(afterLogin)));

    const otherContext = await browser.createBrowserContext();
    try {
      const other = await otherContext.newPage();
      other.on('pageerror', error => errors.push(error.message));
      other.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
      other.on('request', req => { const url = new URL(req.url()); if (['http:','https:'].includes(url.protocol) && url.hostname !== '127.0.0.1') external.push(req.url()); });
      await other.goto(`http://127.0.0.1:${entry.port}/`, {waitUntil:'networkidle0'});
      await loginPage(other, entry.ownerToken);
      assertContinuous(beforeNewSession, await sharedState(other));
      await other.click('[data-open="chat"]');
      await submitChat(other, 'Oi de novo!');
      await other.click('#dialog-chat [data-close]');
      const fromOtherSession = await sharedState(other);
      assert.deepEqual(summaryState(fromOtherSession), {xp:7, level:1, stage:'Despertar', mood:'EXCITED', attributes:[89,70,50,10,29,54], specialty:'COMPANION'});
      // A separate tab is not a globally versioned snapshot: explicitly refresh
      // the first one before comparing it with the other session's new write.
      beforeNewSession = await sharedState(page);
      assertContinuous(fromOtherSession, beforeNewSession);
    } finally { await otherContext.close(); }
    console.log('Outra sessão e atualização da primeira:', JSON.stringify(summaryState(beforeNewSession)));
    console.log('OK · outra sessão lê o mesmo banco; uma nova conversa aparece na primeira após atualização.');

    let restarted = null;
    try {
      await closeServer(entry, {preserveData:true});
      for (const suffix of ['', '-wal', '-shm']) {
        const file = path.join(entry.directory, `pet.sqlite3${suffix}`);
        if (fs.existsSync(file)) assert.equal(fs.readFileSync(file).includes(Buffer.from(marker)), false, 'conteúdo de teste ausente do SQLite');
      }
      restarted = await serverFor(null, entry.directory);
      assert.notEqual(restarted.ownerToken, entry.ownerToken, 'nova execução gera outra credencial');
      await page.goto(`http://127.0.0.1:${restarted.port}/`, {waitUntil:'networkidle0'});
      await page.waitForSelector('#dialog-login[open]');
      await loginPage(page, restarted.ownerToken);
      const afterRestart = await sharedState(page);
      assertContinuous(beforeNewSession, afterRestart);
      assert.equal(await page.$$eval('#chat-output .chat-bubble', nodes => nodes.length), 1);
      await page.click('[data-view="memory"]');
      assert.ok((await page.$eval('#memory-list', el => el.textContent)).includes('Um momento juntos'));
      assert.equal((await page.$eval('#memory-list', el => el.textContent)).includes(marker), false);
      console.log('Após novo processo e nova sessão:', JSON.stringify(summaryState(afterRestart)));
      console.log('OK · SQLite preserva estado e registros genéricos; a UI limpa a conversa e o marcador não consta nas requisições nem no banco inspecionado.');
    } finally {
      if (restarted) await closeServer(restarted);
      else fs.rmSync(entry.directory, {recursive:true, force:true});
    }
  });

  await withPage(null, async page => {
    // Manual local activities are available even when scheduled autonomy is off.
    await page.click('[data-view="diary"]');
    assert.equal(await page.$eval('#autonomy-status', el => el.textContent), 'Autonomia desativada');
    const steps = [
      {activity:'DREAM', title:'Um sonho tranquilo', energy:78, xp:0},
      {activity:'EXPLORE', title:'Descoberta local', energy:73, xp:0},
      {activity:'EXPERIMENT', title:'Experimento criativo', energy:68, xp:8},
      {activity:'JOURNAL', title:'Página do diário', energy:66, xp:8},
    ];
    for (const [index, step] of steps.entries()) {
      await page.click(`[data-auto="${step.activity}"]`);
      await page.waitForFunction((activity, energy, xp, count) => !document.querySelector(`[data-auto="${activity}"]`).disabled &&
        Number(document.querySelector('#energy-value').textContent) === energy &&
        Number(document.querySelector('#xp-current').textContent) === xp &&
        document.querySelectorAll('#autonomy-history .history-row').length >= count, {}, step.activity, step.energy, step.xp, index + 1);
      assert.ok((await page.$eval('#diary-list', el => el.textContent)).includes(step.title));
      console.log(`Diário manual ${step.activity}: ${step.title}; energia ${step.energy}; XP ${step.xp}; execução registrada.`);
    }
    assert.equal(await page.$eval('#autonomy-status', el => el.textContent), 'Autonomia desativada');
    await page.reload({waitUntil:'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#energy-value').textContent === '66' && document.querySelector('#xp-current').textContent === '8');
    await page.click('[data-view="diary"]');
    assert.equal(await page.$$eval('#autonomy-history .history-row', nodes => nodes.length), 4);
    console.log('OK · quatro atividades manuais locais persistem; agendamento continua desativado.');
  });

  await withPage(null, async (page, context, entry) => {
    await page.click('[data-view="evolution"]');
    await page.evaluate(() => {
      window.__visibilityTransitions = [];
      document.addEventListener('visibilitychange', () => window.__visibilityTransitions.push(document.visibilityState));
    });
    const client = await page.createCDPSession();
    const {windowId} = await client.send('Browser.getWindowForTarget');
    // In headless Chromium, minimizing/restoring the test window triggers real
    // document.hidden/visibilitychange events; this is not a physical device.
    await client.send('Browser.setWindowBounds', {windowId, bounds:{windowState:'minimized'}});
    await page.waitForFunction(() => document.hidden, {polling:50});
    const other = await context.newPage();
    try {
      other.on('pageerror', error => errors.push(error.message));
      other.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
      other.on('request', req => { const url = new URL(req.url()); if (['http:','https:'].includes(url.protocol) && url.hostname !== '127.0.0.1') external.push(req.url()); });
      await other.goto(`http://127.0.0.1:${entry.port}/`, {waitUntil:'networkidle0'});
      await other.waitForFunction(() => authenticated && state && !document.querySelector('#dialog-login').open);
      await other.click('[data-action="PLAY"]');
      await other.waitForFunction(() => document.querySelector('#xp-current').textContent === '5' && document.querySelector('[data-action="PLAY"]').getAttribute('aria-disabled') !== 'true');
      assert.equal(await page.$eval('#xp-current', el => el.textContent), '0', 'outra sessão não atualiza instantaneamente a página oculta');
      const refreshed = page.waitForResponse(response => response.url().endsWith('/api/state') && response.request().method() === 'GET');
      await client.send('Browser.setWindowBounds', {windowId, bounds:{windowState:'normal'}});
      await refreshed;
      await page.waitForFunction(() => !document.hidden && document.querySelector('#xp-current').textContent === '5' && document.querySelector('#award-list').textContent.includes('Primeira interação do dia'), {polling:50});
      assert.equal(await page.$eval('#view-evolution', el => !el.hidden), true, 'retorno preserva a tela aberta');
      assert.equal(await page.$eval('#journey-level', el => el.textContent), '01');
      assert.deepEqual(await page.evaluate(() => window.__visibilityTransitions), ['hidden','visible']);
      await screenshot(page, '12-retorno-visibilidade.png', false);
      console.log('Retorno de visibilidade: hidden→visible; outra página Brincar; XP 0→5 e histórico atualizados automaticamente, jornada mantida.');
    } finally {
      await other.close();
      await client.detach();
    }
  });

  await withPage(null, async page => {
    await page.evaluate(() => document.activeElement.blur());
    await tabTo(page, '[data-action="PLAY"]');
    const delayed = await holdOneResponse(page, '*/api/actions');
    await page.keyboard.press('Enter');
    const response = await delayed.paused;
    await tabTo(page, '[data-action="REST"]');
    await delayed.release(response);
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '5' && document.querySelector('[data-action="PLAY"]').getAttribute('aria-disabled') !== 'true');
    assert.equal(await page.evaluate(() => document.activeElement.matches('[data-action="REST"]')), true, 'ação concluída não rouba o foco já movido');
    assert.equal(await page.$eval('#energy-value', el => el.textContent), '70');
    console.log('OK · ação concluída não rouba o foco movido durante a resposta.');
  });

  await withPage('level1-edge', async page => {
    assert.equal(await page.$eval('#level', el => el.textContent), '01');
    await assertXP(page, {total: 98, next: 100, into: 98, needed: 100, percent: 98});
    // Seed ended on the previous local day. This chat earns the first daily
    // interaction (5) and a meaningful conversation (2), crossing the level.
    await page.click('[data-open="chat"]');
    await page.type('#chat-input', 'Outra mensagem de teste com mais de trinta caracteres.');
    await page.click('#chat-form button[type="submit"]');
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '105' && document.querySelector('#chat-form button[type="submit"]').getAttribute('aria-disabled') !== 'true');
    await page.waitForFunction(() => [...document.querySelectorAll('#toast-region .toast')].some(el => el.textContent.includes('Novo nível: 2')));
    await page.click('#dialog-chat [data-close]');
    assert.equal(await page.$eval('#level', el => el.textContent), '02');
    await assertXP(page, {total: 105, next: 283, into: 5, needed: 183, percent: 2.7});
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '105');
    await assertXP(page, {total: 105, next: 283, into: 5, needed: 183, percent: 2.7});
    console.log('OK · transição real na UI: conversa local passa de 98 a 105 XP e atualiza para nível 2; recarga preserva 5/183.');
  });

  await withPage('level2', async page => {
    assert.equal(await page.$eval('#level', el => el.textContent), '02');
    await assertXP(page, {total: 100, next: 283, into: 0, needed: 183, percent: 0});
    await page.click('[data-action="LEARN"]');
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '113');
    await assertXP(page, {total: 113, next: 283, into: 13, needed: 183, percent: 7.1});
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '113');
    await assertXP(page, {total: 113, next: 283, into: 13, needed: 183, percent: 7.1});
    console.log('OK · nível 2: 100 XP = 0/183; após aprender e recarregar, 113 XP = 13/183 (7,1%).');
  });

  await withPage('level2-mid', async page => {
    await assertXP(page, {total: 150, next: 283, into: 50, needed: 183, percent: 27.3});
    assert.equal(await page.$eval('#stage-name', el => el.textContent), 'Despertar');
    assert.equal(await page.$eval('#media-placeholder', el => !el.hidden), true);
    await screenshot(page, '03-nivel2-150xp.png');
    console.log('OK · nível 2: 150 XP acumulados = 50/183 no nível (27,3%); faltam 133 XP.');
  });

  await withPage('rounding-edge', async page => {
    assert.equal(await page.$eval('#level', el => el.textContent), '03');
    // Configured, simulated-day fixture: 1 XP remains in a wide level.
    await assertXP(page, {total: 5195, next: 5196, into: 2367, needed: 2368, percent: 99.9});
    await page.click('[data-action="LEARN"]');
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent.replace(/\D/g, '') === '5295');
    assert.equal(await page.$eval('#level', el => el.textContent), '04');
    await assertXP(page, {total: 5295, next: 8000, into: 99, needed: 2804, percent: 3.5});
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent.replace(/\D/g, '') === '5295');
    await assertXP(page, {total: 5295, next: 8000, into: 99, needed: 2804, percent: 3.5});
    console.log('OK · arredondamento: falta 1 XP e a barra mostra 99,9%, não 100%; nível seguinte persiste após recarga.');
  });

  {
    // A milestone committed after the opening cursor was captured but before
    // the first snapshot must still be announced, not skipped as old history.
    const entry = await serverFor('level1-edge');
    const context = await browser.createBrowserContext();
    try {
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
      page.on('request', req => { const url = new URL(req.url()); if (['http:','https:'].includes(url.protocol) && url.hostname !== '127.0.0.1') external.push(req.url()); });
      await page.goto(`http://127.0.0.1:${entry.port}/`, {waitUntil:'networkidle0'});
      await page.waitForSelector('#dialog-login[open]');
      const gate = await holdOneResponse(page, '*/api/ui/events/cursor');
      await page.type('#owner-token', entry.ownerToken);
      await page.click('#login-form button[type="submit"]');
      await gate.paused;
      const boundary = (await gate.json()).cursor;
      const response = await fetch(`http://127.0.0.1:${entry.port}/api/actions`, {
        method:'POST', headers:{'Content-Type':'application/json', 'Authorization':`Bearer ${entry.ownerToken}`},
        body:JSON.stringify({action:'CHAT', eventId:'cursor-opening-race', meaningful:true}),
      });
      assert.equal(response.status, 200);
      assert.equal((await response.json()).state.xp, 105);
      await gate.release();
      await page.waitForFunction(() => !document.querySelector('#dialog-login').open && document.querySelector('#xp-current').textContent === '105' && document.querySelector('#toast-region').textContent.includes('Novo nível: 2'));
      assert.ok(await page.evaluate(boundary => eventCursor > boundary, boundary));
      console.log('OK · evento novo entre cursor inicial e primeiro estado é anunciado (98→105 XP, nível 2).');
    } finally {
      await context.close();
      await closeServer(entry);
    }
  }

  await withPage('stage5-edge', async (page, context, entry) => {
    const before = await sharedState(page);
    assert.deepEqual([before.xp, before.level, before.stage.key], [797, 4, 'AWAKENING']);
    await page.click('[data-open="chat"]');
    await submitChat(page, 'Mensagem local longa para verificar evolução entre sessões.');
    await page.waitForFunction(() => document.querySelector('#toast-region').textContent.includes('Nova evolução: Descoberta'));
    const reply = await page.$eval('#chat-output .chat-bubble:last-child', el => el.textContent);
    await page.click('#dialog-chat [data-close]');
    const evolved = await sharedState(page);
    assert.deepEqual([evolved.xp, evolved.level, evolved.stage.key], [804, 5, 'DISCOVERY']);
    assert.equal(evolved.bond, before.bond + 2);
    assert.equal(evolved.trust, before.trust + 1);
    assert.equal(evolved.mood, 'TIRED');
    assert.ok(reply.includes(`Estou cansado e tenho ${Math.round(evolved.energy)} de energia.`), 'resposta usa humor e energia retornados pelo motor');
    await page.click('[data-view="evolution"]');
    assert.equal(await page.$eval('#stage-timeline .current strong', el => el.textContent), 'Descoberta');
    console.log('Conversa cruza estágio · antes:', JSON.stringify(summaryState(before)));
    console.log('Conversa cruza estágio · depois:', JSON.stringify(summaryState(evolved)));
    let restarted = null;
    try {
      await closeServer(entry, {preserveData:true});
      restarted = await serverFor(null, entry.directory);
      assert.notEqual(restarted.ownerToken, entry.ownerToken);
      await page.goto(`http://127.0.0.1:${restarted.port}/`, {waitUntil:'networkidle0'});
      await page.waitForSelector('#dialog-login[open]');
      await loginPage(page, restarted.ownerToken);
      const restored = await sharedState(page);
      assertContinuous(evolved, restored);
      await page.click('[data-view="evolution"]');
      assert.equal(await page.$eval('#stage-timeline .current strong', el => el.textContent), 'Descoberta');
      assert.ok((await page.$eval('#award-list', el => el.textContent)).includes('Conversa significativa'));
      console.log('Após reiniciar o processo · estágio:', JSON.stringify(summaryState(restored)));
      console.log('OK · conversa 797→804 XP, Descoberta e vínculo persistem em nova sessão com o mesmo banco.');
    } finally {
      if (restarted) await closeServer(restarted);
      else fs.rmSync(entry.directory, {recursive:true, force:true});
    }
  });

  await withPage('stage5-edge', async page => {
    assert.equal(await page.$eval('#level', el => el.textContent), '04');
    assert.equal(await page.$eval('#stage-name', el => el.textContent), 'Despertar');
    await assertXP(page, {total: 797, next: 800, into: 277, needed: 280, percent: 98.9});
    // The fixture ends on a previous day: CREATE earns 5 first-interaction XP
    // plus 8 creative XP, crossing the stage threshold without bridge events.
    await page.click('[data-action="CREATE"]');
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '810' && document.querySelector('[data-action="CREATE"]').getAttribute('aria-disabled') !== 'true');
    await page.waitForFunction(() => document.querySelector('#toast-region').textContent.includes('Nova evolução: Descoberta'));
    assert.equal(await page.$eval('#level', el => el.textContent), '05');
    assert.equal(await page.$eval('#stage-name', el => el.textContent), 'Descoberta');
    assert.equal(await page.$eval('#habitat-card', el => el.dataset.stageIndex), '1');
    await assertXP(page, {total: 810, next: 1118, into: 10, needed: 318, percent: 3.1});
    await page.click('[data-view="evolution"]');
    assert.equal(await page.$eval('#stage-timeline .current strong', el => el.textContent), 'Descoberta');
    await screenshot(page, '09-evolucao-durante-uso.png', false);
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#level').textContent === '05');
    assert.equal(await page.$eval('#view-home', el => !el.hidden), true, 'recarga retorna à tela inicial');
    assert.equal(await page.$eval('#stage-name', el => el.textContent), 'Descoberta');
    await assertXP(page, {total: 810, next: 1118, into: 10, needed: 318, percent: 3.1});
    console.log('OK · Criar cruza 797→810 XP, desbloqueia Descoberta e exibe notificação; estágio persiste após recarga.');
  });

  const laterStages = [
    {target:'level10-edge', level:10, before:'Descoberta', stage:'Aprendizado', index:2, reward:'Emblema de aprendizado'},
    {target:'level20-edge', level:20, before:'Aprendizado', stage:'Companheiro', index:3, reward:'Decoração halo', option:'input[name="decoration"][value="HALO"]'},
    {target:'level35-edge', level:35, before:'Companheiro', stage:'Explorador', index:4, reward:'Ambiente Aurora', option:'input[name="theme"][value="AURORA"]'},
  ];
  for (const step of laterStages) {
    await withPage(step.target, async page => {
      const xp = Number((await page.$eval('#xp-current', el => el.textContent)).replace(/\D/g, ''));
      const threshold = Number((await page.$eval('#xp-next', el => el.textContent)).replace(/\D/g, ''));
      assert.equal(Number(await page.$eval('#level', el => el.textContent)), step.level - 1);
      assert.equal(await page.$eval('#stage-name', el => el.textContent), step.before);
      assert.ok(xp < threshold && threshold - xp <= 13);
      if (step.option) {
        await page.click('[data-open="customize"]');
        assert.equal(await page.$eval(step.option, el => el.disabled), true);
        await page.click('#dialog-customize [data-close]');
      }
      await page.click('[data-action="CREATE"]');
      await page.waitForFunction(expected => Number(document.querySelector('#level').textContent) === expected && document.querySelector('[data-action="CREATE"]').getAttribute('aria-disabled') !== 'true', {}, step.level);
      assert.equal(Number((await page.$eval('#xp-current', el => el.textContent)).replace(/\D/g, '')), xp + 13);
      assert.equal(await page.$eval('#stage-name', el => el.textContent), step.stage);
      assert.equal(await page.$eval('#habitat-card', el => Number(el.dataset.stageIndex)), step.index);
      assert.equal(await page.$eval('#habitat-stage-badge', el => !el.hidden), true);
      assert.ok((await page.$eval('#toast-region', el => el.textContent)).includes(`Nova evolução: ${step.stage}`));
      if (step.option) {
        await page.click('[data-open="customize"]');
        assert.equal(await page.$eval(step.option, el => el.disabled), false, 'recompensa fica disponível no estágio');
        await page.click('#dialog-customize [data-close]');
      }
      await page.click('[data-view="evolution"]');
      assert.equal(await page.$eval('#stage-timeline .current strong', el => el.textContent), step.stage);
      assert.equal(await page.$eval('#stage-timeline .current p', el => el.textContent), step.reward);
      assert.equal(await page.$$eval('#stage-timeline .stage-row.unlocked', nodes => nodes.length), step.index + 1);
      await page.reload({waitUntil:'networkidle0'});
      await page.waitForFunction(expected => Number(document.querySelector('#level').textContent) === expected, {}, step.level);
      assert.equal(await page.$eval('#stage-name', el => el.textContent), step.stage);
      console.log(`Etapa de UI (dias simulados): ${xp}→${xp + 13} XP; ${step.before}→${step.stage}, nível ${step.level}; ${step.reward}; recarga preserva.`);
    });
  }

  await withPage('level50-edge', async page => {
    // 377 simulated days of genuine local actions leave more than 10,000 old
    // events. Opening the pet must not treat the tail of history as new.
    assert.equal(await page.$eval('#level', el => el.textContent), '49');
    assert.equal(await page.$eval('#stage-name', el => el.textContent), 'Explorador');
    const before = Number((await page.$eval('#xp-current', el => el.textContent)).replace(/\D/g, ''));
    assert.ok(before >= 34287 && before < 34300, `XP anterior ao nível 50: ${before}`);
    assert.deepEqual(await page.$$eval('#toast-region .toast', nodes => nodes.map(node => node.textContent)), []);
    await page.click('[data-open="customize"]');
    assert.equal(await page.$eval('input[name="decoration"][value="CONSTELLATION"]', el => el.disabled), true);
    await page.click('#dialog-customize [data-close]');
    await page.click('[data-action="CREATE"]');
    await page.waitForFunction(expected => Number(document.querySelector('#xp-current').textContent.replace(/\D/g, '')) === expected && document.querySelector('[data-action="CREATE"]').getAttribute('aria-disabled') !== 'true', {}, before + 13);
    assert.equal(await page.$eval('#level', el => el.textContent), '50');
    assert.equal(await page.$eval('#stage-name', el => el.textContent), 'Evoluído');
    assert.equal(await page.$eval('#habitat-card', el => el.dataset.stageIndex), '5');
    const notifications = await page.$$eval('#toast-region .toast', nodes => nodes.map(node => node.textContent));
    assert.deepEqual(notifications.filter(text => text.startsWith('Novo nível:')), ['Novo nível: 50! Uma etapa a mais na jornada.'], `níveis antigos não devem ser celebrados de novo: ${notifications.join(' | ')}`);
    assert.ok(notifications.some(text => text.includes('Nova evolução: Evoluído')));
    assert.ok(notifications.some(text => text.includes('+13 XP')));
    console.log(`Histórico longo: ${before}→${before + 13} XP, nível 49→50, Explorador→Evoluído; avisos: ${notifications.join(' | ')}`);
    await page.click('[data-view="evolution"]');
    assert.equal(await page.$eval('#stage-timeline .current strong', el => el.textContent), 'Evoluído');
    assert.deepEqual(await page.$$eval('#stage-timeline .stage-row.unlocked strong', nodes => nodes.map(el => el.textContent)), ['Despertar','Descoberta','Aprendizado','Companheiro','Explorador','Evoluído']);
    await screenshot(page, '11-estagio-evoluido.png', false);
    await page.click('[data-view="home"]');
    await page.click('[data-open="customize"]');
    assert.equal(await page.$eval('input[name="decoration"][value="CONSTELLATION"]', el => el.disabled), false);
    await page.click('input[name="decoration"][value="CONSTELLATION"] + span');
    await page.click('#customize-form button[type="submit"]');
    await page.waitForFunction(() => !document.querySelector('#dialog-customize').open && document.querySelector('#habitat-card').dataset.decoration === 'CONSTELLATION');
    await page.reload({waitUntil:'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#level').textContent === '50' && document.querySelector('#habitat-card').dataset.decoration === 'CONSTELLATION');
    assert.equal(await page.$eval('#stage-name', el => el.textContent), 'Evoluído');
    assert.deepEqual(await page.$$eval('#toast-region .toast', nodes => nodes.map(node => node.textContent)), [], 'eventos anteriores não reaparecem na abertura');
    console.log('OK · seis estágios desbloqueados; Constelação aplicada e persistida; nenhum nível antigo reanunciado.');
  });

  await withPage('stage5', async page => {
    assert.equal(await page.$eval('#level', el => el.textContent), '05');
    assert.equal(await page.$eval('#stage-name', el => el.textContent), 'Descoberta');
    assert.equal(await page.$eval('#habitat-card', el => el.dataset.stageIndex), '1');
    const frame = await page.$eval('.habitat-stage-frame', el => ({color: getComputedStyle(el).borderTopColor, shadow: getComputedStyle(el).boxShadow}));
    assert.notEqual(frame.color, 'rgba(0, 0, 0, 0)', 'moldura de descoberta visível');
    assert.notEqual(frame.shadow, 'none', 'camada ambiental habilitada');
    await assertXP(page, {total: 805, next: 1118, into: 5, needed: 318, percent: 1.6});
    await page.click('[data-view="evolution"]');
    assert.equal(await page.$eval('#journey-stage', el => el.textContent), 'Descoberta');
    assert.equal(await page.$eval('#journey-level', el => el.textContent), '05');
    const rows = await page.$$eval('#stage-timeline .stage-row', nodes => nodes.map(node => ({
      name: node.querySelector('strong').textContent, level: node.querySelector('small').textContent,
      current: node.classList.contains('current'), unlocked: node.classList.contains('unlocked'),
    })));
    assert.deepEqual(rows.map(row => row.name), ['Despertar', 'Descoberta', 'Aprendizado', 'Companheiro', 'Explorador', 'Evoluído']);
    assert.deepEqual(rows.map(row => row.unlocked), [true, true, false, false, false, false]);
    assert.deepEqual(rows.map(row => row.current), [false, true, false, false, false, false]);
    assert.deepEqual(rows.map(row => Number(row.level.match(/\d+/)[0])), [1, 5, 10, 20, 35, 50]);
    const specialty = await page.$eval('#specialization-name', el => el.textContent);
    assert.ok(specialty.length > 0);
    await screenshot(page, '04-jornada-descoberta.png', false);
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#level').textContent === '05');
    assert.equal(await page.$eval('#stage-name', el => el.textContent), 'Descoberta');
    assert.equal(await page.$eval('#habitat-card', el => el.dataset.stageIndex), '1');
    await assertXP(page, {total: 805, next: 1118, into: 5, needed: 318, percent: 1.6});
    await page.click('[data-view="evolution"]');
    assert.equal(await page.$eval('#stage-timeline .current strong', el => el.textContent), 'Descoberta');
    assert.equal(await page.$eval('#specialization-name', el => el.textContent), specialty);
    console.log('OK · nível 5: estágio, moldura e especialização preservados após recarga; dias simulados.');
  });

  await withPage(null, async page => {
    await page.click('[data-open="settings"]');
    await page.waitForSelector('#dialog-settings[open]');
    const config = JSON.parse(await page.$eval('#config-json', el => el.value));
    config.xpFormula.scale = 200;
    await page.$eval('#config-json', (el, updated) => { el.value = JSON.stringify(updated, null, 2); }, config);
    const saved = page.waitForResponse(r => r.url().endsWith('/api/config') && r.request().method() === 'POST');
    await page.click('#settings-form button[type="submit"]');
    assert.equal((await saved).status(), 200);
    await page.waitForFunction(() => !document.querySelector('#settings-form button[type="submit"]').disabled);
    await page.click('#dialog-settings [data-close]');
    await assertXP(page, {total: 0, next: 200, into: 0, needed: 200, percent: 0});
    await page.click('[data-action="PLAY"]');
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '5');
    await assertXP(page, {total: 5, next: 200, into: 5, needed: 200, percent: 2.5});
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#xp-next').textContent === '200');
    await assertXP(page, {total: 5, next: 200, into: 5, needed: 200, percent: 2.5});
    console.log('OK · fórmula configurada: 5/200 (2,5%), preservada após recarga.');
  });

  await withPage(null, async page => {
    // Hold a *real* old GET response after the server has produced it. A local
    // action commits while that response is delayed, reproducing the race.
    let stateRequests = 0, mediaRequests = 0;
    page.on('request', req => {
      if (new URL(req.url()).pathname === '/api/state') stateRequests++;
      if (new URL(req.url()).pathname === '/api/media') mediaRequests++;
    });
    const delayed = await holdOneResponse(page, '*/api/state');
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    const oldResponse = await delayed.paused;
    const oldState = (await delayed.json(oldResponse)).state;
    assert.equal(oldState.xp, 0, 'snapshot foi obtido antes da ação');
    await page.evaluate(() => {
      for (let i = 0; i < 8; i++) document.dispatchEvent(new Event('visibilitychange'));
      void refresh({includeMedia: true});
    });
    await page.click('[data-action="PLAY"]');
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '5');
    assert.equal(await page.$eval('[data-action="PLAY"]', el => el.getAttribute('aria-disabled')), 'true', 'ação aguarda sincronização pendente');
    await delayed.release(oldResponse);
    await page.waitForFunction(() => document.querySelector('[data-action="PLAY"]').getAttribute('aria-disabled') !== 'true');
    assert.ok(stateRequests <= 3, `atualizações pendentes devem ser coalescidas; recebidas ${stateRequests}`);
    assert.ok(mediaRequests >= 1, 'o lote pendente preserva a opção de incluir mídia');
    await assertXP(page, {total: 5, next: 100, into: 5, needed: 100, percent: 5});
    assert.deepEqual(await page.evaluate(() => ['happiness', 'energy', 'bond'].map(key => document.querySelector(`#${key}-value`).textContent)), ['83', '70', '23']);
    const persisted = await page.evaluate(() => fetch('/api/state', {headers: {'X-Pet-Request': '1'}}).then(r => r.json()).then(({state}) =>
      [state.xp, ...['happiness', 'energy', 'bond'].map(key => Math.round(state[key]))]));
    assert.deepEqual(persisted, [5, 83, 70, 23], 'estado do servidor não retrocedeu');
    assert.ok((await page.$eval('#recent-memories', el => el.textContent)).includes('Hora de brincar'));
    await screenshot(page, '08-apos-resposta-atrasada.png', false);
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '5');
    await assertXP(page, {total: 5, next: 100, into: 5, needed: 100, percent: 5});
    assert.deepEqual(await page.evaluate(() => ['happiness', 'energy', 'bond'].map(key => document.querySelector(`#${key}-value`).textContent)), ['83', '70', '23']);
    console.log('OK · resposta antiga atrasada descartada: UI e servidor mantêm XP=5, felicidade=83, energia=70, vínculo=23; recarga confirma.');
  });

  await withPage(null, async page => {
    // The server has committed PLAY but its reply is delayed. REST must not
    // overtake it in the UI or overwrite the newer state when replies reorder.
    const dispatched = [];
    page.on('request', req => {
      if (req.method() === 'POST' && new URL(req.url()).pathname === '/api/actions') dispatched.push(JSON.parse(req.postData()).action);
    });
    const delayed = await holdOneResponse(page, '*/api/actions');
    await page.click('[data-action="PLAY"]');
    const response = await delayed.paused;
    assert.equal((await delayed.json(response)).state.xp, 5);
    await page.click('[data-action="REST"]');
    assert.equal(await page.$eval('[data-action="REST"]', el => el.getAttribute('aria-disabled')), 'true');
    const current = await page.evaluate(() => fetch('/api/state', {headers: {'X-Pet-Request': '1'}}).then(r => r.json()).then(r => r.state));
    assert.deepEqual(dispatched, ['PLAY'], 'a segunda ação espera a primeira');
    assert.equal(Math.round(current.energy), 70, 'descanso ainda não ultrapassou brincadeira pendente');
    await delayed.release(response);
    await page.waitForFunction(() => document.querySelector('#energy-value').textContent === '90' && document.querySelector('[data-action="REST"]').getAttribute('aria-disabled') !== 'true');
    assert.deepEqual(dispatched, ['PLAY', 'REST']);
    await assertXP(page, {total: 5, next: 100, into: 5, needed: 100, percent: 5});
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#energy-value').textContent === '90');
    assert.equal(await page.$eval('#xp-current', el => el.textContent), '5');
    console.log('OK · ações sobrepostas executam uma vez, na ordem; energia 70→90 e XP persistem.');
  });

  await withPage(null, async page => {
    const dispatched = [];
    page.on('request', req => {
      const pathname = new URL(req.url()).pathname;
      if (req.method() === 'POST' && pathname === '/api/actions') dispatched.push(JSON.parse(req.postData()).action);
      if (req.method() === 'POST' && pathname === '/api/autonomy/run') dispatched.push(JSON.parse(req.postData()).activity);
    });
    const delayed = await holdOneResponse(page, '*/api/actions');
    await page.click('[data-action="PLAY"]');
    const response = await delayed.paused;
    await page.click('[data-view="diary"]');
    await page.click('[data-auto="DREAM"]');
    assert.equal(await page.$eval('[data-auto="DREAM"]', el => el.disabled), true);
    const current = await page.evaluate(() => fetch('/api/state', {headers: {'X-Pet-Request': '1'}}).then(r => r.json()).then(r => r.state));
    assert.equal(Math.round(current.energy), 70);
    assert.deepEqual(dispatched, ['PLAY'], 'atividade local também espera a ação anterior');
    await delayed.release(response);
    await page.waitForFunction(() => !document.querySelector('[data-auto="DREAM"]').disabled && document.querySelector('#autonomy-history').textContent.includes('Sonhar'));
    assert.deepEqual(dispatched, ['PLAY', 'DREAM']);
    await page.click('[data-view="home"]');
    assert.equal(await page.$eval('#energy-value', el => el.textContent), '68');
    await assertXP(page, {total: 5, next: 100, into: 5, needed: 100, percent: 5});
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#energy-value').textContent === '68');
    await page.click('[data-view="diary"]');
    assert.ok((await page.$eval('#autonomy-history', el => el.textContent)).includes('Sonhar'));
    console.log('OK · ação e atividade local sobrepostas respeitam a ordem; histórico e energia persistem.');
  });

  await withPage(null, async page => {
    const marker = 'EXEMPLO-PRIVADO-NA-FILA-0123456789';
    const bodies = [];
    page.on('request', req => {
      if (req.method() === 'POST' && new URL(req.url()).pathname === '/api/actions') bodies.push(req.postData());
    });
    const delayed = await holdOneResponse(page, '*/api/actions');
    await page.click('[data-action="PLAY"]');
    const response = await delayed.paused;
    await page.click('[data-open="chat"]');
    await page.type('#chat-input', marker);
    await page.click('#chat-form button[type="submit"]');
    await page.click('#dialog-chat [data-close]');
    await page.waitForFunction(() => !document.querySelector('#dialog-chat').open && !document.querySelector('#chat-input').value);
    assert.deepEqual(bodies.map(body => JSON.parse(body).action), ['PLAY'], 'conversa aguarda ação anterior');
    await delayed.release(response);
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '7' && document.querySelector('#chat-form button[type="submit"]').getAttribute('aria-disabled') !== 'true');
    assert.deepEqual(bodies.map(body => JSON.parse(body).action), ['PLAY', 'CHAT']);
    assert.equal(bodies.some(body => body.includes(marker)), false);
    await page.click('[data-open="chat"]');
    assert.equal(await page.$eval('#chat-output', (el, value) => el.textContent.includes(value), marker), false);
    assert.equal(await page.$eval('#chat-input', el => el.value), '');
    await page.click('#dialog-chat [data-close]');
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '7');
    console.log('OK · conversa enfileirada mantém privacidade ao fechar, executa após brincar e persiste sem texto.');
  });

  await withPage(null, async page => {
    // A list read can be old even after /api/state returned; both must be
    // discarded together if an action completes before the lists arrive.
    const delayed = await holdOneResponse(page, '*/api/memories');
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    const oldResponse = await delayed.paused;
    assert.equal((await delayed.json(oldResponse)).memories.length, 0);
    await page.click('[data-action="LEARN"]');
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '13');
    await delayed.release(oldResponse);
    await page.waitForFunction(() => document.querySelector('[data-action="LEARN"]').getAttribute('aria-disabled') !== 'true');
    await assertXP(page, {total: 13, next: 100, into: 13, needed: 100, percent: 13});
    assert.equal(await page.$eval('#energy-value', el => el.textContent), '73');
    assert.ok((await page.$eval('#diary-list', el => el.textContent)).includes('Aprendizado do dia'));
    assert.ok((await page.$eval('#award-list', el => el.textContent)).includes('Atividade de aprendizado'));
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '13');
    assert.ok((await page.$eval('#diary-list', el => el.textContent)).includes('Aprendizado do dia'));
    console.log('OK · lista antiga atrasada é refeita junto ao estado; XP, diário e histórico persistem.');
  });

  await withPage(null, async page => {
    const marker = 'EXEMPLO-PRIVADO-NAO-ENVIAR-0123456789';
    const bodies = [];
    page.on('request', req => {
      if (req.method() === 'POST' && new URL(req.url()).pathname === '/api/actions') bodies.push(req.postData());
    });
    const delayed = await holdOneResponse(page, '*/api/actions');
    await page.click('[data-open="chat"]');
    await page.type('#chat-input', marker);
    await page.click('#chat-form button[type="submit"]');
    const response = await delayed.paused;
    assert.equal((await delayed.json(response)).state.xp, 7);
    await page.click('#dialog-chat [data-close]');
    await page.waitForFunction(() => !document.querySelector('#dialog-chat').open && !document.querySelector('#chat-input').value);
    await page.click('[data-open="chat"]');
    await delayed.release(response);
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '7' && document.querySelector('#chat-form button[type="submit"]').getAttribute('aria-disabled') !== 'true');
    assert.equal(await page.$eval('#chat-output', (el, value) => el.textContent.includes(value), marker), false, 'texto antigo não reaparece após fechar/reabrir');
    assert.equal(await page.$$eval('#chat-output .chat-bubble', nodes => nodes.length), 1);
    assert.equal(bodies.some(body => body.includes(marker)), false, 'texto privado não é enviado');
    await page.click('#dialog-chat [data-close]');
    assert.equal(await page.$eval('#memory-list', (el, value) => el.textContent.includes(value), marker), false);
    console.log('OK · resposta de conversa atrasada não restaura o texto após fechar e reabrir.');
  });

  await withPage(null, async page => {
    // Inject failures before a network request to prove both queues recover.
    await page.evaluate(() => {
      const originalFetch = window.fetch.bind(window), originalError = console.error.bind(console);
      const failures = {action: true, state: false};
      window.__syncTestFailures = failures;
      window.fetch = (url, options) => {
        if (url === '/api/actions' && options?.method === 'POST' && failures.action) {
          failures.action = false; return Promise.reject(new Error('falha-injetada-acao'));
        }
        if (url === '/api/state' && failures.state) {
          failures.state = false; return Promise.reject(new Error('falha-injetada-leitura'));
        }
        return originalFetch(url, options);
      };
      console.error = (...args) => {
        if (String(args[0]?.message || args[0]).startsWith('falha-injetada-')) return;
        originalError(...args);
      };
    });
    await page.click('[data-action="PLAY"]');
    await page.waitForFunction(() => document.querySelector('[data-action="PLAY"]').getAttribute('aria-disabled') !== 'true' && document.querySelector('#toast-region').textContent.includes('falha-injetada-acao'));
    assert.equal(await page.evaluate(() => document.activeElement.matches('[data-action="PLAY"]')), true, 'erro da ação não remove foco do botão');
    assert.equal(await page.$eval('#xp-current', el => el.textContent), '0');
    await page.click('[data-action="REST"]');
    await page.waitForFunction(() => document.querySelector('[data-action="REST"]').getAttribute('aria-disabled') !== 'true' && document.querySelector('#xp-current').textContent === '5');
    assert.equal(await page.$eval('#energy-value', el => el.textContent), '100');
    await page.evaluate(() => { window.__syncTestFailures.state = true; document.dispatchEvent(new Event('visibilitychange')); });
    await page.waitForFunction(() => document.querySelector('#toast-region').textContent.includes('falha-injetada-leitura'));
    await page.click('[data-action="PLAY"]');
    await page.waitForFunction(() => document.querySelector('[data-action="PLAY"]').getAttribute('aria-disabled') !== 'true' && document.querySelector('#energy-value').textContent === '90');
    assert.equal(await page.$eval('#xp-current', el => el.textContent), '5');
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => document.querySelector('#energy-value').textContent === '90');
    assert.equal(await page.$eval('#xp-current', el => el.textContent), '5');
    console.log('OK · falhas simuladas de escrita e leitura não bloqueiam interações posteriores.');
  });

  assert.deepEqual(errors, [], 'nenhum erro de console ou de página');
  assert.deepEqual(external, [], 'nenhuma solicitação externa');
  console.log('OK · barra acessível, sem mídia do personagem ou eventos da ponte; bancos temporários descartados.');
})().catch(error => { console.error(error.stack || error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  for (const entry of [...running]) await closeServer(entry);
});
