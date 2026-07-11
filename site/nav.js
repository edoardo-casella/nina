// Menu di navigazione globale, condiviso da tutte le pagine (incluso index).
// Inietta un bottone ☰ nella barra in alto + un overlay con tutte le sezioni.
// Nessuna dipendenza; usa le CSS var della pagina (con fallback) per il tema.
(function () {
  const LINKS = [
    ["index.html", "Plancia", "🧭"],
    ["skipper.html", "Lo skipper", "🎖️"],
    ["aneddoti.html", "Aneddoti", "📖"],
    ["viaggio.html", "I viaggi", "⛵"],
    ["paese.html", "I mari", "🌍"],
    ["mete.html", "Le mete", "🗺️"],
    ["membro.html", "La ciurma", "👥"],
    ["arrivi.html", "Arrivi & partenze", "🛟"],
    ["barca.html", "La barca", "🛥️"],
    ["guida.html", "Guida pre-partenza", "🎒"],
    ["avionica.html", "Avionica a bordo", "🚁"],
    ["foto.html", "Foto condivise", "📷"],
  ];
  const here = (location.pathname.split("/").pop() || "index.html").toLowerCase();

  const css = `
  #nina-menu-btn{font-size:1.3rem;line-height:1;background:none;border:0;cursor:pointer;color:var(--soft,#7089a0);padding:0 .35rem;display:inline-flex;align-items:center}
  #nina-menu-btn:hover{color:var(--accent,#0a7)}
  .top .wrap{justify-content:flex-start!important;gap:.55rem}
  .top .wrap .tag{margin-left:auto}
  #nina-nav{position:fixed;inset:0;z-index:90;background:rgba(3,7,14,.55);backdrop-filter:blur(2px);display:none}
  #nina-nav.on{display:block}
  .nn-panel{position:absolute;top:0;left:0;bottom:0;width:min(80vw,330px);overflow-y:auto;
    background:var(--paper,#fff);border-right:1px solid var(--hair,#c4d2df);padding:1.1rem .8rem 2rem;box-shadow:3px 0 26px rgba(0,0,0,.35)}
  .nn-hd{font:700 .66rem/1 var(--display,system-ui);letter-spacing:.2em;text-transform:uppercase;color:var(--gold,#B8860B);margin:.3rem .4rem 1rem}
  .nn-a{display:flex;align-items:center;gap:.75rem;padding:.72rem .6rem;border-radius:9px;text-decoration:none;color:var(--ink,#0B1320);font-weight:600;font-size:1rem}
  .nn-a:hover{background:var(--sea-1,#EEF4F9)}
  .nn-a.on{background:var(--sea-2,#D8E4EE);color:var(--accent,#006B9F)}
  .nn-ic{width:1.6rem;text-align:center;font-size:1.1rem;flex:none}
  .nn-x{position:absolute;top:.6rem;right:.7rem;font-size:1.5rem;background:none;border:0;color:var(--soft,#7089a0);cursor:pointer;line-height:1}
  @media(prefers-reduced-motion:reduce){*{transition:none!important}}`;
  const style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);

  const ov = document.createElement("div");
  ov.id = "nina-nav";
  ov.innerHTML = `<div class="nn-panel"><button class="nn-x" aria-label="chiudi">✕</button><div class="nn-hd">Naviga · Niña</div>` +
    LINKS.map(([h, t, ic]) => `<a class="nn-a${h === here ? " on" : ""}" href="${h}"><span class="nn-ic">${ic}</span>${t}</a>`).join("") +
    `</div>`;
  document.body.appendChild(ov);
  const open = () => ov.classList.add("on");
  const close = () => ov.classList.remove("on");
  ov.addEventListener("click", e => { if (e.target === ov || e.target.classList.contains("nn-x")) close(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") close(); });

  const btn = document.createElement("button");
  btn.id = "nina-menu-btn"; btn.type = "button"; btn.setAttribute("aria-label", "menu"); btn.textContent = "☰";
  btn.addEventListener("click", open);
  const bar = document.querySelector(".top .wrap") || document.querySelector("header .hdr") || document.querySelector("header");
  if (bar) bar.insertBefore(btn, bar.firstChild);
  else { btn.style.cssText = "position:fixed;top:.7rem;left:.7rem;z-index:91"; document.body.appendChild(btn); }
  window.ninaMenu = { open, close };
})();
