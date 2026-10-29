/* Local pagination regression. Uses disposable databases and no SL-001 media.
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
const servers = new Set(), errors = [], external = [];
let browser;

async function serverFor({large = false} = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'sl001-pagination-'));
  const seed = spawnSync(process.env.PYTHON || 'python3', ['tests/evolution_scenario.py', '--seed-dir', directory, '--target', 'stage5'], {
    cwd: root, env: {...process.env, PYTHONPATH: '.'}, encoding: 'utf8',
  });
  if (seed.status !== 0) {
    fs.rmSync(directory, {recursive: true, force: true});
    throw new Error(seed.stderr || seed.stdout || 'Falha ao preparar cenário.');
  }
  if (large) {
    // Pagination-only fixture: extra ledger rows in a disposable database.
    // These rows are not presented as genuine pet progression or user data.
    const fixture = spawnSync(process.env.PYTHON || 'python3', ['-c', `
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as conn:
    conn.executemany("INSERT INTO xp_awards(event_id,reason,amount,day,created_at) VALUES(?,?,?,?,?)",
        [(f'pagination-fixture-{i}', 'CREATIVE', 1, '2026-01-01', '2026-01-01T00:00:00Z') for i in range(450)])
`, path.join(directory, 'pet.sqlite3')], {encoding: 'utf8'});
    if (fixture.status !== 0) {
      fs.rmSync(directory, {recursive: true, force: true});
      throw new Error(fixture.stderr || 'Falha ao preparar paginação extensa.');
    }
  }
  const server = spawn(process.env.PYTHON || 'python3', ['app.py', '--host', '127.0.0.1', '--port', '0', '--data-dir', directory], {
    cwd: root, stdio: ['ignore', 'pipe', 'pipe'],
  });
  const entry = {server, directory};
  servers.add(entry);
  entry.port = await new Promise((resolve, reject) => {
    let stdout = '', stderr = '';
    const timeout = setTimeout(() => reject(new Error(`Servidor não iniciou: ${stderr}`)), 10000);
    server.stderr.on('data', data => { stderr += data.toString(); });
    server.stdout.on('data', data => {
      stdout += data.toString();
      const match = stdout.match(/:(\d+) \(modo local/);
      if (match) { clearTimeout(timeout); resolve(Number(match[1])); }
    });
    server.once('error', error => { clearTimeout(timeout); reject(error); });
    server.once('exit', code => { clearTimeout(timeout); reject(new Error(`Servidor encerrou (${code}): ${stderr}`)); });
  });
  const access = path.join(directory, '.access');
  entry.token = fs.readFileSync(path.join(access, fs.readdirSync(access)[0], 'owner.token'), 'utf8').trim();
  return entry;
}

async function closeServer(entry) {
  if (!servers.has(entry)) return;
  if (entry.server.exitCode === null && entry.server.signalCode === null) {
    await new Promise(resolve => {
      const timeout = setTimeout(() => { entry.server.kill('SIGKILL'); resolve(); }, 3000);
      entry.server.once('exit', () => { clearTimeout(timeout); resolve(); });
      entry.server.kill('SIGTERM');
    });
  }
  fs.rmSync(entry.directory, {recursive: true, force: true});
  servers.delete(entry);
}

async function withPage(options, callback) {
  const entry = await serverFor(options);
  const context = await browser.createBrowserContext();
  try {
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
    page.on('request', request => {
      const url = new URL(request.url());
      if (['http:', 'https:'].includes(url.protocol) && url.hostname !== '127.0.0.1') external.push(request.url());
    });
    await page.setViewport({width: 1440, height: 1000});
    await page.emulateMediaFeatures([{name: 'prefers-reduced-motion', value: 'reduce'}]);
    if (options.denyStorage) await page.evaluateOnNewDocument(() => {
      Object.defineProperty(window, 'sessionStorage', {configurable: true, get() { throw new DOMException('Storage blocked', 'SecurityError'); }});
    });
    await page.goto(`http://127.0.0.1:${entry.port}/`, {waitUntil: 'networkidle0'});
    await page.waitForSelector('#dialog-login[open]');
    await page.type('#owner-token', entry.token);
    await page.click('#login-form button[type="submit"]');
    await page.waitForFunction(() => !document.querySelector('#dialog-login').open && document.querySelector('#habitat-card').dataset.stageIndex !== undefined);
    await callback(page, context, entry);
  } finally {
    await context.close();
    await closeServer(entry);
  }
}

async function awardState(page) {
  return page.evaluate(() => ({
    ids: awards.map(item => `${item.eventId}:${item.reason}`),
    rows: document.querySelectorAll('#award-list .award-row').length,
    button: {hidden: document.querySelector('#load-more-awards').hidden, disabled: document.querySelector('#load-more-awards').disabled},
  }));
}

async function clickMore(page, button, rows) {
  const before = await page.$$eval(rows, nodes => nodes.length);
  assert.equal(await page.$eval(button, el => !el.hidden && !el.disabled && el.getAttribute('aria-disabled') !== 'true'), true, `${button}: deve estar disponível`);
  await page.$eval(button, el => el.scrollIntoView({block: 'center', behavior: 'instant'}));
  await page.click(button);
  await page.waitForFunction((selector, count) => document.querySelectorAll(selector).length > count, {}, rows, before);
  await page.waitForFunction(selector => !document.querySelector(selector).disabled && document.querySelector(selector).getAttribute('aria-disabled') !== 'true', {timeout: 3000}, button);
  return page.$$eval(rows, nodes => nodes.length);
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

function assertUnique(ids) { assert.equal(new Set(ids).size, ids.length, 'nenhuma concessão duplicada'); }
function assertRetained(previous, current) {
  const present = new Set(current);
  assert.ok(previous.every(id => present.has(id)), 'concessões já vistas continuam presentes');
}

(async () => {
  browser = await puppeteer.launch({executablePath: chrome, headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']});

  if (!process.env.PAGINATION_RACE_ONLY) {
  await withPage({}, async page => {
    // Reach the home shortcut and the historical list with real Tab/Enter keys.
    await page.evaluate(() => document.activeElement.blur());
    await tabTo(page, '[data-go="evolution"]');
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => document.activeElement === document.querySelector('#view-evolution h1')), true, 'foco sai do atalho oculto e chega ao título da jornada');
    assert.equal(await page.$eval('[data-view="evolution"]', el => el.getAttribute('aria-current')), 'page');
    assert.equal(await page.$eval('#load-more-awards', el => el.getAttribute('aria-controls')), 'award-list');
    assert.equal(await page.$eval('#load-more-awards', el => el.getAttribute('aria-label')), 'Mostrar mais registros de XP');
    assert.equal(await page.$eval('#award-announcement', el => el.getAttribute('role')), 'status');
    assert.equal(await page.$eval('#award-announcement', el => el.getAttribute('aria-live')), 'polite');
    await tabTo(page, '#load-more-awards');
    await page.evaluate(() => {
      const original = window.fetch, logError = console.error;
      let failOnce = true;
      window.fetch = (url, options) => {
        if (failOnce && typeof url === 'string' && url.startsWith('/api/awards?') && new URL(url, location.href).searchParams.has('offset')) {
          failOnce = false; return Promise.reject(new Error('falha-teclado-pagina'));
        }
        return original(url, options);
      };
      console.error = (...args) => { if (!String(args[0]?.message || args[0]).includes('falha-teclado-pagina')) logError(...args); };
    });
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => document.querySelector('#toast-region').textContent.includes('falha-teclado-pagina') && document.querySelector('#load-more-awards').getAttribute('aria-disabled') !== 'true');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'load-more-awards', 'falha de rede mantém foco e permite repetir');
    assert.equal(await page.$$eval('#award-list .award-row', rows => rows.length), 20);
    let requests = 0;
    page.on('request', req => { if (new URL(req.url()).pathname === '/api/awards') requests++; });
    const delayed = await holdOneResponse(page, '*/api/awards*');
    await page.keyboard.press('Enter');
    const response = await delayed.paused.catch(async error => {
      const diagnostic = await page.evaluate(() => ({focus:document.activeElement.outerHTML.slice(0,200), busy:document.querySelector('#load-more-awards').getAttribute('aria-disabled'), view:document.querySelector('.view:not([hidden])')?.id}));
      throw new Error(`${error.message}; estado=${JSON.stringify(diagnostic)}; pedidos=${requests}`);
    });
    assert.equal(await page.evaluate(() => document.activeElement.id), 'load-more-awards', 'foco permanece no botão durante a leitura');
    assert.equal(await page.$eval('#load-more-awards', el => el.getAttribute('aria-disabled')), 'true');
    const busyClient = await page.createCDPSession();
    await busyClient.send('Accessibility.enable');
    const busyNodes = (await busyClient.send('Accessibility.getFullAXTree')).nodes;
    assert.ok(busyNodes.some(node => !node.ignored && node.role?.value === 'button' && node.name?.value === 'Mostrar mais registros de XP' && node.properties?.some(p => p.name === 'disabled' && p.value?.value)), 'Chromium expõe o botão como indisponível durante o pedido');
    await busyClient.detach();
    await page.keyboard.press('Enter');
    assert.equal(requests, 1, 'ativação repetida enquanto ocupado não solicita outra página');
    await delayed.release(response);
    await page.waitForFunction(() => document.querySelectorAll('#award-list .award-row').length === 40 && document.querySelector('#load-more-awards').getAttribute('aria-disabled') !== 'true');
    assert.equal(await page.evaluate(() => document.activeElement === document.querySelectorAll('#award-list .award-row')[20]), true, 'foco vai para o primeiro registro recém-carregado');
    assert.ok(await page.evaluate(() => document.activeElement.getAttribute('role') === 'group' && document.activeElement.getAttribute('aria-label')?.includes('XP')), 'registro focado tem nome acessível');
    assert.ok((await page.$eval('#award-announcement', el => el.textContent)).includes('40 de 122'));
    const axClient = await page.createCDPSession();
    await axClient.send('Accessibility.enable');
    const axNodes = (await axClient.send('Accessibility.getFullAXTree')).nodes;
    assert.ok(axNodes.some(node => !node.ignored && node.role?.value === 'group' && node.name?.value?.includes('XP') && node.properties?.some(p => p.name === 'focused' && p.value?.value)), 'Chromium expõe o registro focado e seu nome na árvore de acessibilidade');
    assert.ok(axNodes.some(node => !node.ignored && node.role?.value === 'button' && node.name?.value === 'Mostrar mais registros de XP'), 'Chromium expõe nome do botão');
    assert.ok(axNodes.some(node => !node.ignored && node.role?.value === 'status' && node.properties?.some(p => p.name === 'live' && p.value?.value === 'polite')), 'Chromium expõe o status ao vivo');
    await axClient.detach();
    await page.evaluate(() => { window.__focusedAward = document.activeElement; });
    await page.evaluate(() => refresh());
    assert.equal(await page.evaluate(() => document.activeElement === window.__focusedAward), true, 'atualização sem alterações não recria o registro focado');

    // A person may move focus elsewhere while a slow request is in flight.
    await tabTo(page, '#load-more-awards');
    const movedFocus = await holdOneResponse(page, '*/api/awards*');
    await page.keyboard.press('Enter');
    const movedResponse = await movedFocus.paused;
    await tabTo(page, '[data-view="home"]', true);
    await page.keyboard.press('Enter');
    assert.equal(await page.$eval('#view-home', el => !el.hidden), true);
    await movedFocus.release(movedResponse);
    await page.waitForFunction(() => document.querySelectorAll('#award-list .award-row').length === 60 && document.querySelector('#load-more-awards').getAttribute('aria-disabled') !== 'true');
    assert.equal(await page.evaluate(() => document.activeElement.matches('[data-view="home"]')), true, 'não roubar o foco nem trocar a tela durante o carregamento');
    assert.equal(await page.$eval('#view-home', el => !el.hidden), true);
    await tabTo(page, '[data-view="evolution"]');
    await page.keyboard.press('Enter');
    assert.equal(await page.$eval('#view-evolution', el => !el.hidden), true);

    while (!(await page.$eval('#load-more-awards', el => el.hidden))) {
      const before = await page.$$eval('#award-list .award-row', rows => rows.length);
      await tabTo(page, '#load-more-awards');
      await page.keyboard.press('Enter');
      await page.waitForFunction(n => document.querySelectorAll('#award-list .award-row').length > n && document.querySelector('#load-more-awards').getAttribute('aria-disabled') !== 'true', {}, before);
      assert.equal(await page.evaluate(n => document.activeElement === document.querySelectorAll('#award-list .award-row')[n], before), true, 'foco permanece nos registros, inclusive na última página');
    }
    assert.ok((await page.$eval('#award-announcement', el => el.textContent)).includes('Todos os 122'));
    await tabTo(page, '[data-view="home"]', true);
    await page.keyboard.press('Enter');
    assert.equal(await page.$eval('#view-home', el => !el.hidden), true);
    assert.equal(await page.$eval('[data-view="home"]', el => el.getAttribute('aria-current')), 'page');
    console.log('OK · teclado: atalho → título → histórico; foco preservado, aviso de quantidade, última página e retorno ao slime.');
  });

  await withPage({}, async page => {
    await page.click('[data-view="evolution"]');
    await clickMore(page, '#load-more-awards', '#award-list .award-row');
    const key = await page.evaluate(() => ({eventId:document.activeElement.dataset.awardEvent, reason:document.activeElement.dataset.awardReason}));
    assert.ok(key.eventId && key.reason, 'registro expandido recebe o foco');
    await page.evaluate(() => api('/api/actions', {method:'POST', json:{action:'REST', eventId:'keyboard-focus-refresh-rest'}}));
    await page.evaluate(() => refresh());
    assert.equal(await page.$$eval('#award-list .award-row', rows => rows.length), 41, 'concessão nova entra antes da janela expandida');
    assert.deepEqual(await page.evaluate(() => ({eventId:document.activeElement.dataset.awardEvent, reason:document.activeElement.dataset.awardReason})), key, 'atualização com nova concessão preserva o mesmo registro focado');
    console.log('OK · foco do registro preservado em atualização com nova concessão no início da lista.');
  });

  await withPage({}, async (page, context, entry) => {
    await page.click('[data-view="evolution"]');
    let current = await awardState(page);
    assert.equal(current.rows, 20);
    assert.deepEqual(current.button, {hidden: false, disabled: false});
    const allBefore = await page.evaluate(() => api('/api/awards?limit=500'));
    assert.ok(allBefore.awards.length > 100, 'fixture precisa de várias páginas');

    await clickMore(page, '#load-more-awards', '#award-list .award-row');
    current = await awardState(page);
    assert.equal(current.rows, 40);
    assert.deepEqual(current.button, {hidden: false, disabled: false});
    assertUnique(current.ids);

    // A failed later page must re-enable the same button and permit a retry.
    await page.evaluate(() => {
      const original = window.fetch.bind(window), logError = console.error.bind(console);
      window.__failAwardPageOnce = true;
      window.fetch = (url, options) => {
        if (window.__failAwardPageOnce && typeof url === 'string' && url.startsWith('/api/awards?') && new URL(url, location.href).searchParams.has('offset')) {
          window.__failAwardPageOnce = false;
          return Promise.reject(new Error('falha-injetada-pagina'));
        }
        return original(url, options);
      };
      console.error = (...args) => {
        if (String(args[0]?.message || args[0]).includes('falha-injetada-pagina')) return;
        logError(...args);
      };
    });
    await page.click('#load-more-awards');
    await page.waitForFunction(() => document.querySelector('#toast-region').textContent.includes('falha-injetada-pagina') && document.querySelector('#load-more-awards').getAttribute('aria-disabled') !== 'true');
    assert.equal((await awardState(page)).rows, 40);
    await clickMore(page, '#load-more-awards', '#award-list .award-row');
    current = await awardState(page);
    assert.equal(current.rows, 60);
    assert.deepEqual(current.button, {hidden: false, disabled: false});
    const stored = await page.evaluate(() => JSON.parse(sessionStorage.getItem(AWARD_POSITION_KEY)));
    assert.deepEqual(Object.keys(stored).sort(), ['loaded', 'total'], 'somente contagens ficam no armazenamento da aba');
    assert.deepEqual(stored, {loaded: 60, total: 122});

    // A delayed refresh cannot erase a user request to expand the list.
    const delayedRefresh = await holdOneResponse(page, '*/api/awards*');
    const refreshing = page.evaluate(() => refresh());
    const oldResponse = await delayedRefresh.paused;
    await page.click('#load-more-awards');
    assert.equal(await page.$eval('#load-more-awards', el => el.getAttribute('aria-disabled')), 'true');
    await delayedRefresh.release(oldResponse);
    await refreshing;
    await page.waitForFunction(() => document.querySelectorAll('#award-list .award-row').length === 80 && document.querySelector('#load-more-awards').getAttribute('aria-disabled') !== 'true');
    current = await awardState(page);
    assertUnique(current.ids);

    // A new award while a page response is delayed must not duplicate/drop rows.
    const oldIds = current.ids;
    const delayedPage = await holdOneResponse(page, '*/api/awards*');
    await page.click('#load-more-awards');
    const pageResponse = await delayedPage.paused;
    await page.click('[data-view="home"]');
    await page.click('[data-action="REST"]');
    await page.waitForFunction(() => document.querySelector('#xp-current').textContent === '810');
    await delayedPage.release(pageResponse);
    await page.waitForFunction(() => document.querySelector('[data-action="REST"]').getAttribute('aria-disabled') !== 'true' && document.querySelector('#load-more-awards').getAttribute('aria-disabled') !== 'true');
    await page.click('[data-view="evolution"]');
    current = await awardState(page);
    assert.equal(current.rows, 101, '80 anteriores + 20 solicitados + 1 novo');
    assertRetained(oldIds, current.ids);
    assertUnique(current.ids);
    const beforeReload = current.ids;

    // Another tab starts on page one and adds a grant before the first tab
    // reloads. Stored counts must include the new head without losing the tail.
    const second = await context.newPage();
    try {
      await second.goto(`http://127.0.0.1:${entry.port}/`, {waitUntil: 'networkidle0'});
      await second.waitForFunction(() => document.querySelector('#habitat-card').dataset.stageIndex !== undefined);
      await second.click('[data-view="evolution"]');
      assert.equal((await awardState(second)).rows, 20);
      await second.click('[data-view="home"]');
      await second.click('[data-action="LEARN"]');
      await second.waitForFunction(() => document.querySelector('[data-action="LEARN"]').getAttribute('aria-disabled') !== 'true' && document.querySelector('#xp-current').textContent === '818');
    } finally { await second.close(); }

    // Preserve items in the same tab, without altering which view opens on reload.
    await page.reload({waitUntil: 'networkidle0'});
    await page.waitForFunction(() => !document.querySelector('#view-home').hidden && document.querySelector('#habitat-card').dataset.stageIndex !== undefined);
    await page.click('[data-view="evolution"]');
    current = await awardState(page);
    assert.equal(current.rows, 102, 'recarga inclui a concessão nova e os 101 itens anteriores');
    assertRetained(beforeReload, current.ids);
    assert.deepEqual(current.button, {hidden: false, disabled: false});
    assertUnique(current.ids);

    while (!(await awardState(page)).button.hidden) {
      await clickMore(page, '#load-more-awards', '#award-list .award-row');
      current = await awardState(page);
      assertUnique(current.ids);
    }
    const allAfter = await page.evaluate(() => api('/api/awards?limit=500'));
    const expected = allAfter.awards.map(item => `${item.eventId}:${item.reason}`);
    assert.deepEqual(current.ids, expected);
    assertRetained(allBefore.awards.map(item => `${item.eventId}:${item.reason}`), current.ids);
    assert.equal(current.rows, 124);

    // Even an expanded final page retains its contents when a new grant arrives.
    await page.click('[data-view="home"]');
    await page.click('[data-action="LEARN"]');
    await page.waitForFunction(() => document.querySelector('[data-action="LEARN"]').getAttribute('aria-disabled') !== 'true' && document.querySelector('#xp-current').textContent === '826');
    await page.click('[data-view="evolution"]');
    const final = await awardState(page);
    assert.equal(final.rows, 125);
    assertRetained(current.ids, final.ids);
    assertUnique(final.ids);
    assert.equal(final.button.hidden, true);
    await page.reload({waitUntil: 'networkidle0'});
    await page.click('[data-view="evolution"]');
    assert.deepEqual((await awardState(page)).ids, final.ids);
    console.log('OK · 20→40→60→80→101→102→124→125; erros, respostas atrasadas, outra aba e recargas verificadas.');
  });

  await withPage({large: true}, async page => {
    await page.click('[data-view="evolution"]');
    for (let i = 0; i < 25; i++) await clickMore(page, '#load-more-awards', '#award-list .award-row');
    const before = await awardState(page);
    assert.equal(before.rows, 520);
    assertUnique(before.ids);
    // Simulate another local client writing between two API pages: totals
    // change, so the mixed window must be retried before it is rendered.
    const delayed = await holdOneResponse(page, '*/api/awards*');
    const refreshing = page.evaluate(() => refresh());
    const firstPage = await delayed.paused;
    await page.evaluate(() => api('/api/actions', {method: 'POST', json: {action: 'REST', eventId: 'pagination-external-rest'}}));
    await delayed.release(firstPage);
    await refreshing;
    const afterWrite = await awardState(page);
    assert.equal(afterWrite.rows, 521);
    assertRetained(before.ids, afterWrite.ids);
    assertUnique(afterWrite.ids);
    const requests = [];
    page.on('request', req => { if (new URL(req.url()).pathname === '/api/awards') requests.push(req.url()); });
    await page.reload({waitUntil: 'networkidle0'});
    await page.click('[data-view="evolution"]');
    const after = await awardState(page);
    assert.deepEqual(after.ids, afterWrite.ids, 'recarga restaura mais de 500 itens sem truncar');
    assert.ok(requests.some(url => new URL(url).searchParams.get('offset') === '500'), 'restauração usa mais de uma página da API');
    console.log('OK · 520→521 itens, escrita entre páginas e recarga em múltiplas páginas (fixture sintética descartável).');
  });

  await withPage({denyStorage: true}, async page => {
    await page.click('[data-view="evolution"]');
    await clickMore(page, '#load-more-awards', '#award-list .award-row');
    await page.evaluate(() => refresh());
    assert.equal((await awardState(page)).rows, 40, 'atualização na aba funciona sem sessionStorage');
    await page.reload({waitUntil: 'networkidle0'});
    await page.click('[data-view="evolution"]');
    assert.equal((await awardState(page)).rows, 20, 'sem armazenamento permitido, recarga volta à primeira página');
    await clickMore(page, '#load-more-awards', '#award-list .award-row');
    console.log('OK · sem sessionStorage, o botão e a atualização funcionam; recarga usa a primeira página.');
  });

  await withPage({}, async page => {
    // Real local actions on a disposable database create >200 memories and >40
    // local-activity records. The same async event bug affected these buttons.
    await page.evaluate(async () => {
      for (let i = 0; i < 45; i++) {
        await api('/api/actions', {method: 'POST', json: {action: 'REST', eventId: `pagination-rest-${i}`}});
        await api('/api/autonomy/run', {method: 'POST', json: {activity: 'JOURNAL', eventId: `pagination-journal-${i}`}});
      }
      await refresh();
    });
    await page.click('[data-view="memory"]');
    assert.equal(await page.$$eval('#memory-list .entry', nodes => nodes.length), 100);
    assert.equal(await clickMore(page, '#load-more-memories', '#memory-list .entry'), 200);
    assert.equal(await page.$eval('#load-more-memories', el => !el.hidden && !el.disabled), true);
    assert.equal(await clickMore(page, '#load-more-memories', '#memory-list .entry'), 300);
    await page.click('[data-view="diary"]');
    assert.equal(await page.$$eval('#autonomy-history .history-row', nodes => nodes.length), 20);
    assert.equal(await clickMore(page, '#load-more-history', '#autonomy-history .history-row'), 40);
    assert.equal(await page.$eval('#load-more-history', el => !el.hidden && !el.disabled), true);
    assert.equal(await clickMore(page, '#load-more-history', '#autonomy-history .history-row'), 45);
    assert.equal(await page.$eval('#load-more-history', el => el.hidden && !el.disabled), true);
    console.log('OK · botões com o mesmo defeito: memórias 100→200→300 e histórico local 20→40→45.');
  });
  }

  if (process.env.PAGINATION_RACE_ONLY !== 'history') await withPage({}, async page => {
    // Keep an old page in flight while the user deletes records. The underlying
    // DB commits immediately; only delivery of the old HTTP response is delayed.
    await page.click('[data-view="memory"]');
    const initial = Number(await page.$eval('#memory-count', el => el.textContent));
    assert.ok(initial > 100 && initial <= 200, 'fixture deve ter duas páginas');
    const ids = () => page.$$eval('#memory-list [data-delete-memory]', nodes => nodes.map(node => node.dataset.deleteMemory));

    let gate = await holdOneResponse(page, '/api/memories?limit=100&offset=100');
    await page.click('#load-more-memories');
    await gate.paused;
    page.once('dialog', dialog => dialog.accept());
    await page.click('#memory-list [data-delete-memory]');
    await page.waitForFunction(() => document.querySelector('#toast-region').textContent.includes('Registro apagado.'));
    await gate.release();
    await page.waitForFunction(() => !document.querySelector('#load-more-memories').disabled);
    const afterSingleIds = await ids();
    const afterSingle = {shown:afterSingleIds.length, unique:new Set(afterSingleIds).size,
      total:Number(await page.$eval('#memory-count', el => el.textContent)),
      apiTotal:await page.evaluate(() => api('/api/memories?limit=1').then(data => data.total))};
    console.log(`Exclusão individual com página antiga atrasada: ${JSON.stringify(afterSingle)}.`);
    // Exercise a retry after the discarded page, but continue the reproduction
    // even on the unfixed version so both discrepancies are logged.
    if (afterSingle.shown === 100 && afterSingle.total === initial - 1) {
      assert.equal(await clickMore(page, '#load-more-memories', '#memory-list .entry'), initial - 1);
      assertUnique(await ids());
    }
    await page.evaluate(() => refresh());

    gate = await holdOneResponse(page, '/api/memories?limit=100&offset=100');
    await page.click('#load-more-memories');
    await gate.paused;
    page.once('dialog', dialog => dialog.accept());
    await page.click('#delete-all');
    await page.waitForFunction(() => document.querySelector('#toast-region').textContent.includes('Registros do pet apagados.'));
    await gate.release();
    await page.waitForFunction(() => !document.querySelector('#load-more-memories').disabled);
    const afterAll = {shown:(await ids()).length, total:Number(await page.$eval('#memory-count', el => el.textContent)),
      apiTotal:await page.evaluate(() => api('/api/memories?limit=1').then(data => data.total))};
    console.log(`Exclusão total com página antiga atrasada: ${JSON.stringify(afterAll)}.`);
    assert.deepEqual(afterSingle, {shown:100, unique:100, total:initial - 1, apiTotal:initial - 1}, 'página anterior não deve duplicar nem restaurar a contagem após exclusão individual');
    assert.deepEqual(afterAll, {shown:0, total:0, apiTotal:0}, 'página anterior não deve reapresentar registros apagados');
    console.log('OK · exclusões individual e total não são revertidas visualmente por página atrasada; paginação pode ser repetida.');
  });

  if (process.env.PAGINATION_RACE_ONLY !== 'history') await withPage({}, async (page, context) => {
    // No local write/revision in the first page: a second page changes the DB,
    // then an explicit refresh replaces the displayed memory snapshot.
    await page.click('[data-view="memory"]');
    const initial = Number(await page.$eval('#memory-count', el => el.textContent));
    const displaced = await page.$$eval('#memory-list [data-delete-memory]', nodes => nodes.at(-1).dataset.deleteMemory);
    const gate = await holdOneResponse(page, '/api/memories?limit=100&offset=100');
    await page.click('#load-more-memories');
    await gate.paused;
    const other = await context.newPage();
    try {
      await other.goto(page.url(), {waitUntil:'networkidle0'});
      await other.waitForFunction(() => document.querySelector('#habitat-card').dataset.stageIndex !== undefined);
      await other.click('[data-action="REST"]');
      await other.waitForFunction(() => document.querySelector('#toast-region').textContent.includes('SL-001 descansou') && document.querySelector('[data-action="REST"]').getAttribute('aria-disabled') !== 'true');
    } finally { await other.close(); }
    await page.evaluate(() => refresh());
    const expectedTotal = await page.evaluate(() => api('/api/memories?limit=1').then(data => data.total));
    assert.ok(expectedTotal > initial && expectedTotal <= 200);
    await gate.release();
    await page.waitForFunction(() => !document.querySelector('#load-more-memories').disabled);
    const observed = await page.evaluate(id => ({shown:memories.length, total:memoryTotal,
      hasMore:!document.querySelector('#load-more-memories').hidden,
      displaced:memories.some(row => row.id === id)}), displaced);
    assert.deepEqual(observed, {shown:100, total:expectedTotal, hasMore:true, displaced:false}, 'refresh deve invalidar página antiga mesmo sem revisão local');
    assert.equal(await clickMore(page, '#load-more-memories', '#memory-list .entry'), expectedTotal);
    const ids = await page.$$eval('#memory-list [data-delete-memory]', nodes => nodes.map(node => node.dataset.deleteMemory));
    assertUnique(ids);
    assert.ok(ids.includes(displaced));
    console.log('OK · após outra página agir e a primeira atualizar, página antiga é descartada e a leitura repetida recupera os registros.');
  });

  if (process.env.PAGINATION_RACE_ONLY !== 'memory') await withPage({}, async page => {
    // Populate a short real history; no artificial edits to the persistent DB.
    await page.evaluate(async () => {
      for (let i = 0; i < 23; i++) {
        await api('/api/actions', {method:'POST', json:{action:'REST', eventId:`history-race-rest-${i}`}});
        await api('/api/autonomy/run', {method:'POST', json:{activity:'JOURNAL', eventId:`history-race-journal-${i}`}});
      }
      await refresh();
    });
    await page.click('[data-view="diary"]');
    assert.equal(await page.$$eval('#autonomy-history .history-row', nodes => nodes.length), 20);
    const oldLast = await page.evaluate(() => history.at(-1).id);
    const gate = await holdOneResponse(page, '/api/autonomy/history?limit=20&offset=20');
    await page.click('#load-more-history');
    await gate.paused;
    await page.click('[data-auto="JOURNAL"]');
    await page.waitForFunction(() => !document.querySelector('[data-auto="JOURNAL"]').disabled && document.querySelector('#toast-region').textContent.includes('Registro local:'));
    await gate.release();
    await page.waitForFunction(() => !document.querySelector('#load-more-history').disabled);
    const observed = await page.evaluate(async id => {
      const apiHistory = (await api('/api/autonomy/history?limit=100')).history;
      return {shown:history.length, unique:new Set(history.map(row => row.id)).size,
        total:apiHistory.length, hasMore:!document.querySelector('#load-more-history').hidden,
        oldLastInAPI:apiHistory.some(row => row.id === id), oldLastShown:history.some(row => row.id === id)};
    }, oldLast);
    console.log(`Diário com atividade nova e página antiga atrasada: ${JSON.stringify(observed)}.`);
    assert.deepEqual(observed, {shown:20, unique:20, total:24, hasMore:true, oldLastInAPI:true, oldLastShown:false}, 'a página antiga não deve ocultar registros após nova atividade');
    assert.equal(await clickMore(page, '#load-more-history', '#autonomy-history .history-row'), 24);
    const loaded = await page.evaluate(() => history.map(row => row.id));
    assertUnique(loaded);
    assert.ok(loaded.includes(oldLast));
    console.log('OK · nova atividade não mistura a página antiga do Diário; paginação posterior recupera os 24 registros.');
  });

  assert.deepEqual(errors, [], 'nenhum erro JavaScript inesperado');
  assert.deepEqual(external, [], 'nenhuma requisição externa');
})().catch(error => { console.error(error.stack || error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  for (const entry of [...servers]) await closeServer(entry);
});
