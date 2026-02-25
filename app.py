# pyright: reportMissingImports=false
from datetime import datetime, timezone, timedelta
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
CATEGORY_ORDER = ["Europe", "SA", "US", "Asia", "Pawker"]
SLOTS = [
    {"id": "europe_wed", "label": "Europe Wednesday", "opens": "2026-02-25 18:00 UTC"},
    {"id": "sa_wed", "label": "SA Wednesday", "opens": "2026-02-25 22:00 UTC"},
    {"id": "us_wed", "label": "US Wednesday", "opens": "2026-02-26 01:00 UTC"},
    {"id": "asia_thu", "label": "Asia Thursday", "opens": "2026-02-26 12:00 UTC"},
    {"id": "europe_thu", "label": "Europe Thursday", "opens": "2026-02-26 18:00 UTC"},
    {"id": "sa_thu", "label": "SA Thursday", "opens": "2026-02-26 22:00 UTC"},
    {"id": "us_thu", "label": "US Thursday", "opens": "2026-02-27 01:00 UTC"},
    {"id": "asia_fri", "label": "Asia Friday", "opens": "2026-02-27 12:00 UTC"},
    {"id": "europe_fri", "label": "Europe Friday", "opens": "2026-02-27 18:00 UTC"},
    {"id": "sa_fri", "label": "SA Friday", "opens": "2026-02-27 22:00 UTC"},
    {"id": "us_fri", "label": "US Friday", "opens": "2026-02-28 01:00 UTC"},
    {"id": "asia_sat", "label": "Asia Saturday", "opens": "2026-02-28 06:00 UTC"},
    {"id": "pawker_sat_1", "label": "Pawker Saturday", "opens": "2026-02-28 08:00 UTC"},
    {"id": "europe_sat", "label": "Europe Saturday", "opens": "2026-02-28 13:00 UTC"},
    {"id": "sa_sat", "label": "SA Saturday", "opens": "2026-02-28 17:00 UTC"},
    {"id": "us_sat", "label": "US Saturday", "opens": "2026-02-28 20:00 UTC"},
    {"id": "pawker_sat_2", "label": "Pawker Saturday", "opens": "2026-02-28 20:00 UTC"},
    {"id": "asia_sun", "label": "Asia Sunday", "opens": "2026-03-01 06:00 UTC"},
    {"id": "europe_sun", "label": "Europe Sunday", "opens": "2026-03-01 13:00 UTC"},
    {"id": "sa_sun", "label": "SA Sunday", "opens": "2026-03-01 17:00 UTC"},
    {"id": "us_sun", "label": "US Sunday", "opens": "2026-03-01 20:00 UTC"},
    {"id": "asia_mon", "label": "Asia Monday", "opens": "2026-03-02 12:00 UTC"},
    {"id": "europe_mon", "label": "Europe Monday", "opens": "2026-03-02 18:00 UTC"},
    {"id": "sa_mon", "label": "SA Monday", "opens": "2026-03-02 22:00 UTC"},
    {"id": "us_mon", "label": "US Monday", "opens": "2026-03-03 01:00 UTC"},
    {"id": "asia_tues", "label": "Asia Tuesday", "opens": "2026-03-03 12:00 UTC"},
    {"id": "europe_tues", "label": "Europe Tuesday", "opens": "2026-03-03 18:00 UTC"},
    {"id": "sa_tues", "label": "SA Tuesday", "opens": "2026-03-03 22:00 UTC"},
    {"id": "us_tues", "label": "US Tuesday", "opens": "2026-03-04 01:00 UTC"},
    {"id": "asia_wed", "label": "Asia Wednesday", "opens": "2026-03-04 12:00 UTC"},
]
TABLE = "guild_availability"

state = {"rows": [], "active_slots": []}


def slot_id_set() -> set[str]:
    return {slot["id"] for slot in SLOTS}


def normalize_slots(raw_slots) -> list[str]:
    if isinstance(raw_slots, str):
        try:
            parsed = json.loads(raw_slots)
            raw_slots = parsed
        except Exception:
            raw_slots = []

    if not isinstance(raw_slots, list):
        raw_slots = []

    allowed = slot_id_set()
    deduped = []
    seen = set()
    for slot_id in raw_slots:
        cleaned = str(slot_id).strip()
        if not cleaned or cleaned not in allowed or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def slot_category(slot_label: str) -> str:
    for category in CATEGORY_ORDER:
        if str(slot_label).startswith(category):
            return category
    return "Other"


def slot_short_label(slot_label: str) -> str:
    category = slot_category(slot_label)
    prefix = f"{category} "
    if str(slot_label).startswith(prefix):
        return str(slot_label)[len(prefix) :]
    return str(slot_label)


def local_utc_offset_label(local_dt: datetime) -> str:
    offset = local_dt.utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    absolute_minutes = abs(total_minutes)
    hours = absolute_minutes // 60
    minutes = absolute_minutes % 60
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def parse_utc_text_datetime(raw_value: str) -> datetime | None:
    value = str(raw_value or "").strip()
    if not value:
        return None

    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M UTC")
        return parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def format_local_from_utc_text(raw_value: str) -> str:
    parsed = parse_utc_text_datetime(raw_value)
    if parsed is None:
        return str(raw_value or "")

    local_dt = parsed.astimezone()
    offset = local_utc_offset_label(local_dt)
    return f"{local_dt.strftime('%Y-%m-%d %I:%M %p')} ({offset})"


def render_local_timezone_note():
    note = document.getElementById("local-time-note")
    if note is None:
        return

    now_local = datetime.now().astimezone()
    offset = local_utc_offset_label(now_local)
    note.innerText = f"Times are shown in your local timezone ({offset})."


def current_reset_cycle_start(now: datetime | None = None) -> datetime:
    if now is None:
        now = datetime.now(timezone.utc)

    days_since_wednesday = (now.weekday() - 2) % 7
    last_wednesday = now.date() - timedelta(days=days_since_wednesday)
    reset_anchor = datetime(
        year=last_wednesday.year,
        month=last_wednesday.month,
        day=last_wednesday.day,
        hour=14,
        minute=0,
        second=0,
        microsecond=0,
        tzinfo=timezone.utc,
    )

    if now < reset_anchor:
        reset_anchor = reset_anchor - timedelta(days=7)

    return reset_anchor


def next_reset_datetime(now: datetime | None = None) -> datetime:
    return current_reset_cycle_start(now) + timedelta(days=7)


def current_week_key() -> str:
    return current_reset_cycle_start().strftime("%Y-%m-%dT%H:%M:%SZ")


def render_reset_countdown():
    target = next_reset_datetime()
    now = datetime.now(timezone.utc)
    remaining_seconds = max(0, int((target - now).total_seconds()))

    days, remainder = divmod(remaining_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    countdown_el = document.getElementById("reset-countdown")
    if countdown_el is not None:
        target_local = target.astimezone()
        offset = local_utc_offset_label(target_local)
        countdown_el.innerText = (
            f"Reset in {days}d {hours:02d}h {minutes:02d}m {seconds:02d}s "
            f"(local target: {target_local.strftime('%a %I:%M %p')} {offset})"
        )

    next_el = document.getElementById("reset-next")
    if next_el is not None:
        target_local = target.astimezone()
        offset = local_utc_offset_label(target_local)
        next_el.innerText = f"Next reset: {target_local.strftime('%a, %d %b %Y %I:%M %p')} ({offset})"


async def update_reset_countdown_loop():
    while True:
        render_reset_countdown()
        await asyncio.sleep(1)


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
        "slots": normalize_slots(row.get("slots", [])),
    }
    for day in DAYS:
        normalized[day] = bool(row.get(day, False))

    should_reset = normalized["week_key"] != current_week_key()
    if should_reset:
        normalized["week_key"] = current_week_key()
        normalized["attacks_used"] = 0
        normalized["slots"] = []
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
        f"?select=guild_code,name,week_key,attacks_used,slots,wed,thur,fri,sat,sun,mon,tues"
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


def render_slot_cards(rows: list[dict]):
    container = document.getElementById("slot-grid")
    if container is None:
        return

    selected = set(state.get("active_slots", []))
    member_name = document.getElementById("member-name").value.strip()
    resolved_name = resolve_allowed_member_name(member_name)
    rows_for_counts = [dict(row) for row in rows]
    if resolved_name is not None:
        updated = False
        for row in rows_for_counts:
            if row.get("name") == resolved_name:
                row["slots"] = list(state.get("active_slots", []))
                updated = True
                break
        if not updated and state.get("active_slots", []):
            rows_for_counts.append({"name": resolved_name, "slots": list(state.get("active_slots", []))})

    grouped_html: dict[str, list[str]] = {category: [] for category in CATEGORY_ORDER}
    now_utc = datetime.now(timezone.utc)
    for slot in SLOTS:
        slot_id = slot["id"]
        checked_names = sorted(
            [str(row.get("name", "")).strip() for row in rows_for_counts if slot_id in row.get("slots", []) and str(row.get("name", "")).strip()],
            key=str.lower,
        )
        checked_count = len(checked_names)
        if checked_names:
            preview_names = checked_names[:4]
            remaining = checked_count - len(preview_names)
            preview_text = ", ".join(preview_names)
            if remaining > 0:
                preview_text = f"{preview_text} +{remaining} more"
            checked_by_text = f"Checked by: {preview_text}"
            checked_by_title = ", ".join(checked_names)
        else:
            checked_by_text = "Checked by: none"
            checked_by_title = ""
        is_selected = slot_id in selected
        button_class = "slot-circle is-selected" if is_selected else "slot-circle"
        marker = "✓" if is_selected else ""
        opens_local = format_local_from_utc_text(slot["opens"])
        slot_open_utc = parse_utc_text_datetime(slot["opens"])
        slot_complete = bool(slot_open_utc and now_utc >= (slot_open_utc + timedelta(hours=1)))
        card_class = "slot-card is-complete" if slot_complete else "slot-card"
        button_disabled_attr = " disabled" if slot_complete else ""
        button_title = " title='Slot completed'" if slot_complete else ""
        short_label = slot_short_label(slot["label"])
        category = slot_category(slot["label"])
        card_html = (
            f"<div class='{card_class}'>"
            f"<button type='button' class='{button_class}' onclick=\"toggle_slot('{escape(slot_id)}')\"{button_disabled_attr}{button_title}>{marker}</button>"
            "<div class='slot-meta'>"
            f"<strong>{escape(short_label)}</strong>"
            f"<span>Opens at: {escape(opens_local)}</span>"
            f"<span>{checked_count} checked</span>"
            f"<span class='slot-checkers' title='{escape(checked_by_title)}'>{escape(checked_by_text)}</span>"
            "</div>"
            "</div>"
        )
        if category not in grouped_html:
            grouped_html[category] = []
        grouped_html[category].append(card_html)

    html_parts = []
    for category in CATEGORY_ORDER:
        cards = grouped_html.get(category, [])
        if not cards:
            continue
        html_parts.append(
            "<div class='slot-row'>"
            f"<h3 class='slot-row-title'>{escape(category)}</h3>"
            f"<div class='slot-row-cards'>{''.join(cards)}</div>"
            "</div>"
        )

    container.innerHTML = "".join(html_parts)


def render_roster(rows: list[dict]):
    body = document.getElementById("roster-body")
    lines = []
    for row in rows:
        selected_slots = row.get("slots", [])
        available_days = f"{len(selected_slots)} slot(s) selected"
        attacks_used = clamp_attacks(row.get("attacks_used", 0))
        lines.append(
            "<tr>"
            f"<td>{escape(str(row.get('name', '')))}</td>"
            f"<td>{attacks_used} / 3</td>"
            f"<td>{available_days}</td>"
            "</tr>"
        )
    body.innerHTML = "".join(lines)


def fill_form_for_member(name: str):
    member_name = name.strip()
    row = next((item for item in state["rows"] if item.get("name") == member_name), None)
    if row is None:
        row = {"name": member_name, "attacks_used": 0, "slots": [], **empty_days()}

    document.getElementById("member-name").value = member_name
    document.getElementById("attacks-used").value = str(clamp_attacks(row.get("attacks_used", 0)))
    state["active_slots"] = normalize_slots(row.get("slots", []))
    render_attack_value()
    render_slot_cards(state["rows"])


def toggle_slot(slot_id: str):
    member_name = document.getElementById("member-name").value.strip()
    resolved_name = resolve_allowed_member_name(member_name)
    if resolved_name is None:
        set_status("Load a valid member profile before selecting slots.")
        return

    document.getElementById("member-name").value = resolved_name
    current = set(state.get("active_slots", []))
    if slot_id in current:
        current.remove(slot_id)
    else:
        current.add(slot_id)

    state["active_slots"] = normalize_slots(list(current))
    render_slot_cards(state["rows"])
    set_status(f"Updated slots for {resolved_name}. Click Save to sync.")


async def refresh_data(show_status: bool = True):
    if not has_backend():
        set_status("Set SUPABASE_URL and SUPABASE_ANON_KEY in config.js to enable shared sync.")
        state["rows"] = []
        state["active_slots"] = []
        render_member_name_options([])
        render_slot_cards([])
        render_roster([])
        return

    passcode = get_active_passcode()
    if not passcode:
        set_status("PASSCODE NEEDED TO ENTER")
        state["rows"] = []
        state["active_slots"] = []
        render_member_name_options([])
        render_slot_cards([])
        render_roster([])
        return

    if not is_authorized_passcode(passcode):
        set_status("WRONG PASSCODE ENTERED")
        state["rows"] = []
        state["active_slots"] = []
        render_member_name_options([])
        render_slot_cards([])
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
        render_slot_cards(updated)
        render_roster(updated)

        if show_status:
            set_status(f"Synced {len(updated)} member(s).")
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
        "slots": state.get("active_slots", []),
    }

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
    state["active_slots"] = []
    render_member_name_options([])
    render_slot_cards([])
    render_roster([])
    set_active_guild_label()
    set_status("Guild selection cleared.")


async def boot():
    apply_custom_graphics()
    render_member_name_options([])
    render_local_timezone_note()
    render_slot_cards([])
    render_reset_countdown()
    asyncio.ensure_future(update_reset_countdown_loop())
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
    window.toggle_slot = toggle_slot

if window is not None and document is not None:
    asyncio.ensure_future(boot())
