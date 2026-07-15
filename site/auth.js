// Area riservata Crewin — modulo condiviso (vanilla, zero build).
// Carica supabase-js dal CDN SOLO se config.js è compilato; altrimenti ogni
// funzione degrada a "non configurato" e le pagine restano quelle pubbliche.
// Login: magic link via email (PKCE) → auth-callback.html (query ?code=,
// MAI hash: il sito usa già location.hash per il routing dei profili).
(function () {
  const cfg = window.NINA_CONFIG || {};
  const enabled = !!(cfg.SUPABASE_URL && cfg.SUPABASE_ANON_KEY);
  let clientP = null;

  function client() {
    if (!enabled) return Promise.resolve(null);
    if (!clientP) clientP = new Promise(resolve => {
      const mk = () => resolve(window.supabase.createClient(cfg.SUPABASE_URL, cfg.SUPABASE_ANON_KEY,
        { auth: { flowType: "pkce", detectSessionInUrl: true } }));
      if (window.supabase) return mk();
      const s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js";
      s.onload = mk;
      s.onerror = () => resolve(null);   // CDN giù / offline: area riservata non disponibile
      document.head.appendChild(s);
    });
    return clientP;
  }

  async function session() {
    const c = await client(); if (!c) return null;
    return (await c.auth.getSession()).data.session || null;
  }

  // {session, member}: member è la riga in members (RLS: solo la propria).
  // member.status !== 'approved' ⇒ niente dati riservati (lo garantisce RLS,
  // qui serve solo per scegliere il messaggio giusto in UI).
  async function me() {
    const c = await client(); if (!c) return { session: null, member: null };
    const s = (await c.auth.getSession()).data.session;
    if (!s) return { session: null, member: null };
    const { data } = await c.from("members").select("crew_id,email,role,status").limit(1);
    return { session: s, member: (data && data[0]) || null };
  }

  async function approvedMember() {
    const { member } = await me();
    return member && member.status === "approved" ? member : null;
  }

  // magic link: atterra su auth-callback.html accanto alla pagina corrente
  // (funziona sia su crewin.it/ sia su github.io/nina/)
  async function signIn(email) {
    const c = await client(); if (!c) return { error: { message: "Area riservata non configurata." } };
    return c.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: new URL("auth-callback.html", location.href).href },
    });
  }

  async function signOut() {
    const c = await client(); if (c) await c.auth.signOut();
  }

  // blob riservato ('conti' | 'arrivi') — null se non autorizzati (0 righe da RLS)
  async function blob(key) {
    const c = await client(); if (!c) return null;
    const { data } = await c.from("private_blobs").select("payload,updated_at").eq("key", key).limit(1);
    return (data && data[0] && data[0].payload) || null;
  }

  // tutte le schede profilo come mappa crew_id → riga (solo membri approvati)
  async function profilesMap() {
    const c = await client(); if (!c) return null;
    const { data } = await c.from("profiles").select("*");
    if (!data || !data.length) return null;
    const m = {}; data.forEach(r => { m[r.crew_id] = r; });
    return m;
  }

  window.ninaAuth = { enabled, client, session, me, approvedMember, signIn, signOut, blob, profilesMap };
})();
