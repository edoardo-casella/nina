-- Schema area riservata Crewin (crewin.it) — Supabase free tier.
-- Idempotente: si può rilanciare per intero nello SQL Editor di Supabase.
--
-- Modello: il sito resta statico e pubblico; qui vivono SOLO i dati riservati.
--   members         chi può entrare (email → crew_id), stato richiesta, ruolo admin
--   access_requests richieste di accesso dal form pubblico di unisciti.html
--   profiles        campi profilo EDITABILI dal membro (mai stats/gradi: quelli
--                   restano calcolati nel crew.json statico; mai dieta/allergie)
--   private_blobs   payload JSON riservati scritti dalla CI ('conti', 'arrivi')
--
-- Identità: auth.users si aggancia a members SOLO per email (auth.jwt()->>'email').
-- Niente user_id da mantenere, niente trigger di linkage.

-- ── Tabelle ────────────────────────────────────────────────────────────────

create table if not exists public.members (
  crew_id    text primary key,
  email      text not null unique,
  role       text not null default 'member' check (role in ('member','admin')),
  status     text not null default 'pending' check (status in ('pending','approved','blocked')),
  created_at timestamptz not null default now()
);

create table if not exists public.access_requests (
  id         bigint generated always as identity primary key,
  name       text not null,
  email      text not null,
  message    text,
  status     text not null default 'new' check (status in ('new','approved','rejected')),
  created_at timestamptz not null default now()
);

create table if not exists public.profiles (
  crew_id    text primary key,
  nick       text,
  instagram  text,
  motto      text,
  funfact    text,
  valigia    text,
  specialita text,
  esperienza text,
  ruolo      text,
  updated_at timestamptz not null default now()
);

create table if not exists public.private_blobs (
  key        text primary key,
  payload    jsonb not null,
  updated_at timestamptz not null default now()
);

-- updated_at automatico sull'editor profilo
create or replace function public.touch_updated_at() returns trigger
language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

drop trigger if exists profiles_touch on public.profiles;
create trigger profiles_touch before update on public.profiles
  for each row execute function public.touch_updated_at();

-- ── Helper per le policy (SECURITY DEFINER: evitano la ricorsione RLS) ─────

create or replace function public.current_email() returns text
language sql stable security definer set search_path = public as
$$ select coalesce(auth.jwt()->>'email', '') $$;

create or replace function public.my_crew_id() returns text
language sql stable security definer set search_path = public as
$$ select crew_id from public.members
   where email = public.current_email() and status = 'approved' limit 1 $$;

create or replace function public.is_approved() returns boolean
language sql stable security definer set search_path = public as
$$ select exists (select 1 from public.members
   where email = public.current_email() and status = 'approved') $$;

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as
$$ select exists (select 1 from public.members
   where email = public.current_email() and status = 'approved' and role = 'admin') $$;

-- ── RLS ────────────────────────────────────────────────────────────────────

alter table public.members         enable row level security;
alter table public.access_requests enable row level security;
alter table public.profiles        enable row level security;
alter table public.private_blobs   enable row level security;

-- members: ognuno vede la propria riga (anche se pending: serve alla UI per
-- dire "in attesa di approvazione"); l'admin gestisce tutto.
drop policy if exists members_select_own on public.members;
create policy members_select_own on public.members
  for select to authenticated using (email = public.current_email());

drop policy if exists members_admin_all on public.members;
create policy members_admin_all on public.members
  for all to authenticated using (public.is_admin()) with check (public.is_admin());

-- access_requests: il form pubblico può SOLO inserire; legge/aggiorna solo l'admin.
drop policy if exists access_requests_insert_public on public.access_requests;
create policy access_requests_insert_public on public.access_requests
  for insert to anon, authenticated with check (status = 'new');

drop policy if exists access_requests_admin_all on public.access_requests;
create policy access_requests_admin_all on public.access_requests
  for all to authenticated using (public.is_admin()) with check (public.is_admin());

-- profiles: i membri approvati leggono tutte le schede (è l'equipaggio),
-- ognuno aggiorna SOLO la propria; insert/gestione completa solo admin
-- (il seed passa dalla service key, che bypassa RLS).
drop policy if exists profiles_select_members on public.profiles;
create policy profiles_select_members on public.profiles
  for select to authenticated using (public.is_approved());

drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles
  for update to authenticated
  using (crew_id = public.my_crew_id()) with check (crew_id = public.my_crew_id());

-- un membro appena approvato può non avere ancora la riga: può crearla,
-- ma SOLO la propria (l'editor usa upsert)
drop policy if exists profiles_insert_own on public.profiles;
create policy profiles_insert_own on public.profiles
  for insert to authenticated with check (crew_id = public.my_crew_id());

drop policy if exists profiles_admin_all on public.profiles;
create policy profiles_admin_all on public.profiles
  for all to authenticated using (public.is_admin()) with check (public.is_admin());

-- private_blobs: sola lettura per i membri approvati; scrive solo la CI
-- (service key, bypassa RLS) o l'admin.
drop policy if exists private_blobs_select_members on public.private_blobs;
create policy private_blobs_select_members on public.private_blobs
  for select to authenticated using (public.is_approved());

drop policy if exists private_blobs_admin_all on public.private_blobs;
create policy private_blobs_admin_all on public.private_blobs
  for all to authenticated using (public.is_admin()) with check (public.is_admin());

-- ── Grants espliciti (Supabase li dà di default, qui sono documentati) ─────
grant usage on schema public to anon, authenticated;
grant select, insert, update on public.members, public.access_requests,
      public.profiles, public.private_blobs to authenticated;
grant insert on public.access_requests to anon;
