"""Kontrol ESP32: Continuous dan Gas berbasis waktu.

Jalankan: python kontrol_motor_final.py (memerlukan pyserial).
Kompatibel dengan firmware ON/OFF/CW/CCW/SPEED 10..500, 115200 baud.
Speedometer menunjukkan perintah yang terkirim, bukan sensor putaran motor.
File master dan versi sebelumnya tidak dimodifikasi atau diimpor.
"""

import ctypes
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

import serial
from serial.tools import list_ports

BAUD_RATE = 115200
MIN_SPEED, MAX_SPEED = 10, 500
SPEED_TICKS = (10, 100, 250, 400, 500)
GEAR_RANGES = {1: (10, 100), 2: (101, 250), 3: (251, 400), 4: (401, 500)}
TICK_MS = 40
BG, PANEL, ALT = "#0b1020", "#121a2b", "#172238"
BORDER, TEXT, MUTED = "#283650", "#edf3ff", "#91a1bd"
GREEN, RED, BLUE, YELLOW = "#35e0a1", "#ff657a", "#69a7ff", "#ffd166"
TRACK, TRACK_DOT, HALO = "#26344d", "#51627f", "#1b4c49"
LOG_COLORS = {"info": TEXT, "send": BLUE, "ok": GREEN, "warn": YELLOW, "error": RED}
THEME_KEYS = ("BG", "PANEL", "ALT", "BORDER", "TEXT", "MUTED", "GREEN", "RED", "BLUE", "YELLOW", "TRACK", "TRACK_DOT", "HALO")
THEMES = {
    "dark": dict(zip(THEME_KEYS, (BG, PANEL, ALT, BORDER, TEXT, MUTED, GREEN, RED, BLUE, YELLOW, TRACK, TRACK_DOT, HALO))),
    "light": dict(zip(THEME_KEYS, ("#d6d2cc", "#ebe8e3", "#ddd9d2", "#bab4ab", "#292b2a", "#5c605d", "#006247", "#982033", "#204e91", "#704700", "#c3bdb4", "#87847e", "#bed9cc"))),
}
THEME_EXTRAS = {"dark": ("#34425b", "#080d18"), "light": ("#cec9c1", "#e2ded8")}
SETTINGS_PATH = Path(os.environ.get("APPDATA") or Path.home()) / "StepperControl" / "settings.json"


def set_palette(name):
    globals().update(THEMES[name])
    LOG_COLORS.update(info=TEXT, send=BLUE, ok=GREEN, warn=YELLOW, error=RED)


def read_theme():
    try:
        name = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")).get("theme")
        return name if name in THEMES else "dark"
    except (OSError, ValueError, AttributeError, TypeError):
        return "dark"
BOOT_LINE = re.compile(r"^(ets |rst:0x|configsip:|clk_drv:|mode:|load:|entry |ESP-ROM:|Build:|SPIWP:|boot:)")
PORT_SUFFIX = re.compile(r"\s*\(COM\d+\)\s*$")


class SpeedSlider(tk.Canvas):
    """Slider sadar-DPI dengan titik magnet, mengikuti kontrol master."""

    def __init__(self, parent, command):
        ui = parent.winfo_fpixels("1i") / 96.0
        self.px = lambda n: max(1, round(n * ui))
        self.command, self.value = command, 100
        self.dragging = self.hover = self.focused = False
        self.thumb_r, self.halo_r = self.px(11), self.px(16)
        self.label_font = tkfont.Font(parent, family="Consolas", size=9)
        height = 2 * self.halo_r + self.px(8) + self.label_font.metrics("linespace")
        super().__init__(parent, height=height, width=self.px(200), bg=PANEL,
                         bd=0, highlightthickness=0, takefocus=1, cursor="hand2")
        self._x0, self._x1 = 0, 1
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonPress-1>", self.press)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", self.release)
        self.bind("<Motion>", lambda e: self.highlight("hover", True))
        self.bind("<Leave>", lambda e: self.highlight("hover", False))
        self.bind("<FocusIn>", lambda e: self.highlight("focused", True))
        self.bind("<FocusOut>", lambda e: self.highlight("focused", False))
        self.bind("<MouseWheel>", self.wheel)
        for key, delta in (("Left", -1), ("Down", -1), ("Right", 1), ("Up", 1),
                           ("Prior", 50), ("Next", -50)):
            self.bind(f"<{key}>", lambda e, d=delta: self.apply(self.value + d))
        self.bind("<Home>", lambda e: self.apply(MIN_SPEED))
        self.bind("<End>", lambda e: self.apply(MAX_SPEED))

    def highlight(self, name, value):
        setattr(self, name, value)
        self.redraw()

    def set(self, value):
        self.apply(value, notify=False)

    def apply(self, value, notify=True):
        value = max(MIN_SPEED, min(MAX_SPEED, int(round(value))))
        if value != self.value:
            self.value = value
            self.redraw()
            if notify:
                self.command(value)
        return "break"

    def x_of(self, value):
        return self._x0 + (value - MIN_SPEED) / (MAX_SPEED - MIN_SPEED) * (self._x1 - self._x0)

    def value_at(self, x):
        for tick in SPEED_TICKS:
            if abs(x - self.x_of(tick)) <= self.px(10):
                return tick
        return MIN_SPEED + (x - self._x0) / max(1, self._x1 - self._x0) * (MAX_SPEED - MIN_SPEED)

    def press(self, event):
        self.focus_set()
        self.dragging = True
        self.apply(self.value_at(event.x))
        self.redraw()

    def drag(self, event):
        self.apply(self.value_at(event.x))

    def release(self, event):
        self.dragging = False
        self.redraw()

    def wheel(self, event):
        steps = int(event.delta / 120) or (1 if event.delta > 0 else -1)
        return self.apply(self.value + 10 * steps)

    def redraw(self):
        width = self.winfo_width()
        if width <= 1:
            return
        self.delete("all")
        pad = int(max(self.halo_r, self.label_font.measure("500") / 2)) + 1
        self._x0, self._x1 = pad, width - pad
        cy, tx = self.halo_r, self.x_of(self.value)
        self.create_line(self._x0, cy, self._x1, cy, fill=TRACK, width=self.px(8), capstyle="round")
        self.create_line(self._x0, cy, tx, cy, fill=GREEN, width=self.px(8), capstyle="round")
        for tick in SPEED_TICKS:
            x, r = self.x_of(tick), self.px(2.5)
            self.create_oval(x-r, cy-r, x+r, cy+r, fill=BG if x <= tx else TRACK_DOT, outline="")
        if self.dragging or self.hover or self.focused:
            r = self.halo_r
            self.create_oval(tx-r, cy-r, tx+r, cy+r, fill=HALO, outline="")
        r = self.thumb_r
        self.create_oval(tx-r, cy-r, tx+r, cy+r, fill=TEXT, outline=GREEN, width=self.px(3))
        for tick in SPEED_TICKS:
            self.create_text(self.x_of(tick), 2*self.halo_r+self.px(4), text=str(tick),
                             anchor="n", font=self.label_font, fill=TEXT if tick == self.value else MUTED)


class Speedometer(tk.Canvas):
    def __init__(self, parent):
        self.ui = parent.winfo_fpixels("1i") / 96.0
        super().__init__(parent, height=round(190*self.ui), width=round(280*self.ui),
                         bg=PANEL, highlightthickness=0)
        self.value = 0
        self.bind("<Configure>", lambda e: self.redraw())

    def set_value(self, value):
        if self.value != value:
            self.value = value
            self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        cx, cy = w/2, h*0.74
        radius = min(w*0.36, h*0.59)
        def point(frac, r):
            angle = math.radians(210 - 240*frac)
            return cx+r*math.cos(angle), cy-r*math.sin(angle)
        for i in range(51):
            frac = i/50
            self.create_line(*point(frac, radius-5*self.ui), *point(frac, radius),
                             fill=GREEN if frac <= self.value/MAX_SPEED else TRACK, width=3)
        for tick in (0, 100, 200, 300, 400, 500):
            self.create_text(*point(tick/MAX_SPEED, radius+14*self.ui), text=str(tick),
                             fill=MUTED, font=("Consolas", 9))
        self.create_line(cx, cy, *point(self.value/MAX_SPEED, radius-12*self.ui),
                         fill=YELLOW, width=3, capstyle="round")
        self.create_oval(cx-5, cy-5, cx+5, cy+5, fill=YELLOW, outline="")
        self.create_text(cx, cy-32*self.ui, text=str(self.value), fill=TEXT, font=("Segoe UI", 24, "bold"))
        self.create_text(cx, h-10*self.ui, text="PERINTAH MOTOR · step/s", fill=MUTED, font=("Segoe UI", 9))


@dataclass
class GasController:
    """Logika murni: satu arah aktif, ramp waktu, dan perpindahan gigi tertunda."""

    speed: float = 0.0
    direction: str = "CW"
    gear: int = 1
    requested_gear: int = 1
    acceleration: float = 160.0
    deceleration: float = 220.0
    state: str = "Berhenti"

    def reset(self):
        self.speed = 0.0
        self.requested_gear = self.gear
        self.state = "Berhenti"

    def select_gear(self, gear):
        if gear not in GEAR_RANGES:
            raise ValueError("Gigi harus 1–4")
        self.requested_gear = gear
        if self.speed <= GEAR_RANGES[gear][1]:
            self.gear = gear

    def tick(self, dt, requested_direction, braking=False):
        dt = max(0.0, min(0.10, dt))
        if braking:
            requested_direction = None
        reversing = requested_direction is not None and requested_direction != self.direction
        if reversing and self.speed == 0:
            self.direction = requested_direction
            reversing = False
        new_limit = GEAR_RANGES[self.requested_gear][1]
        shifting = self.requested_gear != self.gear and self.speed > new_limit
        target = 0.0 if requested_direction is None or reversing else float(new_limit)
        if self.speed > target:
            self.speed = max(target, self.speed - self.deceleration*(2 if braking else 1)*dt)
            self.state = "Mengerem" if braking else ("Ganti arah · deselerasi" if reversing else "Deselerasi")
        elif self.speed < target:
            self.speed = min(target, self.speed + self.acceleration*dt)
            self.state = "Akselerasi"
        else:
            self.state = "Stabil" if self.speed else "Berhenti"
        if shifting and self.speed > new_limit:
            self.state = "Turun gigi · deselerasi"
        if self.speed <= new_limit:
            self.gear = self.requested_gear
        if not self.speed:
            self.state = "Berhenti" if requested_direction is None else "Transisi arah"
        elif self.speed == target and target:
            self.state = "Stabil"


class StepperControlApp:
    def __init__(self, root):
        set_palette("dark")
        self.theme = "dark"
        saved_theme = read_theme()
        self.root, self.ser = root, None
        self.port_map, self.rx_buffer = {}, b""
        self.rx_time = 0.0
        self.show_tech = False
        self.boot_notice_time = None
        self._last_warn, self._last_warn_time = "", 0.0
        self.running, self.ready = False, False
        self.direction, self.wire_direction = "CW", None
        self.last_speed_sent = None
        self.speed_after_id = self.ramp_after_id = self.connect_after_id = None
        self.read_after_id = self.focus_after_id = None
        self.release_jobs = {}
        self.pressed, self.blocked_keys = set(), set()
        self.selected_direction = "CW"
        self.mouse_clutch = False
        self.shift_keys = set()
        self.last_tick = None
        self.gas = GasController()
        self.mode = "continuous"
        self.closing = False
        self.port_var = tk.StringVar()
        self.mode_var = tk.StringVar(value=self.mode)
        self.speed_var = tk.IntVar(value=100)
        self.speed_entry_var = tk.StringVar(value="100")
        self.speed_display_var = tk.StringVar(value="100 step/s")
        self.connection_var = tk.StringVar(value="DISCONNECTED")
        self.motor_state_var = tk.StringVar(value="○ Motor berhenti")
        self.direction_var = tk.StringVar(value="Arah: CW")
        self.gear_var = tk.StringVar()
        root.title("Stepper Motor Control | ESP32")
        root.configure(bg=BG)
        root.option_add("*Font", ("Segoe UI", 10))
        dpi = root.winfo_fpixels("1i")
        root.tk.call("tk", "scaling", dpi/72)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=ALT, background=ALT,
                        foreground=TEXT, arrowcolor=GREEN, bordercolor=BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", ALT)], foreground=[("readonly", TEXT)])
        self.build_ui()
        self.update_gas_buttons()
        if saved_theme != self.theme:
            self.apply_theme(saved_theme, save=False)
        self.update_mode_ui()
        self.install_key_bindings(root)
        root.bind("<FocusOut>", self.focus_out, add="+")
        root.bind("<FocusIn>", self.focus_in, add="+")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_ports()
        self.log("Aplikasi siap. Pilih port ESP32, lalu CONNECT.")
        self.fit_window()
        self.read_after_id = root.after(100, self.read_serial)

    def panel(self, parent, title):
        frame = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        tk.Label(frame, text=title, bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=15, pady=(12, 10))
        return frame

    def btn(self, parent, text, command, bg=ALT, fg=TEXT):
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                         activebackground=bg, activeforeground=fg, relief="flat", bd=0,
                         cursor="hand2", font=("Segoe UI", 9, "bold"), padx=12, pady=9)

    def label(self, parent, text=None, variable=None, color=MUTED, **kwargs):
        return tk.Label(parent, text=text, textvariable=variable, bg=PANEL, fg=color, **kwargs)

    def entry(self, parent, variable, width=10):
        return tk.Entry(parent, textvariable=variable, bg=ALT, fg=TEXT, insertbackground=TEXT,
                        relief="flat", font=("Consolas", 12), width=width,
                        highlightthickness=1, highlightbackground=BORDER)

    def build_ui(self):
        outer = tk.Frame(self.root, bg=BG, padx=20, pady=17)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)
        heading = tk.Frame(outer, bg=BG)
        heading.grid(row=0, column=0, sticky="ew")
        tk.Label(heading, text="STEPPER CONTROL", bg=BG, fg=TEXT, font=("Segoe UI", 23, "bold")).pack(side="left")
        self.theme_btn = self.btn(heading, "☀ LIGHT", self.toggle_theme)
        self.theme_btn.pack(side="right")
        tk.Label(outer, text="ESP32  •  28BYJ-48  •  ULN2003 DRIVER", bg=BG, fg=GREEN,
                 font=("Consolas", 10, "bold")).grid(row=1, column=0, sticky="w", pady=(2, 15))
        conn = self.panel(outer, "KONEKSI PERANGKAT")
        conn.grid(row=2, column=0, sticky="ew", pady=(0, 13))
        row = tk.Frame(conn, bg=PANEL)
        row.pack(fill="x", padx=15, pady=(0, 13))
        row.columnconfigure(1, weight=1)
        self.label(row, "PORT SERIAL").grid(row=0, column=0, padx=(0, 9))
        self.port_combo = ttk.Combobox(row, textvariable=self.port_var, state="readonly", width=42)
        self.port_combo.grid(row=0, column=1, sticky="ew", padx=(0, 7), ipady=4)
        for col, text, action, color in ((2, "REFRESH", self.refresh_ports, ALT),
                                         (3, "CONNECT", self.connect, GREEN),
                                         (4, "DISCONNECT", self.disconnect, "#34425b")):
            self.btn(row, text, action, color, BG if color == GREEN else TEXT).grid(row=0, column=col, padx=4)
        self.connection_label = self.label(row, variable=self.connection_var, color=RED, width=23, anchor="e", font=("Consolas", 9, "bold"))
        self.connection_label.grid(row=0, column=5, padx=(12, 0))
        body = tk.Frame(outer, bg=BG)
        body.grid(row=3, column=0, sticky="nsew")
        for col, weight in enumerate((5, 3)):
            body.columnconfigure(col, weight=weight)
        body.rowconfigure(0, weight=1)
        # Kontrol tetap dua kolom seperti master. Area ini dapat digulir pada
        # layar/DPI yang tidak cukup tinggi; log tetap terlihat di sebelah kanan.
        host = tk.Frame(body, bg=BG)
        host.grid(row=0, column=0, sticky="nsew")
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)
        ui = self.root.winfo_fpixels("1i")/96
        self.controls_canvas = tk.Canvas(host, bg=BG, highlightthickness=0,
                                         width=round(620*ui), height=1)
        self.controls_canvas.grid(row=0, column=0, sticky="nsew")
        self.controls_scroll = ttk.Scrollbar(host, command=self.controls_canvas.yview)
        self.controls_scroll.grid(row=0, column=1, sticky="ns")
        self.controls_canvas.configure(yscrollcommand=self.controls_scroll.set)
        controls = tk.Frame(self.controls_canvas, bg=BG)
        controls.columnconfigure(0, weight=3)
        controls.columnconfigure(1, weight=2)
        self.controls_window = self.controls_canvas.create_window(0, 0, window=controls, anchor="nw")
        controls.bind("<Configure>", lambda e: self.controls_canvas.configure(
            scrollregion=self.controls_canvas.bbox("all")))
        self.controls_canvas.bind("<Configure>", lambda e: self.controls_canvas.itemconfigure(
            self.controls_window, width=e.width))
        speed = self.panel(controls, "PENGATURAN KECEPATAN")
        speed.grid(row=0, column=0, sticky="nsew", padx=(0, 7), pady=(0, 13))
        self.continuous_frame = tk.Frame(speed, bg=PANEL)
        self.continuous_frame.pack(fill="both", expand=True)
        top = tk.Frame(self.continuous_frame, bg=PANEL)
        top.pack(fill="x", padx=15)
        self.label(top, "Kecepatan motor").pack(side="left")
        self.label(top, variable=self.speed_display_var, color=GREEN, font=("Segoe UI", 17, "bold")).pack(side="right")
        self.slider = SpeedSlider(self.continuous_frame, self.on_slider_change)
        self.slider.pack(fill="x", padx=15, pady=(8, 14))
        self.label(self.continuous_frame, "ANGKA MANUAL (10–500)").pack(anchor="w", padx=15, pady=(0, 7))
        manual = tk.Frame(self.continuous_frame, bg=PANEL)
        manual.pack(fill="x", padx=15, pady=(0, 13))
        self.speed_entry = self.entry(manual, self.speed_entry_var)
        self.speed_entry.pack(side="left", ipady=7, padx=(0, 8))
        self.speed_entry.bind("<Return>", self.apply_manual_speed)
        self.btn(manual, "SET ANGKA", self.apply_manual_speed, BLUE, BG).pack(side="left")
        self.label(self.continuous_frame, "PRESET CEPAT").pack(anchor="w", padx=15, pady=(0, 7))
        presets = tk.Frame(self.continuous_frame, bg=PANEL)
        presets.pack(fill="x", padx=15, pady=(0, 15))
        for title, value, color in (("MINIMUM", 10, GREEN), ("MEDIUM", 250, BLUE), ("MAKSIMUM", 500, YELLOW)):
            self.btn(presets, f"{title}\n{value}", lambda v=value: self.set_speed(v), ALT, color).pack(side="left", fill="x", expand=True, padx=3)
        self.gas_frame = tk.Frame(speed, bg=PANEL)
        self.speedometer = Speedometer(self.gas_frame)
        self.speedometer.pack(fill="x", padx=15)
        self.label(self.gas_frame, variable=self.direction_var, color=GREEN, font=("Segoe UI", 12, "bold")).pack(pady=(0, 8))
        self.clutch_btn = self.btn(self.gas_frame, "CLUTCH: OFF", self.toggle_clutch)
        self.clutch_btn.pack(fill="x", padx=15, pady=(0, 6))
        directions = tk.Frame(self.gas_frame, bg=PANEL)
        directions.pack(fill="x", padx=15, pady=(0, 8))
        self.gas_direction_buttons = {}
        for direction, text in (("CW", "↑ MAJU / CW"), ("CCW", "↓ MUNDUR / CCW")):
            button = self.btn(directions, text, lambda d=direction: self.mouse_select_direction(d))
            button.pack(side="left", fill="x", expand=True, padx=3)
            self.gas_direction_buttons[direction] = button
        self.label(self.gas_frame, "TEKAN DAN TAHAN", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=15, pady=(0, 6))
        gas_buttons = tk.Frame(self.gas_frame, bg=PANEL)
        gas_buttons.pack(fill="x", padx=15, pady=(0, 8))
        self.gas_buttons = {}
        for control, text in (("gas", "GAS · SPACE"), ("brake", "REM · J")):
            button = self.btn(gas_buttons, text, None)
            button.pack(side="left", fill="x", expand=True, padx=3)
            button.bind("<ButtonPress-1>", lambda e, c=control: self.mouse_pedal_press(c))
            button.bind("<ButtonRelease-1>", lambda e, c=control: self.mouse_pedal_release(c))
            self.gas_buttons[control] = button
        self.label(self.gas_frame, "Shift + ↑ / ↓: pilih arah · Space: gas · J: rem\nKlik CLUTCH lalu pilih arah · Lepas gas: melambat",
                   justify="left", font=("Segoe UI", 9)).pack(anchor="w", padx=15, pady=(0, 12))
        self.direction_panel = self.panel(controls, "ARAH PUTARAN")
        self.direction_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 7))
        dr = tk.Frame(self.direction_panel, bg=PANEL)
        dr.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.cw_btn = self.btn(dr, "↻  CW", lambda: self.set_direction("CW"), GREEN, BG)
        self.ccw_btn = self.btn(dr, "↺  CCW", lambda: self.set_direction("CCW"))
        self.cw_btn.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.ccw_btn.pack(side="left", fill="both", expand=True, padx=(5, 0))
        motor = self.panel(controls, "KONTROL MOTOR")
        motor.grid(row=0, column=1, sticky="nsew", padx=7, pady=(0, 13))
        self.label(motor, variable=self.motor_state_var, color=YELLOW, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=15, pady=(0, 8))
        for text, value in (("Continuous", "continuous"), ("Gas / Manual", "gas")):
            tk.Radiobutton(motor, text=text, variable=self.mode_var, value=value, command=self.on_mode_change,
                           bg=PANEL, fg=TEXT, selectcolor=ALT, activebackground=PANEL,
                           activeforeground=GREEN).pack(anchor="w", padx=15)
        self.start_btn = self.btn(motor, "▶  START MOTOR", self.start_motor, GREEN, BG)
        self.start_btn.pack(fill="x", padx=15, pady=(10, 8), ipady=5)
        self.stop_btn = self.btn(motor, "■  STOP MOTOR", self.stop_motor, RED, BG)
        self.stop_btn.pack(fill="x", padx=15, pady=(8, 15), ipady=5)
        self.gear_frame = tk.Frame(motor, bg=PANEL)
        self.label(self.gear_frame, variable=self.gear_var, color=GREEN, justify="left").pack(anchor="w", pady=(0, 6))
        gears = tk.Frame(self.gear_frame, bg=PANEL)
        gears.pack(fill="x")
        self.gear_buttons = {}
        for gear, (_, high) in GEAR_RANGES.items():
            button = self.btn(gears, f"{gear}\n≤ {high}", lambda g=gear: self.set_gear(g))
            button.pack(side="left", fill="x", expand=True, padx=2)
            self.gear_buttons[gear] = button
        self.label(self.gear_frame, "Shortcut gigi: 1–4", font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))
        wiring = self.panel(controls, "KONFIGURASI PIN")
        wiring.grid(row=1, column=1, sticky="nsew", padx=7)
        self.label(wiring, "ULN2003 IN1  →  GPIO 5\nULN2003 IN2  →  GPIO 18\nULN2003 IN3  →  GPIO 19\nULN2003 IN4  →  GPIO 21",
                   color=TEXT, justify="left", font=("Consolas", 10)).pack(anchor="w", padx=15, pady=(0, 15))
        logs = self.panel(body, "SYSTEM LOG")
        logs.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        logtop = tk.Frame(logs, bg=PANEL)
        logtop.pack(fill="x", padx=15, pady=(0, 7))
        self.label(logtop, "Catatan aktivitas", font=("Segoe UI", 9)).pack(side="left")
        self.btn(logtop, "CLEAR LOG", self.clear_log).pack(side="right")
        legend = tk.Frame(logs, bg=PANEL)
        legend.pack(fill="x", padx=15, pady=(0, 8))
        for i, (kind, text) in enumerate((("info", "Informasi"), ("send", "Dikirim ke ESP32"),
                                         ("ok", "Balasan / berhasil"), ("warn", "Perhatian"), ("error", "Ada masalah"))):
            self.label(legend, "■ " + text, color=LOG_COLORS[kind], font=("Segoe UI", 9)).grid(row=i//2, column=i%2, sticky="w", padx=(0, 12))
        self.tech_btn = self.btn(logs, "LIHAT DETAIL TEKNIS", self.toggle_tech)
        self.tech_btn.pack(side="bottom", fill="x", padx=15, pady=(0, 13))
        logframe = tk.Frame(logs, bg=PANEL)
        logframe.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        self.log_text = tk.Text(logframe, height=7, width=30, bg="#080d18", fg=TEXT, relief="flat", wrap="word",
                                font=("Segoe UI", 10), state="disabled", padx=8, pady=6, spacing1=2, spacing3=2)
        scroll = ttk.Scrollbar(logframe, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        stamp = tkfont.Font(self.root, family="Consolas", size=9)
        self.log_text.tag_configure("entry", lmargin2=stamp.measure("00:00:00  "))
        self.log_text.tag_configure("stamp", foreground=MUTED, font=stamp)
        for kind, color in LOG_COLORS.items():
            self.log_text.tag_configure(kind, foreground=color)
        self.log_text.tag_configure("tech", foreground=MUTED, font=stamp, elide=True)

    def fit_window(self):
        self.root.update_idletasks()
        ui = self.root.winfo_fpixels("1i")/96
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        mw, mh = int(sw*0.96), int(sh*0.90)
        nw, nh = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        w, h = min(max(nw, round(1100*ui)), mw), min(max(nh, round(700*ui)), mh)
        self.root.minsize(min(nw, mw), min(nh, mh))
        self.root.geometry(f"{w}x{h}+{max(0, (sw-w)//2)}+{max(0, (sh-h)//2-20)}")

    def toggle_theme(self):
        self.apply_theme("light" if self.theme == "dark" else "dark")

    def apply_theme(self, name, save=True):
        old = THEMES[self.theme]
        new = THEMES[name]
        colors = {old[key].lower(): new[key] for key in THEME_KEYS}
        colors.update(zip(THEME_EXTRAS[self.theme], THEME_EXTRAS[name]))

        def recolor(widget):
            for option in ("background", "foreground", "activebackground", "activeforeground",
                           "disabledforeground", "highlightbackground", "highlightcolor",
                           "insertbackground", "selectbackground", "selectforeground", "selectcolor"):
                try:
                    value = widget.cget(option)
                    if isinstance(value, str) and value.lower() in colors:
                        widget.configure(**{option: colors[value.lower()]})
                except tk.TclError:
                    pass
            for child in widget.winfo_children():
                recolor(child)

        recolor(self.root)
        self.theme = name
        set_palette(name)
        style = ttk.Style(self.root)
        style.configure("TCombobox", fieldbackground=ALT, background=ALT,
                        foreground=TEXT, arrowcolor=GREEN, bordercolor=BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", ALT)], foreground=[("readonly", TEXT)])
        self.log_text.tag_configure("stamp", foreground=MUTED)
        self.log_text.tag_configure("tech", foreground=MUTED)
        for kind, color in LOG_COLORS.items():
            self.log_text.tag_configure(kind, foreground=color)
        self.slider.redraw()
        self.speedometer.redraw()
        self.theme_btn.configure(text="☾ DARK" if name == "light" else "☀ LIGHT")
        if save:
            try:
                SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
                SETTINGS_PATH.write_text(json.dumps({"theme": name}), encoding="utf-8")
            except OSError:
                self.log("Pilihan tema tidak dapat disimpan.", "warn")

    def log(self, text, kind="info", tech=None, hidden=False):
        now = time.monotonic()
        if kind == "warn":
            if text == self._last_warn and now-self._last_warn_time < 3:
                return
            self._last_warn, self._last_warn_time = text, now
        extra = ("tech",) if hidden else ()
        self.log_text.configure(state="normal")
        self.log_text.insert("end", time.strftime("%H:%M:%S") + "  ", ("entry", "stamp") + extra)
        self.log_text.insert("end", text, ("entry", kind) + extra)
        if tech:
            self.log_text.insert("end", f"  ({tech})", ("entry", "tech"))
        self.log_text.insert("end", "\n", ("entry",) + extra)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def toggle_tech(self):
        self.show_tech = not self.show_tech
        self.log_text.tag_configure("tech", elide=not self.show_tech)
        self.tech_btn.configure(text="SEMBUNYIKAN DETAIL TEKNIS" if self.show_tech else "LIHAT DETAIL TEKNIS")
        self.log_text.see("end")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def cancel(self, attribute):
        job = getattr(self, attribute)
        if job is not None:
            self.root.after_cancel(job)
            setattr(self, attribute, None)

    def refresh_ports(self):
        ports = list(list_ports.comports())
        self.port_map = {f"{p.device} — {PORT_SUFFIX.sub('', p.description or '').strip() or 'Perangkat serial'}": p.device for p in ports}
        choices = list(self.port_map)
        self.port_combo["values"] = choices
        if self.port_var.get() not in choices:
            self.port_var.set(choices[0] if choices else "")
        self.log(f"Ditemukan {len(ports)} port." if ports else "Belum ada port. Colokkan ESP32, lalu REFRESH.", "info" if ports else "warn")

    def connect(self):
        if self.ser and self.ser.is_open:
            if self.ready or self.connect_after_id is not None:
                self.log("ESP32 sudah terhubung atau sedang menunggu boot.")
                return
        port = self.port_map.get(self.port_var.get())
        if port is None:
            messagebox.showwarning("Port belum dipilih", "Pilih port ESP32 terlebih dahulu.")
            return
        self.disconnect(quiet=True)
        try:
            self.ser = serial.Serial(port, BAUD_RATE, timeout=0, write_timeout=0.1)
        except (serial.SerialException, OSError) as exc:
            self.log("Port gagal dibuka. Tutup Serial Monitor atau aplikasi lain yang memakai port.", "error", str(exc))
            return
        self.connection_var.set(f"CONNECTING • {port}")
        self.connection_label.configure(fg=YELLOW)
        self.log(f"Menghubungkan ke {port}; menunggu boot ESP32…", tech=f"{BAUD_RATE} baud")
        self.connect_after_id = self.root.after(1800, self.finish_connect)

    def finish_connect(self):
        self.connect_after_id = None
        if self.ser and self.ser.is_open:
            # OFF menyinkronkan keadaan firmware sebelum menerima input baru.
            if not self.send("OFF", log=False):
                return
            self.ready = True
            self.connection_var.set(f"CONNECTED • {self.ser.port}")
            self.connection_label.configure(fg=GREEN)
            self.log("Terhubung. Continuous: pilih arah dan START. Gas: Space untuk gas, J untuk rem.", "ok")

    def send(self, command, log=True, note=None):
        if not self.ser or not self.ser.is_open:
            return False
        try:
            packet = (command + "\n").encode("utf-8")
            if self.ser.write(packet) != len(packet):
                raise serial.SerialException("Perintah serial tidak terkirim utuh")
        except (serial.SerialException, OSError) as exc:
            self.log("Koneksi serial bermasalah. Kontrol di-reset; periksa kabel lalu CONNECT lagi.", "error", str(exc))
            self.disconnect(quiet=True)
            return False
        if log:
            self.log(note or f"Perintah: {command}", "send", command)
        return True

    def transmit_speed(self, speed, quiet=True):
        if not MIN_SPEED <= speed <= MAX_SPEED:
            raise ValueError("Kecepatan di luar rentang firmware")
        if speed == self.last_speed_sent:
            return True
        if not self.send(f"SPEED {speed}", log=not quiet, note=f"Kecepatan: {speed} step/s"):
            return False
        self.last_speed_sent = speed
        return True

    def activate(self, speed, direction):
        if not self.transmit_speed(speed):
            return False
        if self.wire_direction != direction:
            if not self.send(direction, log=False):
                return False
            self.wire_direction = direction
        if not self.running:
            if not self.send("ON", log=False):
                return False
            self.running = True
        return True

    def reset_controls(self):
        self.cancel("speed_after_id")
        self.cancel("ramp_after_id")
        for job in self.release_jobs.values():
            self.root.after_cancel(job)
        self.release_jobs.clear()
        self.blocked_keys.update(self.pressed & {"space", "j"})
        self.pressed.clear()
        self.mouse_clutch = False
        self.shift_keys.clear()
        self.gas.reset()
        self.update_gas_buttons()
        self.last_tick = None
        self.running = False
        self.last_speed_sent = None
        self.wire_direction = None
        self.speedometer.set_value(0)
        self.motor_state_var.set("○ Motor berhenti")
        self.update_gear_ui()

    def stop_motor(self):
        self.reset_controls()
        if self.ser and self.ser.is_open:
            self.send("OFF", note="Motor dihentikan.")

    def disconnect(self, quiet=False):
        self.cancel("connect_after_id")
        self.reset_controls()
        self.ready = False
        device, self.ser = self.ser, None
        if device:
            try:
                if device.is_open:
                    device.write(b"OFF\n")
            except (serial.SerialException, OSError):
                pass
            finally:
                try:
                    device.close()
                except (serial.SerialException, OSError):
                    pass
        self.rx_buffer = b""
        self.boot_notice_time = None
        self.connection_var.set("DISCONNECTED")
        self.connection_label.configure(fg=RED)
        if not quiet:
            self.log("Koneksi ditutup. Input gas di-reset.")

    def set_speed(self, value):
        if self.mode != "continuous":
            return
        value = max(MIN_SPEED, min(MAX_SPEED, int(value)))
        self.cancel("speed_after_id")
        self.speed_var.set(value)
        self.speed_entry_var.set(str(value))
        self.speed_display_var.set(f"{value} step/s")
        self.slider.set(value)
        if self.ready:
            self.transmit_speed(value, quiet=False)

    def on_slider_change(self, value):
        if self.mode != "continuous":
            return
        self.speed_var.set(value)
        self.speed_entry_var.set(str(value))
        self.speed_display_var.set(f"{value} step/s")
        self.cancel("speed_after_id")
        self.speed_after_id = self.root.after(120, self.flush_slider)

    def flush_slider(self):
        self.speed_after_id = None
        if self.mode == "continuous" and self.ready:
            self.transmit_speed(self.speed_var.get(), quiet=False)

    def apply_manual_speed(self, event=None):
        if self.mode != "continuous":
            return "break"
        try:
            value = int(self.speed_entry_var.get().strip())
            if not MIN_SPEED <= value <= MAX_SPEED:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Angka tidak valid", "Masukkan bilangan bulat 10 sampai 500.")
            return "break"
        self.set_speed(value)
        return "break"

    def set_direction(self, direction):
        if self.mode != "continuous":
            return
        self.direction = direction
        self.update_direction_ui()
        if self.ready and self.send(direction, note=f"Arah dipilih: {direction}"):
            self.wire_direction = direction

    def update_direction_ui(self):
        for button, direction in ((self.cw_btn, "CW"), (self.ccw_btn, "CCW")):
            active = self.direction == direction
            button.configure(bg=GREEN if active else ALT, fg=BG if active else TEXT)

    def start_motor(self):
        if self.mode != "continuous":
            return
        if not self.ready:
            self.log("Hubungkan ESP32 dan tunggu hingga status CONNECTED.", "warn")
            return
        self.cancel("speed_after_id")
        if self.activate(self.speed_var.get(), self.direction):
            self.motor_state_var.set("● Motor berjalan")
            self.log(f"Motor berjalan: {self.direction}, {self.speed_var.get()} step/s.", "send")

    def on_mode_change(self):
        self.stop_motor()
        self.mode = self.mode_var.get()
        self.update_mode_ui()
        self.root.focus_set()
        self.log("Mode Continuous: pilih arah dan kecepatan, lalu START." if self.mode == "continuous" else "Mode Gas: Shift + ↑/↓ pilih arah, Space gas, J rem.")

    def update_mode_ui(self):
        self.controls_canvas.yview_moveto(0)
        if self.mode == "continuous":
            self.gas_frame.pack_forget()
            self.gear_frame.pack_forget()
            self.continuous_frame.pack(fill="both", expand=True)
            self.direction_panel.grid()
            self.start_btn.pack(fill="x", padx=15, pady=(10, 8), ipady=5,
                                before=self.stop_btn)
        else:
            self.continuous_frame.pack_forget()
            self.direction_panel.grid_remove()
            self.start_btn.pack_forget()
            self.gas_frame.pack(fill="both", expand=True)
            self.gear_frame.pack(fill="x", padx=15, pady=(0, 15))
        self.update_gear_ui()

    def set_gear(self, gear):
        if self.mode == "gas":
            self.gas.select_gear(gear)
            self.update_gear_ui()

    def update_gear_ui(self):
        gear = self.gas.gear
        text = f"Gigi {gear} · batas {GEAR_RANGES[gear][1]} step/s"
        if self.gas.requested_gear != gear:
            text += f"\n→ Gigi {self.gas.requested_gear} setelah melambat"
        self.gear_var.set(text)
        for number, button in self.gear_buttons.items():
            button.configure(bg=GREEN if number == gear else ALT, fg=BG if number == gear else TEXT)

    def install_key_bindings(self, widget):
        # Tag khusus sebelum widget/class agar kontrol gas tidak memicu tombol Tk.
        tag = "GasInput"
        widget.bindtags((tag,) + widget.bindtags())
        for child in widget.winfo_children():
            self.install_key_bindings(child)
        if widget is self.root:
            self.root.bind_class(tag, "<KeyPress>", self.on_key_press)
            self.root.bind_class(tag, "<KeyRelease>", self.on_key_release)
            self.root.bind_class(tag, "<MouseWheel>", self.scroll_controls)

    def scroll_controls(self, event):
        # Slider, input, combobox dan log mempertahankan perilaku roda sendiri.
        if isinstance(event.widget, (SpeedSlider, tk.Entry, ttk.Entry, ttk.Combobox, tk.Text)):
            return None
        widget = event.widget
        while widget is not None:
            if widget is self.controls_canvas:
                if self.controls_canvas.yview() != (0.0, 1.0):
                    steps = int(event.delta/120) or (1 if event.delta > 0 else -1)
                    self.controls_canvas.yview_scroll(-steps*2, "units")
                return "break"
            widget = getattr(widget, "master", None)
        return None

    def on_key_press(self, event):
        key = event.keysym
        if self.mode != "gas":
            return None
        if key in ("Shift_L", "Shift_R"):
            self.shift_keys.add(key)
            self.update_gas_buttons()
            return None
        if key in ("Up", "Down") and (self.shift_keys or getattr(event, "state", 0) & 1):
            self.select_gas_direction("CW" if key == "Up" else "CCW")
            return "break"
        if key.lower() in ("space", "j"):
            key = key.lower()
            if key in self.release_jobs:
                self.root.after_cancel(self.release_jobs.pop(key))
            if isinstance(event.widget, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text)):
                return None
            if self.root.focus_get() is None:
                return "break"
            if key in self.blocked_keys:
                return "break"
            if not self.ready:
                self.blocked_keys.add(key)
                self.log("Kontrol belum aktif. CONNECT terlebih dahulu; kemudian tekan ulang tombol.", "warn")
                return "break"
            self.pressed.add(key)
            self.update_gas_buttons()
            self.schedule_ramp()
            return "break"
        if key in ("1", "2", "3", "4"):
            if isinstance(event.widget, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text)):
                return None
            self.set_gear(int(key))
            return "break"
        return None

    def on_key_release(self, event):
        key = event.keysym.lower()
        if key in ("shift_l", "shift_r"):
            self.shift_keys.discard(event.keysym)
            self.update_gas_buttons()
            return None
        if key not in ("space", "j"):
            return None
        if key in self.release_jobs:
            self.root.after_cancel(self.release_jobs.pop(key))
        self.release_jobs[key] = self.root.after(12, lambda k=key: self.release_key(k))
        return "break" if self.mode == "gas" else None

    def release_key(self, key):
        self.release_jobs.pop(key, None)
        self.blocked_keys.discard(key)
        self.pressed.discard(key)
        self.update_gas_buttons()
        if self.mode == "gas" and self.ready:
            self.schedule_ramp()

    def update_gas_buttons(self):
        for control, button in self.gas_buttons.items():
            key = "space" if control == "gas" else "j"
            active = bool(self.pressed & {key, "mouse-" + control})
            color = RED if control == "brake" else GREEN
            button.configure(bg=color if active else ALT, fg=BG if active else TEXT,
                             activebackground=color if active else ALT,
                             activeforeground=BG if active else TEXT)
        clutch = self.mouse_clutch or bool(self.shift_keys)
        self.clutch_btn.configure(text="CLUTCH: ON" if clutch else "CLUTCH: OFF",
                                  bg=BLUE if clutch else ALT, fg=BG if clutch else TEXT,
                                  activebackground=BLUE if clutch else ALT, activeforeground=BG if clutch else TEXT)
        for direction, button in self.gas_direction_buttons.items():
            active = direction == self.selected_direction
            button.configure(bg=GREEN if active else ALT, fg=BG if active else TEXT,
                             activebackground=GREEN if active else ALT, activeforeground=BG if active else TEXT)
        name = "MAJU / CW" if self.selected_direction == "CW" else "MUNDUR / CCW"
        pending = self.gas.speed > 0 and self.gas.direction != self.selected_direction
        self.direction_var.set(f"Arah dipilih: {name}" + (" · menunggu berhenti" if pending else ""))

    def toggle_clutch(self):
        self.mouse_clutch = not self.mouse_clutch
        self.update_gas_buttons()

    def mouse_select_direction(self, direction):
        if not self.mouse_clutch:
            self.log("Aktifkan CLUTCH sebelum memilih arah.", "warn")
            return
        self.mouse_clutch = False
        self.select_gas_direction(direction)

    def select_gas_direction(self, direction):
        self.selected_direction = direction
        self.update_gas_buttons()
        if self.mode == "gas" and self.ready and self.gas.speed > 0:
            self.schedule_ramp()

    def mouse_pedal_press(self, control):
        if self.mode != "gas":
            return "break"
        if not self.ready:
            self.log("Gas belum aktif. CONNECT terlebih dahulu; kemudian tekan ulang tombol.", "warn")
            return "break"
        self.pressed.add("mouse-" + control)
        self.update_gas_buttons()
        self.schedule_ramp()
        return "break"

    def mouse_pedal_release(self, control):
        self.pressed.discard("mouse-" + control)
        self.update_gas_buttons()
        if self.mode == "gas" and self.ready:
            self.schedule_ramp()
        return "break"

    def schedule_ramp(self):
        if self.ramp_after_id is None:
            if self.last_tick is None:
                self.last_tick = time.monotonic()
            self.ramp_after_id = self.root.after(TICK_MS, self.gas_tick)

    def gas_tick(self):
        self.ramp_after_id = None
        if self.mode != "gas" or not self.ready:
            return
        now = time.monotonic()
        dt = now-self.last_tick if self.last_tick is not None else TICK_MS/1000
        self.last_tick = now
        braking = bool(self.pressed & {"j", "mouse-brake"})
        wanted = self.selected_direction if self.pressed & {"space", "mouse-gas"} and not braking else None
        self.gas.tick(dt, wanted, braking=braking)
        # Firmware menolak 1..9. Saat start tunggu ramp mencapai 10; saat
        # deselerasi melewati 10, OFF menjadi representasi nol yang sebenarnya.
        speed = min(GEAR_RANGES[self.gas.gear][1], int(round(self.gas.speed)))
        if self.gas.speed < MIN_SPEED:
            speed = 0
            if self.running:
                if not self.send("OFF", log=False):
                    return
                self.running = False
                self.last_speed_sent = None
                self.gas.speed = 0.0
            if wanted is None:
                self.gas.speed = 0.0
        elif not self.activate(speed, self.gas.direction):
            return
        self.speedometer.set_value(speed)
        self.update_gas_buttons()
        self.motor_state_var.set(self.gas.state if self.gas.speed else "○ Motor berhenti")
        self.update_gear_ui()
        if self.pressed or self.gas.speed > 0:
            self.schedule_ramp()
        else:
            self.last_tick = None

    def focus_out(self, event):
        if self.focus_after_id is None:
            self.focus_after_id = self.root.after_idle(self.check_focus)

    def check_focus(self):
        self.focus_after_id = None
        if self.root.focus_get() is None:
            if self.mode == "gas":
                self.stop_motor()

    def focus_in(self, event):
        # Windows dapat melanjutkan auto-repeat setelah Alt-Tab. Tombol yang
        # masih ditahan saat kembali harus dilepas sebelum motor bisa bergerak.
        try:
            for key, vk in (("space", 0x20), ("j", 0x4A)):
                down = bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
                if down and key not in self.pressed:
                    self.blocked_keys.add(key)
                elif not down:
                    self.blocked_keys.discard(key)
        except AttributeError:
            pass

    def log_serial_line(self, raw):
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return
        if "\ufffd" in text or BOOT_LINE.match(text):
            now = time.monotonic()
            if self.boot_notice_time is None or now-self.boot_notice_time > 5:
                self.log("ESP32 menyala ulang. Menunggu perangkat…", "warn")
            if self.ready:
                self.ready = False
                self.stop_motor()
                self.connection_var.set("RESET • CONNECT ulang")
                self.connection_label.configure(fg=YELLOW)
            self.boot_notice_time = now
            self.log(text, hidden=True)
        else:
            kind = "error" if text.startswith("[ERROR]") else "ok"
            # Balasan SPEED pada ramp bisa banyak; simpan sebagai detail teknis.
            technical = self.mode == "gas" and (text.startswith("[RX]") or "Kecepatan diubah" in text)
            self.log(f"ESP32 membalas: {text}", kind, hidden=technical)

    def read_serial(self):
        self.read_after_id = None
        if self.ser:
            try:
                if not self.ser.is_open:
                    raise serial.SerialException("Port ditutup")
                waiting = self.ser.in_waiting
                if waiting:
                    self.rx_buffer += self.ser.read(waiting)
                    self.rx_time = time.monotonic()
                    parts = self.rx_buffer.split(b"\n")
                    self.rx_buffer = parts.pop()
                    for raw in parts:
                        self.log_serial_line(raw)
                elif self.rx_buffer and time.monotonic()-self.rx_time > 0.3:
                    self.log_serial_line(self.rx_buffer)
                    self.rx_buffer = b""
            except (serial.SerialException, OSError) as exc:
                self.log("Koneksi terputus. Periksa USB lalu CONNECT kembali.", "error", str(exc))
                self.disconnect(quiet=True)
        if not self.closing:
            self.read_after_id = self.root.after(100, self.read_serial)

    def on_close(self):
        # Hentikan Gas sebelum dialog mengambil fokus.
        if self.mode == "gas":
            self.stop_motor()
        if messagebox.askyesno("Keluar", "Tutup aplikasi kontrol motor?"):
            self.closing = True
            self.disconnect(quiet=True)
            self.cancel("read_after_id")
            self.cancel("focus_after_id")
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = StepperControlApp(root)
    root.mainloop()
