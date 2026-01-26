# -*- coding: utf-8 -*-
import streamlit as st
import json
import os
from datetime import datetime, date
import pandas as pd
import plotly.express as px

ROUTINE_FILE = "FinalRoutine/routine_state.json"

# ────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────

def generate_time_slots(step=5):
    """Generate 24h time slots with given step in minutes."""
    slots = []
    for h in range(24):
        for m in range(0, 60, step):
            slots.append(f"{h:02d}:{m:02d}")
    return slots

time_slots = generate_time_slots(5)

def parse_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m

# ────────────────────────────────────────────────
#  State Management
# ────────────────────────────────────────────────

def load_routine() -> dict:
    if not os.path.exists(ROUTINE_FILE):
        return {}
    try:
        with open(ROUTINE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_routine(routine: dict):
    os.makedirs(os.path.dirname(ROUTINE_FILE), exist_ok=True)
    with open(ROUTINE_FILE, "w", encoding="utf-8") as f:
        json.dump(routine, f, ensure_ascii=False, indent=2)

# ────────────────────────────────────────────────
#  Streamlit App
# ────────────────────────────────────────────────

st.set_page_config(page_title="Daily Routine Tracker", layout="wide")
st.title("🗓️ Daily Routine Tracker")

routine = load_routine()

# Sidebar: choose date
st.sidebar.header("Select Date")
selected_date = st.sidebar.date_input("Routine Date", value=date.today())
day_str = selected_date.strftime("%Y-%m-%d")
day_routine = routine.setdefault(day_str, {})

# ── Add Activity ────────────────────────────────────────────
st.sidebar.header("➕ Add Activity")
activity_name = st.sidebar.text_input("Activity name (e.g. Work, Sleep, Gym)")
start_time = st.sidebar.selectbox("Start time", time_slots, index=time_slots.index("09:00"))
end_time   = st.sidebar.selectbox("End time", time_slots, index=time_slots.index("10:00"))

if st.sidebar.button("Add Activity", disabled=not activity_name.strip()):
    act = activity_name.strip()
    day_routine[act] = {
        "completed": False,
        "notes": "",
        "intervals": [{"start": start_time, "end": end_time}],
        "logged_on": None
    }
    save_routine(routine)
    st.sidebar.success(f"Added **{act}** to {day_str}")
    st.rerun()

# ── Delete Activity ─────────────────────────────────────────
st.sidebar.header("🗑️ Delete Activity")
if day_routine:
    to_delete = st.sidebar.selectbox("Select activity", list(day_routine.keys()))
    if st.sidebar.button("Delete Activity"):
        del day_routine[to_delete]
        save_routine(routine)
        st.sidebar.success(f"Deleted **{to_delete}** from {day_str}")
        st.rerun()
else:
    st.sidebar.info("No activities to delete.")

st.sidebar.markdown("---")
if st.sidebar.button("💾 Save Progress"):
    save_routine(routine)
    st.sidebar.success("Progress saved!")

# ── Main content ────────────────────────────────────────────

st.subheader(f"Routine for {day_str}")

total_acts = 0
completed = 0
total_minutes = 0
timeline_data = []

for act, info in day_routine.items():
    total_acts += 1

    with st.expander(f"📌 {act}", expanded=True):
        # ✅ Checkbox with auto-save
        comp_key = f"comp_{day_str}_{act}"
        new_completed = st.checkbox("Done", value=info["completed"], key=comp_key)
        if new_completed != info["completed"]:
            info["completed"] = new_completed
            if info["completed"] and not info.get("logged_on"):
                info["logged_on"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_routine(routine)

        # 🕒 Multiple intervals
        if "intervals" not in info:
            info["intervals"] = [{"start": info.get("start", "09:00"), "end": info.get("end", "10:00")}]
            info.pop("start", None)
            info.pop("end", None)

        total_duration = 0
        for i, interval in enumerate(info["intervals"]):
            cols = st.columns([2, 2, 2])
            new_start = cols[0].selectbox(
                f"Start {i+1}", time_slots,
                index=time_slots.index(interval["start"]),
                key=f"start_{day_str}_{act}_{i}"
            )
            new_end = cols[1].selectbox(
                f"End {i+1}", time_slots,
                index=time_slots.index(interval["end"]),
                key=f"end_{day_str}_{act}_{i}"
            )
            if new_start != interval["start"] or new_end != interval["end"]:
                interval["start"], interval["end"] = new_start, new_end
                save_routine(routine)

            # Duration
            s_min = parse_minutes(interval["start"])
            e_min = parse_minutes(interval["end"])
            duration = (e_min - s_min) if e_min >= s_min else (1440 - s_min + e_min)
            total_duration += duration
            cols[2].write(f"⏱ {duration} min")

            # Add to timeline data
            timeline_data.append({
                "Task": act,
                "Start": f"{day_str} {interval['start']}",
                "Finish": f"{day_str} {interval['end']}",
                "Completed": "Yes" if info["completed"] else "No"
            })

        # ➕ Add new interval
        if st.button(f"Add Interval to {act}", key=f"addint_{day_str}_{act}"):
            info["intervals"].append({"start": "09:00", "end": "10:00"})
            save_routine(routine)
            st.rerun()

        # 📝 Notes
        new_notes = st.text_area("Notes", info["notes"], key=f"notes_{day_str}_{act}")
        if new_notes != info["notes"]:
            info["notes"] = new_notes
            save_routine(routine)

        total_minutes += total_duration
        if info["completed"]:
            completed += 1

# ── Summary ─────────────────────────────────────────────────

st.markdown("---")
if total_acts > 0:
    progress = (completed / total_acts) * 100
    st.progress(progress / 100)
    st.write(f"**Activities**: {total_acts} | Completed: **{completed}**")
    st.write(f"**Progress**: {progress:.1f}%")
    st.write(f"**Total time planned**: {total_minutes} min ≈ {total_minutes/60:.1f} hours")

    # 📊 Timeline chart
    if timeline_data:
        df = pd.DataFrame(timeline_data)
        fig = px.timeline(df, x_start="Start", x_end="Finish", y="Task", color="Completed")
        fig.update_yaxes(autorange="reversed")  # Gantt style
        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("No activities yet. Use the sidebar to add one!")
