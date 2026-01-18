# -*- coding: utf-8 -*-
"""
Study Plan Checklist UI
- Reads a study plan from 'plan.txt'
- Parses days and lectures
- Renders a Tkinter UI with checkboxes for Study and Exam per lecture
- Provides filtering, progress stats, and save/load of checklist state

Expected 'plan.txt' format (example):
Study Plan (18–25 January)
18 January (12 lectures)
Bangla Grammar Lecture-1: শব্দ ১
...
19 January (11 lectures)
...

Author: You
"""

import re
import json
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

PLAN_FILE = "plan.txt"
STATE_FILE = "plan_state.json"


# -----------------------------
# Parsing utilities
# -----------------------------
DAY_HEADER_RE = re.compile(r"^(\d{1,2}\s+January)\s*\((\d+)\s*lectures\)", re.IGNORECASE)

def parse_plan(text):
    """
    Parse the plan.txt content into a structured dict:
    {
      '18 January': {
          'count': 12,
          'lectures': [
              'Bangla Grammar Lecture-1: শব্দ ১',
              ...
          ]
      },
      ...
    }
    """
    lines = [ln.strip() for ln in text.splitlines()]
    plan = {}
    current_day = None
    current_count = None

    for ln in lines:
        if not ln:
            continue

        # Detect day header
        m = DAY_HEADER_RE.match(ln)
        if m:
            day = m.group(1)
            count = int(m.group(2))
            plan[day] = {"count": count, "lectures": []}
            current_day = day
            current_count = count
            continue

        # Skip the global title line
        if ln.lower().startswith("study plan"):
            continue

        # Lecture line (anything non-empty under a day)
        if current_day:
            plan[current_day]["lectures"].append(ln)

    # Optional: sanity check counts
    for day, info in plan.items():
        declared = info["count"]
        actual = len(info["lectures"])
        if declared != actual:
            # Not fatal—just warn in console
            print(f"[WARN] {day}: declared {declared} lectures, parsed {actual}.")
    return plan


# -----------------------------
# State management
# -----------------------------
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        messagebox.showerror("Save Error", f"Could not save state:\n{e}")


# -----------------------------
# UI
# -----------------------------
class ChecklistApp(tk.Tk):
    def __init__(self, plan):
        super().__init__()
        self.title("Study Plan Checklist (18–25 January)")
        self.geometry("1000x700")

        self.plan = plan
        self.state = load_state()  # {day: {lecture: {'study': bool, 'exam': bool}}}

        # Top controls
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)

        self.day_var = tk.StringVar(value="All Days")
        days = ["All Days"] + list(plan.keys())
        ttk.Label(top, text="Day:").pack(side="left")
        self.day_combo = ttk.Combobox(top, textvariable=self.day_var, values=days, state="readonly", width=20)
        self.day_combo.pack(side="left", padx=5)
        self.day_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_list())

        self.search_var = tk.StringVar()
        ttk.Label(top, text="Search:").pack(side="left", padx=(20, 5))
        search_entry = ttk.Entry(top, textvariable=self.search_var, width=40)
        search_entry.pack(side="left")
        search_entry.bind("<Return>", lambda e: self.refresh_list())

        ttk.Button(top, text="Filter", command=self.refresh_list).pack(side="left", padx=5)
        ttk.Button(top, text="Clear", command=self.clear_filters).pack(side="left", padx=5)
        ttk.Button(top, text="Save Progress", command=self.save_progress).pack(side="right", padx=5)
        ttk.Button(top, text="Load plan.txt", command=self.load_plan_file).pack(side="right", padx=5)

        # Progress bar and stats
        stats = ttk.Frame(self)
        stats.pack(fill="x", padx=10, pady=(0, 10))
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(stats, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", side="left", expand=True)
        self.stats_label = ttk.Label(stats, text="")
        self.stats_label.pack(side="left", padx=10)
        self.update_stats()

        # Scrollable checklist area
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.list_frame = ttk.Frame(canvas)

        self.list_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Build initial list
        self.refresh_list()

        # Keyboard shortcuts
        self.bind("<Control-s>", lambda e: self.save_progress())
        self.bind("<F5>", lambda e: self.refresh_list())

    def clear_filters(self):
        self.day_var.set("All Days")
        self.search_var.set("")
        self.refresh_list()

    def load_plan_file(self):
        path = filedialog.askopenfilename(
            title="Select plan.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            self.plan = parse_plan(text)
            self.day_combo["values"] = ["All Days"] + list(self.plan.keys())
            self.day_var.set("All Days")
            self.refresh_list()
            self.update_stats()
            messagebox.showinfo("Loaded", "Plan loaded successfully.")
        except Exception as e:
            messagebox.showerror("Load Error", f"Could not load plan:\n{e}")

    def get_filtered_items(self):
        day_filter = self.day_var.get()
        query = self.search_var.get().strip().lower()

        items = []
        for day, info in self.plan.items():
            if day_filter != "All Days" and day != day_filter:
                continue
            for lecture in info["lectures"]:
                if query and query not in lecture.lower():
                    continue
                items.append((day, lecture))
        return items

    def refresh_list(self):
        # Clear current list
        for w in self.list_frame.winfo_children():
            w.destroy()

        items = self.get_filtered_items()

        # Header row
        header = ttk.Frame(self.list_frame)
        header.pack(fill="x", pady=(0, 5))
        ttk.Label(header, text="Date", width=20, anchor="w").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Lecture", width=70, anchor="w").grid(row=0, column=1, sticky="w")
        ttk.Label(header, text="Study", width=10, anchor="center").grid(row=0, column=2)
        ttk.Label(header, text="Exam", width=10, anchor="center").grid(row=0, column=3)

        # Rows
        for i, (day, lecture) in enumerate(items, start=1):
            row = ttk.Frame(self.list_frame)
            row.pack(fill="x", pady=2)

            ttk.Label(row, text=day, width=20, anchor="w").grid(row=0, column=0, sticky="w")
            ttk.Label(row, text=lecture, width=70, anchor="w").grid(row=0, column=1, sticky="w")

            # Initialize state
            day_state = self.state.setdefault(day, {})
            lec_state = day_state.setdefault(lecture, {"study": False, "exam": False})

            study_var = tk.BooleanVar(value=lec_state["study"])
            exam_var = tk.BooleanVar(value=lec_state["exam"])

            def make_callback(d=day, l=lecture, sv=study_var, ev=exam_var):
                def cb(*_):
                    self.state[d][l]["study"] = sv.get()
                    self.state[d][l]["exam"] = ev.get()
                    self.update_stats()
                return cb

            study_var.trace_add("write", make_callback())
            exam_var.trace_add("write", make_callback())

            ttk.Checkbutton(row, variable=study_var).grid(row=0, column=2, padx=5)
            ttk.Checkbutton(row, variable=exam_var).grid(row=0, column=3, padx=5)

        self.update_stats()

    def update_stats(self):
        total = 0
        studied = 0
        examed = 0

        for day, info in self.plan.items():
            for lecture in info["lectures"]:
                total += 1
                if self.state.get(day, {}).get(lecture, {}).get("study"):
                    studied += 1
                if self.state.get(day, {}).get(lecture, {}).get("exam"):
                    examed += 1

        # Progress: average of study and exam completion
        progress = 0.0
        if total > 0:
            progress = ((studied + examed) / (2 * total)) * 100.0

        self.progress_var.set(progress)
        self.stats_label.config(
            text=f"Lectures: {total} | Studied: {studied} | Exam: {examed} | Progress: {progress:.1f}%"
        )

    def save_progress(self):
        save_state(self.state)
        messagebox.showinfo("Saved", "Progress saved.")


# -----------------------------
# Entry point
# -----------------------------
def main():
    # Read plan.txt
    if not os.path.exists(PLAN_FILE):
        messagebox.showerror("Missing plan.txt", "No 'plan.txt' found. Please create it and paste your study plan.")
        return

    with open(PLAN_FILE, "r", encoding="utf-8") as f:
        text = f.read()

    plan = parse_plan(text)
    if not plan:
        messagebox.showerror("Parse Error", "Could not parse any days/lectures from 'plan.txt'.")
        return

    app = ChecklistApp(plan)
    app.mainloop()


if __name__ == "__main__":
    main()
