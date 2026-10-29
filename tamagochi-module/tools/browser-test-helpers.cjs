/* Test-only response gate. The local server has already produced the response;
 * only delivery to the UI is delayed. Never installed in the shipped web page. */
'use strict';

async function holdOneResponse(page, pattern) {
  const fragment = pattern.replaceAll('*', '');
  await page.evaluate(fragment => {
    if (window.__heldTestResponse) throw new Error('Já há uma resposta de teste aguardando liberação.');
    const original = window.fetch;
    const held = {claimed:false, ready:false, body:null, release:null};
    window.__heldTestResponse = held;
    window.fetch = async function(input, options) {
      const response = await original.call(this, input, options);
      const url = typeof input === 'string' ? input : input.url;
      if (!held.claimed && url.includes(fragment)) {
        held.claimed = true;
        window.fetch = original;
        held.body = await response.clone().json();
        await new Promise(resolve => { held.release = resolve; held.ready = true; });
      }
      return response;
    };
  }, fragment);
  const paused = page.waitForFunction(() => window.__heldTestResponse?.ready === true, {timeout:10000}).then(() => null);
  return {
    paused,
    async json() { return page.evaluate(() => window.__heldTestResponse.body); },
    async release() {
      await page.evaluate(() => {
        const held = window.__heldTestResponse;
        if (!held?.release) throw new Error('A resposta de teste ainda não está retida.');
        held.release();
        delete window.__heldTestResponse;
      });
    },
  };
}

module.exports = {holdOneResponse};
