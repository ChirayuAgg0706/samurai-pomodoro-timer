"""An elegant full-screen Pomodoro timer with split-flap digit transitions."""

from __future__ import annotations

import math
import os
import time
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from tkinter import filedialog, messagebox
from zipfile import BadZipFile, ZipFile

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps, ImageTk
from timer_sticky import StickyClock, another_app_is_active
from timer_tasks import TaskViews


BACKGROUND = "#111216"
CARD_BORDER = (80, 83, 94, 247)
HINGE = (21, 22, 26, 255)
DIGIT = (248, 248, 250, 255)
BUTTON = "#f5f5f7"
PANEL = "#202125"
FIELD = "#2a2c32"
EDGE = "#3a3c44"
TEXT = "#e6e7eb"
DOCK = "#1c1d22"
BUTTON_SURFACE = "#2a2c32"
BUTTON_HOVER = "#383b44"
BUTTON_EDGE = "#434650"
PRIMARY_SURFACE = "#30405a"
PRIMARY_HOVER = "#3e5374"
PRIMARY_EDGE = "#566d92"
BUTTON_INK = "#ffffff"
BUTTON_FONT = ("Segoe UI Semibold", -17)
NAV_FONT = ("Segoe UI", -17)
NAV_PANEL = "#222222"
NAV_WIDTH = 330
NAV_TOP = 12
NAV_ROW = 47


@dataclass
class Timer:
    duration: int = 25 * 60
    remaining: float = 25 * 60
    running: bool = False
    deadline: float | None = None

    def toggle(self) -> None:
        if self.running:
            self.remaining = max(0, (self.deadline or time.perf_counter()) - time.perf_counter())
            self.deadline = None
            self.running = False
        elif self.remaining > 0:
            self.deadline = time.perf_counter() + self.remaining
            self.running = True

    def reset(self) -> None:
        self.remaining = float(self.duration)
        self.running = False
        self.deadline = None

    def seconds(self) -> int:
        if self.running:
            self.remaining = max(0, (self.deadline or time.perf_counter()) - time.perf_counter())
            if self.remaining <= 0:
                self.running = False
                self.deadline = None
        return math.ceil(self.remaining)

@dataclass
class Flip:
    old: str
    new: str
    started: float


class Wallpaper:
    """Show a saved image or play the bundled wallpaper behind the clock."""

    def __init__(self, canvas: tk.Canvas) -> None:
        self.canvas = canvas
        self.photo: ImageTk.PhotoImage | None = None
        self.started: float | None = None
        self.frame_key: tuple[int, int, int] | None = None
        self.item = canvas.create_image(0, 0, anchor="nw")
        self.image_path = Path(os.environ["LOCALAPPDATA"]) / "PomodoroTimer" / "background.jpg"
        self.custom_image: Image.Image | None = None
        try:
            with Image.open(self.image_path) as image:
                self.custom_image = image.convert("RGB")
        except (OSError, Image.DecompressionBombError):
            pass

        self.archive: ZipFile | None = None
        try:
            self.archive = ZipFile(Path(__file__).with_name("wallpaper.zip"))
        except (OSError, BadZipFile):
            return
        self.frames = sorted(name for name in self.archive.namelist() if name.endswith(".jpg"))
        if not self.frames:
            self.close()

    def set_image(self, path: str) -> None:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGBA")
        image.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
        opaque = Image.new("RGB", image.size, BACKGROUND)
        opaque.paste(image, mask=image.getchannel("A"))
        image = ImageEnhance.Brightness(opaque).enhance(0.72)
        self.image_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=self.image_path.parent, delete=False) as handle:
            pending = Path(handle.name)
        try:
            image.save(pending, format="JPEG", quality=92)
            pending.replace(self.image_path)
        finally:
            pending.unlink(missing_ok=True)
        self.custom_image = image
        self.frame_key = None
        self.draw()

    def restore_video(self) -> None:
        self.image_path.unlink(missing_ok=True)
        self.custom_image = None
        self.started = None
        self.frame_key = None
        if self.archive is None:
            self.canvas.itemconfigure(self.item, image="")
            self.photo = None
        self.draw()

    def draw(self) -> None:
        if not self.canvas.winfo_viewable():
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width < 2 or height < 2:
            return
        if self.custom_image is not None:
            index = -1
        elif self.archive is not None:
            now = time.perf_counter()
            if self.started is None:
                self.started = now
            index = int((now - self.started) * 24) % len(self.frames)
        else:
            return
        key = index, width, height
        if key == self.frame_key:
            return

        try:
            if self.custom_image is not None:
                fitted = ImageOps.fit(self.custom_image, (width, height), Image.Resampling.BILINEAR)
            else:
                with Image.open(BytesIO(self.archive.read(self.frames[index]))) as frame:
                    fitted = ImageOps.fit(frame, (width, height), Image.Resampling.BILINEAR)
        except (OSError, BadZipFile):
            self.close()
            return
        photo = ImageTk.PhotoImage(fitted, master=self.canvas)
        self.canvas.itemconfigure(self.item, image=photo)
        self.photo = photo
        self.frame_key = key

    def close(self) -> None:
        if self.archive is not None:
            self.archive.close()
            self.archive = None


class PomodoroApp:
    flip_duration = 0.42

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Pomodoro Timer")
        self.root.configure(bg=BACKGROUND)
        self.root.attributes("-fullscreen", True)
        self.root.minsize(760, 480)

        self.canvas = tk.Canvas(self.root, bg=BACKGROUND, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.wallpaper = Wallpaper(self.canvas)
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Leave>", self.on_leave)
        self.canvas.bind("<Configure>", lambda _event: self.draw())
        self.root.bind("<space>", lambda _event: self.timer_shortcut(self.toggle))
        self.root.bind("r", lambda _event: self.timer_shortcut(self.reset))
        self.root.bind("R", lambda _event: self.timer_shortcut(self.reset))
        self.root.bind("s", lambda _event: self.timer_shortcut(self.open_set_time))
        self.root.bind("S", lambda _event: self.timer_shortcut(self.open_set_time))
        self.root.bind("<KeyPress-b>", lambda _event: self.timer_shortcut(self.choose_background))
        self.root.bind("<KeyPress-B>", lambda _event: self.timer_shortcut(self.choose_background))
        self.root.bind("<KeyPress-t>", lambda _event: self.timer_shortcut(self.open_tasks))
        self.root.bind("<KeyPress-T>", lambda _event: self.timer_shortcut(self.open_tasks))
        self.root.bind("<Alt-m>", lambda _event: self.timer_shortcut(self.toggle_access_menu))
        self.root.bind("<Up>", lambda _event: self.menu_key(-1))
        self.root.bind("<Down>", lambda _event: self.menu_key(1))
        self.root.bind("<Return>", lambda _event: self.menu_key(0))
        self.root.bind("<F11>", lambda _event: self.toggle_fullscreen())
        self.root.bind("<Escape>", lambda _event: self.escape())
        self.root.bind("<Control-q>", lambda _event: self.root.destroy())

        self.timer = Timer()
        self.digits: str | None = None
        self.flips: dict[int, Flip] = {}
        self.was_zero = False
        self.controls_y = 0
        self.dock_step = 0
        self.pointer: tuple[int, int] | None = None
        self.menu_open = False
        self.menu_step = 0
        self.menu_selection = 0
        self.menu_suppressed = False
        self.away = False
        self.time_editor: tk.Frame | None = None
        self.card_cache: dict[tuple[int, int, str], Image.Image] = {}
        self.base_cache: dict[tuple[int, int], Image.Image] = {}
        self.image_refs: list[ImageTk.PhotoImage] = []
        self.font_path = self.find_font()
        self.tasks = TaskViews(self.canvas, self.wallpaper.image_path.with_name("tasks.json"),
                               self.open_tasks, self.close_tasks)
        self.sticky = StickyClock(self.root)

        self.root.after(0, self.draw)
        self.root.after(16, self.tick)
        self.root.after(100, self.check_desktop)

    @staticmethod
    def find_font() -> str:
        fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        for filename in ("bahnschrift.ttf", "segoeuib.ttf", "arialbd.ttf"):
            candidate = os.path.join(fonts, filename)
            if os.path.isfile(candidate):
                return candidate
        return "arial.ttf"

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            self.wallpaper.close()

    def timer_shortcut(self, action: Callable[[], None]) -> str | None:
        if self.time_editor is None and not self.tasks.visible:
            action()
            return "break"
        return None

    def toggle(self) -> None:
        if self.timer.remaining <= 0:
            self.reset()
        self.timer.toggle()
        self.draw_controls()

    def choose_background(self) -> None:
        self.menu_open = False
        self.draw()
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Choose a background image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"), ("All files", "*.*")],
        )
        if path:
            try:
                self.wallpaper.set_image(path)
            except (OSError, ValueError, Image.DecompressionBombError):
                messagebox.showerror(
                    "Background image", "The app couldn't load or save that image.", parent=self.root
                )
        self.on_leave(None)
        self.canvas.focus_set()

    def restore_background(self) -> None:
        try:
            self.wallpaper.restore_video()
        except OSError:
            messagebox.showerror("Background image", "The app couldn't restore the video.", parent=self.root)
        self.draw_controls()

    def reset(self) -> None:
        self.timer.reset()
        self.digits = self.format_time(self.timer.duration)
        self.flips.clear()
        self.was_zero = False
        self.draw()

    def format_time(self, total_seconds: int) -> str:
        if total_seconds <= 60:
            minutes, seconds = divmod(total_seconds, 60)
            return f"{minutes:02d}{seconds:02d}"
        hours, remainder = divmod(max(0, total_seconds), 3600)
        return f"{hours:02d}{remainder // 60:02d}"

    def set_duration(self, hours: int, minutes: int, seconds: int) -> None:
        total_seconds = hours * 3600 + minutes * 60 + seconds
        if not 1 <= total_seconds <= 99 * 3600 + 59 * 60 + 59:
            raise ValueError("Choose a duration from 1 second to 99:59:59.")
        self.timer.duration = total_seconds
        self.reset()

    def open_set_time(self) -> None:
        if self.time_editor is not None:
            return

        hours, remainder = divmod(self.timer.duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        editor = tk.Frame(self.canvas, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
        self.time_editor = editor
        self.menu_open = False
        fields: list[tk.Entry] = []
        for column, (label, value) in enumerate(zip(("Hours", "Minutes", "Seconds"), (hours, minutes, seconds))):
            tk.Label(editor, text=label, bg=PANEL, fg=TEXT, font=("Segoe UI", -12)).grid(
                row=0, column=column, padx=12, pady=(8, 3)
            )
            entry = tk.Entry(
                editor, justify="center", width=4, bg=FIELD, fg=BUTTON,
                insertbackground=BUTTON, relief="flat", bd=4, font=("Segoe UI", -17),
                highlightthickness=1, highlightbackground=EDGE, highlightcolor="#b9b6af",
            )
            entry.insert(0, f"{value:02d}")
            entry.grid(row=1, column=column, padx=10, pady=(0, 5))
            fields.append(entry)

        error = tk.StringVar(master=editor)
        tk.Label(editor, textvariable=error, bg=PANEL, fg="#e4a5a5", font=("Segoe UI", -12)).grid(
            row=2, column=0, columnspan=5, pady=(0, 4)
        )

        def apply() -> None:
            try:
                h, m, s = (int(entry.get().strip() or "0") for entry in fields)
            except ValueError:
                error.set("Enter whole numbers for the time.")
                return
            if not 0 <= h <= 99 or not 0 <= m < 60 or not 0 <= s < 60:
                error.set("Use 0–99 hours and 0–59 minutes or seconds.")
                return
            if not (h or m or s):
                error.set("Set a time of at least one second.")
                return
            self.close_time_editor()
            self.set_duration(h, m, s)

        for column, (label, action, bg, hover) in enumerate((
            ("Cancel", self.close_time_editor, BUTTON_SURFACE, BUTTON_HOVER),
            ("Apply", apply, PRIMARY_SURFACE, PRIMARY_HOVER),
        ), start=3):
            tk.Button(
                editor, text=label, command=action, width=7, relief="flat",
                bg=bg, fg=BUTTON_INK, activebackground=hover, activeforeground=BUTTON_INK,
                font=BUTTON_FONT, cursor="hand2",
            ).grid(row=1, column=column, padx=(4, 10), pady=(0, 5), sticky="ns")
        for entry in fields:
            entry.bind("<Return>", lambda _event: apply())
        self.draw()
        fields[0].focus_set()
        fields[0].selection_range(0, "end")

    def close_time_editor(self) -> None:
        if self.time_editor is not None:
            self.time_editor.destroy()
            self.time_editor = None
            self.pointer = None
            self.menu_suppressed = False
            self.canvas.focus_set()
            self.draw()

    def escape(self) -> None:
        if self.tasks.visible:
            if self.tasks.hover_task:
                self.tasks.close_subtasks()
            else:
                self.close_tasks()
        elif self.menu_step:
            self.dismiss_menu()
            self.draw()
        elif self.time_editor is not None:
            self.close_time_editor()
        else:
            self.leave_fullscreen()

    def toggle_fullscreen(self) -> None:
        self.root.attributes("-fullscreen", not bool(self.root.attributes("-fullscreen")))

    def leave_fullscreen(self) -> None:
        self.root.attributes("-fullscreen", False)

    def open_tasks(self) -> None:
        if self.time_editor is not None:
            self.close_time_editor()
        self.menu_open = False
        self.pointer = None
        self.menu_step = 0
        self.menu_suppressed = False
        self.tasks.open()
        self.update_task_clock()

    def search_tasks(self) -> None:
        self.open_all_tasks()
        self.tasks.search_entry.focus_set()
        self.tasks.search_entry.selection_range(0, "end")

    def open_all_tasks(self) -> None:
        self.open_tasks()
        self.tasks.set_filter("All tasks")

    def open_important_tasks(self) -> None:
        self.open_tasks()
        self.tasks.set_filter("Important")

    def close_tasks(self) -> None:
        self.tasks.close()
        self.canvas.focus_set()
        self.draw()

    def clock_text(self) -> str:
        digits = self.digits or self.format_time(self.timer.seconds())
        return f"{digits[:2]}:{digits[2:]}"

    def update_task_clock(self) -> None:
        text = self.clock_text()
        if self.tasks.clock.cget("text") != text:
            self.tasks.clock.configure(text=text)

    def check_desktop(self) -> None:
        away = another_app_is_active()
        returned = self.away and not away
        self.away = away
        if returned:
            self.draw()
        self.sticky.update(self.clock_text(), self.timer.running, away)
        self.root.after(100, self.check_desktop)

    def tick(self) -> None:
        was_running = self.timer.running
        seconds = self.timer.seconds()
        if seconds == 0 and not self.was_zero:
            self.was_zero = True
            self.root.bell()
        elif seconds > 0:
            self.was_zero = False
        previous_digits = self.digits
        self.set_time(seconds)
        if self.tasks.visible:
            self.update_task_clock()
        elif not self.away:
            dock_target = 6 if self.controls_visible() else 0
            resizing = self.time_editor is None and self.dock_step != dock_target
            if resizing:
                self.dock_step += 1 if dock_target > self.dock_step else -1
            menu_target = 8 if self.menu_open or self.menu_edge_hovered() else 0
            sliding = self.time_editor is None and self.menu_step != menu_target
            if sliding:
                self.menu_step += 1 if menu_target > self.menu_step else -1
            if resizing or self.digits != previous_digits or self.flips or self.timer.running != was_running:
                self.draw()
            elif sliding:
                self.draw_controls()
            self.wallpaper.draw()
        self.root.after(16, self.tick)

    def set_time(self, seconds: int) -> None:
        next_digits = self.format_time(seconds)
        if self.digits is None:
            self.digits = next_digits
            return
        if self.digits != next_digits:
            now = time.perf_counter()
            for index, (old, new) in enumerate(zip(self.digits, next_digits)):
                if old != new:
                    self.flips[index] = Flip(old, new, now)
            self.digits = next_digits

    @staticmethod
    def contains(bounds: tuple[float, float, float, float], x: float, y: float) -> bool:
        return bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]

    def on_click(self, event: tk.Event) -> None:
        if self.time_editor is not None or self.tasks.visible:
            return
        point = (event.x, event.y)
        if self.menu_step and not self.menu_suppressed:
            for _, _, action, bounds in self.menu_items():
                if self.contains(bounds, *point):
                    self.dismiss_menu()
                    action()
                    return
            if self.menu_open or self.contains(self.menu_bounds(), *point):
                if not self.contains(self.menu_bounds(), *point):
                    self.dismiss_menu()
                    self.draw_controls()
                return
        if not self.controls_visible():
            return
        for _, action, bounds in self.control_buttons():
            if self.contains(bounds, event.x, event.y):
                self.canvas.focus_set()
                action()
                return

    def on_motion(self, event: tk.Event) -> None:
        self.pointer = (event.x, event.y)
        if not self.menu_pointer_in_zone():
            self.menu_suppressed = False
        if self.time_editor is None:
            self.draw_controls()

    def on_leave(self, _event: tk.Event | None) -> None:
        self.pointer = None
        self.menu_open = False
        self.menu_suppressed = False
        if self.time_editor is None:
            self.draw_controls()

    def base_card(self, width: int, height: int) -> Image.Image:
        key = (width, height)
        if key in self.base_cache:
            return self.base_cache[key]
        if len(self.base_cache) >= 4:
            self.base_cache.clear()
            self.card_cache.clear()
        radius = max(12, int(min(width, height) * 0.10))
        shades = Image.new("RGBA", (1, height))
        colors = []
        for row in range(height):
            tone = round(52 - 19 * row / height)
            if row >= height // 2:
                tone -= 5
            colors.append((tone, tone + 1, tone + 5, 247))
        shades.putdata(colors)
        image = Image.new("RGBA", (width, height))
        mask = Image.new("L", (width, height))
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
        image.paste(shades.resize((width, height), Image.Resampling.NEAREST), mask=mask)
        ImageDraw.Draw(image).rounded_rectangle(
            (0, 0, width - 1, height - 1), radius=radius, outline=CARD_BORDER, width=1
        )
        self.base_cache[key] = image
        return image

    def card_image(self, width: int, height: int, digit: str) -> Image.Image:
        key = (width, height, digit)
        if key in self.card_cache:
            return self.card_cache[key]
        image = self.base_card(width, height).copy()
        draw = ImageDraw.Draw(image)
        # Fit the glyph to both axes on narrower displays.
        font_size = max(32, int(min(height * 0.83, width * 1.45)))
        try:
            font = ImageFont.truetype(self.font_path, font_size)
        except OSError:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), digit, font=font)
        text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (width - text_width) // 2 - bbox[0]
        y = (height - text_height) // 2 - bbox[1] + int(height * 0.01)
        draw.text((x, y), digit, font=font, fill=DIGIT)
        middle = height // 2
        draw.line((2, middle, width - 3, middle), fill=HINGE, width=max(1, int(height * 0.005)))
        self.card_cache[key] = image
        return image

    def flipped_image(self, width: int, height: int, flip: Flip, now: float) -> Image.Image | None:
        progress = (now - flip.started) / self.flip_duration
        if progress >= 1:
            return None
        old = self.card_image(width, height, flip.old)
        new = self.card_image(width, height, flip.new)
        middle = height // 2
        if progress < 0.5:
            amount = progress * 2
            flap_height = max(1, round(middle * (1 - amount)))
            flap = old.crop((0, 0, width, middle)).resize((width, flap_height), Image.Resampling.BICUBIC)
            frame = new.copy()
            frame.alpha_composite(flap, (0, middle - flap_height))
            shade = Image.new("RGBA", (width, flap_height), (0, 0, 0, int(36 + amount * 95)))
            frame.alpha_composite(shade, (0, middle - flap_height))
        else:
            amount = (progress - 0.5) * 2
            flap_height = max(1, round((height - middle) * amount))
            frame = self.base_card(width, height).copy()
            frame.alpha_composite(new.crop((0, 0, width, middle)), (0, 0))
            flap = new.crop((0, middle, width, height)).resize((width, flap_height), Image.Resampling.BICUBIC)
            frame.alpha_composite(flap, (0, middle))
            shade = Image.new("RGBA", (width, flap_height), (0, 0, 0, int((1 - amount) * 105)))
            frame.alpha_composite(shade, (0, middle))
        return frame

    def draw(self) -> None:
        if self.tasks.visible:
            return
        if self.digits is None:
            self.set_time(self.timer.seconds())
        canvas = self.canvas
        canvas.delete("clock")
        self.image_refs.clear()
        # Windows can invoke the first scheduled draw before Tk has sized the canvas.
        # Rendering with a 1×1 canvas produced negative image dimensions and stopped
        # the periodic update loop in the packaged no-console build.
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 400 or height < 240:
            return

        self.controls_y = height - 48
        if self.time_editor is not None:
            self.dock_step = 6
        step = self.dock_step / 6
        progress = step * step * (3 - 2 * step)
        side = max(24, width * (0.065 + 0.035 * progress))
        small_gap = max(10, width * 0.009)
        colon_gap = max(34, width * 0.036)
        card_width = int((width - side * 2 - small_gap * 2 - colon_gap) / 4)
        height_limit = height * (0.77 - 0.15 * progress)
        if self.time_editor is not None:
            height_limit = min(height_limit, height - 165)
        card_height = int(min(height_limit, card_width * (1.78 - 0.13 * progress)))
        pair_width = card_width * 2 + small_gap
        total_width = pair_width * 2 + colon_gap
        start_x = int((width - total_width) / 2)
        y = int((height - card_height) * (0.5 - 0.18 * progress))
        right_x = start_x + pair_width + colon_gap
        positions = (start_x, start_x + card_width + small_gap,
                     right_x, right_x + card_width + small_gap)

        now = time.perf_counter()
        for index, (x, digit) in enumerate(zip(positions, self.digits or "0025")):
            flip = self.flips.get(index)
            image = self.flipped_image(card_width, card_height, flip, now) if flip else None
            if flip and image is None:
                self.flips.pop(index, None)
            if image is None:
                image = self.card_image(card_width, card_height, digit)
            photo = ImageTk.PhotoImage(image)
            self.image_refs.append(photo)
            canvas.create_image(x, y, anchor="nw", image=photo, tags="clock")

        dot = max(4, min(width, height) * 0.008)
        colon_x = start_x + pair_width + colon_gap / 2
        for dot_y in (y + card_height * 0.39, y + card_height * 0.61):
            canvas.create_oval(colon_x - dot, dot_y - dot, colon_x + dot, dot_y + dot, fill="#c2c0bd", outline="", tags="clock")

        self.draw_controls()

    def controls_visible(self) -> bool:
        if self.pointer is None or self.menu_open:
            return False
        x, y = self.pointer
        return abs(x - self.canvas.winfo_width() / 2) <= 222 and abs(y - self.controls_y) <= 48

    def control_buttons(self) -> list[tuple[str, Callable[[], None], tuple[float, float, float, float]]]:
        actions = [
            ("Stop" if self.timer.running else "Start", self.toggle),
            ("Reset", self.reset),
        ]
        button_width, gap = 124, 8
        row_width = button_width * len(actions) + gap * (len(actions) - 1)
        left = (self.canvas.winfo_width() - row_width) / 2
        y = self.controls_y
        buttons = []
        for label, action in actions:
            buttons.append((label, action, (left, y - 21, left + button_width, y + 21)))
            left += button_width + gap
        return buttons

    def menu_edge_hovered(self) -> bool:
        return not self.menu_suppressed and self.menu_pointer_in_zone()

    def menu_pointer_in_zone(self) -> bool:
        if self.pointer is None:
            return False
        x, y = self.pointer
        return 0 <= x <= 20 or (
            self.menu_step > 0 and 0 <= x <= NAV_WIDTH + 10 and 0 <= y <= self.menu_bottom() + 8
        )

    def toggle_access_menu(self) -> None:
        if self.menu_open:
            self.dismiss_menu()
        else:
            self.menu_open = True
            self.menu_suppressed = False
            self.menu_step = 8
            self.menu_selection = 0
        self.canvas.focus_set()
        self.draw_controls()

    def dismiss_menu(self) -> None:
        self.menu_open = False
        self.menu_suppressed = self.menu_pointer_in_zone()

    def menu_key(self, direction: int) -> str | None:
        if not self.menu_open or self.tasks.visible or self.time_editor is not None:
            return None
        rows = self.menu_items()
        if direction:
            self.menu_selection = (self.menu_selection + direction) % len(rows)
            self.draw_controls()
        else:
            action = rows[self.menu_selection % len(rows)][2]
            self.dismiss_menu()
            action()
        return "break"

    def menu_x(self) -> int:
        step = self.menu_step / 8
        eased = step * step * (3 - 2 * step)
        return round(-(NAV_WIDTH + 2) * (1 - eased))

    def menu_bottom(self) -> int:
        return NAV_TOP + 65 + NAV_ROW * (6 if self.wallpaper.custom_image is not None else 5) + 17

    def menu_bounds(self) -> tuple[int, int, int, int]:
        left = self.menu_x()
        return left, NAV_TOP, left + NAV_WIDTH, self.menu_bottom()

    def menu_items(self) -> list[tuple[str, str, Callable[[], None], tuple[int, int, int, int]]]:
        left = self.menu_x()
        actions = [
            ("Important", "star", self.open_important_tasks),
            ("Tasks", "home", self.open_all_tasks),
            ("Set time", "clock", self.open_set_time),
            ("Reset time", "reset", self.reset),
            ("Change background", "photo", self.choose_background),
        ]
        if self.wallpaper.custom_image is not None:
            actions.append(("Use samurai video", "video", self.restore_background))
        rows = [("Search", "search", self.search_tasks, (left + 12, NAV_TOP + 10, left + NAV_WIDTH - 12, NAV_TOP + 50))]
        for index, (label, icon, action) in enumerate(actions):
            y = NAV_TOP + 59 + index * NAV_ROW + (8 if index >= 2 else 0)
            rows.append((label, icon, action, (left + 4, y, left + NAV_WIDTH - 5, y + NAV_ROW - 3)))
        return rows

    def control_rectangle(
        self, bounds: tuple[float, float, float, float], radius: int, fill: str, outline: str,
        tag: str = "controls",
    ) -> None:
        x1, y1, x2, y2 = bounds
        self.canvas.create_polygon(
            (x1 + radius, y1), (x1 + radius, y1), (x2 - radius, y1), (x2 - radius, y1),
            (x2, y1), (x2, y1 + radius), (x2, y1 + radius),
            (x2, y2 - radius), (x2, y2 - radius), (x2, y2), (x2 - radius, y2),
            (x2 - radius, y2), (x1 + radius, y2), (x1 + radius, y2), (x1, y2),
            (x1, y2 - radius), (x1, y2 - radius), (x1, y1 + radius),
            (x1, y1 + radius), (x1, y1),
            smooth=True, fill=fill, outline=outline, tags=tag,
        )

    def draw_menu(self) -> bool:
        canvas = self.canvas
        canvas.delete("menu")
        if self.time_editor is not None or self.menu_step == 0:
            return False
        self.control_rectangle(self.menu_bounds(), 12, NAV_PANEL, "#3a3a3a", tag="menu")
        hovered = False
        for index, (label, icon, _, row) in enumerate(self.menu_items()):
            x1, y1, x2, y2 = row
            center_y = (y1 + y2) / 2
            row_hover = self.pointer is not None and self.contains(row, *self.pointer)
            keyboard_focus = self.menu_open and self.menu_selection == index
            if icon == "search":
                self.control_rectangle(row, 5, "#292929" if row_hover else NAV_PANEL,
                                       "#83bdff" if keyboard_focus else "#545454", tag="menu")
                self.draw_menu_icon(icon, x2 - 21, center_y)
                text_x = x1 + 13
            else:
                if icon == "clock":
                    canvas.create_line(x1 + 12, y1 - 6, x2 - 12, y1 - 6, fill="#393939", tags="menu")
                if row_hover or keyboard_focus or icon == "home":
                    self.control_rectangle(row, 5, "#3d3d3d" if row_hover else "#333333",
                                           "#83bdff" if keyboard_focus else "", tag="menu")
                if icon == "home":
                    canvas.create_line(x1, center_y - 8, x1, center_y + 8, fill="#8cc9ff",
                                       width=3, capstyle="round", tags="menu")
                    count = str(sum(not task["done"] for task in self.tasks.tasks))
                    width = max(22, 12 + len(count) * 8)
                    self.control_rectangle((x2 - width - 10, center_y - 10, x2 - 10, center_y + 10),
                                           9, "#484848", "", tag="menu")
                    canvas.create_text(x2 - 10 - width / 2, center_y, text=count, fill="#ffffff",
                                       font=("Segoe UI", -13), tags="menu")
                self.draw_menu_icon(icon, x1 + 20, center_y)
                text_x = x1 + 49
            canvas.create_text(text_x, center_y, text=label, anchor="w", fill="#f4f4f4",
                               font=NAV_FONT, tags="menu")
            hovered = hovered or row_hover
        return hovered

    def draw_menu_icon(self, icon: str, x: float, y: float) -> None:
        canvas = self.canvas
        color = {"search": "#ededed", "star": "#e8a6b5", "home": "#9caafc",
                 "clock": "#9cabb6", "reset": "#a5b9ec", "photo": "#8fcac9",
                 "video": "#8fcac9"}[icon]
        stroke = {"fill": color, "width": 1.5, "tags": "menu"}

        def line(*points) -> None:
            canvas.create_line(*[(x + px, y + py) for px, py in points],
                               capstyle="round", joinstyle="round", **stroke)

        if icon == "home":
            line((-8, -1), (0, -8), (8, -1), (8, 8), (3, 8), (3, 2),
                 (-3, 2), (-3, 8), (-8, 8), (-8, -1))
        elif icon == "star":
            points = []
            for index in range(10):
                radius = 9 if index % 2 == 0 else 4
                angle = index * math.pi / 5 - math.pi / 2
                points.append((radius * math.cos(angle), radius * math.sin(angle)))
            line(*points, points[0])
        elif icon == "search":
            canvas.create_oval(x - 7, y - 7, x + 3, y + 3, outline=color, width=1.4, tags="menu")
            line((2, 2), (7, 7))
        elif icon == "clock":
            canvas.create_oval(x - 8, y - 8, x + 8, y + 8, outline=color, width=1.5, tags="menu")
            line((0, -5), (0, 0), (4, 2))
        elif icon == "reset":
            canvas.create_arc(x - 8, y - 8, x + 8, y + 8, start=60, extent=285,
                              style="arc", outline=color, width=1.5, tags="menu")
            line((3, -8), (8, -8), (8, -3))
        else:
            self.control_rectangle((x - 9, y - 7, x + 9, y + 7), 3, "", color, tag="menu")
            if icon == "photo":
                line((-7, 5), (-2, -1), (1, 2), (4, -2), (8, 3))
            else:
                line((-2, -4), (5, 0), (-2, 4), (-2, -4))
    def draw_controls(self) -> None:
        canvas = self.canvas
        canvas.delete("controls")
        menu_hovered = self.draw_menu()
        if self.time_editor is not None:
            canvas.configure(cursor="")
            self.time_editor.place(relx=0.5, y=self.controls_y - 12, anchor="center")
            return
        if not self.controls_visible():
            canvas.configure(cursor="hand2" if menu_hovered else "")
            return

        buttons = self.control_buttons()
        y = self.controls_y
        self.control_rectangle((buttons[0][2][0] - 8, y - 29, buttons[-1][2][2] + 8, y + 29), 26, DOCK, BUTTON_EDGE)
        over_button = False
        for label, action, bounds in buttons:
            hovered = self.pointer is not None and self.contains(bounds, *self.pointer)
            over_button = over_button or hovered
            if action == self.toggle:
                bg, edge = (PRIMARY_HOVER if hovered else PRIMARY_SURFACE), PRIMARY_EDGE
            else:
                bg, edge = (BUTTON_HOVER if hovered else BUTTON_SURFACE), BUTTON_EDGE
            x1, y1, x2, y2 = bounds
            self.control_rectangle(bounds, 20, bg, edge)
            canvas.create_text(
                (x1 + x2) / 2, (y1 + y2) / 2, text=label,
                fill=BUTTON_INK, font=BUTTON_FONT, tags="controls",
            )
        canvas.configure(cursor="hand2" if over_button else "")


if __name__ == "__main__":
    PomodoroApp().run()
