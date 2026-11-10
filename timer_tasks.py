"""Local lists, tasks, and subtasks for the timer."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tempfile import NamedTemporaryFile
from tkinter import messagebox, ttk
from uuid import uuid4

from task_audio import TaskSounds


BG = "#17181b"
SIDEBAR = "#202125"
PANEL = "#24262b"
LINE = "#36383f"
TEXT = "#f5f5f7"
MUTED = "#b1b4bd"
ACCENT = "#a8cdff"
SELECTED = "#303c50"
FONT = ("Segoe UI", -16)
TAB_FONT = ("Segoe UI Semibold", -15)
ROW_HEIGHT = 43
FILTERS = ("All tasks", "Open", "Important", "Completed")
DEFAULT_LIST = "default"
COMPLETED_ROW = "__completed_section__"


def rounded_box(canvas, x1, y1, x2, y2, radius, *, fill, outline=""):
    return canvas.create_polygon(
        x1, y1 + radius, x1, y1 + radius, x1, y1, x1 + radius, y1, x1 + radius, y1,
        x2 - radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius, x2, y1 + radius,
        x2, y2 - radius, x2, y2 - radius, x2, y2, x2 - radius, y2, x2 - radius, y2,
        x1 + radius, y2, x1 + radius, y2, x1, y2, x1, y2 - radius, x1, y2 - radius,
        smooth=True, splinesteps=20, fill=fill, outline=outline,
    )


class ListTab(tk.Canvas):
    def __init__(self, parent, label, action, *, compact=False) -> None:
        super().__init__(parent, bg=SIDEBAR, height=34, highlightthickness=0, bd=0,
                         takefocus=True, cursor="hand2")
        self.label = label
        self.action = action
        self.compact = compact
        self.selected = False
        self.hovered = False
        self.focused = False
        self.bind("<Configure>", lambda _event: self.paint())
        self.bind("<Enter>", lambda _event: self.set_hover(True))
        self.bind("<Leave>", lambda _event: self.set_hover(False))
        self.bind("<FocusIn>", lambda _event: self.set_focus(True))
        self.bind("<FocusOut>", lambda _event: self.set_focus(False))
        self.bind("<Button-1>", self.activate)
        self.bind("<space>", self.activate)
        self.bind("<Return>", self.activate)
        self.set_label(label)

    def set_label(self, label) -> None:
        self.label = label
        measured = int(self.tk.call("font", "measure", TAB_FONT, label))
        self.configure(width=36 if self.compact else max(70, min(266, measured + 24)))
        self.paint()

    def activate(self, _event) -> str:
        self.focus_set()
        self.action()
        return "break"

    def set_hover(self, value) -> None:
        self.hovered = value
        self.paint()

    def set_focus(self, value) -> None:
        self.focused = value
        self.paint()

    def paint(self) -> None:
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 20 or height < 20:
            return
        if self.selected:
            fill, ink = ("#c2dcff" if self.hovered else ACCENT), BG
        else:
            fill, ink = ("#3c414d" if self.hovered else "#2b2e36"), TEXT
        rounded_box(self, 1, 1, width - 1, height - 1, 11,
                    fill=fill, outline=ACCENT if self.focused else "")
        label = self.label
        while len(label) > 1 and int(self.tk.call("font", "measure", TAB_FONT, label)) > width - 15:
            label = label[:-2].rstrip() + "…" if label.endswith("…") else label[:-1] + "…"
        self.create_text(width / 2, height / 2, text=label, fill=ink, font=TAB_FONT)


class TaskViews:
    def __init__(self, canvas, path: Path, on_open, on_close) -> None:
        self.canvas = canvas
        self.path = path
        self.sounds = TaskSounds()
        self.lists_path = path.with_name("task_lists.json")
        self.on_open = on_open
        self.on_close = on_close
        self.tasks = []
        self.lists = [{"id": DEFAULT_LIST, "name": "Task1"}]
        self.load_error = ""
        try:
            self.tasks = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(self.tasks, list) or any(
                not isinstance(task, dict) or not isinstance(task.get("id"), str) or not task["id"]
                or not isinstance(task.get("title"), str) or not isinstance(task.get("done"), bool)
                for task in self.tasks
            ):
                raise ValueError("Invalid task file")
            if len({task["id"] for task in self.tasks}) != len(self.tasks):
                raise ValueError("Duplicate task IDs")
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            self.tasks = []
            self.load_error = "The saved task list could not be read. Its file was kept."

        try:
            lists = json.loads(self.lists_path.read_text(encoding="utf-8"))
            if not isinstance(lists, list) or not lists or any(
                not isinstance(item, dict) or not isinstance(item.get("id"), str)
                or not isinstance(item.get("name"), str) for item in lists
            ) or len({item["id"] for item in lists}) != len(lists):
                raise ValueError("Invalid list file")
            self.lists = lists
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            self.load_error = "The saved list names could not be read. Their file was kept."

        self.active_list = self.lists[0]["id"]
        self.show_completed = True
        self.visible = False
        self.editing: str | None = None
        self.renaming = None
        self.hover_task = None
        self.pending_task = None
        self.hover_job = None
        self.close_job = None
        style = ttk.Style(canvas)
        style.theme_use("clam")
        style.layout("Tasks.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Tasks.Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, font=FONT, rowheight=ROW_HEIGHT, borderwidth=0)
        style.map("Tasks.Treeview", background=[("selected", SELECTED)], foreground=[("selected", TEXT)])
        style.configure("Tasks.Vertical.TScrollbar", background="#41444d", troughcolor=PANEL,
                        bordercolor=PANEL, lightcolor="#41444d", darkcolor="#41444d", arrowsize=10)

        self.page = tk.Frame(canvas, bg=BG)
        rail = tk.Frame(self.page, bg=SIDEBAR, width=184)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        self.button(rail, "‹  Back to clock", self.on_close).pack(fill="x", padx=14, pady=(20, 15))
        self.search = tk.StringVar(master=rail)
        tk.Label(rail, text="Search tasks", bg=SIDEBAR, fg=MUTED, font=("Segoe UI Semibold", -13)).pack(
            anchor="w", padx=22, pady=(0, 3)
        )
        self.search_entry = tk.Entry(rail, textvariable=self.search, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                                     font=FONT, relief="flat", bd=6, highlightthickness=1,
                                     highlightbackground=LINE, highlightcolor=ACCENT)
        self.search_entry.pack(fill="x", padx=14, pady=(0, 16))
        tk.Label(rail, text="Views", bg=SIDEBAR, fg=MUTED, font=("Segoe UI Semibold", -13)).pack(
            anchor="w", padx=22, pady=(0, 5)
        )
        self.filter = tk.StringVar(master=rail, value=FILTERS[0])
        self.filter_buttons = []
        for name in FILTERS:
            item = self.button(rail, name, lambda value=name: self.set_filter(value))
            item.configure(anchor="w")
            item.pack(fill="x", padx=13, pady=2)
            self.filter_buttons.append(item)
        tk.Label(rail, text="Saved on this PC", bg=SIDEBAR, fg=MUTED, font=("Segoe UI", -13)).pack(
            side="bottom", pady=18
        )

        body = self.body = tk.Frame(self.page, bg=BG)
        body.pack(side="left", fill="both", expand=True, padx=28, pady=(23, 21))
        heading = self.heading = tk.Frame(body, bg=BG)
        heading.pack(fill="x")
        self.title = tk.Label(heading, bg=BG, fg=TEXT, font=("Segoe UI Semibold", -36))
        self.clock = tk.Label(heading, text="", bg=PANEL, fg=ACCENT,
                              font=("Segoe UI Semibold", -23), padx=14, pady=6)
        self.clock.pack(side="right")
        self.title.pack(side="left")
        self.summary = tk.Label(body, bg=BG, fg=MUTED, font=FONT)
        self.summary.pack(anchor="w", pady=(0, 9))
        self.build_tab_strip(body)

        composer = self.composer = tk.Frame(body, bg=BG)
        composer.pack(fill="x", pady=(0, 7))
        self.entry_shell = tk.Canvas(composer, bg=BG, bd=0, highlightthickness=0, height=53)
        self.entry_shell.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_shell.bind("<Configure>", lambda _event: self.paint_entry_shell())
        entry_group = tk.Frame(self.entry_shell, bg=PANEL)
        entry_group.place(x=10, y=4, relwidth=1, width=-20, height=45)
        self.entry_label = tk.Label(entry_group, text="New task", bg=PANEL, fg=MUTED, font=("Segoe UI", -12))
        self.entry_label.pack(anchor="w", pady=(2, 0))
        self.entry = tk.Entry(entry_group, bg=PANEL, fg=TEXT, insertbackground=TEXT, font=FONT,
                              relief="flat", bd=0, highlightthickness=0)
        self.entry.pack(fill="x", pady=(0, 4))
        self.entry.bind("<FocusIn>", lambda _event: self.paint_entry_shell())
        self.entry.bind("<FocusOut>", lambda _event: self.paint_entry_shell())
        self.entry.bind("<Return>", lambda _event: self.submit())
        self.submit_button = ListTab(composer, "Add task", self.submit)
        self.submit_button.selected = True
        self.submit_button.configure(bg=BG, height=40)
        self.submit_button.pack(side="left")
        self.cancel = self.button(composer, "Cancel edit", self.clear_composer)
        footer = self.footer = tk.Frame(body, bg=BG, height=35)
        footer.pack_propagate(False)
        self.status = tk.Label(footer, text=self.load_error, bg=BG, fg=MUTED, font=("Segoe UI", -13))
        self.status.pack(side="left")
        self.actions = tk.Frame(footer, bg=BG)
        self.toggle_button = self.button(self.actions, "Complete", self.toggle_task)
        self.toggle_button.pack(side="left", padx=3)
        for label, action in (("Edit", self.edit_task), ("Delete", self.delete_task)):
            self.button(self.actions, label, action).pack(side="left", padx=3)
        self.full_list = self.make_list(body)
        footer.pack(fill="x", pady=(4, 0))
        self.empty = tk.Label(self.full_list, bg=PANEL, fg=MUTED, font=FONT)
        self.full_list.bind("<<TreeviewSelect>>", lambda _event: self.selection_changed())
        self.full_list.bind("<ButtonRelease-1>", self.checklist_click)
        self.full_list.bind("<Return>", lambda _event: self.toggle_task())
        self.full_list.bind("<space>", lambda _event: self.toggle_task())
        self.full_list.bind("<Delete>", lambda _event: self.delete_task())
        self.full_list.bind("<Right>", lambda _event: self.open_selected_subtasks())
        self.full_list.bind("<Motion>", self.hover_row)
        self.full_list.bind("<Leave>", lambda _event: self.schedule_close_subtasks())
        self.build_subtasks()
        self.body.bind("<Configure>", lambda _event: self.fit_list())
        self.search.trace_add("write", lambda *_args: self.refresh())
        self.refresh()

    @staticmethod
    def button(parent, text, command, *, primary=False):
        return tk.Button(
            parent, text=text, command=command, font=("Segoe UI Semibold", -15), cursor="hand2",
            bg=ACCENT if primary else PANEL, fg=BG if primary else TEXT,
            activebackground="#d5e3ff" if primary else SELECTED,
            activeforeground=BG if primary else TEXT, relief="flat", padx=12, pady=5,
            highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT,
        )

    def make_list(self, parent):
        self.list_shell = tk.Canvas(parent, bg=BG, bd=0, highlightthickness=0, height=100)
        self.list_shell.pack(fill="x")
        self.list_shell.bind("<Configure>", self.paint_list_shell)
        holder = tk.Frame(self.list_shell, bg=PANEL)
        holder.place(x=8, y=6, relwidth=1, relheight=1, width=-16, height=-12)
        tree = ttk.Treeview(holder, columns=("mark", "task", "status"), show="", selectmode="browse",
                            style="Tasks.Treeview", height=5)
        tree.column("mark", width=37, stretch=False, anchor="center")
        tree.column("task", width=155, minwidth=65)
        tree.column("status", width=42, stretch=False, anchor="center")
        tree.tag_configure("done", foreground=MUTED)
        tree.tag_configure("alternate", background="#282a30")
        tree.tag_configure("section", background=SIDEBAR, foreground=ACCENT,
                           font=("Segoe UI Semibold", -14))
        scroll = ttk.Scrollbar(holder, orient="vertical", command=tree.yview, style="Tasks.Vertical.TScrollbar")
        tree.pack(side="left", fill="both", expand=True)
        def update_scrollbar(first, last):
            scroll.set(first, last)
            overflow = float(first) > 0.0 or float(last) < 1.0
            if overflow and not scroll.winfo_manager():
                scroll.pack(side="right", fill="y", before=tree)
            elif not overflow and scroll.winfo_manager():
                scroll.pack_forget()
        tree.configure(yscrollcommand=update_scrollbar)
        return tree

    def paint_list_shell(self, event) -> None:
        if event.width > 30 and event.height > 30:
            self.list_shell.delete("shell")
            shape = rounded_box(self.list_shell, 1, 1, event.width - 2, event.height - 2, 14,
                                fill=PANEL, outline=LINE)
            self.list_shell.addtag_withtag("shell", shape)

    def paint_entry_shell(self) -> None:
        shell = self.entry_shell
        width, height = shell.winfo_width(), shell.winfo_height()
        if width > 30 and height > 30:
            shell.delete("shell")
            edge = ACCENT if self.entry is shell.focus_get() else LINE
            shape = rounded_box(shell, 1, 1, width - 2, height - 2, 12, fill=PANEL, outline=edge)
            shell.addtag_withtag("shell", shape)

    def fit_list(self) -> None:
        height = self.body.winfo_height()
        if height <= 1:
            return
        occupied = sum(w.winfo_reqheight() for w in
                       (self.heading, self.summary, self.tab_bar, self.composer, self.footer))
        available = max(85, height - occupied - 32)
        rows = len(self.full_list.get_children())
        wanted = max(100, rows * ROW_HEIGHT + 12, 204 if self.hover_task else 0)
        target = min(available, wanted)
        if int(self.list_shell.cget("height")) != target:
            self.list_shell.configure(height=target)

    def build_tab_strip(self, parent) -> None:
        bar = self.tab_bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", pady=(0, 7))
        bar.columnconfigure(2, weight=1)
        self.add_tab = ListTab(bar, "+", self.add_list, compact=True)
        self.add_tab.selected = True
        self.add_tab.configure(bg=BG)
        self.add_tab.grid(row=0, column=1, padx=(5, 0))
        self.tab_scroll = ttk.Scrollbar(bar, orient="horizontal")
        self.tab_canvas = tk.Canvas(bar, bg=BG, height=40, width=88, bd=0, highlightthickness=0,
                                    xscrollincrement=24, xscrollcommand=self.update_tab_scroll)
        self.tab_scroll.configure(command=self.tab_canvas.xview)
        self.tab_canvas.grid(row=0, column=0, sticky="w")
        self.tab_strip = tk.Frame(self.tab_canvas, bg=BG)
        self.tab_canvas.create_window(0, 0, anchor="nw", window=self.tab_strip)
        self.tab_strip.bind("<Configure>", lambda _event: self.fit_tabs())
        self.tab_bar.bind("<Configure>", lambda _event: self.fit_tabs())
        self.tab_canvas.bind("<Shift-MouseWheel>", self.scroll_tabs)
        self.render_tabs()

    def fit_tabs(self) -> None:
        content = self.tab_canvas.bbox("all")
        if content is not None and self.tab_bar.winfo_width() > 48:
            width = min(content[2], self.tab_bar.winfo_width() - 43)
            if int(self.tab_canvas.cget("width")) != width:
                self.tab_canvas.configure(width=width)
            self.tab_canvas.configure(scrollregion=content)

    def scroll_tabs(self, event) -> str:
        self.tab_canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def update_tab_scroll(self, first, last) -> None:
        self.tab_scroll.set(first, last)
        overflow = float(first) > 0 or float(last) < 1
        if overflow and not self.tab_scroll.winfo_manager():
            self.tab_scroll.grid(row=1, column=0, sticky="ew")
        elif not overflow:
            self.tab_scroll.grid_remove()
        if hasattr(self, "full_list"):
            self.fit_list()

    def render_tabs(self) -> None:
        for child in self.tab_strip.winfo_children():
            child.destroy()
        self.tab_buttons = {}
        for column, item in enumerate(self.lists):
            list_id = item["id"]
            button = ListTab(self.tab_strip, item["name"], lambda key=list_id: self.switch_list(key))
            button.configure(bg=BG)
            button.grid(row=0, column=column, padx=(0, 4), pady=3, sticky="ew")
            button.bind("<Double-Button-1>", lambda _event, key=list_id: self.rename_list(key))
            button.bind("<F2>", lambda _event, key=list_id: self.rename_list(key))
            button.bind("<Shift-MouseWheel>", self.scroll_tabs)
            self.tab_buttons[list_id] = button
        self.style_tabs()

    def style_tabs(self) -> None:
        for list_id, button in self.tab_buttons.items():
            button.selected = list_id == self.active_list
            button.paint()

    def switch_list(self, list_id: str) -> None:
        if list_id == self.active_list:
            return
        self.active_list = list_id
        self.close_subtasks()
        self.clear_composer()
        self.style_tabs()
        self.set_filter(FILTERS[0])

    def add_list(self) -> None:
        used = {item["name"].casefold() for item in self.lists}
        number = 1
        while f"task{number}" in used:
            number += 1
        item = {"id": uuid4().hex, "name": f"Task{number}"}
        lists = self.lists + [item]
        if self.save_file(self.lists_path, lists):
            self.lists = lists
            self.render_tabs()
            self.switch_list(item["id"])
            self.tab_canvas.after_idle(lambda: self.tab_canvas.xview_moveto(1))

    def rename_list(self, list_id: str) -> str:
        if self.renaming is not None:
            return "break"
        self.switch_list(list_id)
        button = self.tab_buttons[list_id]
        old_name = button.label
        entry = tk.Entry(self.tab_strip, font=FONT, bg=PANEL, fg=TEXT, insertbackground=TEXT, width=16)
        entry.grid(row=0, column=button.grid_info()["column"], padx=2, pady=3)
        button.grid_remove()
        self.renaming = entry
        entry.insert(0, old_name)
        entry.select_range(0, "end")
        entry.focus_set()

        def finish(save: bool, restore_focus: bool = True) -> str:
            if save:
                name = entry.get().strip()
                if not 1 <= len(name) <= 32:
                    self.status.configure(text="Use 1 to 32 characters for a list name.")
                    return "break"
                lists = [dict(item, name=name) if item["id"] == list_id else item for item in self.lists]
                if not self.save_file(self.lists_path, lists):
                    return "break"
                self.lists = lists
                button.set_label(name)
            self.renaming = None
            entry.destroy()
            button.grid()
            if restore_focus:
                button.focus_set()
            self.refresh()
            return "break"

        entry.bind("<Return>", lambda _event: finish(True))
        entry.bind("<Escape>", lambda _event: finish(False))
        entry.bind("<FocusOut>", lambda _event: finish(False, False) if self.renaming is entry else None)
        return "break"

    def open(self) -> None:
        self.visible = True
        self.page.place(x=0, y=0, relwidth=1, relheight=1)
        self.page.lift()
        self.entry.focus_set()
        self.canvas.after_idle(self.fit_list)

    def close(self) -> None:
        self.visible = False
        self.close_subtasks()
        self.page.place_forget()

    def build_subtasks(self) -> None:
        self.details = tk.Frame(self.full_list.master, bg=SIDEBAR, width=256, highlightthickness=1,
                                highlightbackground=LINE)
        self.details.pack_propagate(False)
        self.details.bind("<Enter>", lambda _event: self.cancel_job("close_job"))
        self.details.bind("<Leave>", lambda _event: self.schedule_close_subtasks())
        header = tk.Frame(self.details, bg=SIDEBAR)
        header.pack(fill="x", padx=8, pady=(5, 1))
        self.button(header, "×", self.close_subtasks).pack(side="right")
        tk.Label(header, text="Subtasks", bg=SIDEBAR, fg=ACCENT, font=("Segoe UI Semibold", -14)).pack(side="left")
        self.details_title = tk.Label(self.details, bg=SIDEBAR, fg=TEXT, font=("Segoe UI Semibold", -15),
                                      anchor="w", padx=10, wraplength=240, justify="left")
        self.details_title.pack(fill="x", pady=(0, 4))
        composer = tk.Frame(self.details, bg=SIDEBAR)
        composer.pack(side="bottom", fill="x", padx=7, pady=7)
        self.subentry = tk.Entry(composer, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat",
                                 font=FONT, bd=5, highlightthickness=1, highlightbackground=LINE,
                                 highlightcolor=ACCENT, width=8)
        self.subentry.pack(side="left", expand=True, fill="x")
        self.subentry.bind("<Return>", lambda _event: self.add_subtask())
        self.button(composer, "Add subtask", self.add_subtask, primary=True).pack(side="right", padx=(5, 0))
        self.sublist = tk.Listbox(self.details, bg=PANEL, fg=TEXT, selectbackground=SELECTED,
                                  selectforeground=TEXT, font=FONT, bd=0, highlightthickness=1,
                                  highlightbackground=LINE, highlightcolor=ACCENT, exportselection=False)
        self.sublist.pack(fill="both", expand=True, padx=8)
        self.sublist.bind("<ButtonRelease-1>", lambda _event: self.change_subtask())
        self.sublist.bind("<Return>", lambda _event: self.change_subtask())
        self.sublist.bind("<space>", lambda _event: self.change_subtask())
        self.sublist.bind("<Delete>", lambda _event: self.change_subtask(remove=True))

    def cancel_job(self, name: str) -> None:
        job = getattr(self, name)
        if job is not None:
            self.canvas.after_cancel(job)
            setattr(self, name, None)

    def hover_row(self, event) -> None:
        self.cancel_job("close_job")
        row = self.full_list.identify_row(event.y)
        if row == self.hover_task or self.canvas.focus_get() is self.subentry:
            return
        if self.pending_task == row and self.hover_job is not None:
            return
        self.cancel_job("hover_job")
        if row and row != COMPLETED_ROW:
            self.pending_task = row
            self.hover_job = self.canvas.after(200, lambda: self.show_subtasks(row))
        else:
            self.schedule_close_subtasks()

    def schedule_close_subtasks(self) -> None:
        self.cancel_job("hover_job")
        self.cancel_job("close_job")
        self.close_job = self.canvas.after(330, self.close_if_outside)

    def close_if_outside(self) -> None:
        self.close_job = None
        if not self.details.winfo_ismapped():
            return
        x = self.details.winfo_pointerx() - self.details.winfo_rootx()
        y = self.details.winfo_pointery() - self.details.winfo_rooty()
        if 0 <= x < self.details.winfo_width() and 0 <= y < self.details.winfo_height():
            return
        if self.canvas.focus_get() is not self.subentry:
            self.close_subtasks()

    def open_selected_subtasks(self) -> str:
        task = self.selected()
        if task:
            self.show_subtasks(task["id"])
            self.subentry.focus_set()
        return "break"

    def show_subtasks(self, task_id: str) -> None:
        self.cancel_job("hover_job")
        self.cancel_job("close_job")
        if not self.visible or not self.full_list.exists(task_id):
            return
        if task_id != self.hover_task:
            self.subentry.delete(0, "end")
        self.hover_task = task_id
        self.refresh_subtasks()
        if not self.details.winfo_manager():
            self.details.pack(side="right", fill="y", padx=(6, 0), before=self.full_list)
            self.fit_list()

    def close_subtasks(self) -> None:
        self.cancel_job("hover_job")
        self.cancel_job("close_job")
        self.hover_task = None
        self.details.pack_forget()
        self.fit_list()
        if self.canvas.focus_get() in (self.subentry, self.sublist):
            self.full_list.focus_set()

    def find_task(self, task_id):
        return next((task for task in self.tasks if task["id"] == task_id), None)

    def refresh_subtasks(self) -> None:
        task = self.find_task(self.hover_task)
        if task:
            title = task["title"]
            self.details_title.configure(text=title if len(title) <= 52 else title[:51] + "…")
            self.sublist.delete(0, "end")
            for item in task.get("subtasks", []):
                self.sublist.insert("end", ("✓  " if item["done"] else "○  ") + item["title"])

    def add_subtask(self) -> str:
        task = self.find_task(self.hover_task)
        name = self.subentry.get().strip()
        if task and 1 <= len(name) <= 160:
            subtasks = task.get("subtasks", []) + [{"title": name, "done": False}]
            if self.update_task(task, subtasks=subtasks):
                self.subentry.delete(0, "end")
                self.refresh_subtasks()
                self.sublist.see("end")
        return "break"

    def change_subtask(self, *, remove=False) -> str:
        task = self.find_task(self.hover_task)
        selected = self.sublist.curselection()
        if task and selected:
            index = selected[0]
            subtasks = list(task.get("subtasks", []))
            completing = not remove and not subtasks[index]["done"]
            if remove:
                del subtasks[index]
            else:
                subtasks[index] = dict(subtasks[index], done=not subtasks[index]["done"])
            if self.update_task(task, subtasks=subtasks):
                if completing:
                    self.sounds.complete()
                self.refresh_subtasks()
                if index < len(subtasks):
                    self.sublist.selection_set(index)
                    self.sublist.activate(index)
                    self.sublist.see(index)
        return "break"

    def select_task(self, task_id: str) -> None:
        if not self.full_list.exists(task_id):
            self.set_filter(FILTERS[0])
        if self.full_list.exists(task_id):
            self.full_list.selection_set(task_id)
            self.full_list.focus(task_id)
            self.full_list.see(task_id)
            self.full_list.focus_set()

    def set_filter(self, name: str) -> None:
        self.close_subtasks()
        self.filter.set(name)
        self.status.configure(text=self.load_error)
        self.refresh()

    def checklist_click(self, event) -> None:
        tree = self.full_list
        row = tree.identify_row(event.y)
        if row == COMPLETED_ROW:
            self.toggle_completed()
        elif row and tree.identify_column(event.x) in ("#1", "#3"):
            tree.selection_set(row)
            tree.focus(row)
            if tree.identify_column(event.x) == "#1":
                self.toggle_task()
            else:
                task = self.selected()
                if task:
                    self.update_task(task, important=not task.get("important", False))

    def toggle_completed(self) -> None:
        self.show_completed = not self.show_completed
        self.close_subtasks()
        self.refresh()

    def selection_changed(self) -> None:
        task = self.selected()
        if task is None:
            self.actions.pack_forget()
        else:
            self.toggle_button.configure(text="Reopen" if task["done"] else "Complete")
            self.actions.pack(side="right")

    def refresh(self) -> None:
        selected = self.full_list.selection()
        current = self.filter.get()
        list_tasks = [task for task in self.tasks if task.get("list_id", DEFAULT_LIST) == self.active_list]
        done = sum(task["done"] for task in list_tasks)
        counts = (len(list_tasks), len(list_tasks) - done, sum(bool(task.get("important")) for task in list_tasks), done)
        self.title.configure(text=next(item["name"] for item in self.lists if item["id"] == self.active_list))
        self.summary.configure(text=f"{counts[1]} open  ·  {done} completed")
        for name, button, count in zip(FILTERS, self.filter_buttons, counts):
            active = name == current
            button.configure(text=f"{name}   {count}", bg=SELECTED if active else SIDEBAR,
                             fg=ACCENT if active else TEXT, highlightbackground=SIDEBAR)
        tree = self.full_list
        tree.delete(*tree.get_children())
        query = self.search.get().strip().casefold()
        matching = [task for task in list_tasks if not query or query in task["title"].casefold()]
        if current == "Important":
            matching = [task for task in matching if task.get("important")]
        open_tasks = [task for task in matching if not task["done"]]
        done_tasks = [task for task in matching if task["done"]]
        if current != "Completed":
            self.render_rows(open_tasks)
        if done_tasks and current in ("All tasks", "Important"):
            tree.insert("", "end", iid=COMPLETED_ROW, tags=("section",), values=(
                "⌄" if self.show_completed else "›", f"Completed  {len(done_tasks)}", ""
            ))
        if current == "Completed" or (current != "Open" and self.show_completed):
            self.render_rows(done_tasks)
        if tree.get_children():
            self.empty.place_forget()
        else:
            self.empty.configure(text="No matching tasks" if query else "No tasks in this view")
            self.empty.place(relx=0.5, rely=0.5, anchor="center")
        if selected and self.full_list.exists(selected[0]):
            self.full_list.selection_set(selected[0])
            self.full_list.focus(selected[0])
        self.selection_changed()
        if self.hover_task and not tree.exists(self.hover_task):
            self.close_subtasks()
        self.fit_list()

    def render_rows(self, tasks) -> None:
        for index, task in enumerate(tasks):
            tags = ["alternate"] if index % 2 else []
            if task["done"]:
                tags.append("done")
            subtasks = task.get("subtasks", [])
            title = task["title"]
            if subtasks:
                title += f"    ·    {sum(item['done'] for item in subtasks)}/{len(subtasks)}"
            self.full_list.insert("", "end", iid=task["id"], tags=tags, values=(
                "✓" if task["done"] else "○", title, "★" if task.get("important") else "☆"
            ))

    def save_file(self, path: Path, data) -> bool:
        if self.load_error:
            self.status.configure(text=self.load_error)
            return False
        pending = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=path.parent, encoding="utf-8", mode="w", delete=False) as handle:
                pending = Path(handle.name)
                json.dump(data, handle, ensure_ascii=False, indent=2)
            pending.replace(path)
        except OSError:
            self.status.configure(text="Couldn't save the task list. Your previous list was kept.")
            return False
        finally:
            if pending is not None:
                try:
                    pending.unlink(missing_ok=True)
                except OSError:
                    pass
        return True

    def save(self, tasks) -> bool:
        if not self.save_file(self.path, tasks):
            return False
        self.tasks = tasks
        self.refresh()
        return True

    def update_task(self, task, **changes) -> bool:
        return self.save([dict(item, **changes) if item is task else item for item in self.tasks])

    def selected(self):
        selected = self.full_list.selection()
        return next((task for task in self.tasks if selected and task["id"] == selected[0]), None)

    def clear_composer(self) -> None:
        self.entry.delete(0, "end")
        self.editing = None
        self.entry_label.configure(text="New task")
        self.submit_button.set_label("Add task")
        self.cancel.pack_forget()

    def submit(self) -> None:
        title = self.entry.get().strip()
        if not 1 <= len(title) <= 240:
            self.status.configure(text="Enter a task name between 1 and 240 characters.")
            return
        task_id = self.editing or uuid4().hex
        if self.editing:
            tasks = [dict(task, title=title) if task["id"] == task_id else task for task in self.tasks]
        else:
            tasks = self.tasks + [{"id": task_id, "title": title, "done": False, "list_id": self.active_list}]
        if self.save(tasks):
            self.clear_composer()
            self.status.configure(text="Task saved.")
            self.entry.focus_set()

    def toggle_task(self) -> None:
        if self.full_list.selection() == (COMPLETED_ROW,):
            self.toggle_completed()
            return
        task = self.selected()
        if task and self.update_task(task, done=not task["done"]):
            if not task["done"]:
                self.sounds.complete()
            self.status.configure(text="Task reopened." if task["done"] else "Task completed.")

    def edit_task(self) -> None:
        task = self.selected()
        if task:
            self.clear_composer()
            self.editing = task["id"]
            self.entry_label.configure(text="Edit task")
            self.entry.insert(0, task["title"])
            self.entry.selection_range(0, "end")
            self.entry.focus_set()
            self.submit_button.set_label("Save")
            self.cancel.pack(side="left", padx=(8, 0))

    def delete_task(self) -> None:
        task = self.selected()
        if task and messagebox.askyesno("Delete task", f'Delete "{task["title"]}"?', parent=self.canvas.winfo_toplevel()):
            if self.save([item for item in self.tasks if item is not task]):
                if self.editing == task["id"]:
                    self.clear_composer()
                self.status.configure(text="Task deleted.")
