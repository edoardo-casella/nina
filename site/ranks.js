// Gradi navali a DUE CARRIERE — insegne argento (marinai) / oro (comandanti).
// Modulo condiviso da skipper.html, membro.html, viaggio.html, classifica.html
// (prima era duplicato inline in ognuna: una copia era divergente e rendeva
// badge vuoti). Classic script: espone GRADES, gradeAt, starPath, rankSVG in
// scope globale. Seniority = giorni in mare.
//
// rankSVG(rank, abil): se `abil` è true ("Abilitato al comando" — ha la patente
// ma non ha ancora comandato, resta nel ramo marinaio) le insegne del ramo
// marinaio si disegnano in ORO invece che in argento, con un arco di comando
// tratteggiato sotto: stesso grado, carriera di plancia.
const GRADES = {
  marinaio: [[0, "mozzo", "Mozzo"], [7, "marinaio", "Marinaio"], [20, "marinaio-scelto", "Marinaio scelto"], [45, "nostromo", "Nostromo"], [80, "sottoten", "Sottotenente di vascello"], [130, "tenente", "Tenente di vascello"]],
  comandante: [[0, "cap-corvetta", "Capitano di corvetta"], [70, "cap-fregata", "Capitano di fregata"], [140, "cap-vascello", "Capitano di vascello"], [220, "contrammiraglio", "Contrammiraglio"], [280, "ammiraglio", "Ammiraglio"], [560, "grande-ammiraglio", "Grande Ammiraglio"]],
  abilitato: [[0, "abilitato", "Abilitato al comando"]],
};
function gradeAt(track, days) { const L = GRADES[track] || GRADES.marinaio; let g = L[0]; for (const s of L) if (days >= s[0]) g = s; return g; }
function starPath(cx, cy, r) { let p = ""; for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + i * Math.PI / 5, rr = i % 2 ? r * 0.4 : r; p += (i ? "L" : "M") + (cx + rr * Math.cos(a)).toFixed(1) + " " + (cy + rr * Math.sin(a)).toFixed(1); } return p + "Z"; }
function rankSVG(r, abil) {
  const G = "#C9A227", S = "#AEB6BD", E = "rgba(0,0,0,.35)";
  const M = abil ? G : S;   // colore delle insegne del ramo marinaio (oro se abilitato al comando)
  const open = '<svg viewBox="0 0 44 24" class="ins">';
  const bar = (x, c) => `<rect x="${x}" y="4.5" width="5.5" height="15" rx="2" fill="${c}" stroke="${E}" stroke-width=".6"/>`;
  const chev = (cy, c) => `<path d="M13,${cy + 5} L22,${cy} L31,${cy + 5}" fill="none" stroke="${c}" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>`;
  const leaf = c => `<g transform="translate(22,12)"><path d="M0,-9 C3.2,-5 7,-4 5.6,0 C8,1.6 6.6,6 3,6.6 C3.6,9 0,9 0,9.6 C0,9 -3.6,9 -3,6.6 C-6.6,6 -8,1.6 -5.6,0 C-7,-4 -3.2,-5 0,-9 Z" fill="${c}" stroke="${E}" stroke-width=".6"/><path d="M0,-7 L0,8.6" stroke="${E}" stroke-width=".7" opacity=".45" fill="none"/></g>`;
  const eagle = c => `<g fill="${c}" stroke="${E}" stroke-width=".5"><path d="M22,10.6 C15,8 7,9.4 3,13 C10,12 16,12.6 22,13.6 C28,12.6 34,12 41,13 C37,9.4 29,8 22,10.6 Z"/><circle cx="22" cy="8.4" r="2"/><path d="M22,6.8 L24.2,8 L22,9.2 Z"/></g>`;
  const star = x => `<path d="${starPath(x, 12, 4.4)}" fill="${G}" stroke="${E}" stroke-width=".4"/>`;
  const anchor = c => `<g transform="translate(22,12)" fill="none" stroke="${c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="0" cy="-7" r="2.1"/><line x1="0" y1="-4.9" x2="0" y2="7.6"/><path d="M-5.6,2.6 Q0,10.6 5.6,2.6"/><line x1="-3.7" y1="-1.2" x2="3.7" y2="-1.2"/></g>`;
  // accento "abilitato al comando": arco dorato tratteggiato sotto le insegne (entro il viewBox, y<24)
  const cmd = abil ? `<path d="M13,23 Q22,23.8 31,23" fill="none" stroke="${G}" stroke-width="1" stroke-dasharray="2.4 1.9" stroke-linecap="round"/>` : "";
  switch (r) {
    case "mozzo": return open + anchor(M) + cmd + "</svg>";
    case "marinaio": return open + chev(11, M) + cmd + "</svg>";
    case "marinaio-scelto": return open + chev(8, M) + chev(14, M) + cmd + "</svg>";
    case "nostromo": return open + chev(5, M) + chev(11, M) + chev(17, M) + cmd + "</svg>";
    case "sottoten": return open + bar(19.7, M) + cmd + "</svg>";
    case "tenente": return open + bar(16.2, M) + bar(23.2, M) + cmd + "</svg>";
    case "abilitato": return open + `<circle cx="22" cy="12" r="8.5" fill="none" stroke="${G}" stroke-width="1.4" stroke-dasharray="2.8 2.3"/>` + anchor(G) + "</svg>";
    case "cap-corvetta": return open + leaf(G) + "</svg>";
    case "cap-fregata": return open + eagle(G) + "</svg>";
    case "cap-vascello": return open + star(22) + "</svg>";
    case "contrammiraglio": return open + star(15) + star(29) + "</svg>";
    case "ammiraglio": return open + [7, 18, 29, 40].map(star).join("") + "</svg>";
    case "grande-ammiraglio": return open + `<ellipse cx="22" cy="12" rx="21" ry="11" fill="none" stroke="${G}" stroke-width="1" opacity=".65"/>` + [7, 18, 29, 40].map(star).join("") + "</svg>";
    default: return open + `<circle cx="22" cy="12" r="3.4" fill="none" stroke="${S}" stroke-width="1.5" opacity=".55"/></svg>`;
  }
}
