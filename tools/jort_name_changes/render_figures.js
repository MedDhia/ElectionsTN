const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
  for (const [theme, out] of [['light','sankey_noms_jort.png'], ['dark','sankey_noms_jort_sombre.png']]) {
    const p = await b.newPage({ viewport: { width: 1480, height: 1200 }, deviceScaleFactor: 2 });
    const errs = []; p.on('pageerror', e => errs.push(e.message));
    await p.goto('file://' + process.cwd() + '/_export.html');
    await p.evaluate(t => document.documentElement.setAttribute('data-theme', t), theme);
    // the renderer reads theme tokens at draw time — force a redraw under the new theme
    await p.evaluate(() => window.dispatchEvent(new Event('resize')));
    await p.waitForTimeout(600);
    await p.evaluate(() => document.fonts.ready);
    await p.waitForTimeout(500);
    const info = await p.evaluate(() => {
      const s = document.getElementById('sk');
      return { theme: document.documentElement.getAttribute('data-theme'),
               ground: getComputedStyle(document.body).backgroundColor,
               fills: [...new Set([...s.querySelectorAll('path.link')].map(n => n.getAttribute('fill')))],
               links: s.querySelectorAll('path.link').length,
               labelFill: getComputedStyle(s.querySelector('.nlabel')).fill };
    });
    await (await p.$('.wrap')).screenshot({ path: out });
    console.log(theme, JSON.stringify(info), 'errors:', errs.length ? errs : 'none');
    await p.close();
  }
  await b.close();
})();
