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

def save_state(state):
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
                "start": {"h":0,"m":0},
                "end": {"h":0,"m":0},
                "link": ""
            }
        )

        cols = st.columns([5,1,1,2,2,2])
        cols[0].write(lecture)
        lec_state["study"] = cols[1].checkbox("Study", value=lec_state["study"], key=f"{day}-{lecture}-study")
        lec_state["exam"] = cols[2].checkbox("Exam", value=lec_state["exam"], key=f"{day}-{lecture}-exam")

        # Start time dropdowns
        lec_state["start"]["h"] = cols[3].selectbox("Start Hr", list(range(24)), index=lec_state["start"]["h"], key=f"{day}-{lecture}-start-h")
        lec_state["start"]["m"] = cols[3].selectbox("Start Min", list(range(60)), index=lec_state["start"]["m"], key=f"{day}-{lecture}-start-m")

        # End time dropdowns
        lec_state["end"]["h"] = cols[4].selectbox("End Hr", list(range(24)), index=lec_state["end"]["h"], key=f"{day}-{lecture}-end-h")
        lec_state["end"]["m"] = cols[4].selectbox("End Min", list(range(60)), index=lec_state["end"]["m"], key=f"{day}-{lecture}-end-m")

        # Duration calculation
        start_minutes = lec_state["start"]["h"]*60 + lec_state["start"]["m"]
        end_minutes = lec_state["end"]["h"]*60 + lec_state["end"]["m"]
        duration = (end_minutes - start_minutes) if end_minutes >= start_minutes else (1440 - start_minutes + end_minutes)
        cols[5].write(f"⏱ {duration} min")
        total_minutes += duration
        day_total_minutes += duration

        # Notes + Link
        with st.expander(f"Notes & Link for {lecture}", expanded=False):
            lec_state["notes"] = st.text_area("Notes:", value=lec_state["notes"], key=f"{day}-{lecture}-notes")
            lec_state["link"] = st.text_input("Video/Resource Link:", value=lec_state["link"], key=f"{day}-{lecture}-link")
            if lec_state["link"]:
                st.markdown(f"[Open Resource]({lec_state['link']})")

            if st.button("Save", key=f"{day}-{lecture}-save"):
                save_state(state)
                st.success("Saved notes, times, and link!")

        if lec_state["study"]:
            studied += 1
        if lec_state["exam"]:
            examed += 1
        total += 1

    daily_minutes[day] = day_total_minutes

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
