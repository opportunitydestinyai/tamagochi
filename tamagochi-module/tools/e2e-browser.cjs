/* Optional browser integration checks. Requires Node 22, puppeteer-core and a local Chromium.
 * Runs a disposable isolated server/database and imports ONLY a color-pattern test video. */
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const puppeteer = require('puppeteer-core');
const root = path.resolve(__dirname,'..');
const fixture = path.join(root,'tests','fixtures','solid-color-test.webm');
const chrome = process.env.CHROME_BIN;
if (!chrome) throw new Error('Defina CHROME_BIN para um Chromium/Chrome local.');
const temp = fs.mkdtempSync(path.join(os.tmpdir(),'sl001-e2e-'));
const server = spawn(process.env.PYTHON || 'python3',['app.py','--host','127.0.0.1','--port','0','--data-dir',temp],{cwd:root,stdio:['ignore','pipe','pipe']});
let browser;
function waitPort() {
  return new Promise((resolve,reject) => {
    const timeout=setTimeout(()=>reject(new Error('Servidor de teste não iniciou.')),10000);
    server.stdout.on('data',data=>{const m=data.toString().match(/:(\d+) \(modo local/);if(m){clearTimeout(timeout);resolve(Number(m[1]));}});
    server.once('exit',code=>{clearTimeout(timeout);reject(new Error(`Servidor de teste saiu: ${code}`));});
  });
}
(async () => {
  const port=await waitPort();
  const sessionDir=path.join(temp,'.access',fs.readdirSync(path.join(temp,'.access'))[0]);
  const ownerToken=fs.readFileSync(path.join(sessionDir,'owner.token'),'utf8').trim();
  const bridgeToken=fs.readFileSync(path.join(sessionDir,'bridge.token'),'utf8').trim();
  browser=await puppeteer.launch({executablePath:chrome,headless:true,args:['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required']});
  const page=await browser.newPage(); const errors=[], external=[], bodies=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',msg=>{if(msg.type()==='error') errors.push(msg.text());});
  page.on('request',req=>{const u=new URL(req.url());if(u.hostname!=='127.0.0.1') external.push(req.url()); if(u.pathname!=='/api/session' && req.postData()) bodies.push(req.postData());});
  await page.setViewport({width:1440,height:1000,deviceScaleFactor:1});
  await page.goto(`http://127.0.0.1:${port}/`,{waitUntil:'networkidle0'});
  await page.waitForSelector('#dialog-login[open]');
  await page.type('#owner-token',ownerToken);
  await page.click('#login-form button[type="submit"]');
  await page.waitForFunction(()=>!document.querySelector('#dialog-login').open);
  await page.waitForFunction(()=>document.querySelector('#level').textContent==='01');
  assert.equal(await page.$eval('#media-placeholder',e=>!e.hidden),true,'mídia ausente deve ser explicitada');
  assert.equal(await page.$eval('#xp-current',e=>e.textContent),'0');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'sem overflow horizontal no desktop');
  await page.click('[data-open="stats"]');
  assert.equal(await page.$$eval('#all-stats .detail-stat',e=>e.length),6);
  await page.click('#dialog-stats [data-close]');
  await page.click('[data-action="PLAY"]');
  await page.waitForFunction(()=>document.querySelector('#xp-current').textContent==='5');
  assert.equal(await page.$eval('#energy-value',e=>e.textContent),'70');
  await page.click('[data-open="chat"]');
  const privateMarker='EXAMPLE-PRIVATE-DO-NOT-SEND';
  await page.type('#chat-input',privateMarker);
  await page.click('#chat-form button[type="submit"]');
  await page.waitForFunction(()=>document.querySelectorAll('#chat-output .chat-bubble').length===3);
  assert.equal(bodies.some(x=>x.includes(privateMarker)),false,'texto de conversa não deve sair do navegador');
  await page.click('#dialog-chat [data-close]');
  await page.waitForFunction(()=>!document.querySelector('#chat-output').textContent.includes('EXAMPLE-PRIVATE'));
  assert.equal(await page.$eval('#chat-output',e=>e.textContent.includes('EXAMPLE-PRIVATE')),false);
  await page.click('[data-open="customize"]');
  await page.click('input[name="theme"][value="SKY"] + span');
  await page.select('select[name="playerFit"]','FILL');
  await page.click('#customize-form button[type="submit"]');
  await page.waitForFunction(()=>!document.querySelector('#dialog-customize').open);
  assert.equal(await page.$eval('#habitat-card',e=>e.dataset.theme),'SKY');
  assert.equal(await page.$eval('#habitat-center',e=>e.dataset.fit),'FILL');
  await page.click('[data-view="diary"]');
  await page.click('[data-auto="DREAM"]');
  await page.waitForFunction(()=>[...document.querySelectorAll('#diary-list .entry')].some(e=>e.textContent.includes('Um sonho tranquilo')));
  await page.click('[data-view="home"]');
  await page.click('[data-open="settings"]');
  await page.waitForSelector('#dialog-settings[open]');
  await page.select('#media-slot','idle_video');
  await (await page.$('#media-file')).uploadFile(fixture);
  await page.click('#media-upload');
  await page.waitForFunction(()=>document.querySelector('#pet-video').getAttribute('src')?.includes('idle_video'),{timeout:10000});
  await page.waitForFunction(()=>document.querySelector('#pet-video').readyState>=2 && document.querySelector('#pet-video').currentTime>0,{timeout:10000});
  assert.equal(await page.$eval('#pet-video',e=>!e.hidden && e.loop),true,'vídeo local de teste deve ser reproduzido em loop');
  await page.select('#media-slot','milestone_video');
  await (await page.$('#media-file')).uploadFile(fixture);
  await page.click('#media-upload');
  await page.waitForFunction(()=>document.querySelector('#media-list').textContent.includes('Vídeo · milestone'));
  assert.equal(await page.$eval('#bridge-receive',e=>e.checked),false);
  assert.equal(await page.$eval('#bridge-share',e=>e.checked),false);
  await page.click('#bridge-receive');
  let consentSaved=page.waitForResponse(r=>r.url().endsWith('/api/bridge/consent') && r.request().method()==='POST');
  await page.click('#bridge-save');
  assert.deepEqual((await (await consentSaved).json()).consent,{receiveEvents:true,shareData:false});
  await page.click('#dialog-settings [data-close]');
  // Local authenticated test client; the production UI never receives the bridge key.
  // Five unique confirmed tasks are below the default per-day limit.
  for(let i=0;i<5;i++){
    const r=await fetch(`http://127.0.0.1:${port}/api/bridge/events`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${bridgeToken}`},body:JSON.stringify({eventId:`test-task-event-${i}`,eventType:'AGENT_TASK_COMPLETED',timestamp:new Date().toISOString(),source:'browser-test',payload:{taskId:`task-${i}`,success:true}})});
    assert.equal(r.status,200,'evento autorizado com consentimento de entrada');
    assert.equal(Object.hasOwn(await r.json(),'state'),false,'resposta não expõe estado');
  }
  for(let i=0;i<3;i++){
    await page.click('[data-action="LEARN"]');
    await page.waitForFunction(()=>document.querySelector('[data-action="LEARN"]').getAttribute('aria-disabled') !== 'true');
  }
  await page.waitForFunction(()=>Number(document.querySelector('#level').textContent)>=2,{timeout:10000});
  await page.waitForFunction(()=>document.querySelector('#pet-video').getAttribute('src')?.includes('milestone_video'),{timeout:10000});
  assert.equal(await page.$eval('#pet-video',e=>e.loop),false,'milestone reproduz uma vez');
  await page.waitForFunction(()=>document.querySelector('#pet-video').getAttribute('src')?.includes('idle_video'),{timeout:10000});
  await page.reload({waitUntil:'networkidle0'});
  assert.equal(await page.$eval('#habitat-card',e=>e.dataset.theme),'SKY','personalização persiste ao recarregar');
  assert.equal(await page.$eval('#habitat-center',e=>e.dataset.fit),'FILL');
  assert.ok(Number(await page.$eval('#level',e=>e.textContent))>=2,'nível persiste ao recarregar');
  // Cover the remaining visible actions with real server-side consequences.
  let energy=Number(await page.$eval('#energy-value',e=>e.textContent));
  await page.click('[data-action="REST"]');
  await page.waitForFunction(previous=>Number(document.querySelector('#energy-value').textContent)>previous,{},energy);
  energy=Number(await page.$eval('#energy-value',e=>e.textContent));
  await page.click('[data-action="EXPLORE"]');
  await page.waitForFunction(previous=>Number(document.querySelector('#energy-value').textContent)<previous,{},energy);
  const xpBeforeCreate=Number(await page.$eval('#xp-current',e=>e.textContent.replace(/\D/g,'')));
  await page.click('[data-action="CREATE"]');
  await page.waitForFunction(previous=>Number(document.querySelector('#xp-current').textContent.replace(/\D/g,''))>previous,{},xpBeforeCreate);
  await page.click('[data-view="diary"]');
  let executions=await page.$$eval('#autonomy-history .history-row',rows=>rows.length);
  for (const activity of ['DREAM','EXPLORE','EXPERIMENT','JOURNAL']) {
    await page.click(`[data-auto="${activity}"]`);
    executions++;
    await page.waitForFunction(expected=>document.querySelectorAll('#autonomy-history .history-row').length>=expected,{},executions);
  }
  // Revoke input consent through the UI; the same bridge key stops working.
  await page.click('[data-open="settings"]');
  await page.waitForSelector('#dialog-settings[open]');
  assert.equal(await page.$eval('#bridge-receive',e=>e.checked),true);
  await page.click('#bridge-receive');
  consentSaved=page.waitForResponse(r=>r.url().endsWith('/api/bridge/consent') && r.request().method()==='POST');
  await page.click('#bridge-save');
  assert.deepEqual((await (await consentSaved).json()).consent,{receiveEvents:false,shareData:false});
  const denied=await fetch(`http://127.0.0.1:${port}/api/bridge/events`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':`Bearer ${bridgeToken}`},body:JSON.stringify({eventId:'revoked',eventType:'APPROVAL_GRANTED',timestamp:new Date().toISOString(),source:'browser-test',payload:{}})});
  assert.equal(denied.status,403,'revogação impede novos eventos');
  // Turn the real scheduler on and then off; cancellation clears the next run.
  assert.equal(await page.$eval('#auto-enabled',e=>e.checked),false);
  await page.click('.switch span');
  let saved=page.waitForResponse(r=>r.url().endsWith('/api/config') && r.request().method()==='POST');
  await page.click('#settings-form button[type="submit"]');
  let result=await (await saved).json();
  assert.equal(result.state.autonomy.enabled,true);
  assert.ok(result.state.autonomy.nextRunAt);
  await page.waitForFunction(()=>!document.querySelector('#settings-form button[type="submit"]').disabled);
  await page.click('.switch span');
  saved=page.waitForResponse(r=>r.url().endsWith('/api/config') && r.request().method()==='POST');
  await page.click('#settings-form button[type="submit"]');
  result=await (await saved).json();
  assert.equal(result.state.autonomy.enabled,false);
  assert.equal(result.state.autonomy.nextRunAt,null);
  await page.waitForFunction(()=>!document.querySelector('#settings-form button[type="submit"]').disabled);
  await page.click('#dialog-settings [data-close]');
  await page.setViewport({width:390,height:844,deviceScaleFactor:1});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'sem overflow horizontal no celular');
  await page.click('[data-view="memory"]');
  assert.equal(await page.$eval('#view-memory',e=>!e.hidden),true);
  assert.equal(await page.$eval('#toast-region',e=>getComputedStyle(e).pointerEvents),'none','notificações não devem bloquear cliques');
  assert.ok(await page.$$eval('#toast-region .toast',items=>items.length<=3),'o número de notificações simultâneas deve ser limitado');
  const memoryCount=Number(await page.$eval('#memory-count',e=>e.textContent));
  assert.ok(memoryCount>1,'as ações devem criar memórias reais');
  page.once('dialog',dialog=>dialog.accept());
  await page.click('#memory-list [data-delete-memory]');
  await page.waitForFunction(expected=>Number(document.querySelector('#memory-count').textContent)===expected,{},memoryCount-1);
  const xpBeforeDelete=(await page.evaluate(()=>fetch('/api/state',{headers:{'X-Pet-Request':'1'}}).then(r=>r.json()))).state.xp;
  page.once('dialog',dialog=>dialog.accept());
  await page.click('#delete-all');
  await page.waitForFunction(()=>document.querySelector('#memory-count').textContent==='0');
  const xpAfterDelete=(await page.evaluate(()=>fetch('/api/state',{headers:{'X-Pet-Request':'1'}}).then(r=>r.json()))).state.xp;
  assert.equal(xpAfterDelete,xpBeforeDelete,'apagar memórias não deve apagar XP');
  const ownerCookie=(await page.cookies()).find(cookie=>cookie.name==='muse_owner');
  assert.ok(ownerCookie && ownerCookie.httpOnly && ownerCookie.sameSite==='Strict','sessão usa cookie HttpOnly e SameSite=Strict');
  await page.click('.top-settings');
  await page.waitForSelector('#dialog-settings[open]');
  assert.equal(await page.evaluate(()=>document.querySelector('#dialog-settings').getBoundingClientRect().width<=innerWidth),true,'configurações cabem no celular');
  await page.click('#bridge-share');
  consentSaved=page.waitForResponse(r=>r.url().endsWith('/api/bridge/consent') && r.request().method()==='POST');
  await page.click('#bridge-save');
  assert.equal((await (await consentSaved).json()).consent.shareData,true);
  assert.equal((await fetch(`http://127.0.0.1:${port}/api/bridge/context`,{headers:{'Authorization':`Bearer ${bridgeToken}`}})).status,200);
  await Promise.all([page.waitForNavigation({waitUntil:'networkidle0'}),page.click('#owner-logout')]);
  await page.waitForSelector('#dialog-login[open]');
  assert.equal(await page.evaluate(()=>document.querySelector('#dialog-login').getBoundingClientRect().width<=innerWidth),true,'desbloqueio cabe no celular');
  assert.equal((await fetch(`http://127.0.0.1:${port}/api/bridge/context`,{headers:{'Authorization':`Bearer ${bridgeToken}`}})).status,403,'bloqueio revoga compartilhamento');
  assert.deepEqual(external,[],'nenhuma solicitação externa ou API paga');
  assert.deepEqual(errors,[],'nenhum erro de console ou página');
  console.log('OK · sessão local; consentimento e revogação; desktop e celular; ações; 6 atributos; privacidade; autonomia; exclusão de memórias; vídeo neutro e milestone; sem chamadas externas.');
})().catch(error=>{console.error(error.stack || error);process.exitCode=1;}).finally(async()=>{
  if(browser) await browser.close(); server.kill('SIGTERM'); fs.rmSync(temp,{recursive:true,force:true});
});
