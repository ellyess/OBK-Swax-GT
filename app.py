# pyright: reportMissingImports=false
from datetime import datetime, timezone
import json
import asyncio
from html import escape
from urllib.parse import quote

try:
    from js import window
    from pyodide.http import pyfetch
    from pyscript import document
except ImportError:  # Local editor/runtime fallback
    window = None
    pyfetch = None
    document = None

DAYS = ["wed", "thur", "fri", "sat", "sun", "mon", "tues"]
TABLE = "guild_availability"

state = {"rows": []}


def current_week_key() -> str:
    now = datetime.now(timezone.utc).date()
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def clamp_attacks(value: int) -> int:
    return max(0, min(3, int(value)))


def empty_days() -> dict:
    return {day: False for day in DAYS}


def set_status(message: str):
    document.getElementById("status").innerText = message


def normalize_passcode(raw: str) -> str:
    return str(raw or "").strip()


def get_default_passcode() -> str:
    return normalize_passcode(getattr(window, "GUILD_PASSCODE", ""))


def get_active_passcode() -> str:
    return normalize_passcode(document.getElementById("guild-passcode").value)


def get_configured_members() -> list[str]:
    members = getattr(window, "GUILD_MEMBERS", [])
    if members is None:
        return []
    return [str(member).strip() for member in members if str(member).strip()]


def get_member_lookup() -> dict[str, str]:
    return {member.lower(): member for member in get_configured_members()}


def resolve_allowed_member_name(raw_name: str) -> str | None:
    cleaned = str(raw_name or "").strip()
    if not cleaned:
        return None
    return get_member_lookup().get(cleaned.lower())


def is_authorized_passcode(passcode: str) -> bool:
    configured = get_default_passcode()
    if not configured:
        return bool(passcode)
    return passcode == configured


def set_active_guild_label():
    passcode = get_active_passcode()
    label = document.getElementById("guild-active")
    if not passcode:
        label.innerText = "ENTER PASSCODE"
        return

    if is_authorized_passcode(passcode):
        label.innerText = "ACCESS GRANTED TO SWAX"
    else:
        label.innerText = "Passcode entered, but not authorized."


def apply_custom_graphics():
    title = str(getattr(window, "GUILD_TITLE", "")).strip()
    logo = str(getattr(window, "GUILD_LOGO_URL", "")).strip()
    background = str(getattr(window, "GUILD_BACKGROUND_URL", "")).strip()

    if title:
        document.title = title
        document.querySelector("h1").innerText = title

    logo_el = document.getElementById("guild-logo")
    if logo:
        logo_el.setAttribute("src", logo)
        logo_el.style.display = "block"
    else:
        logo_el.style.display = "none"

    if background:
        document.body.style.backgroundImage = f"url('{background}')"
        document.body.style.backgroundRepeat = "no-repeat"
        document.body.style.backgroundPosition = "center"
        document.body.style.backgroundSize = "cover"


def render_member_name_options(rows: list[dict]):
    del rows
    datalist = document.getElementById("member-names")
    names_sorted = sorted(get_configured_members(), key=str.lower)
    datalist.innerHTML = "".join(f'<option value="{escape(name)}"></option>' for name in names_sorted)


def render_attack_value(*_):
    attacks = document.getElementById("attacks-used").value
    document.getElementById("attacks-value").innerText = f"{attacks} / 3"


def normalize_row(row: dict) -> tuple[dict, bool]:
    normalized = {
        "guild_code": str(row.get("guild_code", "")).strip(),
        "name": str(row.get("name", "")).strip(),
        "week_key": str(row.get("week_key", "")).strip(),
        "attacks_used": clamp_attacks(row.get("attacks_used", 0)),
    }
    for day in DAYS:
        normalized[day] = bool(row.get(day, False))

    should_reset = normalized["week_key"] != current_week_key()
    if should_reset:
        normalized["week_key"] = current_week_key()
        normalized["attacks_used"] = 0
        for day in DAYS:
            normalized[day] = False
    return normalized, should_reset


def get_supabase_config() -> tuple[str, str]:
    url = str(getattr(window, "SUPABASE_URL", "")).strip().rstrip("/")
    key = str(getattr(window, "SUPABASE_ANON_KEY", "")).strip()
    return url, key


def has_backend() -> bool:
    url, key = get_supabase_config()
    return bool(url and key)


def supabase_headers(upsert: bool = False) -> dict:
    _, key = get_supabase_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if upsert:
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    return headers


async def fetch_rows() -> list[dict]:
    guild_code = get_active_passcode()
    guild_code_encoded = quote(guild_code, safe="")
    url, _ = get_supabase_config()
    endpoint = (
        f"{url}/rest/v1/{TABLE}"
        f"?select=guild_code,name,week_key,attacks_used,wed,thur,fri,sat,sun,mon,tues"
        f"&guild_code=eq.{guild_code_encoded}&order=name.asc"
    )
    response = await pyfetch(endpoint, method="GET", headers=supabase_headers())
    if not response.ok:
        raise RuntimeError(await response.text())
    return await response.json()


async def upsert_row(row: dict):
    url, _ = get_supabase_config()
    endpoint = f"{url}/rest/v1/{TABLE}?on_conflict=guild_code,name"
    response = await pyfetch(
        endpoint,
        method="POST",
        headers=supabase_headers(upsert=True),
        body=json.dumps([row]),
    )
    if not response.ok:
        raise RuntimeError(await response.text())


def render_day_counts(rows: list[dict]):
    counts_container = document.getElementById("day-counts")
    html_parts = []
    for day in DAYS:
        count = sum(1 for row in rows if row.get(day, False))
        html_parts.append(f"<div><strong>{day.upper()}</strong><br/>{count} available</div>")
    counts_container.innerHTML = "".join(html_parts)


def render_roster(rows: list[dict]):
    body = document.getElementById("roster-body")
    lines = []
    for row in rows:
        available_days = ", ".join(day.upper() for day in DAYS if row.get(day, False)) or "-"
        attacks_used = clamp_attacks(row.get("attacks_used", 0))
        attacks_left = 3 - attacks_used
        lines.append(
            "<tr>"
            f"<td>{escape(str(row.get('name', '')))}</td>"
            f"<td>{attacks_used}</td>"
            f"<td>{attacks_left}</td>"
            f"<td>{available_days}</td>"
            "</tr>"
        )
    body.innerHTML = "".join(lines)


def fill_form_for_member(name: str):
    member_name = name.strip()
    row = next((item for item in state["rows"] if item.get("name") == member_name), None)
    if row is None:
        row = {"name": member_name, "attacks_used": 0, **empty_days()}

    document.getElementById("member-name").value = member_name
    document.getElementById("attacks-used").value = str(clamp_attacks(row.get("attacks_used", 0)))
    for day in DAYS:
        document.getElementById(f"day-{day}").checked = bool(row.get(day, False))
    render_attack_value()


async def refresh_data(show_status: bool = True):
    if not has_backend():
        set_status("Set SUPABASE_URL and SUPABASE_ANON_KEY in config.js to enable shared sync.")
        state["rows"] = []
        render_member_name_options([])
        render_day_counts([])
        render_roster([])
        return

    passcode = get_active_passcode()
    if not passcode:
        set_status("Enter guild passcode and click Join Guild.")
        state["rows"] = []
        render_member_name_options([])
        render_day_counts([])
        render_roster([])
        return

    if not is_authorized_passcode(passcode):
        set_status("Invalid guild passcode.")
        state["rows"] = []
        render_member_name_options([])
        render_day_counts([])
        render_roster([])
        return

    if show_status:
        set_status("Syncing guild data...")

    try:
        rows = await fetch_rows()
        updated = []
        rows_need_reset = []

        for row in rows:
            normalized, was_reset = normalize_row(row)
            updated.append(normalized)
            if was_reset:
                rows_need_reset.append(normalized)

        for row in rows_need_reset:
            await upsert_row(row)

        if rows_need_reset:
            rows = await fetch_rows()
            updated = [normalize_row(row)[0] for row in rows]

        state["rows"] = updated
        render_member_name_options(updated)
        render_day_counts(updated)
        render_roster(updated)

        if show_status:
            set_status(f"Synced {len(updated)} member(s) for {current_week_key()}.")
    except Exception as error:
        set_status(f"Sync failed: {error}")


async def load_profile(event=None):
    del event
    name = document.getElementById("member-name").value.strip()
    if not name:
        set_status("Enter a member name first.")
        return

    resolved_name = resolve_allowed_member_name(name)
    if resolved_name is None:
        set_status("Member must be selected from the guild member list.")
        return

    document.getElementById("member-name").value = resolved_name

    await refresh_data(show_status=False)
    fill_form_for_member(resolved_name)
    set_status(f"Loaded profile for {resolved_name}.")


async def save_member(event=None):
    del event

    name = document.getElementById("member-name").value.strip()
    if not name:
        set_status("Member name is required.")
        return

    resolved_name = resolve_allowed_member_name(name)
    if resolved_name is None:
        set_status("Member must be selected from the guild member list.")
        return

    document.getElementById("member-name").value = resolved_name

    if not has_backend():
        set_status("Shared save is disabled until config.js has Supabase values.")
        return

    guild_code = get_active_passcode()
    if not guild_code:
        set_status("Join a guild first using passcode.")
        return

    if not is_authorized_passcode(guild_code):
        set_status("Invalid guild passcode.")
        return

    row = {
        "guild_code": guild_code,
        "name": resolved_name,
        "week_key": current_week_key(),
        "attacks_used": clamp_attacks(document.getElementById("attacks-used").value),
    }
    for day in DAYS:
        row[day] = bool(document.getElementById(f"day-{day}").checked)

    set_status(f"Saving {resolved_name}...")
    try:
        await upsert_row(row)
        await refresh_data(show_status=False)
        set_status(f"Saved {resolved_name}.")
    except Exception as error:
        set_status(f"Save failed: {error}")


async def join_guild(event=None):
    del event
    passcode = get_active_passcode()
    if not passcode:
        set_status("Guild passcode is required.")
        return

    if not is_authorized_passcode(passcode):
        set_active_guild_label()
        set_status("Invalid guild passcode.")
        return

    window.localStorage.setItem("guild_passcode", passcode)
    set_active_guild_label()
    await refresh_data()


def clear_guild(event=None):
    del event
    document.getElementById("guild-passcode").value = ""
    window.localStorage.removeItem("guild_passcode")
    state["rows"] = []
    render_member_name_options([])
    render_day_counts([])
    render_roster([])
    set_active_guild_label()
    set_status("Guild selection cleared.")


async def boot():
    apply_custom_graphics()
    render_member_name_options([])
    persisted = normalize_passcode(window.localStorage.getItem("guild_passcode"))
    initial = persisted
    if initial:
        document.getElementById("guild-passcode").value = initial
    set_active_guild_label()
    render_attack_value()
    await refresh_data()


if window is not None:
    window.render_attack_value = render_attack_value
    window.load_profile = load_profile
    window.save_member = save_member
    window.join_guild = join_guild
    window.clear_guild = clear_guild

if window is not None and document is not None:
    asyncio.ensure_future(boot())
