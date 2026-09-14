/* =============================================================
   DOCS DOCS — runtime compartilhado
   Tema light/dark, copy de código, smooth scroll, TOC highlight,
   compartilhar e toast. Idêntico ao do design system de referência.
   ============================================================= */
(() => {
  const KEY = 'kinto-theme';
  const root = document.documentElement;
  const saved = localStorage.getItem(KEY);
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const initial = saved || (prefersDark ? 'dark' : 'light');
  root.setAttribute('data-theme', initial);

  // Toggle de tema
  document.querySelectorAll('.theme-toggle button').forEach(b => {
    b.addEventListener('click', () => {
      const next = b.getAttribute('data-set');
      root.classList.add('theme-switching');
      root.setAttribute('data-theme', next);
      localStorage.setItem(KEY, next);
      requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('theme-switching')));
    });
  });

  // Copy de blocos de código
  document.querySelectorAll('.copy[data-copy]').forEach(btn => {
    btn.addEventListener('click', () => {
      const el = document.getElementById(btn.getAttribute('data-copy'));
      if (el) navigator.clipboard.writeText(el.innerText).then(() => showToast('Código copiado ✓'));
    });
  });

  // Smooth scroll
  document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', e => {
      const href = a.getAttribute('href');
      if (href.length > 1) {
        const t = document.querySelector(href);
        if (t) { e.preventDefault(); t.scrollIntoView({ behavior: 'smooth', block: 'start' }); history.replaceState(null, '', href); }
      }
    });
  });

  // Highlight do TOC conforme a rolagem.
  //
  // Só o TOC: os links da SIDEBAR apontam para outras páginas, e marcá-los por
  // âncora apagaria o destaque da página atual.
  //
  // O listener vai no documento E no shell porque quem rola depende do tamanho
  // da tela: no desktop é o shell (colunas com sidebar sticky), no celular é a
  // página. Evento de scroll de elemento não borbulha — sem os dois, o TOC
  // ficava parado no primeiro item.
  const tocLinks = document.querySelectorAll('.toc a');
  const sections = Array.from(document.querySelectorAll('h2[id], h3[id]'));
  const marcarSecaoAtual = () => {
    let atual = sections[0]?.id;
    for (const s of sections) { if (s.getBoundingClientRect().top < 100) atual = s.id; }
    tocLinks.forEach(l => l.classList.toggle('active', l.getAttribute('href') === '#' + atual));
  };
  document.addEventListener('scroll', marcarSecaoAtual, { passive: true });
  document.querySelector('.shell')?.addEventListener('scroll', marcarSecaoAtual, { passive: true });
  marcarSecaoAtual();

  // Codetabs — abas de código por linguagem (Python/Java/C#), escala p/ N grupos
  document.querySelectorAll('.codetabs').forEach(group => {
    const tabs = Array.from(group.querySelectorAll('.codetab'));
    const panels = Array.from(group.querySelectorAll('.codetabs-panel'));
    tabs.forEach((tab, i) => tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      panels[i]?.classList.add('active');
    }));
    group.querySelector('.codetabs-copy')?.addEventListener('click', () => {
      const active = group.querySelector('.codetabs-panel.active');
      if (active) navigator.clipboard.writeText(active.innerText).then(() => showToast('Código copiado ✓'));
    });
  });

  const toast = document.getElementById('toast');
  let tt;
  window.showToast = function (m) {
    toast.textContent = m; toast.classList.add('on');
    clearTimeout(tt); tt = setTimeout(() => toast.classList.remove('on'), 1600);
  };
})();
