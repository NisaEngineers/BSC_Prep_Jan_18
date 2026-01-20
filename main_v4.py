# -*- coding: utf-8 -*-
import streamlit as st
import re, json, os
import datetime
import pandas as pd

PLAN_FILE = "FinalStudy/plan.txt"
STATE_FILE = "FinalStudy/plan_state.json"

DAY_HEADER_RE = re.compile(r"^(\d{1,2}\s+January)\s*\((\d+)\s*lectures\)", re.IGNORECASE)

def parse_plan(text):
    lines = [ln.strip() for ln in text.splitlines()]
    plan = {}
    current_day = None
    for ln in lines:
        if not ln:
            continue
        m = DAY_HEADER_RE.match(ln)
        if m:
            day = m.group(1)
            count = int(m.group(2))
            plan[day] = {"count": count, "lectures": []}
            current_day = day
            continue
        if ln.lower().startswith("study plan"):
            continue
        if current_day:
            plan[current_day]["lectures"].append(ln)
    return plan

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def normalize_state(state):
    """Ensure all time objects are converted to strings before saving."""
    for d, info in state.items():
        for l, lec_state in info.items():
            if isinstance(lec_state.get("start"), datetime.time):
                lec_state["start"] = lec_state["start"].strftime("%H:%M")
            if isinstance(lec_state.get("end"), datetime.time):
                lec_state["end"] = lec_state["end"].strftime("%H:%M")
    return state

def save_state(state):
    state = normalize_state(state)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ---------------- Streamlit UI ----------------
st.set_page_config(page_title="Study Plan Checklist", layout="wide")
st.title("📚 Study Plan Checklist")

if not os.path.exists(PLAN_FILE):
    st.error("No plan.txt found. Please create it and paste your study plan.")
    st.stop()

with open(PLAN_FILE, "r", encoding="utf-8") as f:
    text = f.read()

plan = parse_plan(text)
state = load_state()

# Detect today's date (example: 18 January)
today = datetime.date.today()
today_str = f"{today.day} January"

days = list(plan.keys())
default_day = today_str if today_str in days else days[0]

day_filter = st.sidebar.selectbox("Select Day", days, index=days.index(default_day))
search_query = st.sidebar.text_input("Search Lecture")

# Stats counters
total, studied, examed, total_minutes = 0, 0, 0, 0
daily_minutes = {}

# Checklist rendering
for day, info in plan.items():
    if day != day_filter:
        continue
    st.subheader(f"{day} ({info['count']} lectures)")
    day_total_minutes = 0
    for lecture in info["lectures"]:
        if search_query and search_query.lower() not in lecture.lower():
            continue

        day_state = state.setdefault(day, {})
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
                "assigned_day": day
            }
        )

        cols = st.columns([4,1,1,2,2,2])
        cols[0].write(lecture)
        lec_state["study"] = cols[1].checkbox("Study", value=lec_state["study"], key=f"{day}-{lecture}-study")
        lec_state["exam"] = cols[2].checkbox("Exam", value=lec_state["exam"], key=f"{day}-{lecture}-exam")

        # Start/End time inputs (24h clock)
        start_val = datetime.datetime.strptime(lec_state["start"], "%H:%M").time()
        end_val = datetime.datetime.strptime(lec_state["end"], "%H:%M").time()
        lec_state["start"] = cols[3].time_input("Start", value=start_val, key=f"{day}-{lecture}-start")
        lec_state["end"] = cols[4].time_input("End", value=end_val, key=f"{day}-{lecture}-end")

        # Duration calculation
        start_minutes = lec_state["start"].hour*60 + lec_state["start"].minute
        end_minutes = lec_state["end"].hour*60 + lec_state["end"].minute
        duration = (end_minutes - start_minutes) if end_minutes >= start_minutes else (1440 - start_minutes + end_minutes)
        cols[5].write(f"⏱ {lec_state['start'].strftime('%H:%M')} → {lec_state['end'].strftime('%H:%M')} = {duration} min")
        total_minutes += duration
        day_total_minutes += duration

        # Notes + Link + Day reassignment
        with st.expander(f"Notes, Link & Adjust Day for {lecture}", expanded=False):
            lec_state["notes"] = st.text_area("Notes:", value=lec_state["notes"], key=f"{day}-{lecture}-notes")
            lec_state["link"] = st.text_input("Video/Resource Link:", value=lec_state["link"], key=f"{day}-{lecture}-link")
            if lec_state["link"]:
                st.markdown(f"[Open Resource]({lec_state['link']})")

            # Day reassignment
            lec_state["assigned_day"] = st.selectbox("Assign to Day:", days, index=days.index(lec_state.get("assigned_day", day)), key=f"{day}-{lecture}-assign")

            if st.button("Save", key=f"{day}-{lecture}-save"):
                lec_state["start"] = lec_state["start"].strftime("%H:%M")
                lec_state["end"] = lec_state["end"].strftime("%H:%M")
                if lec_state["study"]:
                    lec_state["completed_on"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                save_state(state)
                st.success("Saved notes, times, link, and assignment!")

        if lec_state["study"]:
            studied += 1
        if lec_state["exam"]:
            examed += 1
        total += 1

    daily_minutes[day] = day_total_minutes

# --- Add Lecture ---
st.sidebar.subheader("➕ Add Lecture")
add_day = st.sidebar.selectbox("Day to add lecture", days, key="add_day")
new_lecture = st.sidebar.text_input("Lecture name", key="new_lecture")
if st.sidebar.button("Add Lecture"):
    if new_lecture.strip():
        plan[add_day]["lectures"].append(new_lecture.strip())
        state.setdefault(add_day, {})[new_lecture.strip()] = {
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
        st.sidebar.success(f"Lecture '{new_lecture}' added to {add_day}")
    else:
        st.sidebar.warning("Please enter a lecture name.")

# --- Remove Lecture ---
st.sidebar.subheader("➖ Remove Lecture")
remove_day = st.sidebar.selectbox("Day to remove lecture", days, key="remove_day")
if plan[remove_day]["lectures"]:
    remove_lecture = st.sidebar.selectbox("Select lecture", plan[remove_day]["lectures"], key="remove_lecture")
    if st.sidebar.button("Remove Lecture"):
        plan[remove_day]["lectures"].remove(remove_lecture)
        if remove_lecture in state.get(remove_day, {}):
            del state[remove_day][remove_lecture]
        save_state(state)
        st.sidebar.success(f"Lecture '{remove_lecture}' removed from {remove_day}")
else:
    st.sidebar.info("No lectures to remove for this day.")

# Save progress button
if st.sidebar.button("💾 Save Progress"):
    save_state(state)
    st.sidebar.success("Progress saved to plan_state.json")

# Stats
if total > 0:
    progress = ((studied + examed) / (2 * total)) * 100
    st.progress(progress / 100)
    st.write(f"Lectures: {total} | Studied: {studied} | Exam: {examed} | Progress: {progress:.1f}%")
    st.write(f"Total Time Spent Today ({day_filter}): ⏱ {daily_minutes.get(day_filter,0)} minutes (~{daily_minutes.get(day_filter,0)/60:.2f} hours)")

# Daily breakdown chart
if daily_minutes:
    df = pd.DataFrame(list(daily_minutes.items()), columns=["Day","Minutes"])
    st.sidebar.subheader("📊 Daily Study Time")
    st.sidebar.bar_chart(df.set_index("Day"))

# Completion log view
st.sidebar.subheader("🕒 Completion Log")
log_entries = []
for d, info in state.items():
    for l, lec_state in info.items():
        if lec_state.get("completed_on"):
            # Display start/end times nicely if available
            start_str = lec_state.get("start", "")
            end_str = lec_state.get("end", "")
            log_entries.append({
                "Lecture": l,
                "Assigned Day": lec_state.get("assigned_day", d),
                "Completed On": lec_state["completed_on"],
                "Time Range": f"{start_str} → {end_str}"
            })

if log_entries:
    log_df = pd.DataFrame(log_entries)
    st.sidebar.dataframe(log_df)
else:
    st.sidebar.write("No lectures completed yet.")
