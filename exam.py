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

def redistribute_to_days(base_plan, start_day=22, end_day=26, total_lectures=93):
    """Redistribute all lectures into days 22–26 evenly."""
    # Flatten all lectures from base_plan
    all_lectures = []
    for info in base_plan.values():
        all_lectures.extend(info["lectures"])

    # Trim to total_lectures if needed
    all_lectures = all_lectures[:total_lectures]

    days = [f"{day} January" for day in range(start_day, end_day+1)]
    per_day = total_lectures // len(days)
    remainder = total_lectures % len(days)

    redistributed = {}
    idx = 0
    for i, day in enumerate(days):
        extra = 1 if i < remainder else 0
        count = per_day + extra
        redistributed[day] = {
            "count": count,
            "lectures": all_lectures[idx: idx+count]
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

# ────────────────────────────────────────────────
#  Streamlit App
# ────────────────────────────────────────────────

st.set_page_config(page_title="Study Plan Checklist", layout="wide")
st.title("📚 Study Plan Checklist (Days 22–26)")

# Load base plan
if not os.path.exists(PLAN_FILE):
    st.error(f"File not found: **{PLAN_FILE}**\nPlease create it and paste your study plan.")
    st.stop()

with open(PLAN_FILE, encoding="utf-8") as f:
    raw_text = f.read()

base_plan = parse_plan(raw_text)
state = load_state()

# Replace with redistributed plan starting from 22
current_plan = redistribute_to_days(base_plan, start_day=22, end_day=26, total_lectures=93)

# ── Sidebar controls ────────────────────────────────────────

today = date.today()
today_str = f"{today.day} January"

days = sorted(current_plan.keys())  # better ordering
default_idx = days.index(today_str) if today_str in days else 0

selected_day = st.sidebar.selectbox("Select Day", days, index=default_idx)
search = st.sidebar.text_input("Filter lectures", placeholder="e.g. Linear Algebra")

st.sidebar.markdown("---")

# ── Add new lecture ─────────────────────────────────────────

st.sidebar.subheader("➕ Add Lecture")
col_add_day, col_add_btn = st.sidebar.columns([3, 2])
add_day = col_add_day.selectbox("To day", days, key="add_day_select")
new_lecture = st.sidebar.text_input("Lecture name", key="new_lecture_name")

if st.sidebar.button("Add Lecture", disabled=not new_lecture.strip()):
    lec = new_lecture.strip()
    overrides = state.setdefault("overrides", {})
    adds = overrides.setdefault("add", {})
    adds.setdefault(add_day, []).append(lec)

    # Initialize state for new lecture
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

# ── Remove lecture ──────────────────────────────────────────

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

        # Clean up state if exists
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

