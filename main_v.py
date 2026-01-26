# -*- coding: utf-8 -*-
import streamlit as st
import re
import json
import os
from datetime import datetime, date, time, timedelta

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
#  Redistribution Logic (NEW - Only 25-27)
# ────────────────────────────────────────────────

def redistribute_to_25_27_without_completed(base_plan: dict, state: dict) -> dict:
    """
    Redistribute only uncompleted lectures into days 25, 26, 27 January.
    Completed lectures (study AND exam checked) stay in their original days.
    """
    # Get all lectures from base_plan
    all_lectures = []
    original_day_of_lecture = {}  # Track which day each lecture originally belongs to
    
    for day, info in base_plan.items():
        for lecture in info["lectures"]:
            all_lectures.append(lecture)
            original_day_of_lecture[lecture] = day
    
    # Filter out completed lectures (both study AND exam checked)
    uncompleted_lectures = []
    completed_lectures = []
    
    for lecture in all_lectures:
        # Check if this lecture is marked as completed in state
        is_completed = False
        original_day = original_day_of_lecture.get(lecture)
        
        # Check all days in state for this lecture
        for day in state:
            if day == "overrides":
                continue
            if lecture in state[day]:
                lec_state = state[day][lecture]
                if lec_state.get("study", False) and lec_state.get("exam", False):
                    is_completed = True
                    break
        
        if is_completed:
            completed_lectures.append(lecture)
        else:
            uncompleted_lectures.append(lecture)
    
    # Create target days (25, 26, 27 January)
    target_days = [f"{day} January" for day in [25, 26, 27]]
    
    # Calculate distribution for uncompleted lectures
    total_uncompleted = len(uncompleted_lectures)
    per_day = total_uncompleted // len(target_days)
    remainder = total_uncompleted % len(target_days)
    
    redistributed = {}
    idx = 0
    
    # First, preserve completed lectures in their original days
    for day in base_plan:
        redistributed[day] = {
            "count": 0,
            "lectures": []
        }
    
    for lecture in completed_lectures:
        original_day = original_day_of_lecture.get(lecture)
        if original_day and lecture not in redistributed[original_day]["lectures"]:
            redistributed[original_day]["lectures"].append(lecture)
    
    # Now redistribute uncompleted lectures to 25-27
    for i, day in enumerate(target_days):
        extra = 1 if i < remainder else 0
        count = per_day + extra
        
        # Initialize if not exists
        if day not in redistributed:
            redistributed[day] = {"count": 0, "lectures": []}
        
        # Add uncompleted lectures
        day_lectures = uncompleted_lectures[idx: idx + count]
        redistributed[day]["lectures"].extend(day_lectures)
        idx += count
    
    # Update counts and filter out empty days
    final_plan = {}
    for day in target_days + [d for d in base_plan.keys() if d not in target_days]:
        if day in redistributed and redistributed[day]["lectures"]:
            final_plan[day] = {
                "count": len(redistributed[day]["lectures"]),
                "lectures": redistributed[day]["lectures"]
            }
    
    return final_plan

# ────────────────────────────────────────────────
#  State Management
# ────────────────────────────────────────────────

def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
            # Ensure intervals structure exists for backward compatibility
            for day in state:
                if day == "overrides":
                    continue
                for lecture in state[day]:
                    if "intervals" not in state[day][lecture]:
                        # Convert old format to new format
                        old_start = state[day][lecture].get("start", "00:00")
                        old_end = state[day][lecture].get("end", "00:00")
                        state[day][lecture]["intervals"] = [{
                            "start": old_start,
                            "end": old_end
                        }]
            return state
    except Exception:
        return {}

def save_state(state: dict):
    """Save state with interval support"""
    # Convert time objects to strings
    for day, data in state.items():
        if day == "overrides":
            continue
        for lec, info in data.items():
            if "intervals" in info:
                for interval in info["intervals"]:
                    for key in ("start", "end"):
                        if isinstance(interval.get(key), time):
                            interval[key] = interval[key].strftime("%H:%M")
    
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
#  Helper Functions for Time Intervals
# ────────────────────────────────────────────────

def parse_time_str(time_str):
    """Parse time string to time object"""
    if isinstance(time_str, time):
        return time_str
    try:
        return datetime.strptime(time_str, "%H:%M").time()
    except:
        return time(0, 0)

def calculate_interval_duration(start_time, end_time):
    """Calculate duration in minutes between two times"""
    s_min = start_time.hour * 60 + start_time.minute
    e_min = end_time.hour * 60 + end_time.minute
    if e_min >= s_min:
        return e_min - s_min
    else:  # Cross midnight
        return (1440 - s_min) + e_min

def format_time_display(duration_minutes):
    """Format duration for display"""
    hours = duration_minutes // 60
    minutes = duration_minutes % 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

# ────────────────────────────────────────────────
#  Streamlit App
# ────────────────────────────────────────────────

st.set_page_config(page_title="Study Plan Checklist", layout="wide")
st.title("📚 Study Plan Checklist (Days 25–27)")

# Load base plan
if not os.path.exists(PLAN_FILE):
    st.error(f"File not found: **{PLAN_FILE}**\nPlease create it and paste your study plan.")
    st.stop()

with open(PLAN_FILE, encoding="utf-8") as f:
    raw_text = f.read()

base_plan = parse_plan(raw_text)
state = load_state()

# ── NEW: Redistribute only to 25-27, excluding completed lectures ──
current_plan = redistribute_to_25_27_without_completed(base_plan, state)
current_plan = merge_plan(current_plan, state)  # apply user overrides

# Show statistics
st.sidebar.markdown("### 📊 Statistics")
total_lectures = sum(day_info["count"] for day_info in current_plan.values())
completed_count = 0
for day in state:
    if day == "overrides":
        continue
    for lecture in state[day]:
        if state[day][lecture].get("study", False) and state[day][lecture].get("exam", False):
            completed_count += 1

st.sidebar.write(f"**Total Lectures**: {total_lectures}")
st.sidebar.write(f"**Completed**: {completed_count}")
st.sidebar.write(f"**Remaining**: {total_lectures - completed_count}")

# Show completed lectures
if completed_count > 0:
    with st.sidebar.expander("✅ Completed Lectures"):
        for day in state:
            if day == "overrides":
                continue
            for lecture in state[day]:
                lec_state = state[day][lecture]
                if lec_state.get("study", False) and lec_state.get("exam", False):
                    completed_on = lec_state.get("completed_on", "Unknown")
                    st.write(f"• {lecture} ({completed_on})")

# ── Sidebar controls ────────────────────────────────────────

today = date.today()
today_str = f"{today.day} January"

days = sorted(current_plan.keys())  # should be 25, 26, 27 January
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
        "intervals": [{"start": "00:00", "end": "00:00"}],
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

if st.sidebar.button("🔄 Redistribute Uncompleted"):
    """Button to manually trigger redistribution"""
    # Show confirmation
    if st.sidebar.button("Confirm Redistribution", type="primary", key="confirm_redistribute"):
        # Recalculate distribution
        current_plan = redistribute_to_25_27_without_completed(base_plan, state)
        current_plan = merge_plan(current_plan, state)
        save_state(state)
        st.sidebar.success("Lectures redistributed!")
        st.rerun()

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
            "intervals": [{"start": "00:00", "end": "00:00"}],
            "link": "",
            "completed_on": None,
            "assigned_day": selected_day,
        },
    )
    
    # Ensure intervals exist for backward compatibility
    if "intervals" not in lec_state or not lec_state["intervals"]:
        lec_state["intervals"] = [{"start": "00:00", "end": "00:00"}]

    # Create a clean, elegant layout
    col1, col2, col3 = st.columns([6, 2, 2])
    
    with col1:
        st.markdown(f"**{lecture}**")
    
    with col2:
        study_key = f"study_{selected_day}_{lecture}"
        lec_state["study"] = st.checkbox("Study", value=lec_state["study"], key=study_key, label_visibility="collapsed")
    
    with col3:
        exam_key = f"exam_{selected_day}_{lecture}"
        lec_state["exam"] = st.checkbox("Exam", value=lec_state["exam"], key=exam_key, label_visibility="collapsed")
    
    # Time intervals section with expander
    with st.expander("⏱ Time Slots & Details", expanded=False):
        # Calculate and display total time
        total_duration = 0
        for interval in lec_state["intervals"]:
            start_time = parse_time_str(interval["start"])
            end_time = parse_time_str(interval["end"])
            total_duration += calculate_interval_duration(start_time, end_time)
        
        st.caption(f"Total time: **{format_time_display(total_duration)}** ({total_duration//10} × 10 min)")
        
        # Time intervals management
        st.markdown("**Time Intervals:**")
        
        # Create a container for intervals
        interval_container = st.container()
        
        with interval_container:
            for i, interval in enumerate(lec_state["intervals"]):
                col_a, col_b, col_c = st.columns([3, 3, 1])
                
                with col_a:
                    # Parse current start time
                    current_start = parse_time_str(interval["start"])
                    new_start = st.time_input(
                        "Start",
                        value=current_start,
                        key=f"start_{selected_day}_{lecture}_{i}",
                        label_visibility="collapsed"
                    )
                    interval["start"] = new_start
                
                with col_b:
                    # Parse current end time
                    current_end = parse_time_str(interval["end"])
                    new_end = st.time_input(
                        "End",
                        value=current_end,
                        key=f"end_{selected_day}_{lecture}_{i}",
                        label_visibility="collapsed"
                    )
                    interval["end"] = new_end
                
                with col_c:
                    # Remove interval button (only if more than one interval exists)
                    if len(lec_state["intervals"]) > 1:
                        if st.button("❌", key=f"remove_interval_{selected_day}_{lecture}_{i}", help="Remove this time slot"):
                            lec_state["intervals"].pop(i)
                            save_state(state)
                            st.rerun()
                    else:
                        st.write("")  # Empty space for alignment
        
        # Add new interval button
        col_add1, col_add2 = st.columns([3, 1])
        with col_add1:
            if st.button("➕ Add Another Time Slot", key=f"add_interval_{selected_day}_{lecture}"):
                # Add a new interval, default to last end time + 15 minutes
                if lec_state["intervals"]:
                    last_end = parse_time_str(lec_state["intervals"][-1]["end"])
                    # Add 15 minutes to last end time
                    last_end_minutes = last_end.hour * 60 + last_end.minute
                    new_start_minutes = (last_end_minutes + 15) % 1440
                    new_start_time = time(new_start_minutes // 60, new_start_minutes % 60)
                    new_end_minutes = (new_start_minutes + 30) % 1440  # Default 30 min slot
                    new_end_time = time(new_end_minutes // 60, new_end_minutes % 60)
                else:
                    new_start_time = time(0, 0)
                    new_end_time = time(0, 30)
                
                lec_state["intervals"].append({
                    "start": new_start_time,
                    "end": new_end_time
                })
                save_state(state)
                st.rerun()
        
        # Quick time slot presets
        with col_add2:
            preset_time = st.selectbox(
                "Quick Add",
                ["Select...", "30 min", "45 min", "60 min", "90 min", "2 hours"],
                key=f"preset_{selected_day}_{lecture}",
                label_visibility="collapsed"
            )
            
            if preset_time != "Select...":
                if lec_state["intervals"]:
                    last_end = parse_time_str(lec_state["intervals"][-1]["end"])
                    last_end_minutes = last_end.hour * 60 + last_end.minute
                    new_start_minutes = (last_end_minutes + 15) % 1440  # 15 min break
                else:
                    new_start_minutes = 540  # Default to 9:00 AM
                
                # Calculate duration based on preset
                duration_map = {
                    "30 min": 30,
                    "45 min": 45,
                    "60 min": 60,
                    "90 min": 90,
                    "2 hours": 120
                }
                duration = duration_map.get(preset_time, 30)
                new_end_minutes = (new_start_minutes + duration) % 1440
                
                lec_state["intervals"].append({
                    "start": time(new_start_minutes // 60, new_start_minutes % 60),
                    "end": time(new_end_minutes // 60, new_end_minutes % 60)
                })
                save_state(state)
                st.rerun()
        
        # Notes and links
        st.markdown("---")
        col_notes, col_link = st.columns([2, 1])
        
        with col_notes:
            lec_state["notes"] = st.text_area(
                "Notes",
                lec_state.get("notes", ""),
                key=f"notes_{selected_day}_{lecture}",
                height=100
            )
        
        with col_link:
            lec_state["link"] = st.text_input(
                "Resource Link",
                lec_state.get("link", ""),
                key=f"link_{selected_day}_{lecture}"
            )
            if lec_state["link"]:
                st.markdown(f"[Open Resource]({lec_state['link']})")
        
        # Day reassignment
        st.markdown("---")
        col_move, col_save = st.columns([2, 1])
        
        with col_move:
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
        
        with col_save:
            if st.button("💾 Save Lecture", key=f"save_{selected_day}_{lecture}", type="secondary"):
                if lec_state["study"] and lec_state["exam"] and not lec_state.get("completed_on"):
                    lec_state["completed_on"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_state(state)
                st.success("Saved!")
    
    # Update statistics
    if lec_state["study"]:
        studied += 1
    if lec_state["exam"]:
        examed += 1
    
    # Calculate total minutes for this lecture
    lecture_total_min = 0
    for interval in lec_state["intervals"]:
        start_time = parse_time_str(interval["start"])
        end_time = parse_time_str(interval["end"])
        lecture_total_min += calculate_interval_duration(start_time, end_time)
    
    total_min_today += lecture_total_min

# ── Summary ─────────────────────────────────────────────────

st.markdown("---")

if total_lec > 0:
    progress = ((studied + examed) / (2 * total_lec)) * 100
    st.progress(progress / 100)
    
    # Summary metrics in columns
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    
    with col_stat1:
        st.metric("Lectures", total_lec)
    
    with col_stat2:
        st.metric("Progress", f"{progress:.1f}%")
    
    with col_stat3:
        st.metric("Time Today", format_time_display(total_min_today))
    
    # Detailed breakdown
    with st.expander("Detailed Breakdown"):
        st.write(f"**Studied**: {studied} lectures")
        st.write(f"**Examined**: {examed} lectures")
        st.write(f"**Total time planned**: {total_min_today} minutes ≈ {total_min_today/60:.1f} hours")
        
        # Calculate completed today
        completed_today = 0
        for lecture in current_plan[selected_day]["lectures"]:
            if lecture in state.get(selected_day, {}):
                lec_state = state[selected_day][lecture]
                if lec_state.get("study", False) and lec_state.get("exam", False):
                    completed_today += 1
        
        if completed_today > 0:
            st.success(f"✅ {completed_today} lecture(s) completed today!")
else:
    st.info("No lectures match the current filter.")

# ── Day Summary Table ──────────────────────────────────────

st.markdown("---")
st.subheader("📅 Day Summaries")

# Create a summary table for all days
summary_data = []
for day in sorted(days):
    day_lectures = current_plan.get(day, {}).get("lectures", [])
    day_total_min = 0
    day_completed = 0
    day_studied = 0
    day_examed = 0
    
    for lecture in day_lectures:
        if lecture in state.get(day, {}):
            lec_state = state[day][lecture]
            
            # Calculate time
            lecture_total_min = 0
            for interval in lec_state.get("intervals", [{"start": "00:00", "end": "00:00"}]):
                start_time = parse_time_str(interval["start"])
                end_time = parse_time_str(interval["end"])
                lecture_total_min += calculate_interval_duration(start_time, end_time)
            day_total_min += lecture_total_min
            
            # Count status
            if lec_state.get("study", False):
                day_studied += 1
            if lec_state.get("exam", False):
                day_examed += 1
            if lec_state.get("study", False) and lec_state.get("exam", False):
                day_completed += 1
    
    summary_data.append({
        "Day": day,
        "Lectures": len(day_lectures),
        "Completed": day_completed,
        "Time": format_time_display(day_total_min),
        "Progress": f"{(day_studied + day_examed) / (2 * max(len(day_lectures), 1)) * 100:.1f}%"
    })

# Display summary table
if summary_data:
    st.dataframe(
        summary_data,
        column_config={
            "Day": st.column_config.TextColumn("Day", width="small"),
            "Lectures": st.column_config.NumberColumn("Total", width="small"),
            "Completed": st.column_config.NumberColumn("Done", width="small"),
            "Time": st.column_config.TextColumn("Time", width="small"),
            "Progress": st.column_config.TextColumn("Progress", width="small"),
        },
        hide_index=True,
        use_container_width=True
    )