// Oroscopo di bordo: segno da giorno+mese (mai l'anno) + contenuto scherzoso
// generato in modo deterministico (stesso giorno+segno = sempre lo stesso risultato,
// nessuna rete, nessun servizio esterno). Tema: barca a vela, non presa sul serio.
(function () {
  // [segno, inizio MMGG, fine MMGG] — Capricorno "avvolge" il capodanno (inizio > fine).
  const RANGES = [
    ["ariete", 321, 419], ["toro", 420, 520], ["gemelli", 521, 620],
    ["cancro", 621, 722], ["leone", 723, 822], ["vergine", 823, 922],
    ["bilancia", 923, 1022], ["scorpione", 1023, 1121], ["sagittario", 1122, 1221],
    ["capricorno", 1222, 119], ["acquario", 120, 218], ["pesci", 219, 320],
  ];

  function signFromMD(mm, gg) {
    const v = mm * 100 + gg;
    for (const [sign, start, end] of RANGES) {
      if (start <= end) { if (v >= start && v <= end) return sign; }
      else if (v >= start || v <= end) return sign;
    }
    return null;
  }
  // "MM-GG" (come salvato in Supabase profiles.birth_md) -> segno
  function signFromMd(birthMd) {
    const m = (birthMd || "").match(/^(\d{2})-(\d{2})$/);
    return m ? signFromMD(+m[1], +m[2]) : null;
  }

  const SIGN_META = {
    ariete:     { emoji: "♈", element: "fuoco", label: "Ariete",     boat: "Il primo a tuffarsi, l'ultimo a mollare il timone." },
    toro:       { emoji: "♉", element: "terra", label: "Toro",       boat: "Se ha trovato la sua cuccetta comoda, non la cambia per nessuno." },
    gemelli:    { emoji: "♊", element: "aria",  label: "Gemelli",    boat: "Parla con tutta la ciurma nella stessa mattinata." },
    cancro:     { emoji: "♋", element: "acqua", label: "Cancro",     boat: "Il cuoco non ufficiale, cura tutti come fossero famiglia." },
    leone:      { emoji: "♌", element: "fuoco", label: "Leone",      boat: "Vuole guidare la manovra e farsi vedere al timone." },
    vergine:    { emoji: "♍", element: "terra", label: "Vergine",    boat: "Controlla i nodi due volte, per sicurezza." },
    bilancia:   { emoji: "♎", element: "aria",  label: "Bilancia",   boat: "Media tra chi vuole fare rotta e chi vuole restare in rada." },
    scorpione:  { emoji: "♏", element: "acqua", label: "Scorpione",  boat: "Sa già tutti i segreti dell'equipaggio entro il terzo giorno." },
    sagittario: { emoji: "♐", element: "fuoco", label: "Sagittario", boat: "Propone sempre la cala più lontana e più bella." },
    capricorno: { emoji: "♑", element: "terra", label: "Capricorno", boat: "Ha già calcolato la ripartizione delle spese al centesimo." },
    acquario:   { emoji: "♒", element: "aria",  label: "Acquario",   boat: "L'unico che si informa sulle correnti prima di tuffarsi." },
    pesci:      { emoji: "♓", element: "acqua", label: "Pesci",      boat: "Il primo ad addormentarsi cullato dalle onde, ovunque sia." },
  };
  const SIGN_INDEX = Object.keys(SIGN_META).reduce((o, s, i) => (o[s] = i, o), {});

  const FARE = [
    "Offri il caffè al timoniere di turno.", "Fai il bagno prima che si svegli tutta la ciurma.",
    "Proponiti per la spesa al prossimo porto.", "Insegna un nodo a chi non lo sa ancora.",
    "Guarda il tramonto senza il telefono in mano.", "Aiuta in cambusa senza che te lo chiedano.",
    "Fai una foto che finirà sicuramente nel gruppo.", "Racconta un aneddoto vecchio all'equipaggio nuovo.",
    "Prova a issare la randa almeno una volta.", "Nuota fino alla prua e ritorno.",
    "Offri il turno di guardia a chi ha dormito peggio.", "Metti in ordine la tua cuccetta, per una volta.",
    "Fai amicizia con chi conosci meno a bordo.", "Chiedi allo skipper una manovra da provare.",
    "Balla sul pozzetto quando parte la playlist giusta.", "Prova il piatto nuovo del cuoco di giornata senza storcere il naso.",
  ];
  const EVITARE = [
    "Litigare per l'ultima branda all'ombra.", "Finire l'acqua della doccia solare per primo.",
    "Dimenticare il costume ad asciugare sulle sartie durante la manovra.", "Fare il saccente sulle previsioni meteo.",
    "Monopolizzare la presa USB del quadro elettrico.", "Sparire proprio quando c'è da lavare i piatti.",
    "Prendere il sole nelle ore sbagliate e finire come un gambero.", "Perdere le infradito overboard (ne hai già perse troppe).",
    "Fare tardi la sera prima di una levataccia per la traversata.", "Cambiare canale alla playlist di bordo senza chiedere.",
    "Lasciare il bagnoschiuma in mare aperto — rispetta la posidonia.", "Sottovalutare quanto scotta il ponte a mezzogiorno.",
    "Promettere aiuto in manovra e poi sparire sottocoperta.", "Fidarti troppo del segnale del telefono per il meteo.",
    "Bere il primo spritz prima dell'ormeggio.", "Svegliarti tardi il giorno della sveglia all'alba per lo spot migliore.",
  ];
  const UMORE = [
    ["⚓", "Ancorato e sereno"], ["🌊", "Onda lunga, umore alto"], ["🍹", "Modalità aperitivo permanente"],
    ["🧭", "Voglia di scoprire una cala nuova"], ["😴", "Serve un pisolino post-pranzo"], ["🎶", "Playlist in loop nella testa"],
    ["🔥", "Energia da issare vele"], ["🐚", "Filosofico, guarda il mare e pensa"], ["🤙", "Rilassato oltre ogni previsione"],
    ["📸", "Vuole immortalare tutto"], ["🐟", "Pronto a tuffarsi appena si molla l'ancora"], ["☕", "Ha bisogno del primo caffè prima di parlare"],
    ["🎲", "Sente che oggi è giornata fortunata"], ["🌅", "Sveglia all'alba, umore top"], ["🥥", "Vacanza totale, zero pensieri"],
    ["🦀", "Un po' scorbutico, meglio non stuzzicarlo"],
  ];

  function daysSinceEpoch(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    return Math.floor(Date.UTC(y, m - 1, d) / 86400000);
  }

  // Deterministico: stesso (segno, giorno) -> sempre lo stesso risultato. Niente
  // Math.random, niente String.hash (instabile tra run) — solo aritmetica su interi.
  function dayHoroscope(sign, isoDate) {
    const day = daysSinceEpoch(isoDate), s = SIGN_INDEX[sign] || 0;
    const seed = day * 31 + s * 7;
    let n1 = 1 + (seed % 90);
    let n2 = 1 + ((seed * 17 + 41) % 90);
    if (n2 === n1) n2 = n2 === 90 ? 1 : n2 + 1;
    return {
      numeri: [n1, n2],
      fare: FARE[(seed * 3 + 1) % FARE.length],
      evitare: EVITARE[(seed * 5 + 2) % EVITARE.length],
      umore: UMORE[(seed * 7 + 3) % UMORE.length],
    };
  }

  // Compatibilità per elemento classico: stesso elemento = ottima; coppie
  // complementari (fuoco-aria, terra-acqua) = buona; adiacenti = così così;
  // opposti (fuoco-acqua, terra-aria) = frizione.
  // Chiavi SEMPRE in ordine alfabetico degli elementi (acqua, aria, fuoco, terra),
  // cosi' combaciano con [ea,eb].sort().join("-") qui sotto.
  const COMPAT = {
    "acqua-acqua": ["ottima", "🌊"], "aria-aria": ["ottima", "🌬️"], "fuoco-fuoco": ["ottima", "🔥"], "terra-terra": ["ottima", "🪨"],
    "acqua-terra": ["buona", "🌱"], "aria-fuoco": ["buona", "✨"],
    "acqua-aria": ["così così", "🤷"], "fuoco-terra": ["così così", "🤷"],
    "acqua-fuoco": ["scintille", "⚡"], "aria-terra": ["scintille", "⚡"],
  };
  function compatibility(signA, signB) {
    const ea = SIGN_META[signA]?.element, eb = SIGN_META[signB]?.element;
    if (!ea || !eb) return null;
    const key = [ea, eb].sort().join("-");
    const [label, emoji] = COMPAT[key] || ["così così", "🤷"];
    return { label, emoji };
  }

  window.ninaZodiac = { signFromMD, signFromMd, SIGN_META, dayHoroscope, compatibility };
})();
