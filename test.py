# -*- coding: utf-8 -*-
import time as time_mod
from datetime import datetime, date, timedelta
from datetime import time as dtime
import streamlit as st
import json
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

ROUTINE_FILE = "FinalRoutine/routine_state.json"

# ────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────

def time_to_str(t: dtime) -> str:
    """Convert datetime.time to 12-hour string with AM/PM"""
    return t.strftime("%I:%M %p").lstrip("0")

def str_to_time(t_str: str) -> dtime:
    """Convert '09:00 AM' → datetime.time"""
    return datetime.strptime(t_str, "%I:%M %p").time()

def parse_minutes(t: str) -> int:
    """Parse '09:00 AM' to minutes since midnight"""
    return str_to_time(t).hour * 60 + str_to_time(t).minute

def format_time(seconds: float) -> str:
    """Format seconds into HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

CATEGORIES = {
    "Work": "blue",
    "Sleep": "purple",
    "Exercise": "green",
    "Leisure": "orange",
    "Study": "cyan",
    "Other": "gray"
}

# ────────────────────────────────────────────────
#  State Management
# ────────────────────────────────────────────────

def load_routine() -> dict:
    if not os.path.exists(ROUTINE_FILE):
        return {"routines": {}, "habits": {}}
    try:
        with open(ROUTINE_FILE, encoding="utf-8") as f:
            data = json.load(f)
            # Backward compatibility
            if "routines" not in data:
                data["routines"] = data
            if "habits" not in data:
                data["habits"] = {}
            return data
    except Exception:
        return {"routines": {}, "habits": {}}

def save_routine(data: dict):
    os.makedirs(os.path.dirname(ROUTINE_FILE), exist_ok=True)
    with open(ROUTINE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_routine()
routines = data.setdefault("routines", {})
habits = data.setdefault("habits", {})

# ────────────────────────────────────────────────
#  Streamlit App
# ────────────────────────────────────────────────

st.set_page_config(page_title="Routine & Habit Tracker", layout="wide", initial_sidebar_state="expanded")
st.title("🗓️ Professional Routine & Habit Tracker")

# Tabs
daily_tab, habits_tab, weekly_tab, analytics_tab = st.tabs(["Daily Routines", "Habits", "Weekly Summary", "Analytics"])

with daily_tab:
    # Sidebar: choose date
    st.sidebar.header("Select Date")
    selected_date = st.sidebar.date_input("Routine Date", value=date.today())
    day_str = selected_date.strftime("%Y-%m-%d")
    day_routine = routines.setdefault(day_str, {})

    # ── Add Activity ────────────────────────────────────────────
    st.sidebar.header("➕ Add Activity")
    activity_name = st.sidebar.text_input("Activity name (e.g. Work, Sleep, Gym)")
    category = st.sidebar.selectbox("Category", list(CATEGORIES.keys()), index=0)
    default_start = dtime(9, 0)
    default_end = dtime(10, 0)
    start_t = st.sidebar.time_input("Start time", value=default_start)
    end_t = st.sidebar.time_input("End time", value=default_end)
    start_time = time_to_str(start_t)
    end_time = time_to_str(end_t)

    if st.sidebar.button("Add Activity", disabled=not activity_name.strip()):
        act = activity_name.strip()
        day_routine[act] = {
            "completed": False,
            "notes": "",
            "category": category,
            "intervals": [{"start": start_time, "end": end_time}],
            "logged_on": None,
            "timer": {
                "state": "idle",
                "accumulated_seconds": 0.0,
                "last_update": None
            }
        }
        save_routine(data)
        st.sidebar.success(f"Added **{act}** to {day_str}")
        st.rerun()

    # ── Delete Activity ─────────────────────────────────────────
    st.sidebar.header("🗑️ Delete Activity")
    if day_routine:
        to_delete = st.sidebar.selectbox("Select activity", list(day_routine.keys()))
        if st.sidebar.button("Delete Activity"):
            del day_routine[to_delete]
            save_routine(data)
            st.sidebar.success(f"Deleted **{to_delete}** from {day_str}")
            st.rerun()
    else:
        st.sidebar.info("No activities to delete.")

    st.sidebar.markdown("---")
    if st.sidebar.button("💾 Save Progress"):
        save_routine(data)
        st.sidebar.success("Progress saved!")

    # ── Main content ────────────────────────────────────────────

    st.subheader(f"Routine for {day_str}")

    total_acts = 0
    completed = 0
    total_planned_minutes = 0
    total_actual_seconds = 0
    timeline_data = []

    # Check if any timer is running to enable auto-refresh
    any_running = any(info.get("timer", {}).get("state") == "running" for info in day_routine.values())
    if any_running:
        st_autorefresh(interval=1000, key="timer_refresh")

    for act, info in day_routine.items():
        total_acts += 1

        # Initialize timer if missing
        if "timer" not in info:
            info["timer"] = {
                "state": "idle",
                "accumulated_seconds": 0.0,
                "last_update": None
            }

        with st.expander(f"📌 {act} ({info['category']})", expanded=True):
            # ✅ Checkbox with auto-save
            comp_key = f"comp_{day_str}_{act}"
            new_completed = st.checkbox("Done", value=info["completed"], key=comp_key)
            if new_completed != info["completed"]:
                info["completed"] = new_completed
                if info["completed"] and not info.get("logged_on"):
                    info["logged_on"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_routine(data)

            if info["completed"]:
                completed += 1

            # 🕒 Multiple planned intervals
            if "intervals" not in info:
                info["intervals"] = [{"start": "09:00 AM", "end": "10:00 AM"}]

            total_duration = 0
            for i, interval in enumerate(info["intervals"]):
                cols = st.columns([2, 2, 2])
                start_t_val = str_to_time(interval["start"])
                end_t_val = str_to_time(interval["end"])
                new_start = cols[0].time_input(
                    f"Start {i+1}", value=start_t_val,
                    key=f"start_{day_str}_{act}_{i}"
                )
                new_end = cols[1].time_input(
                    f"End {i+1}", value=end_t_val,
                    key=f"end_{day_str}_{act}_{i}"
                )
                if new_start != start_t_val or new_end != end_t_val:
                    interval["start"] = time_to_str(new_start)
                    interval["end"] = time_to_str(new_end)
                    save_routine(data)

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
                    "Completed": "Yes" if info["completed"] else "No",
                    "Category": info["category"]
                })

            # ➕ Add new interval
            if st.button(f"Add Interval to {act}", key=f"addint_{day_str}_{act}"):
                info["intervals"].append({"start": "09:00 AM", "end": "10:00 AM"})
                save_routine(data)
                st.rerun()

            # ── Time Tracker ───────────────────────────────────────
            st.markdown("### ⏲️ Time Tracker")
            timer = info["timer"]
            now = time_mod.time()

            # Update if running
            if timer["state"] == "running":
                if timer["last_update"] is not None:
                    delta = now - timer["last_update"]
                    timer["accumulated_seconds"] += delta
                timer["last_update"] = now
                save_routine(data)

            elapsed_seconds = int(timer["accumulated_seconds"])

            st.metric("Time Spent", format_time(elapsed_seconds))

            state = timer["state"]
            btn_cols = st.columns(4)

            if state in ["idle", "stopped"]:
                if btn_cols[0].button("Start", key=f"start_timer_{day_str}_{act}"):
                    timer["state"] = "running"
                    timer["last_update"] = time_mod.time()
                    save_routine(data)
                    st.rerun()
            elif state == "running":
                if btn_cols[0].button("Pause", key=f"pause_timer_{day_str}_{act}"):
                    timer["state"] = "paused"
                    timer["last_update"] = None
                    save_routine(data)
                    st.rerun()
                if btn_cols[1].button("Stop", key=f"stop_timer_{day_str}_{act}"):
                    timer["state"] = "stopped"
                    timer["last_update"] = None
                    save_routine(data)
                    st.rerun()
            elif state == "paused":
                if btn_cols[0].button("Resume", key=f"resume_timer_{day_str}_{act}"):
                    timer["state"] = "running"
                    timer["last_update"] = time_mod.time()
                    save_routine(data)
                    st.rerun()
                if btn_cols[1].button("Stop", key=f"stop_timer_{day_str}_{act}"):
                    timer["state"] = "stopped"
                    timer["last_update"] = None
                    save_routine(data)
                    st.rerun()

            if btn_cols[3].button("Reset Timer", key=f"reset_timer_{day_str}_{act}"):
                timer["state"] = "idle"
                timer["accumulated_seconds"] = 0.0
                timer["last_update"] = None
                save_routine(data)
                st.rerun()

            # 📝 Notes
            new_notes = st.text_area("Notes", info["notes"], key=f"notes_{day_str}_{act}")
            if new_notes != info["notes"]:
                info["notes"] = new_notes
                save_routine(data)

            total_planned_minutes += total_duration
            total_actual_seconds += elapsed_seconds

    # ── Summary ─────────────────────────────────────────────────

    st.markdown("---")
    if total_acts > 0:
        progress = (completed / total_acts) * 100
        st.progress(progress / 100)
        st.write(f"**Activities**: {total_acts} | Completed: **{completed}**")
        st.write(f"**Progress**: {progress:.1f}%")
        st.write(f"**Total planned time**: {total_planned_minutes} min ≈ {total_planned_minutes/60:.1f} hours")
        st.write(f"**Total actual time**: {format_time(total_actual_seconds)} ≈ {total_actual_seconds/3600:.1f} hours")

        # 📊 Timeline chart
        if timeline_data:
            df = pd.DataFrame(timeline_data)
            fig = px.timeline(df, x_start="Start", x_end="Finish", y="Task", color="Category",
                              color_discrete_map=CATEGORIES)
            fig.update_yaxes(autorange="reversed")  # Gantt style
            fig.update_layout(xaxis_title="Time")
            st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No activities yet. Use the sidebar to add one!")

    st.info("Note: Timers continue counting even if the app is closed/reopened, as long as state is 'running'. Refresh the page or interact to update displayed times.")

with habits_tab:
    st.subheader("Habit Tracker – Build Consistency")

    col1, col2 = st.columns([3,1])

    with col1:
        habit_name = st.text_input("New Habit", placeholder="e.g. Drink 2L water, Read 20 pages, Meditate")
        freq = st.selectbox("Frequency", ["Daily", "Weekly", "Custom (times per week)"])
        target = 1
        if freq == "Custom (times per week)":
            target = st.number_input("Target times per week", min_value=1, max_value=7, value=3)

        notes = st.text_area("Notes / Reminder", height=80)

        if st.button("Add Habit", disabled=not habit_name.strip()):
            hname = habit_name.strip()
            if hname not in habits:
                habits[hname] = {
                    "frequency": freq,
                    "target": target if freq != "Daily" else 1,
                    "completions": {},  # "YYYY-MM-DD": true/false
                    "notes": notes,
                    "created": date.today().isoformat()
                }
                save_routine(data)
                st.success(f"Added habit: **{hname}**")
                st.rerun()
            else:
                st.warning("Habit already exists.")

    with col2:
        if habits:
            to_del = st.selectbox("Delete Habit", list(habits.keys()))
            if st.button("🗑️ Delete", type="primary"):
                del habits[to_del]
                save_routine(data)
                st.rerun()

    # Display Habits
    if habits:
        st.markdown("### Your Habits")
        today_str = date.today().isoformat()

        for hname, hinfo in habits.items():
            with st.expander(f"**{hname}**  ({hinfo['frequency']})", expanded=True):
                comp_today = hinfo["completions"].get(today_str, False)

                checked = st.checkbox("Completed today", value=comp_today, key=f"chk_{hname}")
                if checked != comp_today:
                    hinfo["completions"][today_str] = checked
                    save_routine(data)
                    st.rerun()

                st.caption(hinfo.get("notes", ""))

                # Streak calculation (simple for daily; adjust for weekly/custom)
                streak = 0
                longest = 0
                current = 0
                dates = sorted(hinfo["completions"].keys(), reverse=True)
                for d in dates:
                    if hinfo["completions"][d]:
                        current += 1
                        longest = max(longest, current)
                    else:
                        current = 0
                    if d == today_str and checked:
                        streak = current

                if streak > 0:
                    st.success(f"Current streak: **{streak}** day{'s' if streak>1 else ''} 🔥")
                else:
                    st.info("No streak yet – start today!")

                st.write(f"Longest streak: **{longest}**")

                # Simple 30-day heatmap-like view
                if len(hinfo["completions"]) > 0:
                    df = pd.DataFrame({
                        "Date": pd.to_datetime(list(hinfo["completions"].keys())),
                        "Completed": [1 if v else 0 for v in hinfo["completions"].values()]
                    }).tail(30)
                    fig = px.bar(df, x="Date", y="Completed", color="Completed",
                                 color_continuous_scale=["lightgray", "green"])
                    fig.update_layout(showlegend=False, height=150)
                    st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No habits yet. Add one above!")

with weekly_tab:
    st.subheader("Weekly Summary")
    # Get current week
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    week_dates = [start_of_week + timedelta(days=i) for i in range(7)]
    week_data = []
    for d in week_dates:
        d_str = d.strftime("%Y-%m-%d")
        d_routine = routines.get(d_str, {})
        comp = sum(1 for info in d_routine.values() if info.get("completed", False))
        total_acts = len(d_routine)
        planned_min = sum(sum((parse_minutes(intv["end"]) - parse_minutes(intv["start"]) if parse_minutes(intv["end"]) >= parse_minutes(intv["start"]) else (1440 - parse_minutes(intv["start"]) + parse_minutes(intv["end"]))) for intv in info.get("intervals", [])) for info in d_routine.values())
        actual_sec = sum(info.get("timer", {}).get("accumulated_seconds", 0) for info in d_routine.values())
        week_data.append({
            "Date": d_str,
            "Completed": comp,
            "Total Activities": total_acts,
            "Planned Hours": planned_min / 60,
            "Actual Hours": actual_sec / 3600
        })
    if week_data:
        df_week = pd.DataFrame(week_data)
        st.dataframe(df_week.style.format({"Planned Hours": "{:.1f}", "Actual Hours": "{:.1f}"}))
        fig_week = px.bar(df_week, x="Date", y=["Planned Hours", "Actual Hours"], barmode="group", title="Weekly Planned vs Actual Time")
        st.plotly_chart(fig_week)
    else:
        st.info("No data for this week.")

with analytics_tab:
    st.subheader("Analytics")
    # Aggregate by category
    all_data = []
    for day_str, day_routine in routines.items():
        for act, info in day_routine.items():
            actual_sec = info.get("timer", {}).get("accumulated_seconds", 0)
            all_data.append({
                "Date": day_str,
                "Activity": act,
                "Category": info.get("category", "Other"),
                "Completed": info.get("completed", False),
                "Actual Hours": actual_sec / 3600
            })
    if all_data:
        df_all = pd.DataFrame(all_data)
        # Total time by category
        cat_time = df_all.groupby("Category")["Actual Hours"].sum().reset_index()
        fig_pie = px.pie(cat_time, values="Actual Hours", names="Category", title="Time Distribution by Category")
        st.plotly_chart(fig_pie)

        # Completion rate
        completion_rate = df_all["Completed"].mean() * 100
        st.write(f"Overall Completion Rate: {completion_rate:.1f}%")

        # Time series
        df_all["Date"] = pd.to_datetime(df_all["Date"])
        time_series = df_all.groupby("Date")["Actual Hours"].sum().reset_index()
        fig_line = px.line(time_series, x="Date", y="Actual Hours", title="Daily Actual Time Spent")
        st.plotly_chart(fig_line)
    else:
        st.info("No data available for analytics.")