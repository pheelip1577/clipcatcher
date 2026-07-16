"""
ClipCatcher GUI
Fully modernized UI built with CustomTkinter.
Supports both Single-Channel clipping and Multi-Stream World Cup HypeGrid compilation (2x2 format).
"""
import sys
import os
import time
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from collections import deque
from typing import Optional, Dict, List

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

# Imports from app
from app.chat_monitor import TwitchChatMonitor
from app.recorder import StreamRecorder, find_tool
from app.hype_detector import HypeDetector
from app.settings import Settings
from app.twitch_utils import parse_channel
from app import youtube

# Import new multi-stream components
from app.multi_monitor import MultiTwitchChatMonitor, MultiHypeDetector
from app.multi_recorder import MultiStreamRecorder, escape_ffmpeg_text

# Theme and Color Scheme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")  # Base CTk theme

# Neon Accent Palette
BG_MAIN       = "#09090d"
BG_SIDEBAR    = "#0f0f15"
BG_CARD       = "#161622"
BG_INPUT      = "#1f1f2e"
BORDER_COLOR  = "#2a2a3e"

COLOR_PURPLE  = "#9147ff"  # Primary Twitch Purple
COLOR_PURPLE_H= "#7722ff"
COLOR_CYAN    = "#00f5ff"
COLOR_GREEN   = "#00ff66"
COLOR_PINK    = "#ff007f"
COLOR_AMBER   = "#ffc107"
COLOR_RED     = "#ff4757"
COLOR_GRAY    = "#8888a0"
COLOR_WHITE   = "#ffffff"

LINE_COLORS = [COLOR_PURPLE, COLOR_CYAN, COLOR_GREEN, COLOR_PINK]


class YouTubeUploadDialog(ctk.CTkToplevel):
    def __init__(self, parent, default_title: str, default_description: str, default_tags: str, default_visibility: str, on_submit):
        super().__init__(parent)
        self.parent = parent
        self.on_submit = on_submit
        self.submitted = False

        self.title("YouTube Upload Details")
        self.geometry("550x580")
        self.resizable(False, False)
        
        # Style like the main application
        self.configure(fg_color=BG_MAIN)
        
        # Make it modal
        self.transient(parent)
        self.grab_set()

        # Center dialog relative to parent
        self.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        x = parent_x + (parent_w - 550) // 2
        y = parent_y + (parent_h - 580) // 2
        self.geometry(f"550x580+{x}+{y}")

        # Main Container with padding
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=25)

        # Header
        header_lbl = ctk.CTkLabel(
            container, text="Edit YouTube Video Details",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=COLOR_PURPLE
        )
        header_lbl.pack(anchor=tk.W, pady=(0, 15))

        # Title Field
        title_label_frame = ctk.CTkFrame(container, fg_color="transparent")
        title_label_frame.pack(fill=tk.X, pady=(5, 2))
        
        ctk.CTkLabel(
            title_label_frame, text="Video Title",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_WHITE
        ).pack(side=tk.LEFT)

        self.char_count_lbl = ctk.CTkLabel(
            title_label_frame, text=f"{len(default_title)}/100",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_GRAY
        )
        self.char_count_lbl.pack(side=tk.RIGHT)

        self.title_entry = ctk.CTkEntry(
            container, fg_color=BG_INPUT, border_color=BORDER_COLOR,
            font=ctk.CTkFont(size=12)
        )
        self.title_entry.pack(fill=tk.X, pady=(0, 10))
        self.title_entry.insert(0, default_title)
        self.title_entry.bind("<KeyRelease>", self._update_char_count)

        # Description Field
        ctk.CTkLabel(
            container, text="Description",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_WHITE
        ).pack(anchor=tk.W, pady=(5, 2))

        self.desc_text = ctk.CTkTextbox(
            container, height=180, fg_color=BG_INPUT, border_color=BORDER_COLOR,
            border_width=1, font=ctk.CTkFont(size=12)
        )
        self.desc_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.desc_text.insert("1.0", default_description)

        # Tags Field
        ctk.CTkLabel(
            container, text="Tags (comma-separated, includes hashtags)",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_WHITE
        ).pack(anchor=tk.W, pady=(5, 2))

        self.tags_entry = ctk.CTkEntry(
            container, fg_color=BG_INPUT, border_color=BORDER_COLOR,
            font=ctk.CTkFont(size=12)
        )
        self.tags_entry.pack(fill=tk.X, pady=(0, 10))
        self.tags_entry.insert(0, default_tags)

        # Visibility Field
        ctk.CTkLabel(
            container, text="Visibility",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_WHITE
        ).pack(anchor=tk.W, pady=(5, 2))

        self.visibility_var = tk.StringVar(value=default_visibility)
        self.visibility_menu = ctk.CTkOptionMenu(
            container, variable=self.visibility_var,
            values=["public", "unlisted", "private"],
            fg_color=BG_INPUT, button_color=BORDER_COLOR,
            button_hover_color=COLOR_PURPLE, font=ctk.CTkFont(size=12)
        )
        self.visibility_menu.pack(anchor=tk.W, pady=(0, 20))

        # Buttons Row
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ctk.CTkButton(
            btn_frame, text="Cancel", fg_color=BG_CARD, hover_color=COLOR_RED,
            width=100, font=ctk.CTkFont(size=12, weight="bold"),
            command=self.on_cancel
        ).pack(side=tk.RIGHT, padx=(10, 0))

        ctk.CTkButton(
            btn_frame, text="🚀 Upload", fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_H,
            width=120, font=ctk.CTkFont(size=12, weight="bold"),
            command=self.on_upload
        ).pack(side=tk.RIGHT)

        # Focus first field and run initial check
        self.title_entry.focus()
        self._update_char_count()

    def _update_char_count(self, event=None):
        count = len(self.title_entry.get())
        self.char_count_lbl.configure(text=f"{count}/100")
        if count > 100:
            self.char_count_lbl.configure(text_color=COLOR_RED)
        else:
            self.char_count_lbl.configure(text_color=COLOR_GRAY)

    def on_upload(self):
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showwarning("Validation Error", "Title cannot be empty.")
            return
        
        description = self.desc_text.get("1.0", tk.END).strip()
        tags = self.tags_entry.get().strip()
        visibility = self.visibility_var.get()

        self.submitted = True
        self.grab_release()
        self.destroy()
        
        self.on_submit(title, description, tags, visibility)

    def on_cancel(self):
        self.grab_release()
        self.destroy()


class ClipCatcherApp:
    GRAPH_POINTS = 80
    GRAPH_MAX_RATE = 25.0

    def __init__(self):
        # Backend Instances
        self.settings = Settings()
        self.save_folder = self.settings["save_folder"]

        # Single Stream Engine
        self.chat = TwitchChatMonitor()
        self.recorder = StreamRecorder(self.save_folder)
        self.detector = HypeDetector(
            threshold=self.settings["threshold"],
            cooldown=self.settings["cooldown"]
        )
        self.detector.get_rate = self.chat.get_rate

        # Multi Stream Engine (HypeGrid)
        self.multi_chat = MultiTwitchChatMonitor()
        self.multi_recorder = MultiStreamRecorder(self.save_folder)
        self.multi_detector = MultiHypeDetector(
            threshold=self.settings["threshold"],
            cooldown=self.settings["cooldown"] + 15,  # Slightly higher cooldown for grids
            sync_window=12.0,
            min_sync_count=2
        )
        self.multi_detector.get_rates = self.multi_chat.get_rates

        # State Variables
        self._monitoring_mode = "idle"  # "single", "grid", or "idle"
        self._session_clips: List[dict] = []
        self._session_start: Optional[float] = None
        self._peak_rate = 0.0

        # Graph History
        # Single mode: deque of float
        self._graph_data = deque([0.0] * self.GRAPH_POINTS, maxlen=self.GRAPH_POINTS)
        self._clip_graph_markers: List[int] = []

        # Grid mode: dict of channel -> deque
        self._grid_graph_data: Dict[str, deque] = {}
        self._grid_clip_markers: List[int] = []

        # OAuth State
        self._yt_linked_var = None
        self._yt_channel_name = ""

        # Content Engine
        from content_engine.engine import ContentEngine
        self.content_engine = ContentEngine(self.settings)
        self.content_engine.on_status = self._on_ce_status
        self.content_engine.on_progress = self._on_ce_progress
        self.content_engine.on_video_complete = self._on_ce_video_complete
        self.content_engine.on_error = self._on_ce_error

        # Build application window
        self._build_window()
        self._wire_callbacks()
        self._check_youtube_link()

    def _build_window(self):
        self.root = ctk.CTk()
        self.root.title("ClipCatcher - World Cup 2026 Edition")
        self.root.geometry("1200x760")
        self.root.minsize(1000, 640)
        self.root.configure(fg_color=BG_MAIN)

        self._yt_linked_var = tk.StringVar(value="Checking status...")

        # Logo and Top Title Bar
        topbar = ctk.CTkFrame(self.root, height=60, corner_radius=0, fg_color=BG_SIDEBAR, border_width=0)
        topbar.pack(fill=tk.X, side=tk.TOP)

        logo_label = ctk.CTkLabel(
            topbar, text="⚡ ClipCatcher", 
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=COLOR_WHITE
        )
        logo_label.pack(side=tk.LEFT, padx=20, pady=15)

        wc_badge = ctk.CTkFrame(topbar, fg_color=COLOR_PURPLE, height=26, corner_radius=13)
        wc_badge.pack(side=tk.LEFT, padx=(5, 0), pady=17)
        wc_badge_lbl = ctk.CTkLabel(
            wc_badge, text="WORLD CUP GRID 2X2", 
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLOR_WHITE
        )
        wc_badge_lbl.pack(padx=10, pady=2)

        # Status Bar on top right
        status_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        status_frame.pack(side=tk.RIGHT, padx=20, pady=15)

        self._status_indicator = ctk.CTkLabel(
            status_frame, text="● Idle", 
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_GRAY
        )
        self._status_indicator.pack(side=tk.LEFT, padx=(0, 15))

        self._global_stop_btn = ctk.CTkButton(
            status_frame, text="Stop Capture", 
            fg_color=COLOR_RED, hover_color="#d63031",
            text_color=COLOR_WHITE, width=100, height=28,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._stop_monitoring
        )
        # Keep hidden initially
        
        # Main Layout Container
        main_container = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0)
        main_container.pack(fill=tk.BOTH, expand=True)

        # Sidebar navigation panel
        self.sidebar = ctk.CTkFrame(main_container, width=170, corner_radius=0, fg_color=BG_SIDEBAR)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        # Content view pages container
        self.pages_container = ctk.CTkFrame(main_container, fg_color="transparent", corner_radius=0)
        self.pages_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=15, pady=15)

        # Right Live Chat Console
        self.chat_panel = ctk.CTkFrame(main_container, width=280, corner_radius=0, fg_color=BG_SIDEBAR)
        self.chat_panel.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_panel.pack_propagate(False)
        self._build_chat_panel(self.chat_panel)

        # Build Sidebar Navigation Buttons
        self._build_sidebar_nav()

        # Build Page Views
        self.pages: Dict[str, ctk.CTkFrame] = {}
        self._build_single_monitor_page()
        self._build_grid_monitor_page()
        self._build_content_engine_page()
        self._build_clips_page()
        self._build_settings_page()

        # Show initial page
        self._show_page("grid")  # Default to our new World Cup mode!

        # Start timer routines
        self._start_graph_timer()
        self._start_clock_timer()
        self._start_ce_stats_timer()

    def _build_sidebar_nav(self):
        title_nav = ctk.CTkLabel(
            self.sidebar, text="NAVIGATION", 
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLOR_GRAY
        )
        title_nav.pack(anchor=tk.W, padx=15, pady=(20, 10))

        nav_items = [
            ("📡 Single Monitor", "single"),
            ("🏆 HypeGrid 2x2", "grid"),
            ("🤖 Content Engine", "content_engine"),
            ("🎬 Saved Clips", "clips"),
            ("⚙ Settings", "settings")
        ]
        self.nav_buttons = {}
        for text, page in nav_items:
            btn = ctk.CTkButton(
                self.sidebar, text=text, 
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                fg_color="transparent", text_color=COLOR_GRAY,
                hover_color=BG_CARD, height=36, anchor=tk.W,
                command=lambda p=page: self._show_page(p)
            )
            btn.pack(fill=tk.X, padx=10, pady=2)
            self.nav_buttons[page] = btn

    def _show_page(self, name: str):
        # Deselect all sidebar buttons
        for page_name, btn in self.nav_buttons.items():
            if page_name == name:
                btn.configure(fg_color=COLOR_PURPLE, text_color=COLOR_WHITE)
            else:
                btn.configure(fg_color="transparent", text_color=COLOR_GRAY)

        # Pack forget all pages and pack the selected one
        for p in self.pages.values():
            p.pack_forget()
        self.pages[name].pack(fill=tk.BOTH, expand=True)

    def _build_chat_panel(self, parent):
        lbl = ctk.CTkLabel(
            parent, text="LIVE CHAT STREAM",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_WHITE
        )
        lbl.pack(anchor=tk.W, padx=15, pady=(15, 10))

        self.chat_box = ctk.CTkTextbox(
            parent, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR,
            text_color=COLOR_GRAY, font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8
        )
        self.chat_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.chat_box.configure(state=tk.DISABLED)

        # Tags for colored usernames
        # In customTkinter textboxes we can configure tags via underlying tkinter textbox
        self.chat_box._textbox.tag_config("system", foreground=COLOR_GRAY, font=("Consolas", 9, "italic"))
        self.chat_box._textbox.tag_config("username", foreground=COLOR_PURPLE, font=("Consolas", 10, "bold"))
        self.chat_box._textbox.tag_config("username_grid0", foreground=COLOR_PURPLE, font=("Consolas", 10, "bold"))
        self.chat_box._textbox.tag_config("username_grid1", foreground=COLOR_CYAN, font=("Consolas", 10, "bold"))
        self.chat_box._textbox.tag_config("username_grid2", foreground=COLOR_GREEN, font=("Consolas", 10, "bold"))
        self.chat_box._textbox.tag_config("username_grid3", foreground=COLOR_PINK, font=("Consolas", 10, "bold"))

        # Channel Rate Bar
        self.rate_bar_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.rate_bar_frame.pack(fill=tk.X, padx=10, pady=(0, 15))

        rate_lbl_row = ctk.CTkFrame(self.rate_bar_frame, fg_color="transparent")
        rate_lbl_row.pack(fill=tk.X)
        
        ctk.CTkLabel(
            rate_lbl_row, text="Aggregate Activity",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_GRAY
        ).pack(side=tk.LEFT)

        self.chat_rate_lbl = ctk.CTkLabel(
            rate_lbl_row, text="0.0 msg/s",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=COLOR_WHITE
        )
        self.chat_rate_lbl.pack(side=tk.RIGHT)

        self.activity_progressbar = ctk.CTkProgressBar(
            self.rate_bar_frame, height=6, progress_color=COLOR_PURPLE, fg_color=BG_INPUT
        )
        self.activity_progressbar.pack(fill=tk.X, pady=(5, 0))
        self.activity_progressbar.set(0)

    # ── PAGE: SINGLE MONITOR ──────────────────────────────────────────────────
    def _build_single_monitor_page(self):
        page = ctk.CTkFrame(self.pages_container, fg_color="transparent")
        self.pages["single"] = page

        # Connection Control Box
        conn_box = ctk.CTkFrame(page, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=12)
        conn_box.pack(fill=tk.X, pady=(0, 15))

        ctk.CTkLabel(
            conn_box, text="Connect to Stream", 
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
        ).pack(anchor=tk.W, padx=20, pady=(15, 5))

        form_row = ctk.CTkFrame(conn_box, fg_color="transparent")
        form_row.pack(fill=tk.X, padx=20, pady=(0, 15))

        self.single_channel_entry = ctk.CTkEntry(
            form_row, placeholder_text="Twitch Channel Name (e.g. xqc)", 
            fg_color=BG_INPUT, border_color=BORDER_COLOR, width=300, height=36
        )
        self.single_channel_entry.pack(side=tk.LEFT, padx=(0, 10))

        # Quality Selection
        self.single_quality_var = tk.StringVar(value="best")
        quality_menu = ctk.CTkOptionMenu(
            form_row, variable=self.single_quality_var,
            values=["best", "1080p", "720p", "480p", "360p"],
            fg_color=BG_INPUT, button_color=BG_INPUT, button_hover_color=BORDER_COLOR,
            dropdown_fg_color=BG_CARD, dropdown_hover_color=BORDER_COLOR,
            width=100, height=36
        )
        quality_menu.pack(side=tk.LEFT, padx=(0, 15))

        self.single_connect_btn = ctk.CTkButton(
            form_row, text="Start Monitoring", 
            fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_H,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=36, command=self._start_single_monitoring
        )
        self.single_connect_btn.pack(side=tk.LEFT)

        # Graph Panel
        graph_box = ctk.CTkFrame(page, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=12)
        graph_box.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        graph_hdr = ctk.CTkFrame(graph_box, fg_color="transparent")
        graph_hdr.pack(fill=tk.X, padx=20, pady=(15, 5))

        ctk.CTkLabel(
            graph_hdr, text="Live Hype Graph",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        ).pack(side=tk.LEFT)

        self.single_threshold_lbl = ctk.CTkLabel(
            graph_hdr, text=f"Clip Threshold: {self.detector.threshold:.0f} msg/s",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_AMBER
        )
        self.single_threshold_lbl.pack(side=tk.RIGHT)

        # Graph Canvas
        self.single_graph_canvas = tk.Canvas(
            graph_box, bg=BG_CARD, highlightthickness=0, bd=0
        )
        self.single_graph_canvas.pack(fill=tk.BOTH, expand=True, padx=20, pady=(5, 15))

        # Bottom Session Stats Cards Row
        stats_row = ctk.CTkFrame(page, fg_color="transparent")
        stats_row.pack(fill=tk.X)

        self.single_stat_timer = self._create_stat_card(stats_row, "SESSION TIME", "0:00")
        self.single_stat_clips = self._create_stat_card(stats_row, "CLIPS SAVED", "0")
        self.single_stat_peak = self._create_stat_card(stats_row, "PEAK CHAT RATE", "0%")

    def _create_stat_card(self, parent, title: str, value: str) -> ctk.CTkLabel:
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=8, height=75)
        card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10) if parent.winfo_children() else 0)
        card.pack_propagate(False)

        ctk.CTkLabel(
            card, text=title,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLOR_GRAY
        ).pack(anchor=tk.W, padx=15, pady=(10, 2))

        val_lbl = ctk.CTkLabel(
            card, text=value,
            font=ctk.CTkFont(family="Consolas", size=24, weight="bold"),
            text_color=COLOR_WHITE
        )
        val_lbl.pack(anchor=tk.W, padx=15)
        return val_lbl

    # ── PAGE: HYPEGRID (WORLD CUP 2X2) ────────────────────────────────────────
    def _build_grid_monitor_page(self):
        page = ctk.CTkFrame(self.pages_container, fg_color="transparent")
        self.pages["grid"] = page

        # Config Panel (Horizontal Scroll/Grid)
        config_box = ctk.CTkFrame(page, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=12)
        config_box.pack(fill=tk.X, pady=(0, 15))

        config_hdr = ctk.CTkFrame(config_box, fg_color="transparent")
        config_hdr.pack(fill=tk.X, padx=20, pady=(15, 5))
        ctk.CTkLabel(
            config_hdr, text="Configure watch-party grid (4 streams)", 
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
        ).pack(side=tk.LEFT)

        # 4 Streamer Channels Card grid
        channels_row = ctk.CTkFrame(config_box, fg_color="transparent")
        channels_row.pack(fill=tk.X, padx=15, pady=(5, 10))

        self.grid_entries = []
        default_streamers = self.settings["wc_streamers"]
        
        # Color codes for each of the 4 streams
        channel_borders = [COLOR_PURPLE, COLOR_CYAN, COLOR_GREEN, COLOR_PINK]

        for i in range(4):
            card = ctk.CTkFrame(
                channels_row, fg_color=BG_INPUT, 
                border_width=1.5, border_color=channel_borders[i], 
                corner_radius=8
            )
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

            ctk.CTkLabel(
                card, text=f"STREAMER {i+1}", 
                font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
                text_color=channel_borders[i]
            ).pack(anchor=tk.W, padx=12, pady=(8, 2))

            # Entry
            default_val = default_streamers[i] if i < len(default_streamers) else ""
            ent = ctk.CTkEntry(
                card, fg_color=BG_CARD, border_color=BORDER_COLOR, height=28,
                placeholder_text=f"channel name"
            )
            ent.insert(0, default_val)
            ent.pack(fill=tk.X, padx=10, pady=(0, 10))
            self.grid_entries.append(ent)

        # Scoreboard Overlays (Match title & Score/event details)
        overlay_row = ctk.CTkFrame(config_box, fg_color="transparent")
        overlay_row.pack(fill=tk.X, padx=20, pady=(5, 15))

        # Match Title Entry
        ctk.CTkLabel(
            overlay_row, text="Match Banner Title:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.match_title_ent = ctk.CTkEntry(
            overlay_row, fg_color=BG_INPUT, border_color=BORDER_COLOR, width=160, height=32
        )
        self.match_title_ent.insert(0, self.settings["match_title"])
        self.match_title_ent.pack(side=tk.LEFT, padx=(0, 20))

        # Score Entry
        ctk.CTkLabel(
            overlay_row, text="Score / Subtitle:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.match_score_ent = ctk.CTkEntry(
            overlay_row, fg_color=BG_INPUT, border_color=BORDER_COLOR, width=160, height=32
        )
        self.match_score_ent.insert(0, self.settings["match_score"])
        self.match_score_ent.pack(side=tk.LEFT, padx=(0, 30))

        # Trigger Controls
        self.grid_connect_btn = ctk.CTkButton(
            overlay_row, text="Start HypeGrid Capture", 
            fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_H,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=32, command=self._start_grid_monitoring
        )
        self.grid_connect_btn.pack(side=tk.RIGHT)

        # Live Graph and Rates Box
        display_box = ctk.CTkFrame(page, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=12)
        display_box.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        display_hdr = ctk.CTkFrame(display_box, fg_color="transparent")
        display_hdr.pack(fill=tk.X, padx=20, pady=(15, 5))
        
        ctk.CTkLabel(
            display_hdr, text="HypeGrid Synchronizer Graph",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        ).pack(side=tk.LEFT)

        self.grid_threshold_lbl = ctk.CTkLabel(
            display_hdr, text=f"Correlated Threshold: {self.detector.threshold:.0f} msg/s",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_AMBER
        )
        self.grid_threshold_lbl.pack(side=tk.RIGHT)

        # Split: Left side = graph, Right side = 4 vertical rate meters
        splits_frame = ctk.CTkFrame(display_box, fg_color="transparent")
        splits_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 15))

        # Canvas graph on left
        self.grid_graph_canvas = tk.Canvas(
            splits_frame, bg=BG_CARD, highlightthickness=0, bd=0
        )
        self.grid_graph_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Rate bars list on right
        self.meters_frame = ctk.CTkFrame(splits_frame, fg_color=BG_INPUT, border_width=1, border_color=BORDER_COLOR, width=180, corner_radius=8)
        self.meters_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(15, 0))
        self.meters_frame.pack_propagate(False)

        ctk.CTkLabel(
            self.meters_frame, text="STREAM ACTIVITY",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLOR_GRAY
        ).pack(anchor=tk.W, padx=12, pady=10)

        # 4 activity bars
        self.grid_activity_widgets = []
        for i in range(4):
            bar_c = ctk.CTkFrame(self.meters_frame, fg_color="transparent")
            bar_c.pack(fill=tk.X, padx=12, pady=4)
            
            lbl_row = ctk.CTkFrame(bar_c, fg_color="transparent")
            lbl_row.pack(fill=tk.X)
            
            ch_name_lbl = ctk.CTkLabel(
                lbl_row, text=f"Channel {i+1}", 
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=channel_borders[i]
            )
            ch_name_lbl.pack(side=tk.LEFT)
            
            rate_val_lbl = ctk.CTkLabel(
                lbl_row, text="0.0 msg/s", 
                font=ctk.CTkFont(family="Consolas", size=10),
                text_color=COLOR_GRAY
            )
            rate_val_lbl.pack(side=tk.RIGHT)
            
            prog = ctk.CTkProgressBar(bar_c, height=6, progress_color=channel_borders[i], fg_color=BG_CARD)
            prog.pack(fill=tk.X, pady=(2, 0))
            prog.set(0)
            
            self.grid_activity_widgets.append({
                "name": ch_name_lbl,
                "val": rate_val_lbl,
                "prog": prog
            })

        # Bottom Grid stats row
        grid_stats_row = ctk.CTkFrame(page, fg_color="transparent")
        grid_stats_row.pack(fill=tk.X)

        self.grid_stat_timer = self._create_stat_card(grid_stats_row, "SESSION ELAPSED TIME", "0:00")
        self.grid_stat_clips = self._create_stat_card(grid_stats_row, "STITCHED GRIDS EXPORTED", "0")
        self.grid_stat_peak = self._create_stat_card(grid_stats_row, "PEAK SPIKE RANGE", "0%")

    # ── PAGE: CLIPS LIBRARY ───────────────────────────────────────────────────
    def _build_clips_page(self):
        page = ctk.CTkFrame(self.pages_container, fg_color="transparent")
        self.pages["clips"] = page

        # Scrollable container for clips
        clips_hdr = ctk.CTkFrame(page, fg_color="transparent")
        clips_hdr.pack(fill=tk.X, pady=(0, 10))

        ctk.CTkLabel(
            clips_hdr, text="Export Library",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold")
        ).pack(side=tk.LEFT)

        self._clip_count_label = ctk.CTkLabel(
            clips_hdr, text="0 clips saved",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_GRAY
        )
        self._clip_count_label.pack(side=tk.RIGHT)

        # Main scroll frame
        self.clips_scroll = ctk.CTkScrollableFrame(
            page, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=12
        )
        self.clips_scroll.pack(fill=tk.BOTH, expand=True)

        self._refresh_clips_page()

    def _refresh_clips_page(self):
        # Clear existing clip cards
        for widget in self.clips_scroll.winfo_children():
            widget.destroy()

        if not self._session_clips:
            # Display empty placeholder
            placeholder = ctk.CTkFrame(self.clips_scroll, fg_color="transparent")
            placeholder.pack(pady=100, fill=tk.BOTH, expand=True)
            
            ctk.CTkLabel(
                placeholder, text="🎬", font=ctk.CTkFont(size=48)
            ).pack()
            ctk.CTkLabel(
                placeholder, text="No clips saved in this session yet.\nConnect to streams and wait for chat events!",
                font=ctk.CTkFont(family="Segoe UI", size=14),
                text_color=COLOR_GRAY, justify=tk.CENTER
            ).pack(pady=10)
            return

        for clip in self._session_clips:
            self._build_clip_card(self.clips_scroll, clip)

    def _build_clip_card(self, parent, clip: dict):
        card = ctk.CTkFrame(parent, fg_color=BG_INPUT, border_width=1, border_color=BORDER_COLOR, corner_radius=8)
        card.pack(fill=tk.X, pady=6, padx=5)

        # Header Row
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill=tk.X, padx=15, pady=(12, 4))

        # Check if this is a grid clip or single clip
        is_grid = "grid_" in str(clip.get("path", ""))
        clip_icon = "🏆 HypeGrid (2x2)" if is_grid else "🔥 Single Stream"

        ctk.CTkLabel(
            hdr, text=f"{clip_icon} · {clip['channel'].upper()}",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=COLOR_WHITE
        ).pack(side=tk.LEFT)

        ctk.CTkLabel(
            hdr, text=f"{clip['hype']}% Hype Spike",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_AMBER
        ).pack(side=tk.RIGHT)

        # Detail Row (File Path)
        path_str = str(clip["path"]) if clip["path"] else "File failed to save (check environment settings)"
        meta_color = COLOR_GRAY if clip["path"] else COLOR_RED
        path_lbl = ctk.CTkLabel(
            card, text=path_str,
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=meta_color, anchor=tk.W
        )
        path_lbl.pack(fill=tk.X, padx=15, pady=(0, 2))

        # Meta Details
        meta_lbl = ctk.CTkLabel(
            card, text=f"Captured: {clip['datetime']}   ·   Duration: {clip['duration']}s   ·   Score: {clip.get('score', 'N/A')}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_GRAY, anchor=tk.W
        )
        meta_lbl.pack(fill=tk.X, padx=15, pady=(0, 10))

        # YouTube Upload Status Label
        yt_status = clip.get("youtube_status", "")
        if yt_status:
            status_color = COLOR_GREEN if "successfully" in yt_status.lower() or "uploaded" in yt_status.lower() else COLOR_AMBER
            yt_lbl = ctk.CTkLabel(
                card, text=f"YouTube Status: {yt_status}",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold", slant="italic"),
                text_color=status_color, anchor=tk.W
            )
            yt_lbl.pack(fill=tk.X, padx=15, pady=(0, 10))

        # Action Buttons Row
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill=tk.X, padx=15, pady=(0, 12))

        if clip["path"]:
            ctk.CTkButton(
                actions, text="▶ Play", fg_color=BG_CARD, hover_color=BORDER_COLOR,
                width=80, height=28, font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda: self._play_clip(clip)
            ).pack(side=tk.LEFT, padx=(0, 6))

            ctk.CTkButton(
                actions, text="📁 Show Folder", fg_color=BG_CARD, hover_color=BORDER_COLOR,
                width=110, height=28, font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda: self._reveal_clip(clip)
            ).pack(side=tk.LEFT, padx=(0, 6))

            # TikTok crop option is only for standard single 16:9 streams (Grid is already vertical!)
            if not is_grid:
                ctk.CTkButton(
                    actions, text="📱 TikTok Crop", fg_color=BG_CARD, hover_color=BORDER_COLOR,
                    width=110, height=28, font=ctk.CTkFont(size=12, weight="bold"),
                    command=lambda: self._export_tiktok(clip)
                ).pack(side=tk.LEFT, padx=(0, 6))

            # YouTube Upload Trigger
            btn_text = "🚀 YouTube Upload"
            btn_state = tk.NORMAL
            if "uploading" in yt_status.lower():
                btn_text = "Uploading..."
                btn_state = tk.DISABLED

            ctk.CTkButton(
                actions, text=btn_text, fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_H,
                width=140, height=28, font=ctk.CTkFont(size=12, weight="bold"),
                state=btn_state, command=lambda c=clip: self._manual_youtube_upload(c)
            ).pack(side=tk.LEFT, padx=(0, 6))

        ctk.CTkButton(
            actions, text="✕ Delete", fg_color=BG_CARD, hover_color=COLOR_RED,
            width=80, height=28, font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._delete_clip(clip, card)
        ).pack(side=tk.RIGHT)

    # ── PAGE: SETTINGS ────────────────────────────────────────────────────────
    def _build_settings_page(self):
        page = ctk.CTkFrame(self.pages_container, fg_color="transparent")
        self.pages["settings"] = page

        # Scrollable layout for Settings Panels
        scroll_c = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scroll_c.pack(fill=tk.BOTH, expand=True)

        # 1. HYPE DETECTION PARAMS
        hype_card = ctk.CTkFrame(scroll_c, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=12)
        hype_card.pack(fill=tk.X, pady=(0, 15))

        ctk.CTkLabel(
            hype_card, text="Hype Spike Sensitivity Settings",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
        ).pack(anchor=tk.W, padx=20, pady=(15, 10))

        # Spike Sensitivity Slider
        slider_frame = ctk.CTkFrame(hype_card, fg_color="transparent")
        slider_frame.pack(fill=tk.X, padx=20, pady=5)

        self.thresh_slider_lbl = ctk.CTkLabel(
            slider_frame, text=f"Hype Trigger Threshold: {self.detector.threshold:.0f} msg/s",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        )
        self.thresh_slider_lbl.pack(side=tk.LEFT)

        thresh_slider = ctk.CTkSlider(
            slider_frame, from_=2, to=50, number_of_steps=48,
            progress_color=COLOR_PURPLE, button_color=COLOR_PURPLE,
            command=self._apply_threshold
        )
        thresh_slider.set(self.detector.threshold)
        thresh_slider.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(20, 0))

        # Cooldown Slider
        cooldown_frame = ctk.CTkFrame(hype_card, fg_color="transparent")
        cooldown_frame.pack(fill=tk.X, padx=20, pady=5)

        self.cooldown_slider_lbl = ctk.CTkLabel(
            cooldown_frame, text=f"Trigger Cooldown: {self.detector.cooldown:.0f} seconds",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        )
        self.cooldown_slider_lbl.pack(side=tk.LEFT)

        cooldown_slider = ctk.CTkSlider(
            cooldown_frame, from_=10, to=180, number_of_steps=170,
            progress_color=COLOR_PURPLE, button_color=COLOR_PURPLE,
            command=self._apply_cooldown
        )
        cooldown_slider.set(self.detector.cooldown)
        cooldown_slider.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(20, 0))

        # Save Directory Browser
        dir_frame = ctk.CTkFrame(hype_card, fg_color="transparent")
        dir_frame.pack(fill=tk.X, padx=20, pady=(10, 15))

        ctk.CTkLabel(
            dir_frame, text="Clips Export Folder:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        ).pack(side=tk.LEFT, padx=(0, 10))

        self.folder_var = tk.StringVar(value=self.save_folder)
        self.folder_ent = ctk.CTkEntry(
            dir_frame, textvariable=self.folder_var, fg_color=BG_INPUT, border_color=BORDER_COLOR, height=30
        )
        self.folder_ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        ctk.CTkButton(
            dir_frame, text="Browse Folder", fg_color=BG_INPUT, hover_color=BORDER_COLOR,
            width=110, height=30, command=self._browse_folder
        ).pack(side=tk.LEFT)

        # 2. YOUTUBE OAUTH INTEGRATION
        yt_card = ctk.CTkFrame(scroll_c, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=12)
        yt_card.pack(fill=tk.X, pady=(0, 15))

        ctk.CTkLabel(
            yt_card, text="YouTube Channel Integration",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold")
        ).pack(anchor=tk.W, padx=20, pady=(15, 10))

        # Connection Row
        conn_row = ctk.CTkFrame(yt_card, fg_color="transparent")
        conn_row.pack(fill=tk.X, padx=20, pady=5)

        ctk.CTkLabel(
            conn_row, text="Authorized Account Status:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        ).pack(side=tk.LEFT)

        self.yt_status_label = ctk.CTkLabel(
            conn_row, textvariable=self._yt_linked_var,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_AMBER
        )
        self.yt_status_label.pack(side=tk.LEFT, padx=8)

        self.link_yt_btn = ctk.CTkButton(
            conn_row, text="Link Google/YouTube Account", 
            fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_H,
            font=ctk.CTkFont(size=12, weight="bold"),
            width=180, height=28, command=self._toggle_youtube_link
        )
        self.link_yt_btn.pack(side=tk.RIGHT)

        # Auto-upload checkboxes
        self.yt_auto_var = tk.BooleanVar(value=self.settings["youtube_auto_upload"])
        auto_chk = ctk.CTkCheckBox(
            yt_card, text="Auto-upload generated clips directly to YouTube",
            variable=self.yt_auto_var, checkbox_width=18, checkbox_height=18,
            border_color=BORDER_COLOR, hover_color=COLOR_PURPLE, fg_color=COLOR_PURPLE,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=lambda: self.settings.set("youtube_auto_upload", self.yt_auto_var.get())
        )
        auto_chk.pack(anchor=tk.W, padx=20, pady=6)

        self.yt_shorts_var = tk.BooleanVar(value=self.settings["youtube_upload_shorts"])
        shorts_chk = ctk.CTkCheckBox(
            yt_card, text="Publish as YouTube Shorts format (crops 16:9 to portrait 9:16 automatically)",
            variable=self.yt_shorts_var, checkbox_width=18, checkbox_height=18,
            border_color=BORDER_COLOR, hover_color=COLOR_PURPLE, fg_color=COLOR_PURPLE,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=lambda: self.settings.set("youtube_upload_shorts", self.yt_shorts_var.get())
        )
        shorts_chk.pack(anchor=tk.W, padx=20, pady=6)

        # Title Templates inputs
        tmpl_frame = ctk.CTkFrame(yt_card, fg_color="transparent")
        tmpl_frame.pack(fill=tk.X, padx=20, pady=(10, 15))

        # Row: Standard template
        row1 = ctk.CTkFrame(tmpl_frame, fg_color="transparent")
        row1.pack(fill=tk.X, pady=4)
        ctk.CTkLabel(
            row1, text="Single Clip Title Template:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), width=200, anchor=tk.W
        ).pack(side=tk.LEFT)
        self.yt_title_var = tk.StringVar(value=self.settings["youtube_title_template"])
        title_ent = ctk.CTkEntry(
            row1, textvariable=self.yt_title_var, fg_color=BG_INPUT, border_color=BORDER_COLOR, height=28
        )
        title_ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
        title_ent.bind("<KeyRelease>", lambda e: self.settings.set("youtube_title_template", self.yt_title_var.get()))

        # Row: HypeGrid template
        row2 = ctk.CTkFrame(tmpl_frame, fg_color="transparent")
        row2.pack(fill=tk.X, pady=4)
        ctk.CTkLabel(
            row2, text="2x2 HypeGrid Title Template:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), width=200, anchor=tk.W
        ).pack(side=tk.LEFT)
        self.yt_grid_title_var = tk.StringVar(value=self.settings["youtube_wc_grid_template"])
        grid_title_ent = ctk.CTkEntry(
            row2, textvariable=self.yt_grid_title_var, fg_color=BG_INPUT, border_color=BORDER_COLOR, height=28
        )
        grid_title_ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
        grid_title_ent.bind("<KeyRelease>", lambda e: self.settings.set("youtube_wc_grid_template", self.yt_grid_title_var.get()))

    # ── PAGE: CONTENT ENGINE ──────────────────────────────────────────────────
    def _build_content_engine_page(self):
        page = ctk.CTkFrame(self.pages_container, fg_color="transparent")
        self.pages["content_engine"] = page

        # Scrollable layout for Content Engine view
        scroll_c = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scroll_c.pack(fill=tk.BOTH, expand=True)

        # Split frame for Two-Column layout
        split_frame = ctk.CTkFrame(scroll_c, fg_color="transparent")
        split_frame.pack(fill=tk.BOTH, expand=True)

        # Left Column (Controls)
        left_col = ctk.CTkFrame(split_frame, fg_color="transparent")
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # Right Column (Console & Logs)
        right_col = ctk.CTkFrame(split_frame, fg_color="transparent", width=420)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(10, 0))
        right_col.pack_propagate(False)

        # ── Left Column Cards ──

        # 1. API Configuration Card
        api_card = ctk.CTkFrame(left_col, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=12)
        api_card.pack(fill=tk.X, pady=(0, 15))

        ctk.CTkLabel(
            api_card, text="API Keys Configuration",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        ).pack(anchor=tk.W, padx=15, pady=(12, 8))

        # Gemini API Key Entry
        gemini_row = ctk.CTkFrame(api_card, fg_color="transparent")
        gemini_row.pack(fill=tk.X, padx=15, pady=4)
        ctk.CTkLabel(gemini_row, text="Gemini Key:", font=ctk.CTkFont(family="Segoe UI", size=12), width=90, anchor=tk.W).pack(side=tk.LEFT)
        self.ce_gemini_key_var = tk.StringVar(value=self.settings["ce_gemini_api_key"])
        self.ce_gemini_ent = ctk.CTkEntry(gemini_row, textvariable=self.ce_gemini_key_var, placeholder_text="AI.Ab...", fg_color=BG_INPUT, border_color=BORDER_COLOR, height=28, show="*")
        self.ce_gemini_ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ce_gemini_ent.bind("<KeyRelease>", lambda e: self._save_ce_api_keys())

        # Pexels API Key Entry
        pexels_row = ctk.CTkFrame(api_card, fg_color="transparent")
        pexels_row.pack(fill=tk.X, padx=15, pady=(4, 12))
        ctk.CTkLabel(pexels_row, text="Pexels Key:", font=ctk.CTkFont(family="Segoe UI", size=12), width=90, anchor=tk.W).pack(side=tk.LEFT)
        self.ce_pexels_key_var = tk.StringVar(value=self.settings["ce_pexels_api_key"])
        self.ce_pexels_ent = ctk.CTkEntry(pexels_row, textvariable=self.ce_pexels_key_var, placeholder_text="Lwd...", fg_color=BG_INPUT, border_color=BORDER_COLOR, height=28, show="*")
        self.ce_pexels_ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ce_pexels_ent.bind("<KeyRelease>", lambda e: self._save_ce_api_keys())

        # 2. Manual Video Generator Card
        gen_card = ctk.CTkFrame(left_col, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=12)
        gen_card.pack(fill=tk.X, pady=(0, 15))

        ctk.CTkLabel(
            gen_card, text="Manual Video Generation",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        ).pack(anchor=tk.W, padx=15, pady=(12, 8))

        # Template Row
        temp_row = ctk.CTkFrame(gen_card, fg_color="transparent")
        temp_row.pack(fill=tk.X, padx=15, pady=4)
        ctk.CTkLabel(temp_row, text="Select Template:", font=ctk.CTkFont(family="Segoe UI", size=12), width=110, anchor=tk.W).pack(side=tk.LEFT)
        self.ce_template_var = tk.StringVar(value="Auto-Pick")
        temp_options = [
            "Auto-Pick", "YouTube Inspiration", "Match Preview", "Player Profile", "Top 10", 
            "Daily Recap", "Quiz", "History", "Squad Guide", "Controversy", "Facts",
            "Transfer Quiz", "National Team Quiz"
        ]
        self.ce_temp_menu = ctk.CTkOptionMenu(
            temp_row, variable=self.ce_template_var, values=temp_options,
            fg_color=BG_INPUT, button_color=BG_INPUT, button_hover_color=BORDER_COLOR,
            dropdown_fg_color=BG_CARD, dropdown_hover_color=BORDER_COLOR,
            height=28
        )
        self.ce_temp_menu.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Topic Row
        topic_row = ctk.CTkFrame(gen_card, fg_color="transparent")
        topic_row.pack(fill=tk.X, padx=15, pady=4)
        ctk.CTkLabel(topic_row, text="Topic (Optional):", font=ctk.CTkFont(family="Segoe UI", size=12), width=110, anchor=tk.W).pack(side=tk.LEFT)
        self.ce_topic_ent = ctk.CTkEntry(
            topic_row, placeholder_text="e.g. Messi vs Mbappe, or leave empty", 
            fg_color=BG_INPUT, border_color=BORDER_COLOR, height=28
        )
        self.ce_topic_ent.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Options Row
        opt_row = ctk.CTkFrame(gen_card, fg_color="transparent")
        opt_row.pack(fill=tk.X, padx=15, pady=6)
        
        self.ce_skip_upload_var = tk.BooleanVar(value=True)
        self.ce_skip_upload_chk = ctk.CTkCheckBox(
            opt_row, text="Skip YouTube Upload (Save Locally)",
            variable=self.ce_skip_upload_var, checkbox_width=16, checkbox_height=16,
            border_color=BORDER_COLOR, hover_color=COLOR_PURPLE, fg_color=COLOR_PURPLE,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold")
        )
        self.ce_skip_upload_chk.pack(side=tk.LEFT)

        # Channel Name Row
        channel_row = ctk.CTkFrame(gen_card, fg_color="transparent")
        channel_row.pack(fill=tk.X, padx=15, pady=4)
        ctk.CTkLabel(channel_row, text="Channel Name:", font=ctk.CTkFont(family="Segoe UI", size=12), width=110, anchor=tk.W).pack(side=tk.LEFT)
        self.ce_channel_var = tk.StringVar(value=self.settings.get("ce_channel_name", "World Cup Central"))
        self.ce_channel_ent = ctk.CTkEntry(channel_row, textvariable=self.ce_channel_var, fg_color=BG_INPUT, border_color=BORDER_COLOR, height=28)
        self.ce_channel_ent.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ce_channel_ent.bind("<KeyRelease>", lambda e: self.settings.set("ce_channel_name", self.ce_channel_var.get()))

        # Trigger Row
        trig_row = ctk.CTkFrame(gen_card, fg_color="transparent")
        trig_row.pack(fill=tk.X, padx=15, pady=(8, 12))
        self.ce_gen_btn = ctk.CTkButton(
            trig_row, text="🎬 Generate & Produce Video", 
            fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_H,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=32, command=self._trigger_ce_manual_generation
        )
        self.ce_gen_btn.pack(fill=tk.X)

        # 3. Scheduler Control Card
        sched_card = ctk.CTkFrame(left_col, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=12)
        sched_card.pack(fill=tk.X, pady=(0, 15))

        sched_hdr = ctk.CTkFrame(sched_card, fg_color="transparent")
        sched_hdr.pack(fill=tk.X, padx=15, pady=(12, 4))
        
        ctk.CTkLabel(
            sched_hdr, text="Scheduler Loop",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        ).pack(side=tk.LEFT)

        self.ce_sched_status_lbl = ctk.CTkLabel(
            sched_hdr, text="● STOPPED",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLOR_GRAY
        )
        self.ce_sched_status_lbl.pack(side=tk.RIGHT)

        # Interval selection
        int_row = ctk.CTkFrame(sched_card, fg_color="transparent")
        int_row.pack(fill=tk.X, padx=15, pady=4)
        ctk.CTkLabel(int_row, text="Interval (Hours):", font=ctk.CTkFont(family="Segoe UI", size=12), width=120, anchor=tk.W).pack(side=tk.LEFT)
        self.ce_interval_var = tk.StringVar(value=str(self.settings.get("ce_schedule_interval_hours", 4)))
        self.ce_interval_menu = ctk.CTkOptionMenu(
            int_row, variable=self.ce_interval_var, values=["1", "2", "3", "4", "6", "8", "12", "24"],
            fg_color=BG_INPUT, button_color=BG_INPUT, button_hover_color=BORDER_COLOR,
            dropdown_fg_color=BG_CARD, dropdown_hover_color=BORDER_COLOR,
            height=28, command=self._apply_ce_interval
        )
        self.ce_interval_menu.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Trigger scheduler
        self.ce_sched_btn = ctk.CTkButton(
            sched_card, text="Start Scheduler Loop",
            fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_H,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            height=32, command=self._toggle_ce_scheduler
        )
        self.ce_sched_btn.pack(fill=tk.X, padx=15, pady=(8, 12))

        # 4. YouTube Inspiration Ideas Card
        insp_card = ctk.CTkFrame(left_col, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=12)
        insp_card.pack(fill=tk.X, pady=(0, 15))

        ctk.CTkLabel(
            insp_card, text="YouTube Inspiration Queue",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        ).pack(anchor=tk.W, padx=15, pady=(12, 4))

        ctk.CTkLabel(
            insp_card, text="Enter ideas given by YouTube Studio (one per line):",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_GRAY
        ).pack(anchor=tk.W, padx=15, pady=(0, 6))

        self.ce_insp_box = ctk.CTkTextbox(
            insp_card, height=100, fg_color=BG_INPUT, border_width=1, border_color=BORDER_COLOR,
            text_color=COLOR_WHITE, font=ctk.CTkFont(family="Segoe UI", size=12),
            corner_radius=8
        )
        self.ce_insp_box.pack(fill=tk.X, padx=15, pady=(0, 8))

        # Save Button for Inspiration Queue
        btn_row = ctk.CTkFrame(insp_card, fg_color="transparent")
        btn_row.pack(fill=tk.X, padx=15, pady=(0, 12))

        self.ce_save_insp_btn = ctk.CTkButton(
            btn_row, text="💾 Save Ideas Queue",
            fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_H,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            height=28, command=self._save_ce_inspiration_ui
        )
        self.ce_save_insp_btn.pack(fill=tk.X)

        # Load initial ideas into textbox
        self._load_ce_inspiration_ui()

        # ── Right Column Cards ──

        # 1. Console & Logs Card
        console_card = ctk.CTkFrame(right_col, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=12)
        console_card.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        ctk.CTkLabel(
            console_card, text="Engine Logs",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        ).pack(anchor=tk.W, padx=15, pady=(12, 4))

        self.ce_log_box = ctk.CTkTextbox(
            console_card, fg_color=BG_INPUT, border_width=1, border_color=BORDER_COLOR,
            text_color=COLOR_GRAY, font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8
        )
        self.ce_log_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.ce_log_box.configure(state=tk.DISABLED)

        # Progress row
        progress_frame = ctk.CTkFrame(console_card, fg_color="transparent")
        progress_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        lbl_row = ctk.CTkFrame(progress_frame, fg_color="transparent")
        lbl_row.pack(fill=tk.X)
        self.ce_status_lbl = ctk.CTkLabel(
            lbl_row, text="Ready", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=COLOR_GRAY
        )
        self.ce_status_lbl.pack(side=tk.LEFT)
        self.ce_progress_lbl = ctk.CTkLabel(
            lbl_row, text="0%", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color=COLOR_WHITE
        )
        self.ce_progress_lbl.pack(side=tk.RIGHT)

        self.ce_progress_bar = ctk.CTkProgressBar(
            progress_frame, height=6, progress_color=COLOR_PURPLE, fg_color=BG_INPUT
        )
        self.ce_progress_bar.pack(fill=tk.X, pady=(4, 0))
        self.ce_progress_bar.set(0)

        # 2. Stats Card
        stats_card = ctk.CTkFrame(right_col, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR, corner_radius=12, height=220)
        stats_card.pack(fill=tk.X)
        stats_card.pack_propagate(False)

        ctk.CTkLabel(
            stats_card, text="Daily Production Statistics",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
        ).pack(anchor=tk.W, padx=15, pady=(12, 6))

        grid_frame = ctk.CTkFrame(stats_card, fg_color="transparent")
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 12))

        def create_stat_cell(parent, row, col, label, val_color=COLOR_WHITE):
            cell = ctk.CTkFrame(parent, fg_color=BG_INPUT, border_width=1, border_color=BORDER_COLOR, corner_radius=6)
            cell.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
            parent.grid_columnconfigure(col, weight=1)
            parent.grid_rowconfigure(row, weight=1)

            ctk.CTkLabel(cell, text=label, font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"), text_color=COLOR_GRAY).pack(anchor=tk.W, padx=10, pady=(6, 0))
            val_lbl = ctk.CTkLabel(cell, text="0", font=ctk.CTkFont(family="Consolas", size=18, weight="bold"), text_color=val_color)
            val_lbl.pack(anchor=tk.W, padx=10, pady=(0, 6))
            return val_lbl

        self.ce_stat_total = create_stat_cell(grid_frame, 0, 0, "TOTAL VIDEOS")
        self.ce_stat_today = create_stat_cell(grid_frame, 0, 1, "TODAY PRODUCED")
        self.ce_stat_success = create_stat_cell(grid_frame, 1, 0, "SUCCESSFUL", COLOR_GREEN)
        self.ce_stat_failed = create_stat_cell(grid_frame, 1, 1, "FAILED", COLOR_RED)

        self.ce_quota_lbl = ctk.CTkLabel(
            stats_card, text="Remaining Quota: 6 uploads today",
            font=ctk.CTkFont(family="Segoe UI", size=10, slant="italic"),
            text_color=COLOR_GRAY
        )
        self.ce_quota_lbl.pack(anchor=tk.E, padx=20, pady=(0, 6))

        # Initial refresh
        self._refresh_ce_stats()

    def _save_ce_api_keys(self):
        gem_key = self.ce_gemini_key_var.get().strip()
        pex_key = self.ce_pexels_key_var.get().strip()
        self.settings.set("ce_gemini_api_key", gem_key)
        self.settings.set("ce_pexels_api_key", pex_key)
        if hasattr(self, "content_engine"):
            self.content_engine.gemini_key = gem_key
            self.content_engine.pexels_key = pex_key

    def _trigger_ce_manual_generation(self):
        if not self.settings["ce_gemini_api_key"]:
            messagebox.showerror("Setup Error", "Gemini API key is required for video generation.")
            return

        template = self.ce_template_var.get().strip().lower().replace(" ", "_")
        if template == "auto-pick":
            template = None
        topic = self.ce_topic_ent.get().strip()
        if not topic:
            topic = None
        skip_upload = self.ce_skip_upload_var.get()
        
        self.ce_log_box.configure(state=tk.NORMAL)
        self.ce_log_box.delete("1.0", tk.END)
        self.ce_log_box.configure(state=tk.DISABLED)
        
        self.ce_progress_bar.set(0)
        self.ce_progress_lbl.configure(text="0%")
        self.ce_gen_btn.configure(state=tk.DISABLED)
        
        def job():
            try:
                res = self.content_engine.run_once(
                    template_name=template,
                    topic_override=topic,
                    skip_upload=skip_upload,
                    ignore_quota=True
                )
                self.root.after(0, lambda: self._on_ce_completed(res))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda msg=err_msg: self._on_ce_job_error(msg))
        
        threading.Thread(target=job, daemon=True).start()

    def _on_ce_completed(self, result):
        self.ce_gen_btn.configure(state=tk.NORMAL)
        if result:
            self._on_ce_success(result)
        else:
            messagebox.showerror("Error", "Video generation failed. Check the logs.")

    def _on_ce_job_error(self, err_msg):
        self.ce_gen_btn.configure(state=tk.NORMAL)
        messagebox.showerror("Job Error", f"An unexpected error occurred during generation:\n{err_msg}")

    def _on_ce_success(self, result: dict):
        self._refresh_ce_stats()
        self._load_ce_inspiration_ui()
        
        # Add to saved clips list — include Content Engine metadata for upload
        clip = {
            "id": int(time.time() * 1000),
            "channel": f"AI Engine ({result['content_type']})",
            "hype": 100,
            "rate": 0.0,
            "buf_before": 0,
            "buf_after": 0,
            "duration": int(result["duration_s"]),
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "path": Path(result["video_path"]),
            "score": result["topic"],
            "youtube_status": "Uploaded successfully!" if result["video_url"] else "Saved locally",
            # Content Engine metadata for YouTube upload
            "ce_title": result.get("title", ""),
            "ce_description": result.get("description", ""),
            "ce_tags": result.get("tags", []),
            "ce_thumbnail_path": result.get("thumbnail_path", ""),
            "is_ce_video": True,
        }
        self._session_clips.insert(0, clip)
        self._clip_count_label.configure(text=f"{len(self._session_clips)} clips saved")
        self._refresh_clips_page()
        
        messagebox.showinfo(
            "Video Completed", 
            f"Successfully generated vertical video:\n{result['title']}\n\nSaved to:\n{result['video_path']}"
        )

    def _toggle_ce_scheduler(self):
        if not hasattr(self, "content_engine"):
            return
            
        if self.content_engine._running:
            self.content_engine.stop()
            self._refresh_ce_stats()
            self._append_ce_log("🛑 Scheduler stop requested.")
        else:
            if not self.settings["ce_gemini_api_key"]:
                messagebox.showerror("Setup Error", "Gemini API key is required to start the scheduler.")
                return
            
            self._append_ce_log("⏰ Starting automated Content Engine scheduler...")
            self.content_engine.run_scheduled_bg()
            self._refresh_ce_stats()

    def _apply_ce_interval(self, val):
        try:
            hours = int(val)
            self.settings.set("ce_schedule_interval_hours", hours)
        except Exception:
            pass

    def _load_ce_inspiration_ui(self):
        try:
            if hasattr(self, "content_engine") and hasattr(self.content_engine, "scheduler"):
                ideas = self.content_engine.scheduler.load_inspiration_ideas()
                self.ce_insp_box.delete("1.0", tk.END)
                self.ce_insp_box.insert("1.0", "\n".join(ideas))
        except Exception as e:
            pass

    def _save_ce_inspiration_ui(self):
        try:
            raw_text = self.ce_insp_box.get("1.0", tk.END).strip()
            ideas = [line.strip() for line in raw_text.split("\n") if line.strip()]
            self.content_engine.scheduler.save_inspiration_ideas(ideas)
            self._append_ce_log(f"💾 Saved {len(ideas)} YouTube inspiration ideas to queue.")
            messagebox.showinfo("Saved", f"Saved {len(ideas)} inspiration ideas to the scheduler queue.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save inspiration ideas: {e}")

    def _start_ce_stats_timer(self):
        def tick():
            try:
                self._refresh_ce_stats()
            except Exception:
                pass
            self.root.after(5000, tick)
        self.root.after(5000, tick)

    def _refresh_ce_stats(self):
        if not hasattr(self, "content_engine"):
            return
        
        stats = self.content_engine.get_stats()
        self.ce_stat_total.configure(text=str(stats.get("total_produced", 0)))
        self.ce_stat_today.configure(text=str(stats.get("today_produced", 0)))
        self.ce_stat_success.configure(text=str(stats.get("today_successful", 0)))
        self.ce_stat_failed.configure(text=str(stats.get("today_failed", 0)))
        self.ce_quota_lbl.configure(text=f"Remaining Quota: {stats.get('remaining_today', 6)} uploads today")
        
        if self.content_engine._running:
            self.ce_sched_status_lbl.configure(text="● RUNNING", text_color=COLOR_GREEN)
            self.ce_sched_btn.configure(text="Stop Scheduler Loop", fg_color=COLOR_RED, hover_color="#d63031")
        else:
            self.ce_sched_status_lbl.configure(text="● STOPPED", text_color=COLOR_GRAY)
            self.ce_sched_btn.configure(text="Start Scheduler Loop", fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_H)

    def _on_ce_status(self, message: str):
        self.root.after(0, lambda: self._append_ce_log(message))

    def _on_ce_progress(self, step: str, percent: int):
        self.root.after(0, lambda: self._update_ce_progress(step, percent))

    def _on_ce_video_complete(self, result: dict):
        self.root.after(0, lambda: self._on_ce_completed(result))

    def _on_ce_error(self, error_message: str):
        self.root.after(0, lambda: self._append_ce_log(error_message))

    def _append_ce_log(self, text: str):
        self.ce_log_box.configure(state=tk.NORMAL)
        self.ce_log_box.insert(tk.END, f"{text}\n")
        self.ce_log_box.see(tk.END)
        self.ce_log_box.configure(state=tk.DISABLED)
        self.ce_status_lbl.configure(text=text)

    def _update_ce_progress(self, step: str, percent: int):
        self.ce_progress_bar.set(percent / 100.0)
        self.ce_progress_lbl.configure(text=f"{percent}%")

    # ── TIMER OPERATIONS ──────────────────────────────────────────────────────
    def _start_graph_timer(self):
        def tick():
            try:
                if self._monitoring_mode == "single":
                    self._draw_single_graph()
                elif self._monitoring_mode == "grid":
                    self._draw_grid_graph()
            except Exception:
                pass
            self.root.after(500, tick)
        self.root.after(500, tick)

    def _start_clock_timer(self):
        def tick():
            if self._monitoring_mode != "idle" and self._session_start:
                elapsed = int(time.time() - self._session_start)
                m, s = divmod(elapsed, 60)
                time_str = f"{m}:{s:02d}"
                clips_count = str(len(self._session_clips))
                
                if self._monitoring_mode == "single":
                    self.single_stat_timer.configure(text=time_str)
                    self.single_stat_clips.configure(text=clips_count)
                elif self._monitoring_mode == "grid":
                    self.grid_stat_timer.configure(text=time_str)
                    self.grid_stat_clips.configure(text=clips_count)
            self.root.after(1000, tick)
        self.root.after(1000, tick)

    # ── CALLBACKS & BINDINGS ──────────────────────────────────────────────────
    def _wire_callbacks(self):
        # Single monitor callbacks
        self.chat.on_message = lambda u, m: self._append_chat(f"[{self.chat._channel.upper()}] {u}", m, "username")
        self.chat.on_rate_update = self._on_single_rate_update
        self.detector.on_clip_triggered = self._on_single_clip_triggered
        self.recorder.on_error = self._on_recorder_error
        self.recorder.on_status = self._on_recorder_status

        # Multi/HypeGrid callbacks
        self.multi_chat.on_message = self._on_grid_message
        self.multi_chat.on_rate_update = self._on_grid_rates_update
        self.multi_detector.on_global_clip_triggered = self._on_grid_clip_triggered
        self.multi_recorder.on_error = self._on_recorder_error
        self.multi_recorder.on_status = self._on_recorder_status

    def _append_chat(self, user: str, msg: str, tag: str = "username"):
        self.chat_box.configure(state=tk.NORMAL)
        # Append formatted line
        self.chat_box.insert(tk.END, f"{user}", tag)
        self.chat_box.insert(tk.END, f": {msg}\n")
        
        # Scroll check & trim lines (keep history below 300)
        lines = int(self.chat_box.index(tk.END).split(".")[0])
        if lines > 300:
            self.chat_box.delete("1.0", "100.0")
        
        self.chat_box.see(tk.END)
        self.chat_box.configure(state=tk.DISABLED)

    def _set_status(self, text: str, color: str = COLOR_GRAY):
        self._status_indicator.configure(text=f"● {text}", text_color=color)

    def _show_toast(self, text: str):
        # Temp overlay toast in status line
        original_lbl = self._status_indicator.cget("text")
        original_col = self._status_indicator.cget("text_color")
        self._set_status(text, COLOR_GREEN)
        self.root.after(4000, lambda: self._set_status(original_lbl.replace("● ", ""), original_col))

    def _on_recorder_error(self, msg: str):
        self.root.after(0, lambda: self._set_status(f"Error: {msg}", COLOR_RED))

    def _on_recorder_status(self, msg: str):
        # Log to chat window
        self.root.after(0, lambda: self._append_chat("SYSTEM", msg, "system"))

    # ── ENGINE SINGLE MONITOR IMPLEMENTATION ──────────────────────────────────
    def _start_single_monitoring(self):
        raw_ch = self.single_channel_entry.get().strip()
        ch = parse_channel(raw_ch)
        if not ch:
            messagebox.showwarning("Invalid Input", "Please enter a valid Twitch channel name.")
            return

        self._monitoring_mode = "single"
        self._session_start = time.time()
        self._peak_rate = 0.0
        self._graph_data = deque([0.0] * self.GRAPH_POINTS, maxlen=self.GRAPH_POINTS)
        self._clip_graph_markers.clear()

        # Connect recorder
        self._set_status(f"Connecting to {ch}...", COLOR_AMBER)
        self._append_chat("SYSTEM", f"Starting Single Monitor for {ch}...", "system")

        ok = self.recorder.start(ch, self.single_quality_var.get())
        if not ok:
            self._monitoring_mode = "idle"
            self._set_status("Connect Failed", COLOR_RED)
            return

        # Connect chat
        self.chat.connect(ch)
        self.detector.start()

        # Update UI states
        self.single_connect_btn.configure(state=tk.DISABLED)
        self.grid_connect_btn.configure(state=tk.DISABLED)
        self._global_stop_btn.pack(side=tk.RIGHT, padx=10)
        self._set_status(f"Monitoring {ch}", COLOR_GREEN)

    def _on_single_rate_update(self, rate: float):
        self.root.after(0, lambda: self._ui_single_rate_update(rate))

    def _ui_single_rate_update(self, rate: float):
        self.chat_rate_lbl.configure(text=f"{rate:.1f} msg/s")
        # Update progressbar activity
        pct = min(1.0, rate / self.GRAPH_MAX_RATE)
        self.activity_progressbar.set(pct)

        # Update peak rate
        if rate > self._peak_rate:
            self._peak_rate = rate
            pct_hype = min(99, int((rate / self.GRAPH_MAX_RATE) * 100))
            self.single_stat_peak.configure(text=f"{pct_hype}% Hype")

        self._graph_data.append(rate)

    def _on_single_clip_triggered(self, rate: float):
        self.root.after(0, lambda: self._ui_single_clip_triggered(rate))

    def _ui_single_clip_triggered(self, rate: float):
        ch = self.chat._channel
        self._clip_graph_markers.append(len(self._graph_data) - 1)
        self._set_status("🔥 SPIKE DETECTED - Saving Clip...", COLOR_AMBER)
        self._append_chat("SYSTEM", f"Hype Spike detected ({rate:.1f} msg/s). Saving Clip...", "system")

        # Save clip in background thread
        buf_before = self.settings["buf_before"]
        buf_after = self.settings["buf_after"]
        
        def save():
            wait_time = buf_after + 2
            self.root.after(0, lambda: self._set_status(f"capturing aftermath… ({wait_time}s)", COLOR_AMBER))
            time.sleep(wait_time)
            p = self.recorder.save_clip(buf_before, buf_after, ch)
            if p:
                self.root.after(0, lambda: self._on_clip_saved(ch, p, rate))
            else:
                self.root.after(0, lambda: self._set_status(f"Clip save failed", COLOR_RED))

        threading.Thread(target=save, daemon=True).start()

    def _draw_single_graph(self):
        c = self.single_graph_canvas
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10 or h < 10:
            return
        c.delete("all")

        data = list(self._graph_data)
        n = len(data)
        threshold = self.detector.threshold
        mx = self.GRAPH_MAX_RATE

        # Draw Grid Lines
        for val in [5, 10, 15, 20]:
            y_grid = h - (val / mx) * h
            c.create_line(0, y_grid, w, y_grid, fill="#1c1c2a", width=1)
            c.create_text(15, y_grid - 8, text=f"{val} msg/s", fill="#4c4c6a", font=("Consolas", 8))

        # Threshold line
        ty = h - (threshold / mx) * h
        c.create_line(0, ty, w, ty, fill=COLOR_AMBER, dash=(4, 4), width=1.5)

        # Highlight markers where clips happened
        for idx in self._clip_graph_markers:
            rel = idx / self.GRAPH_POINTS
            x = rel * w
            c.create_rectangle(max(0, x - 8), 0, min(w, x + 8), h, fill="#ffc10712", outline="")
            c.create_line(x, 0, x, h, fill=COLOR_AMBER, width=1)

        # Line Graph and gradient fill
        if n > 1:
            pts = []
            for i, v in enumerate(data):
                x = (i / (n - 1)) * w
                y = h - (min(v, mx) / mx) * h
                pts.extend([x, y])
            
            # Draw line
            c.create_line(pts, fill=COLOR_PURPLE, width=2.5)

    # ── ENGINE HYPEGRID (2X2 GRID) MONITOR IMPLEMENTATION ─────────────────────
    def _start_grid_monitoring(self):
        # Load active channels from grid entries
        channels = []
        for ent in self.grid_entries:
            ch = parse_channel(ent.get().strip())
            if ch:
                channels.append(ch)

        if len(channels) < 2:
            messagebox.showwarning("Incomplete Setup", "Please specify at least 2 active streamers to trigger sync compilations.")
            return

        # Save default channels configuration
        self.settings.set("wc_streamers", channels)
        self.settings.set("match_title", self.match_title_ent.get().strip())
        self.settings.set("match_score", self.match_score_ent.get().strip())

        self._monitoring_mode = "grid"
        self._session_start = time.time()
        self._peak_rate = 0.0
        self._grid_clip_markers.clear()

        # Initialize Grid Graph Buffer
        self._grid_graph_data = {ch: deque([0.0] * self.GRAPH_POINTS, maxlen=self.GRAPH_POINTS) for ch in channels}

        # Update indicators
        for i in range(4):
            widget = self.grid_activity_widgets[i]
            if i < len(channels):
                widget["name"].configure(text=channels[i].upper())
                widget["val"].configure(text="0.0 msg/s")
                widget["prog"].set(0)
            else:
                widget["name"].configure(text="Offline slot", text_color=COLOR_GRAY)
                widget["val"].configure(text="")
                widget["prog"].set(0)

        # Start multi-stream recorders
        self._set_status("Initializing Multi-Recorders...", COLOR_AMBER)
        self._append_chat("SYSTEM", f"Starting HypeGrid (2x2) recording for {', '.join(channels)}...", "system")

        ok = self.multi_recorder.start_recording(channels, "720p")  # 720p resolution is ideal for 2x2 multi-grid
        if not ok:
            self._monitoring_mode = "idle"
            self._set_status("Multi-Recorder Start Failed", COLOR_RED)
            return

        # Connect Multi-Chat and Multi-Detector
        self.multi_chat.connect(channels)
        self.multi_detector.start()

        # Update UI States
        self.single_connect_btn.configure(state=tk.DISABLED)
        self.grid_connect_btn.configure(state=tk.DISABLED)
        self._global_stop_btn.pack(side=tk.RIGHT, padx=10)
        self._set_status(f"HypeGrid Active ({len(channels)} streams)", COLOR_GREEN)

    def _on_grid_message(self, channel: str, username: str, message: str):
        # We find which index this channel maps to, to style with corresponding color
        active_channels = self.multi_chat._channels
        try:
            idx = active_channels.index(channel)
            tag = f"username_grid{idx}"
        except ValueError:
            tag = "username"

        self.root.after(0, lambda: self._append_chat(f"[{channel.upper()}] {username}", message, tag))

    def _on_grid_rates_update(self, rates: Dict[str, float]):
        self.root.after(0, lambda: self._ui_grid_rates_update(rates))

    def _ui_grid_rates_update(self, rates: Dict[str, float]):
        active_channels = self.multi_chat._channels
        
        # Calculate sum rate for the aggregate Activity progressbar
        sum_rate = sum(rates.values())
        self.chat_rate_lbl.configure(text=f"{sum_rate:.1f} msg/s")
        self.activity_progressbar.set(min(1.0, sum_rate / (self.GRAPH_MAX_RATE * 2.0)))

        # Update individual rate dials
        for i in range(4):
            widget = self.grid_activity_widgets[i]
            if i < len(active_channels):
                ch = active_channels[i]
                rate = rates.get(ch, 0.0)
                widget["val"].configure(text=f"{rate:.1f} msg/s")
                widget["prog"].set(min(1.0, rate / self.GRAPH_MAX_RATE))
                
                # Append to history
                if ch in self._grid_graph_data:
                    self._grid_graph_data[ch].append(rate)

        # Update Hype Range
        if sum_rate > self._peak_rate:
            self._peak_rate = sum_rate
            pct_hype = min(99, int((sum_rate / (self.GRAPH_MAX_RATE * 2)) * 100))
            self.grid_stat_peak.configure(text=f"{pct_hype}% Sync Hype")

    def _on_grid_clip_triggered(self, rates_info: Dict[str, float]):
        self.root.after(0, lambda: self._ui_grid_clip_triggered(rates_info))

    def _ui_grid_clip_triggered(self, rates_info: Dict[str, float]):
        # Save compilation marker
        first_ch = list(self._grid_graph_data.keys())[0]
        self._grid_clip_markers.append(len(self._grid_graph_data[first_ch]) - 1)

        channels_involved = list(rates_info.keys())
        ch_str = ", ".join([c.upper() for c in channels_involved])
        self._set_status("🏆 GRID CLIP EVENT DETECTED!", COLOR_GREEN)
        self._append_chat("SYSTEM", f"Synchronized spike on {ch_str}! Assembling HypeGrid...", "system")

        # Capture metadata values
        title = self.match_title_ent.get().strip() or "WORLD CUP 2026"
        score = self.match_score_ent.get().strip() or "LIVE REACTION"

        # Clip parameter
        buf_before = self.settings["buf_before"]
        buf_after = self.settings["buf_after"]
        active_recorders = self.multi_recorder.get_active_channels()

        def save_and_stitch():
            wait_time = buf_after + 2
            self.root.after(0, lambda: self._set_status(f"capturing aftermath… ({wait_time}s)", COLOR_GREEN))
            time.sleep(wait_time)
            p = self.multi_recorder.save_grid_clip(
                channels=active_recorders,
                seconds_before=buf_before,
                seconds_after=buf_after,
                match_title=title,
                match_score=score
            )
            if p:
                self.root.after(0, lambda: self._on_clip_saved("HypeGrid", p, 85, score))
            else:
                self.root.after(0, lambda: self._set_status("Stitch failed", COLOR_RED))

        threading.Thread(target=save_and_stitch, daemon=True).start()

    def _draw_grid_graph(self):
        c = self.grid_graph_canvas
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10 or h < 10:
            return
        c.delete("all")

        active_channels = list(self._grid_graph_data.keys())
        if not active_channels:
            return

        threshold = self.multi_detector.threshold
        mx = self.GRAPH_MAX_RATE

        # Draw Grid Lines
        for val in [5, 10, 15, 20]:
            y_grid = h - (val / mx) * h
            c.create_line(0, y_grid, w, y_grid, fill="#1c1c2a", width=1)
            c.create_text(15, y_grid - 8, text=f"{val} msg/s", fill="#4c4c6a", font=("Consolas", 8))

        # Threshold line
        ty = h - (threshold / mx) * h
        c.create_line(0, ty, w, ty, fill=COLOR_AMBER, dash=(4, 4), width=1.5)

        # Highlight markers where sync clips happened
        for idx in self._grid_clip_markers:
            rel = idx / self.GRAPH_POINTS
            x = rel * w
            c.create_rectangle(max(0, x - 8), 0, min(w, x + 8), h, fill="#00ff6608", outline="")
            c.create_line(x, 0, x, h, fill=COLOR_GREEN, width=1.2)

        # Draw lines for each channel
        for ch_idx, ch in enumerate(active_channels):
            data = list(self._grid_graph_data.get(ch, []))
            n = len(data)
            if n > 1:
                pts = []
                for i, v in enumerate(data):
                    x = (i / (n - 1)) * w
                    y = h - (min(v, mx) / mx) * h
                    pts.extend([x, y])
                c.create_line(pts, fill=LINE_COLORS[ch_idx % len(LINE_COLORS)], width=2.0)

    # ── GENERAL UTILS ─────────────────────────────────────────────────────────
    def _on_clip_saved(self, channel: str, clip_path: Path, rate: float, score: str = "LIVE"):
        hype_score = min(99, int((rate / self.GRAPH_MAX_RATE) * 100))
        buf_before = self.settings["buf_before"]
        buf_after = self.settings["buf_after"]

        clip = {
            "id": int(time.time() * 1000),
            "channel": channel,
            "hype": hype_score,
            "rate": rate,
            "buf_before": buf_before,
            "buf_after": buf_after,
            "duration": buf_before + buf_after,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "path": clip_path,
            "score": score,
            "youtube_status": ""
        }
        self._session_clips.insert(0, clip)
        self._set_status("✓ Clip saved!", COLOR_GREEN)
        self._show_toast(f"🔥 Clip Exported · {clip['duration']}s")
        
        # Refresh clips list
        self._refresh_clips_page()

        # Handle YouTube auto-upload
        if self.settings["youtube_auto_upload"]:
            self._auto_youtube_upload(clip)

    def _stop_monitoring(self):
        self._append_chat("SYSTEM", "Stopping capture engine and disconnecting monitors...", "system")
        self._set_status("Disconnecting...", COLOR_AMBER)

        # Single stop
        self.chat.disconnect()
        self.detector.stop()
        self.recorder.stop()

        # Grid stop
        self.multi_chat.disconnect()
        self.multi_detector.stop()
        self.multi_recorder.stop_all()

        self._monitoring_mode = "idle"
        self._set_status("Idle", COLOR_GRAY)

        # Reset button states
        self.single_connect_btn.configure(state=tk.NORMAL)
        self.grid_connect_btn.configure(state=tk.NORMAL)
        self._global_stop_btn.pack_forget()

    # ── CLIPS UTILITIES ───────────────────────────────────────────────────────
    def _play_clip(self, clip: dict):
        p = clip.get("path")
        if not p or not Path(p).exists():
            messagebox.showwarning("Not Found", "Clip file no longer exists on disk.")
            return
        if sys.platform == "win32":
            os.startfile(str(p))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])

    def _reveal_clip(self, clip: dict):
        p = clip.get("path")
        if not p:
            return
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(p)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(Path(p).parent)])

    def _delete_clip(self, clip: dict, card: ctk.CTkFrame):
        p = clip.get("path")
        if p and Path(p).exists():
            if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete this video file?\n\n{p}"):
                try:
                    Path(p).unlink()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to delete file:\n{e}")
                    return
        self._session_clips = [c for c in self._session_clips if c["id"] != clip["id"]]
        card.destroy()
        self._clip_count_label.configure(text=f"{len(self._session_clips)} clips saved")
        self._refresh_clips_page()

    def _create_vertical_letterbox_video(self, src: Path, out: Path, clip: dict) -> bool:
        """
        Scale and pad a landscape 16:9 video into a vertical 1080x1920 video with solid black bars,
        and centered top/bottom text overlays.
        """
        ffmpeg = find_tool("ffmpeg")
        if not ffmpeg:
            return False

        top_text = self.settings.get("match_title", "").strip().upper()
        if not top_text:
            top_text = clip.get("channel", "STREAM").upper()

        bottom_text = self.settings.get("match_score", "").strip().upper()
        if not bottom_text:
            bottom_text = "HYPE MOMENT"

        font_arg = "font='Arial':"
        paths = [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\impact.ttf",
        ]
        for p in paths:
            if os.path.exists(p):
                safe_p = p.replace('\\', '/').replace(':', '\\:')
                font_arg = f"fontfile='{safe_p}':"
                break

        esc_top = escape_ffmpeg_text(top_text)
        esc_bottom = escape_ffmpeg_text(bottom_text)

        vf_filters = [
            "scale=1080:-2",
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",
            f"drawtext={font_arg}text='{esc_top}':x=(w-tw)/2:y=328-th/2:fontsize=72:fontcolor=white",
            f"drawtext={font_arg}text='{esc_bottom}':x=(w-tw)/2:y=1592-th/2:fontsize=64:fontcolor=lime"
        ]
        vf_string = ",".join(vf_filters)

        cmd = [
            ffmpeg, "-y", "-i", str(src),
            "-vf", vf_string,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", str(out)
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, timeout=120)
            return res.returncode == 0
        except Exception:
            return False

    def _export_tiktok(self, clip: dict):
        if not clip.get("path") or not Path(clip["path"]).exists():
            messagebox.showwarning("No Video", "No valid clip file to crop.")
            return

        ffmpeg = find_tool("ffmpeg")
        if not ffmpeg:
            messagebox.showerror("Tool Missing", "ffmpeg is required to process TikTok crops.")
            return

        src = Path(clip["path"])
        out_folder = src.parent / "tiktok_exports"
        out_folder.mkdir(parents=True, exist_ok=True)
        out = out_folder / (src.stem + "_tiktok.mp4")

        def crop_job():
            success = self._create_vertical_letterbox_video(src, out, clip)
            if success:
                self.root.after(0, lambda: (
                    messagebox.showinfo("Export Successful", f"Saved TikTok 9:16 format to:\n{out}"),
                    self._reveal_clip({"path": out})
                ))
            else:
                self.root.after(0, lambda: messagebox.showerror("Crop Failed", "FFmpeg failed to process the vertical letterbox layout."))

        threading.Thread(target=crop_job, daemon=True).start()
        self._show_toast("📱 Exporting TikTok vertical crop...")

    # ── YOUTUBE API OPERATIONS ────────────────────────────────────────────────
    def _check_youtube_link(self):
        def check():
            if youtube.is_linked():
                name = youtube.get_channel_name()
                if name:
                    self.root.after(0, lambda: self._update_youtube_ui(True, name))
                    return
            self.root.after(0, lambda: self._update_youtube_ui(False, ""))
        threading.Thread(target=check, daemon=True).start()

    def _update_youtube_ui(self, linked: bool, channel: str):
        self._yt_channel_name = channel
        if linked:
            self._yt_linked_var.set(f"Linked: {channel}")
            self.link_yt_btn.configure(text="Unlink YouTube", fg_color=COLOR_RED, hover_color="#d63031")
        else:
            self._yt_linked_var.set("Not linked")
            self.link_yt_btn.configure(text="Link YouTube Channel", fg_color=COLOR_PURPLE, hover_color=COLOR_PURPLE_H)

    def _toggle_youtube_link(self):
        if youtube.is_linked():
            if messagebox.askyesno("Confirm Unlink", "Unlink your YouTube account?"):
                youtube.unlink()
                self._update_youtube_ui(False, "")
                self._show_toast("YouTube unlinked")
        else:
            self._yt_linked_var.set("Authorizing in browser...")
            self.link_yt_btn.configure(state=tk.DISABLED)

            def auth():
                success, result = youtube.authenticate()
                if success:
                    self.root.after(0, lambda: (
                        self._update_youtube_ui(True, result),
                        self.link_yt_btn.configure(state=tk.NORMAL),
                        self._show_toast("OAuth Authorized!")
                    ))
                else:
                    self.root.after(0, lambda: (
                        self._update_youtube_ui(False, ""),
                        self.link_yt_btn.configure(state=tk.NORMAL),
                        messagebox.showerror("Auth Failure", f"Failed to authorize Google OAuth:\n{result}")
                    ))
            threading.Thread(target=auth, daemon=True).start()

    def _manual_youtube_upload(self, clip: dict, bypass_dialog: bool = False):
        if not youtube.is_linked():
            messagebox.showwarning("Not Authorized", "Please link your YouTube account under Settings first.")
            return

        filepath = clip.get("path")
        if not filepath or not Path(filepath).exists():
            messagebox.showerror("Missing File", "Clip video file not found on disk.")
            return

        clip["youtube_status"] = "Preparing..."
        self._refresh_clips_page()

        # ── Content Engine videos: use the AI-generated metadata ──────
        if clip.get("is_ce_video") and clip.get("ce_title"):
            title = clip["ce_title"]
            description = clip.get("ce_description", "")
            ce_tags = clip.get("ce_tags", [])
            tags = ",".join(ce_tags) if isinstance(ce_tags, list) else ce_tags
            visibility = self.settings.get("ce_upload_visibility", "public")

            # Ensure #Shorts is in title
            if "#shorts" not in title.lower():
                if len(title) + 8 <= 100:
                    title += " #Shorts"
            title = title[:100]

            # Append channel branding to description
            channel_name = self.settings.get("ce_channel_name", "World Cup Central")
            description += f"\n\n🔔 Follow @{channel_name} for daily World Cup content!"
            description += "\n\n#WorldCup #WorldCup2026 #Football #Soccer #Shorts"

        # ── Twitch clips: use the template-based metadata ─────────────
        else:
            channel = clip.get("channel", "stream")
            dt_str = clip.get("datetime", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            ts_str = clip.get("timestamp", datetime.now().strftime("%H:%M:%S"))
            hype_score = clip.get("hype", 0)
            duration = clip.get("duration", 0)

            # Decide template: if this is a grid clip, use wc_grid_template
            is_grid = "grid_" in str(filepath)
            if is_grid:
                # We pad names to exactly 4 for template replacement
                wc_chans = self.settings["wc_streamers"]
                while len(wc_chans) < 4:
                    wc_chans.append("Slot")
                title = self.settings["youtube_wc_grid_template"].format(
                    streamer1=wc_chans[0].upper(),
                    streamer2=wc_chans[1].upper(),
                    streamer3=wc_chans[2].upper(),
                    streamer4=wc_chans[3].upper()
                )
            else:
                title = self.settings["youtube_title_template"].format(
                    channel=channel, timestamp=ts_str, datetime=dt_str, hype=hype_score, duration=duration
                )

            # Ensure hashtags are valid
            if "#shorts" not in title.lower() and self.settings["youtube_upload_shorts"]:
                title = f"{title[:90]} #shorts"

            description = self.settings["youtube_description"].format(
                channel=channel, timestamp=ts_str, datetime=dt_str, hype=hype_score, duration=duration
            )
            tags = self.settings["youtube_tags"]
            visibility = self.settings["youtube_visibility"]

        # Run background thread
        def run_upload(final_title, final_desc, final_tags, final_vis):
            upload_path = str(filepath)
            temp_file = None

            is_grid = "grid_" in str(filepath)
            is_tiktok = "_tiktok" in str(filepath)

            if self.settings["youtube_upload_shorts"] and not (is_grid or is_tiktok):
                clip["youtube_status"] = "Processing Short..."
                self.root.after(0, self._refresh_clips_page)

                temp_dir = Path(filepath).parent / "temp_uploads"
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_file = temp_dir / (Path(filepath).stem + "_short.mp4")

                success = self._create_vertical_letterbox_video(Path(filepath), temp_file, clip)
                if success:
                    upload_path = str(temp_file)
                else:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Short Processing Failed",
                        "FFmpeg failed to create the vertical Shorts layout. Uploading original widescreen video instead."
                    ))
                    temp_file = None

            clip["youtube_status"] = "Uploading..."
            self.root.after(0, self._refresh_clips_page)
            
            # Perform upload
            self._do_youtube_upload(upload_path, final_title, final_desc, final_tags, final_vis, clip)

            # Clean up temp file if created
            if temp_file and temp_file.exists():
                try:
                    time.sleep(1)  # Allow final file handle release
                    temp_file.unlink()
                except Exception as e:
                    print(f"Failed to delete temp upload file: {e}")

        if bypass_dialog:
            threading.Thread(target=run_upload, args=(title, description, tags, visibility), daemon=True).start()
        else:
            def on_dialog_submit(edited_title, edited_desc, edited_tags, edited_vis):
                threading.Thread(target=run_upload, args=(edited_title, edited_desc, edited_tags, edited_vis), daemon=True).start()
            
            def check_cancel(event=None):
                if event and event.widget != dialog:
                    return
                if not dialog.submitted:
                    clip["youtube_status"] = "Saved locally" if not clip.get("youtube_url") else "Uploaded successfully!"
                    self._refresh_clips_page()

            dialog = YouTubeUploadDialog(self.root, title, description, tags, visibility, on_dialog_submit)
            dialog.bind("<Destroy>", check_cancel)

    def _auto_youtube_upload(self, clip: dict):
        # Triggered automatically after clip save
        if not youtube.is_linked():
            return
        self._manual_youtube_upload(clip, bypass_dialog=True)

    def _do_youtube_upload(self, filepath: str, title: str, description: str, tags: str, visibility: str, clip: dict):
        def progress(pct):
            clip["youtube_status"] = f"Uploading ({pct}%)"
            self.root.after(0, self._refresh_clips_page)

        def success(url):
            clip["youtube_status"] = "Uploaded successfully!"
            clip["youtube_url"] = url
            self.root.after(0, lambda: (
                self._refresh_clips_page(),
                self._show_toast("🚀 Upload Finished!"),
                messagebox.showinfo("Upload Complete", f"Video published successfully!\n\nLink: {url}")
            ))

        def error(err):
            clip["youtube_status"] = "Upload Failed"
            self.root.after(0, lambda: (
                self._refresh_clips_page(),
                messagebox.showerror("Upload Error", f"Google API Error:\n{err}")
            ))

        youtube.upload_video(
            filepath=filepath,
            title=title,
            description=description,
            tags=tags,
            visibility=visibility,
            progress_callback=progress,
            success_callback=success,
            error_callback=error
        )

    # ── GENERAL CONFIG WRAPPERS ───────────────────────────────────────────────
    def _apply_threshold(self, v):
        self.settings["threshold"] = v
        self.detector.threshold = v
        self.multi_detector.threshold = v
        self.single_threshold_lbl.configure(text=f"Clip Threshold: {v:.0f} msg/s")
        self.grid_threshold_lbl.configure(text=f"Correlated Threshold: {v:.0f} msg/s")
        self.thresh_slider_lbl.configure(text=f"Hype Trigger Threshold: {v:.0f} msg/s")

    def _apply_cooldown(self, v):
        self.settings["cooldown"] = int(v)
        self.detector.cooldown = int(v)
        self.multi_detector.cooldown = int(v) + 15
        self.cooldown_slider_lbl.configure(text=f"Trigger Cooldown: {int(v)} seconds")

    def _browse_folder(self):
        f = filedialog.askdirectory(initialdir=self.save_folder)
        if f:
            self.save_folder = f
            self.settings["save_folder"] = f
            self.folder_var.set(f)
            self.recorder.save_folder = Path(f)
            self.multi_recorder.save_folder = Path(f)

    def run(self):
        # Force the window to become visible and come to the foreground
        self.root.deiconify()
        self.root.update()
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(200, lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()

        # On Windows, use ctypes to forcefully bring the window to front
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            # Get the actual window handle from tkinter
            tk_hwnd = self.root.winfo_id()
            ctypes.windll.user32.ShowWindow(tk_hwnd, 9)  # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(tk_hwnd)
        except Exception:
            pass

        self.root.mainloop()

