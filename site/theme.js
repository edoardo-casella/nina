/* Tema notte/giorno condiviso per le sottopagine (skipper, barca, avionica,
   guida, arrivi, membro, viaggio). La home ha il suo toggle nell'header ma
   usa la STESSA chiave localStorage "nina_theme", quindi la preferenza è unica.
   Trucco: inietto la palette sotto html[data-theme=...] con specificità più
   alta del @media prefers-color-scheme, così il toggle vince sempre. Niente
   modifiche CSS per pagina: basta includere questo script. */
(function () {
  var KEY = "nina_theme";
  var mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : { matches: false, addEventListener: function () {} };

  // palette canonica (identica alle 6 sottopagine)
  var CSS = "" +
    "html[data-theme=\"light\"]{--paper:#FBFDFF;--sea-1:#EEF4F9;--sea-2:#D8E4EE;--panel:#FFFFFF;--ink:#0B1320;--soft:#3E556B;--hair:#C4D2DF;--accent:#006B9F;--gold:#B8860B;--gold-2:#E5C158;--verde:#0A7A43;--rosso:#C0392B;--magenta:#C2185B;}" +
    "html[data-theme=\"dark\"]{--paper:#070E1A;--sea-1:#101E33;--sea-2:#1C3552;--panel:#0C1728;--ink:#DCE7F5;--soft:#8299B4;--hair:#22384F;--accent:#35C4E7;--gold:#E5C158;--gold-2:#FBE7A8;--verde:#2FBF71;--rosso:#E2536F;--magenta:#E8536F;}" +
    "#nina-theme-btn{position:fixed;right:.85rem;bottom:.85rem;z-index:60;width:2.7rem;height:2.7rem;border-radius:50%;border:1px solid var(--hair);background:var(--panel);color:var(--ink);font-size:1.15rem;line-height:1;cursor:pointer;box-shadow:0 3px 14px rgba(0,0,0,.28);display:flex;align-items:center;justify-content:center;transition:transform .12s}" +
    "#nina-theme-btn:hover{transform:scale(1.07)}" +
    "@media(prefers-reduced-motion:reduce){#nina-theme-btn{transition:none}}";

  var st = document.createElement("style");
  st.textContent = CSS;
  (document.head || document.documentElement).appendChild(st);

  function mode() { try { return localStorage.getItem(KEY) || "auto"; } catch (e) { return "auto"; } }
  function isDark(m) { return m === "dark" || (m === "auto" && mq.matches); }
  function apply() {
    var m = mode(), dark = isDark(m);
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = dark ? "#0A1424" : "#FBFDFF";
    var btn = document.getElementById("nina-theme-btn");
    if (btn) { btn.textContent = m === "auto" ? "🌗" : (dark ? "🌙" : "☀️"); btn.title = "Tema: " + m + " — tocca per cambiare"; }
  }
  function cycle() {
    var next = { auto: "light", light: "dark", dark: "auto" }[mode()] || "auto";
    try { localStorage.setItem(KEY, next); } catch (e) {}
    apply();
  }
  apply(); // subito (in <head>): setta data-theme prima del primo paint

  function inject() {
    if (document.getElementById("nina-theme-btn")) { apply(); return; }
    var b = document.createElement("button");
    b.id = "nina-theme-btn"; b.type = "button";
    b.setAttribute("aria-label", "Cambia tema");
    b.addEventListener("click", cycle);
    document.body.appendChild(b);
    apply();
  }
  if (document.body) inject();
  else document.addEventListener("DOMContentLoaded", inject);

  if (mq.addEventListener) mq.addEventListener("change", apply);
  window.addEventListener("storage", function (e) { if (e.key === KEY) apply(); });
})();
