# Guild GT Availability (Python + GitHub Pages)

A Python-in-the-browser (PyScript) web app for guild members to:

- select available days (Wed-Tues),
- track attacks used out of 3,
- join a guild via passcode,
- reset automatically every Wednesday at 14:00 UTC.

## Stack

- Static site on GitHub Pages
- Python frontend with PyScript
- Shared data via Supabase REST API

## 1) Configure Supabase (required for shared guild sync)

Create a project and run this SQL in Supabase SQL editor:

```sql
create table if not exists public.guild_availability (
  guild_code text not null default 'default',
  name text not null,
  week_key text not null,
  attacks_used int not null default 0,
  wed boolean not null default false,
  thur boolean not null default false,
  fri boolean not null default false,
  sat boolean not null default false,
  sun boolean not null default false,
  mon boolean not null default false,
  tues boolean not null default false,
  updated_at timestamptz not null default now(),
  primary key (guild_code, name)
);

alter table public.guild_availability add column if not exists guild_code text;
update public.guild_availability set guild_code = 'default' where guild_code is null or guild_code = '';
alter table public.guild_availability alter column guild_code set default 'default';
alter table public.guild_availability alter column guild_code set not null;
alter table public.guild_availability alter column name set not null;

create unique index if not exists guild_availability_guild_name_idx
on public.guild_availability (guild_code, name);

alter table public.guild_availability drop constraint if exists guild_availability_pkey;
alter table public.guild_availability add constraint guild_availability_pkey primary key using index guild_availability_guild_name_idx;

alter table public.guild_availability enable row level security;

drop policy if exists "Allow read to anon" on public.guild_availability;
create policy "Allow read to anon"
on public.guild_availability
for select
using (true);

drop policy if exists "Allow upsert to anon" on public.guild_availability;
create policy "Allow upsert to anon"
on public.guild_availability
for insert
with check (true);

drop policy if exists "Allow update to anon" on public.guild_availability;
create policy "Allow update to anon"
on public.guild_availability
for update
using (true)
with check (true);
```

Then edit `config.js`:

```js
window.SUPABASE_URL = "https://YOUR-PROJECT.supabase.co";
window.SUPABASE_ANON_KEY = "YOUR-ANON-KEY";
window.GUILD_PASSCODE = "optional-default-passcode";
window.GUILD_TITLE = "Your Guild GT Availability";
window.GUILD_LOGO_URL = "./assets/logo.png";
window.GUILD_BACKGROUND_URL = "./assets/background.jpg";
```

Notes:

- `GUILD_PASSCODE` can prefill the passcode input for convenience.
- Passcode is a guild namespace, not strong authentication.
- Put custom graphics into your repo (for example in `assets/`) and reference them with relative URLs.

## 2) Run locally

Open [index.html](index.html) with a local static server (recommended) and test updates.

Example with Python:

```bash
python -m http.server 8000
```

Then browse to `http://localhost:8000`.

## 3) Deploy

1. Push to `main`.
2. In GitHub repo settings, set **Pages** source to **GitHub Actions**.
3. The workflow in [.github/workflows/deploy.yml](.github/workflows/deploy.yml) deploys automatically.

## Weekly Reset Behavior

On load/sync, if a member row has an old `week_key`, the app resets:

- attacks used → `0`
- all day availability → `false`
- week key → current reset cycle start (`Wednesday 14:00 UTC`)
