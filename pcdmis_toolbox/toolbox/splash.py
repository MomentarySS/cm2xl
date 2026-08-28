"""
toolbox/splash.py
=================
cm2xl 启动画面（Splash Screen）。

线程安全协作方案：
- 主线程：创建 Splash 窗口，只用 after() 调度更新（不调用 mainloop）
- 后台线程：执行耗时初始化（Shell / PaddleOCR），通过 queue 推送进度
- 主线程：用 after() 轮询队列并更新 Splash UI
- 初始化完成后，后台线程通知主线程关闭 Splash，再创建 Shell 窗口

全程所有 CTk 调用均在主线程，安全无竞态。
"""
import queue
import threading
import time
import customtkinter as ctk

from toolbox.app_meta import APP_VERSION
from utils.app_icon import apply_window_icon, get_logo_image

# ── 主题色（与 utils/theme.py 保持一致）───────────────────────────────────────
_ACCENT      = "#0F766E"
_ACCENT_LITE = "#14B8A6"
_MUTED       = "#6B7280"

# 模拟启动阶段（init_fn 真正执行时这些被忽略，以实际进度为准）
_BOOT_STEPS = [
    (0.05, "加载配置...",               80),
    (0.15, "初始化模块...",            150),
    (0.40, "加载 PaddleOCR...",       2800),
    (0.70, "准备界面...",             1800),
    (0.90, "就绪",                      0),
]


class SplashScreen:
    """
    show_and_wait(init_fn) -> (root, shell_instance)
    ─────────────────────────────────────────────────────
    init_fn : () -> (ctk.CTk, shell_instance)
        在后台线程调用。返回创建的 root 和 shell 实例。
        可以在内部执行耗时操作（PaddleOCR 加载等）。
    """

    def __init__(self, min_display_ms: int = 1500):
        self._min_ms = min_display_ms
        self._start_ts = time.monotonic()
        self._queue: queue.Queue = queue.Queue()

        self._root: ctk.CTk | None = None
        self._progress: ctk.CTkProgressBar | None = None
        self._status: ctk.CTkLabel | None = None

        self._init_done = False
        self._init_result: tuple | None = None
        self._init_exc: BaseException | None = None
        self._splash_closed = False

    # ── 公开 API ──────────────────────────────────────────────────────────────

    def show_and_wait(self, init_fn) -> tuple:
        """
        显示 Splash，在后台线程运行 init_fn，返回 (root, shell_instance)。
        """
        # 启动后台初始化线程
        t = threading.Thread(target=self._run_init, args=(init_fn,), daemon=True)
        t.start()

        # 创建 Splash 窗口
        self._create_window()

        # 用 after() 轮询队列 + 驱动 Splash 动画，直到初始化完成
        self._event_loop()

        # Splash 已关闭，返回 Shell 创建结果
        return self._init_result

    # ── 内部 ─────────────────────────────────────────────────────────────────

    def _run_init(self, init_fn) -> None:
        """后台线程：执行初始化，实时推送进度。"""
        def progress(frac: float, text: str):
            self._queue.put(("progress", (frac, text)))

        # 预热阶段（加载配置等，init_fn 还未真正开始）
        for frac, label, delay in _BOOT_STEPS[:-1]:
            progress(frac, label)
            time.sleep(delay / 1000)

        # 真正执行耗时初始化
        try:
            result = init_fn()
            progress(1.0, "完成")
            self._init_result = result
        except BaseException as e:
            self._init_result = None
            self._init_exc = e
        finally:
            self._queue.put(("done", None))

    def _create_window(self) -> None:
        """主线程：创建 Splash CTk 窗口（无 mainloop）。"""
        splash = ctk.CTk()
        splash.withdraw()
        splash.overrideredirect(True)
        splash.resizable(False, False)

        W, H = 420, 270
        sw = splash.winfo_screenwidth()
        sh = splash.winfo_screenheight()
        splash.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")

        self._root = splash
        apply_window_icon(splash)
        self._build_ui(splash)
        splash.deiconify()

    def _build_ui(self, parent: ctk.CTk) -> None:
        """构建 Splash UI。"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        card = ctk.CTkFrame(
            parent, corner_radius=14,
            fg_color=["#FFFFFF", "#1C2330"],
            border_width=0,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=28, pady=28)
        card.columnconfigure(0, weight=1)

        self._logo = get_logo_image(72)
        if self._logo is not None:
            ctk.CTkLabel(
                card, text="", image=self._logo, fg_color="transparent",
            ).grid(row=0, column=0, pady=(20, 2))
        else:
            ctk.CTkLabel(
                card, text="cm2xl",
                font=ctk.CTkFont(family="Segoe UI", size=52, weight="bold"),
                text_color=_ACCENT, fg_color="transparent",
            ).grid(row=0, column=0, pady=(20, 2))

        ctk.CTkLabel(
            card, text=f"Version {APP_VERSION}",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=_MUTED, fg_color="transparent",
        ).grid(row=1, column=0, pady=(0, 14))

        sep = ctk.CTkFrame(card, height=1, fg_color=[_ACCENT_LITE, "#28303F"])
        sep.grid(row=2, column=0, padx=16, sticky="ew")
        sep.configure(height=1)

        self._status = ctk.CTkLabel(
            card, text="正在启动...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=_MUTED, fg_color="transparent",
        )
        self._status.grid(row=3, column=0, pady=(12, 6))

        self._progress = ctk.CTkProgressBar(
            card, progress_color=_ACCENT,
            fg_color=["#E5E7EB", "#2A3545"], corner_radius=6,
        )
        self._progress.grid(row=4, column=0, padx=16, pady=(0, 20), sticky="ew")
        self._progress.set(0)

    def _event_loop(self) -> None:
        """主线程：用 after() 轮询队列，直到初始化完成。"""
        step_index = [0]
        steps = list(_BOOT_STEPS)

        def advance():
            if self._init_done or self._root is None:
                return
            if step_index[0] < len(steps):
                frac, label, delay = steps[step_index[0]]
                step_index[0] += 1
                self._set_progress(frac, label)
                if delay > 0:
                    self._root.after(delay, advance)

        # 启动模拟进度动画（后台线程还没推送真实进度时用）
        self._root.after(60, advance)

        # after() 轮询主循环
        def _poll():
            # 处理队列中的所有消息
            try:
                while True:
                    msg_type, data = self._queue.get_nowait()
                    if msg_type == "progress":
                        frac, text = data
                        self._set_progress(frac, text)
                    elif msg_type == "done":
                        self._init_done = True
            except queue.Empty:
                pass

            if not self._init_done:
                self._root.after(80, _poll)
            else:
                self._close_splash()

        self._root.after(100, _poll)
        self._root.after(100, _poll)   # 立即触发第一次
        self._root.mainloop()           # 阻塞，直到 _close_splash() 调用 destroy()

    def _set_progress(self, value: float, text: str = "") -> None:
        if self._root is None:
            return
        try:
            if self._progress is not None:
                self._progress.set(value)
            if text and self._status is not None:
                self._status.configure(text=text)
        except Exception:
            pass

    def _close_splash(self) -> None:
        """确保最小显示时间后关闭 Splash。"""
        if self._root is None:
            return
        elapsed = (time.monotonic() - self._start_ts) * 1000
        remain = max(0, self._min_ms - elapsed)

        def _destroy():
            if self._root is not None:
                self._root.withdraw()   # 先 hide，防止闪
                self._root.destroy()
                self._root = None

        if remain > 0:
            self._root.after(int(remain), _destroy)
        else:
            _destroy()
