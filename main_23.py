# -*- coding: utf-8 -*-
import streamlit as st
import re
import json
import os
from datetime import datetime, date, time

PLAN_FILE = "FinalStudy/plan.txt"
STATE_FILE = "FinalStudy/plan_state.json"

# ────────────────────────────────────────────────
#  Parsing
# ────────────────────────────────────────────────

DAY_HEADER_RE = re.compile(r"^(\d{1,2}\s+January)\s*\((\d+)\s*lectures?\)", re.IGNORECASE)

def parse_plan(text: str) -> dict:
    """Parse original plan.txt into {day: {"count": int, "lectures": list[str]}}"""
    plan = {}
    current_day = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        m = DAY_HEADER_RE.match(line)
        if m:
            day = m.group(1).strip()
            count = int(m.group(2))
            plan[day] = {"count": count, "lectures": []}
            current_day = day
            continue

        if line.lower().startswith("study plan"):
            continue

        if current_day and line:
            plan[current_day]["lectures"].append(line)

    return plan

# ────────────────────────────────────────────────
#  Redistribution Logic
# ────────────────────────────────────────────────

def redistribute_to_days(base_plan, start_day=23, end_day=27, total_lectures=93):
    """
    Redistribute all lectures evenly into days 23–27 January.
    """
    # Flatten all lectures from base_plan
    all_lectures = []
    for info in base_plan.values():
        all_lectures.extend(info["lectures"])

    # Limit to desired total (optional safety)
    all_lectures = all_lectures[:total_lectures]

    days = [f"{day} January" for day in range(start_day, end_day + 1)]
    per_day = total_lectures // len(days)
    remainder = total_lectures % len(days)

    redistributed = {}
    idx = 0
    for i, day in enumerate(days):
        extra = 1 if i < remainder else 0
        count = per_day + extra
        redistributed[day] = {
            "count": count,
            "lectures": all_lectures[idx: idx + count]
        }
        idx += count

    return redistributed

# ────────────────────────────────────────────────
#  State Management
# ────────────────────────────────────────────────

def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(state: dict):
    """Normalize time objects → strings before saving"""
    for day, data in state.items():
        if day == "overrides":
            continue
        for lec, info in data.items():
            for key in ("start", "end"):
                if isinstance(info.get(key), time):
                    info[key] = info[key].strftime("%H:%M")

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def merge_plan(base_plan: dict, state: dict) -> dict:
    """Apply overrides (add/remove/move) to create final working plan"""
    merged = {
        day: {"count": info["count"], "lectures": info["lectures"][:]}
        for day, info in base_plan.items()
    }

    overrides = state.get("overrides", {"add": {}, "remove": {}, "move": {}})

    # 1. Additions
    for day, lectures in overrides.get("add", {}).items():
        merged.setdefault(day, {"count": 0, "lectures": []})
        for lec in lectures:
            if lec not in merged[day]["lectures"]:
                merged[day]["lectures"].append(lec)

    # 2. Removals
    for day, lectures in overrides.get("remove", {}).items():
        if day in merged:
            merged[day]["lectures"] = [
                lec for lec in merged[day]["lectures"] if lec not in lectures
            ]

    # 3. Moves
    for lecture, target_day in overrides.get("move", {}).items():
        # Remove from original location
        for day in list(merged):
            if lecture in merged[day]["lectures"]:
                merged[day]["lectures"].remove(lecture)
        # Add to target
        merged.setdefault(target_day, {"count": 0, "lectures": []})
        if lecture not in merged[target_day]["lectures"]:
            merged[target_day]["lectures"].append(lecture)

    # Update counts
    for day in merged:
        merged[day]["count"] = len(merged[day]["lectures"])

    return merged

# ────────────────────────────────────────────────
#  Streamlit App
# ────────────────────────────────────────────────

st.set_page_config(page_title="Study Plan Checklist", layout="wide")
st.title("📚 Study Plan Checklist (Days 23–27)")

# Load base plan
if not os.path.exists(PLAN_FILE):
    st.error(f"File not found: **{PLAN_FILE}**\nPlease create it and paste your study plan.")
    st.stop()

with open(PLAN_FILE, encoding="utf-8") as f:
    raw_text = f.read()

base_plan = parse_plan(raw_text)
state = load_state()

# ── Redistribute lectures into 23–27 ───────────────────────────
current_plan = redistribute_to_days(base_plan, start_day=23, end_day=27, total_lectures=93)
current_plan = merge_plan(current_plan, state)  # apply user overrides

# ── Sidebar controls ────────────────────────────────────────

today = date.today()
today_str = f"{today.day} January"

days = sorted(current_plan.keys())  # usually already sorted, but safe
default_idx = 0
if today_str in days:
    default_idx = days.index(today_str)

selected_day = st.sidebar.selectbox("Select Day", days, index=default_idx)
search = st.sidebar.text_input("Filter lectures", placeholder="e.g. Linear Algebra")

st.sidebar.markdown("---")

# ➕ Add Lecture
st.sidebar.subheader("➕ Add Lecture")
col_add_day, col_add_btn = st.sidebar.columns([3, 2])
add_day = col_add_day.selectbox("To day", days, key="add_day_select")
new_lecture = st.sidebar.text_input("Lecture name", key="new_lecture_name")

if st.sidebar.button("Add Lecture", disabled=not new_lecture.strip()):
    lec = new_lecture.strip()
    overrides = state.setdefault("overrides", {})
    adds = overrides.setdefault("add", {})
    adds.setdefault(add_day, []).append(lec)

    state.setdefault(add_day, {})[lec] = {
        "study": False,
        "exam": False,
        "notes": "",
        "start": "00:00",
        "end": "00:00",
        "link": "",
        "completed_on": None,
        "assigned_day": add_day
    }

    save_state(state)
    st.sidebar.success(f"Added **{lec}** to {add_day}")
    st.rerun()

# ➖ Remove Lecture
st.sidebar.subheader("➖ Remove Lecture")
remove_day = st.sidebar.selectbox("From day", days, key="remove_day_select")

if current_plan.get(remove_day, {}).get("lectures"):
    to_remove = st.sidebar.selectbox(
        "Lecture to remove",
        current_plan[remove_day]["lectures"],
        key="lecture_to_remove"
    )
    if st.sidebar.button("Remove", type="primary"):
        overrides = state.setdefault("overrides", {})
        removes = overrides.setdefault("remove", {})
        removes.setdefault(remove_day, []).append(to_remove)

        if remove_day in state and to_remove in state[remove_day]:
            del state[remove_day][to_remove]

        save_state(state)
        st.sidebar.success(f"Removed **{to_remove}** from {remove_day}")
        st.rerun()
else:
    st.sidebar.info("No lectures on this day.")

st.sidebar.markdown("---")

if st.sidebar.button("💾 Save All Progress"):
    save_state(state)
    st.sidebar.success("Progress saved!")

# ── Main content ────────────────────────────────────────────

st.subheader(f"{selected_day}  ({current_plan[selected_day]['count']} lectures)")

total_lec = 0
studied = 0
examed = 0
total_min_today = 0

for lecture in current_plan[selected_day]["lectures"]:
    if search and search.lower() not in lecture.lower():
        continue

    total_lec += 1

    day_state = state.setdefault(selected_day, {})
    lec_state = day_state.setdefault(
        lecture,
        {
            "study": False,
            "exam": False,
            "notes": "",
            "start": "00:00",
            "end": "00:00",
            "link": "",
            "completed_on": None,
            "assigned_day": selected_day,
        },
    )

    cols = st.columns([5, 1.1, 1.1, 2, 2, 2.4])

    cols[0].write(lecture)

    study_key = f"study_{selected_day}_{lecture}"
    exam_key   = f"exam_{selected_day}_{lecture}"

    lec_state["study"] = cols[1].checkbox("Study", value=lec_state["study"], key=study_key)
    lec_state["exam"]  = cols[2].checkbox("Exam",  value=lec_state["exam"],  key=exam_key)

    # Time inputs
    try:
        start_t = datetime.strptime(lec_state["start"], "%H:%M").time()
        end_t   = datetime.strptime(lec_state["end"], "%H:%M").time()
    except:
        start_t = time(0, 0)
        end_t   = time(0, 0)

    lec_state["start"] = cols[3].time_input("Start", value=start_t, key=f"start_{selected_day}_{lecture}")
    lec_state["end"]   = cols[4].time_input("End",   value=end_t,   key=f"end_{selected_day}_{lecture}")

    # Calculate duration
    s_min = lec_state["start"].hour * 60 + lec_state["start"].minute
    e_min = lec_state["end"].hour * 60 + lec_state["end"].minute
    duration = (e_min - s_min) if e_min >= s_min else (1440 - s_min + e_min)
    total_min_today += duration

    cols[5].write(f"⏱ {duration} min  ({duration//10} × 10 min)")

    # Details expander
    with st.expander("Notes • Link • Reassign", expanded=False):
        lec_state["notes"] = st.text_area("Notes", lec_state["notes"], key=f"notes_{selected_day}_{lecture}")
        lec_state["link"]  = st.text_input("Resource Link", lec_state["link"], key=f"link_{selected_day}_{lecture}")

        if lec_state["link"]:
            st.markdown(f"[Open →]({lec_state['link']})")

        # Reassign day
        current_assigned = lec_state.get("assigned_day", selected_day)
        new_day = st.selectbox(
            "Move to day",
            days,
            index=days.index(current_assigned) if current_assigned in days else 0,
            key=f"move_{selected_day}_{lecture}"
        )

        if new_day != current_assigned:
            lec_state["assigned_day"] = new_day
            state.setdefault("overrides", {}).setdefault("move", {})[lecture] = new_day
            save_state(state)
            st.rerun()

        if st.button("Save Lecture", key=f"save_{selected_day}_{lecture}"):
            if lec_state["study"] and not lec_state.get("completed_on"):
                lec_state["completed_on"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_state(state)
            st.success("Saved!", icon="✅")

    if lec_state["study"]:
        studied += 1
    if lec_state["exam"]:
        examed += 1

# ── Summary ─────────────────────────────────────────────────

st.markdown("---")

if total_lec > 0:
    progress = ((studied + examed) / (2 * total_lec)) * 100
    st.progress(progress / 100)
    st.write(f"**Lectures shown**: {total_lec}  |  Studied: **{studied}**  |  Examined: **{examed}**")
    st.write(f"**Progress**: {progress:.1f}%")
    st.write(f"**Time planned today**: **{total_min_today}** min  ≈ **{total_min_today/60:.1f}** hours")
else:
    st.info("No lectures match the current filter.")