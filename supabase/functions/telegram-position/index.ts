// Webhook Telegram della Plancia: condividi la posizione (pin o live) in chat
// col bot o nel gruppo equipaggio → la funzione lancia il workflow_dispatch di
// "Aggiorna briefing" (update.yml) con lat/lon/luogo → il workflow scrive
// data/position.json, rigenera il sito e lo pubblica. La Plancia mostra
// "GPS · X h fa" finché la posizione ha meno di 24 h (publish.py).
//
// Deploy:  npx supabase functions deploy telegram-position --no-verify-jwt
// Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_SECRET, GH_PAT (fine-grained, solo
//          repo nina, permesso Actions:write), ALLOWED_CHAT_IDS (csv).
// Webhook: setWebhook con secret_token=TELEGRAM_SECRET e
//          allowed_updates=["message","edited_message"].
const BOT = Deno.env.get("TELEGRAM_BOT_TOKEN")!;
const SECRET = Deno.env.get("TELEGRAM_SECRET")!;
const GH_PAT = Deno.env.get("GH_PAT")!;
const ALLOWED = (Deno.env.get("ALLOWED_CHAT_IDS") ?? "")
  .split(",").map((s) => s.trim()).filter(Boolean);
// auto-iniettate da Supabase: servono solo per la riga di throttle in bot_state
const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SB_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const THROTTLE_MIN = 10; // live location: max un dispatch ogni 10 minuti
const MAX_AGE_MIN = 15;  // update più vecchi = coda Telegram riconsegnata: mai
                         // pubblicarli come posizione "fresca" (at = now nel workflow)
const HELP_TEXT = "Condividi la posizione (📎 → Posizione) e aggiorno la Plancia " +
  "su everywaves.com. Vale anche la posizione live: la seguo ogni ~10 minuti.";

const ok = () => new Response("ok"); // sempre 200 dopo il check del secret:
                                     // un non-2xx fa ritentare Telegram per ore

const send = (chat_id: number | string, text: string, reply_to?: number) =>
  fetch(`https://api.telegram.org/bot${BOT}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id, text, reply_to_message_id: reply_to }),
  }).catch(() => {});

// "luogo" finisce interpolato in un printf shell dentro update.yml: whitelist
// stretta di caratteri, la funzione è il gate anti-injection.
const sanitizeLuogo = (s: string) =>
  s.replace(/[^\p{L}\p{N} .,'()\/-]/gu, "").slice(0, 60).trim();

const SB_HEADERS = {
  apikey: SB_KEY,
  authorization: `Bearer ${SB_KEY}`,
  "content-type": "application/json",
};

// fallback in-memory: se bot_state non esiste ancora (schema.sql non
// rilanciato) il throttle regge comunque finché l'istanza resta calda
let memTs = 0;

async function lastDispatch(): Promise<number> {
  try {
    const r = await fetch(
      `${SB_URL}/rest/v1/bot_state?key=eq.telegram_position&select=value`,
      { headers: SB_HEADERS },
    );
    if (!r.ok) return memTs;
    const rows = await r.json();
    return Math.max(Number(rows?.[0]?.value?.ts) || 0, memTs);
  } catch {
    return memTs; // senza stato meglio un dispatch in più che uno perso
  }
}

async function markDispatch(): Promise<void> {
  memTs = Date.now();
  await fetch(`${SB_URL}/rest/v1/bot_state`, {
    method: "POST",
    headers: { ...SB_HEADERS, prefer: "resolution=merge-duplicates" },
    body: JSON.stringify([{
      key: "telegram_position",
      value: { ts: memTs },
      updated_at: new Date().toISOString(),
    }]),
  }).catch(() => {});
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("telegram-position");
  if (req.headers.get("x-telegram-bot-api-secret-token") !== SECRET) {
    return new Response("forbidden", { status: 401 });
  }

  const update = await req.json().catch(() => null);
  const msg = update?.message ?? update?.edited_message;
  const isEdit = Boolean(update?.edited_message);
  if (!msg?.chat) return ok();

  const chatId = String(msg.chat.id);

  // /id risponde OVUNQUE (anche chat non abilitate, anche gruppi con privacy
  // mode attiva: i comandi arrivano sempre): serve per l'onboarding, il numero
  // va poi messo in ALLOWED_CHAT_IDS
  if (msg.text && /^\/id(@\w+)?$/.test(msg.text.trim())) {
    await send(chatId, `Chat ID: ${chatId}`, msg.message_id);
    return ok();
  }

  if (!ALLOWED.includes(chatId)) {
    console.log("chat non in allow-list, ignoro:", chatId);
    if (msg.chat.type === "private" && msg.text) {
      await send(chatId, `Questa chat non è ancora abilitata. Chat ID: ${chatId}`);
    }
    return ok();
  }

  if (!msg.location) { // testo o altro: aiuto in privato, silenzio nei gruppi
    if (msg.chat.type === "private" && msg.text) await send(chatId, HELP_TEXT);
    return ok();
  }

  const tsSec = isEdit ? (msg.edit_date ?? msg.date) : msg.date;
  if (Date.now() / 1000 - tsSec > MAX_AGE_MIN * 60) return ok();

  if (isEdit && Date.now() - await lastDispatch() < THROTTLE_MIN * 60_000) {
    return ok(); // live location: edit troppo ravvicinato, throttled
  }

  const lat = Number(msg.location.latitude), lon = Number(msg.location.longitude);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) ||
    Math.abs(lat) > 90 || Math.abs(lon) > 180) return ok();
  // "" → publish.py mette "posizione GPS" (venue = unico nome in-band possibile)
  const luogo = sanitizeLuogo(update?.message?.venue?.title ?? "");

  const r = await fetch(
    "https://api.github.com/repos/edoardo-casella/nina/actions/workflows/update.yml/dispatches",
    {
      method: "POST",
      headers: {
        authorization: `Bearer ${GH_PAT}`,
        accept: "application/vnd.github+json",
        "x-github-api-version": "2022-11-28",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: { lat: lat.toFixed(5), lon: lon.toFixed(5), luogo },
      }),
    },
  );

  await markDispatch();
  if (r.status === 204) {
    if (!isEdit) { // pin statico: conferma; edit live: silenzio in chat
      await send(chatId,
        `⚓ Posizione ricevuta${luogo ? ` (${luogo})` : ""}: ${lat.toFixed(4)}, ${lon.toFixed(4)}.` +
        (msg.location.live_period
          ? " Seguo la posizione live: aggiorno la Plancia ogni ~10 min."
          : " La Plancia si aggiorna in ~2 minuti."), msg.message_id);
    }
  } else {
    console.error("dispatch fallito", r.status, await r.text());
    if (!isEdit) {
      await send(chatId, "⚠️ Non sono riuscito ad aggiornare la Plancia, riprova tra un minuto.");
    }
  }
  return ok();
});
