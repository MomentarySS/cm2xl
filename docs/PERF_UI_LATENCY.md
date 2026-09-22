# UI 延迟性能排查记录

> 排查范围：cm2xl Shell 的界面卡顿。全部数据在本机实测，环境见文末「测量环境」。
> 三个问题的根因彼此独立，但共同点是「主线程上做了本不该做的事」。

---

## TL;DR

| # | 现象 | 根因 | 状态 |
|---|------|------|------|
| 1 | 深色/浅色切换卡顿 | `ctk.set_appearance_mode()` 同步遍历**全部存活 widget**，O(n)；CMMFiller 预览窗口又一次性挂上万 widget 进 tracker | ✅ 已修 `bce103c` |
| 2 | 切到 PCDMIS 模块卡 ~560 ms | `_perm_text()` 内 3 次 `get_pcdmis_pid()`，等价 spawn 3 个 `tasklist.exe` | ✅ 已修 `f6a4a42` |
| 3 | watcher after-id 生命周期 | 触发后的 id 未清零，`_stop_status_watcher()` 去取消已执行 id | ✅ 已修 `94aa08b` |
| 4 | **已连接 PCDMIS 时每次激活/轮询 ~620 ms** | `dispatch_pcdmis()` **内部**调 `is_pcdmis_running()`，每次 dispatch 付一次 tasklist；且 `get_active_part_name()` 因 `ensure_session()` 重复 dispatch | ✅ 已修 `HEAD`（4-A + 4-B） |

第 4 项是当前剩余的最大卡点，实测比第 2 项还严重，但尚未动代码（本次仅完成研究 + 记录方案）。

---

## 问题 1：深色/浅色切换卡顿

### 根因

CustomTkinter 6.0 的 `ctk.set_appearance_mode()` 最终走到
`customtkinter/windows/widgets/appearance_mode/appearance_mode_tracker.py:53`
的 `AppearanceModeTracker.update_callbacks()`：

```python
@classmethod
def update_callbacks(cls):
    if cls.appearance_mode == 0:
        for callback in cls.callback_list:      # ← 同步遍历每个 widget 的
            try:                                 #   _set_appearance_mode()
                callback("Light")
```

**每个创建过的 CTk widget 都在 `callback_list` 里注册了一个回调**，切换主题就是
**主线程同步遍历全部 widget 逐个重配颜色 + 重绘 canvas**，O(n)。

### 本项目里谁在放大效应

| 来源 | 位置 | widget 数 |
|------|------|----------|
| 静态 UI 构造 | `modules/cmm_filler/gui.py` (162)、`modules/pc_to_excel/gui/main_window.py` (77)、`toolbox/*` (70) | ~309 处构造点 |
| **CMMFiller 预览窗口** | `gui._build_preview_card()` 每测量项 5–6 widget（Frame/CheckBox/2 Label/Entry ± NG） | 30 PDF×80 项 ≈ **13 200** |

模块 host 复用（`toolbox/shell.py` 的 `if host is None`）使 widget 切模块不释放，
tracker 回调只增不减。**预览窗口一打开，tracker 从 ~800 涨到上万。**

### 实测

| widget 数 | `set_appearance_mode` + `root.update()`（median） |
|----------:|-------------------------------------------------:|
| 200 | 70 ms |
| 500 | 118 ms |
| 1 000 | 163 ms |
| 2 000 | 361 ms |

### 修复（`bce103c`）

1. `toolbox/settings_dialog.py`：`ctk.set_appearance_mode()` 改走 `self._win.after_idle(...)`，
   不再在「保存」按钮回调里同步执行。
2. `modules/cmm_filler/gui.py::_build_preview_card()`：删掉内层 `cols` Frame，
   把 `label` + `desc` 合并为单个 Label（`sticky='ew'`），**保留 tol 独立列**
   （灰色 / `size=12` / `anchor='e'`）以维持表格可读性。每行 5–6 widget → 3–4。

取舍说明：合并后 label 在 ng/low_conf 行会跟随 `desc_font` 加粗（原来只 desc 加粗），
但 `⚡`/`⚠` 前缀 + `row_bg` 状态色仍是强信号。tol 列保留是对可读性的关键让步。

---

## 问题 2：切到 PCDMIS 模块卡 ~560 ms

### 根因链路

```
modules/pc_to_excel/module.py:57   on_activate()
  → gui/main_window.py:1265        _start_status_watcher()
    → main_window.py:1283          _schedule_status_watch()
      → main_window.py:1283        self._status_watcher_tick()   ← 同步！没用 after()
        → main_window.py:1294      _refresh_connection_ui()
          → main_window.py:813     self.perm_var.set(self._perm_text())
            → main_window.py:674,675,677  _perm_text() 里 3 次探测
              → com_detector.py:212 subprocess.run(["tasklist", ...])  ← 每次 ~190 ms
```

`_perm_text()` 原实现：

```python
tool = admin_status_text()
if is_pcdmis_running():                                    # spawn #1
    pcd = "PCDMIS:管理员" if is_pcdmis_elevated() else ...   # spawn #2
    elevated = is_pcdmis_elevated()                        # spawn #3
```

`is_pcdmis_running()` = `get_pcdmis_pid() is not None`，
`is_pcdmis_elevated()` = `is_process_elevated(get_pcdmis_pid())`
——**同一个值 spawn 3 次 tasklist.exe**。

### 实测

| 调用 | median |
|------|-------:|
| `get_pcdmis_pid()`（spawn 一次 tasklist） | 192 ms |
| `_perm_text()`（3 次 spawn） | **561 ms** |

### 修复（`f6a4a42`）

1. **单次探测**：只调一次 `get_pcdmis_pid()`；并把 `elevated` 三元判定改为显式
   `is True` / `is False` / `else`，让 `None`（查不到 token）显示为 `PCDMIS:?`
   而非误报「普通」。
2. **2s TTL 缓存**：`_perm_text()` 是状态栏展示字段，2s 陈旧无感知风险。
   **所有返回路径统一先构造 `text` 再写缓存**——`pid is None` 分支不能提前
   return，否则「PCDMIS 未运行」永远不进缓存。`mount / 连接 / 断开 / watcher tick`
   的重复调用命中缓存后约 0.001 ms。
3. **首次 tick 推一帧**：`_schedule_status_watch()` 的第一次 `_status_watcher_tick()`
   改 `after(0)`（=当前 UI 事件处理完后下一轮事件循环，**不是**延迟 30 秒），
   模块切换立即返回。两个 after id 分开存，`_stop_status_watcher()` 才能分别取消。

### 效果

| 路径 | before | after |
|------|-------:|------:|
| 冷路径（1 次真实 spawn） | 560 ms | **194 ms** |
| 2s 内重复调用 | 560 ms | **0.001 ms** |

---

## 问题 3：watcher after-id 生命周期

首次 tick 改 `after(0)` 后引入两个 id：`_status_watcher_tick_id` 与
`_status_watcher_after_id`。二者只在 `_stop_status_watcher()` 里被取消，但
tick / 30s timer **自身触发后 id 并未清零**，于是之后 stop 会对一个已经执行过的
id 调 `after_cancel`——Tkinter 抛 `TclError`，虽被 `except Exception: pass` 吞掉
不影响功能，但句柄状态陈旧，读代码时无法判断哪个 id 仍然有效。

### 修复（`94aa08b`，5 行）

```python
def _schedule_status_watch(self) -> None:
    self._status_watcher_after_id = None     # ← 置 None
    if not self._status_watcher_running:     # ← 紧跟 running guard
        return
    ...

def _status_watcher_tick(self) -> None:
    self._status_watcher_tick_id = None      # ← 置 None
    if not self._status_watcher_running:     # ← 紧跟 running guard
        return
    if self._busy:                           # ← 额外一道：抽数中不抢 COM
        return
```

两处置 None 都放在 `running` 检查**之前**：置 None 的语义是「该 id 已触发」，
与 `running` 是否为 False 无关，早退时也必须清理。`_status_watcher_tick` 里的
`running` guard 尤其关键——里面就是 `session_alive()` / `_refresh_connection_ui()`
这些耗时探测，stop 与 tick 交错时能挡掉一次无效 COM 调用。

---

## 问题 4：已连接 PCDMIS 时每次激活/轮询 ~620 ms

> **状态：已修复。** 以下为完整根因分析与实施记录。Fix 4-A + 4-B 已落地，
> 实测单次 tick 从 ~606 ms 降到 **44.8 ms（−93%）**。

### 4.1 现象与范围

问题 2 修完后，`_perm_text` 已不是瓶颈。但在**已连接**状态下，
`_status_watcher_tick()` 与 `_refresh_connection_ui()` 里的 COM 探测仍全部
跑在主线程，量级比问题 2 更大。影响面：

- 每次切到 PCDMIS 模块（`on_activate` → `_refresh_conn_status`）
- 每 30s 一次 watcher tick
- 连接成功 / 断开 / 每次导出后的 `_refresh_connection_ui()`

### 4.2 实测（PCDMIS 2024.1 真实运行中）

| 调用 | median |
|------|-------:|
| `is_pcdmis_running()`（spawn tasklist） | **184 ms** |
| `com_apartment()`（CoInitialize/CoUninitialize） | **0.00 ms** |
| `win32com.client.GetActiveObject(prog_id)` | 2.7 – 7.6 ms |
| `app.ActivePartProgram`（app 对象复用） | 9.8 ms |
| `dispatch_pcdmis(prog_id)`（本项目路径） | **192 ms** |
| `conn.session_alive()` | 206 ms |
| `conn.get_active_part_name()` | **416 ms** |

### 4.3 关键发现：192 ms 的 dispatch 里 **96% 是 tasklist**

`modules/pc_to_excel/connector/com_detector.py:305`：

```python
def dispatch_pcdmis(prog_id: str):
    import win32com.client
    errors = []
    running = is_pcdmis_running()      # ← com_detector.py:314  ← tasklist spawn！
    factories = []
    if running:
        factories.append(("GetActiveObject", lambda: ...))
        factories.append(("Dispatch", lambda: ...))
    else:
        factories.append(("Dispatch", lambda: ...))     # ← 顺序反过来
        factories.append(("GetActiveObject", lambda: ...))
    for label, factory in factories:
        try:
            with com_call_lock:
                return factory()
```

**`is_pcdmis_running()` 的唯一作用是决定 GetActiveObject 与 Dispatch 的尝试顺序。
为这个顺序判断，每次 dispatch 都 spawn 一个 tasklist.exe（184 ms）。**

而两个工厂都是「失败即抛异常 → 落到下一个」：
- PCDMIS 未运行时先试 GetActiveObject，快速失败后转 Dispatch，结果一样；
- 反过来也一样。

**也就是说这个前置 `running` 判断只影响「多走一次异常开销」，不影响任何功能正确性。**

### 4.4 第二个冗余：`get_active_part_name()` 内部重复 dispatch

`pcdmis_connector.py:148`：

```python
def get_active_part_name(self) -> str:
    if not com_call_lock.acquire(blocking=False):
        return self._last_part_name
    try:
        info = self.ensure_session()        # ← 内部又调 session_alive()（1 dispatch）
        if not info.connected:
            return self._last_part_name
        with com_apartment():
            app = self._bind_app()          # ← 又一次 dispatch
            part = app.ActivePartProgram    # ← 又一次属性读
            name = str(part.Name or "")
```

外层 `_status_watcher_tick()` 已经先调过一次 `session_alive()` 确认会话存活，
`get_active_part_name()` 内部 `ensure_session()` 又把同一件事做一遍，
**再加自己那次 dispatch，一次显示字段刷新 = 2 次 dispatch = 416 ms**
（实测 205.69 × 2 ≈ 411，与 415.81 吻合，反证了重复 dispatch 的存在）。

### 4.5 单次 `_status_watcher_tick` 的完整开销（已连接）

```
_status_watcher_tick()
├─ session_alive()                      1 dispatch → 192 ms
└─ _refresh_connection_ui()
   └─ get_active_part_name()
      ├─ ensure_session() → session_alive()   1 dispatch → 192 ms
      └─ com_apartment + _bind_app + prop     1 dispatch → 196 ms
                                         ────────────────────────
                                         3 dispatch ≈ 580 ms
                                         + 真实 COM ~30 ms
                                         ≈ 620 ms / tick
```

**这是当前剩余的最大卡点，比已修复的问题 2（560 ms）还严重。**

### 4.6 已实施的修复

#### Fix 4-A ✅ `dispatch_pcdmis()` 去掉 tasklist 前置判断

`modules/pc_to_excel/connector/com_detector.py` — 顺序固定为先
`GetActiveObject`、失败再 `Dispatch`：

```python
factories: list[tuple[str, object]] = [
    ("GetActiveObject", lambda: win32com.client.GetActiveObject(prog_id)),
    ("Dispatch", lambda: win32com.client.Dispatch(prog_id)),
]
```

已运行实例仍优先附着；未运行时只是多一次毫秒级的 `GetActiveObject` 失败再转
`Dispatch`。顺序只影响异常路径开销，不影响任何功能正确性。

**实测：dispatch 192 ms → 7.95 ms（24×）。**

#### Fix 4-B ✅ `get_active_part_name()` 去掉内部 `ensure_session()`

`modules/pc_to_excel/connector/pcdmis_connector.py` — 改为纯轻量读取：
未连接直接返回 `_last_part_name`；已连接则尝试一次
`_bind_app()` + `ActivePartProgram.Name`，任何失败兜底缓存。
并把 `com_call_lock` 抢锁失败与「未连接」都提到最前面，避免无谓开销。

导出前的会话自愈仍在 `_ensure_connected()` → `ensure_session()`，**未受影响**
（`get_active_part_name()` 的调用方都是 UI 刷新）。

**实测：`get_active_part_name()` 416 ms → 24.04 ms（17×）。**

#### 总体效果

| 调用 | before | after | |
|------|-------:|------:|---|
| `dispatch_pcdmis()` | 192 ms | 7.95 ms | 24× |
| `session_alive()` | 206 ms | 20.79 ms | 10× |
| `get_active_part_name()` | 416 ms | 24.04 ms | 17× |
| **单次 `_status_watcher_tick`（已连接）** | **~606 ms** | **44.8 ms** | **−93%** |

（`session_alive` 的 20.79 ms = 7.95 dispatch + ~13 ms `ActivePartProgram`
属性读，与 4.2 节单独测得的 9.8 ms 同量级。）

### 4.7 测试变更

`modules/pc_to_excel/tests/test_com_compat.py`：

- `test_dispatch_running_does_not_use_ensure_dispatch`
  → `test_dispatch_prefers_get_active_object`：去掉 `is_pcdmis_running=True`
  的 monkeypatch（该探测已不存在），**新增断言 `dispatch_pcdmis()` 不得调用
  `is_pcdmis_running()`**（spy 记录调用次数，防回归），并源码级断言
  `EnsureDispatch` 不出现在实现中（项目铁律）。
- 新增 `test_dispatch_falls_back_to_dispatch`：`GetActiveObject` 失败后回退
  `Dispatch`，且顺序为先前者。
- 新增 `test_dispatch_raises_when_both_fail`：两条路都失败时报
  `PCDMIS_CONNECT_FAIL`，且错误信息含两个工厂的失败原因。
- 新增 Fix 4-B 专项 5 个：跳过 `ensure_session`（monkeypatch 成抛异常来守）、
  未连接返缓存、读失败兜底、`ActivePartProgram is None`、抢不到
  `com_call_lock` 返缓存（**注意 `com_call_lock` 是 `RLock`，同线程可重入，
  必须由另一个线程持有才能真正制造抢锁失败**）、源码级断言无
  `ensure_session` 调用。
- 测试辅助 `_code_source()`：源码级断言前先剔除 docstring，否则 docstring 里
  为说明背景提到的禁用 API 名会造成误报。

### 4.8 未采用的方案（备查）

#### Fix 4-C：part name 加 TTL 缓存

`part_var` 是纯展示字段，可加 2–5s TTL 让大部分激活/轮询零 COM 成本。
当前 44.8 ms 已足够低，**暂不值得**；若将来 watcher 间隔缩短或发现仍有感知
再考虑。注意导出完成后要显式失效缓存。

#### Fix 4-D：整个 tick 移到工作线程

最彻底，但改动面大、回归风险高。**仅在 4-A/4-B 仍不够时才考虑。**

### 4.9 风险与注意点

- `dispatch_pcdmis` 的 CLAUDE.md 约束：**已运行实例只用 GetActiveObject /
  Dispatch，禁止 EnsureDispatch**（会重建 gencache，二次导出假死）。Fix 4-A 的
  两个工厂都不涉及 EnsureDispatch，且新增了源码级测试守护。
- `com_call_lock` 是 `threading.RLock`；`get_active_part_name()` 与
  `session_alive()` 都用 `acquire(blocking=False)` 非阻塞抢锁，抽数时返回缓存值
  不阻塞。删掉 `ensure_session()` 不影响这个保护。
- `dispatch_pcdmis()` **自己不包 `com_apartment()`**，依赖调用方预先
  CoInitialize。app 内 `session_alive()` / `get_active_part_name()` /
  `try_connect_with_app()` 均有包裹；新增调用点时必须自行包裹。
- **连接流程中仍有 tasklist**：`try_connect_with_app():437` 的
  `is_pcdmis_running()` 与 `check_elevation_match()`。但连接是一次性动作，
  190 ms 可接受，**未改动**。
- 需真机回归：连接 / 断开 / 一键导出 / 多件连续测。

---

## 测量环境

| 项 | 值 |
|----|----|
| Python | 3.10.21 64-bit（conda env `paddleocr_gpu`） |
| CustomTkinter | 6.0.0 |
| PC-DMIS | 2024.1，运行中，`PCDLRN.Application.19.1`，pid 18296 |
| paddle | 2.6.2（**CPU wheel**，`is_compiled_with_cuda() == False`） |
| PaddleOCR | 2.10.0，`use_gpu=True` 由 `check_gpu()` 自动降级 CPU |

### 复现方式

以下脚本均为**只读**（dispatch + 属性读，不导出、不写文件、不改 PRG），
跑完删除即可。全部数字取 5 次采样 median。

```powershell
# 问题 2：tasklist 单次 spawn 成本
D:\AI\miniconda3\envs\paddleocr_gpu\python.exe bench_switch.py

# 问题 1：set_appearance_mode 随 widget 数增长
D:\AI\miniconda3\envs\paddleocr_gpu\python.exe bench_theme2.py

# 问题 4：COM 探测分解 + 修复后复测（需 PCDMIS 运行中）
D:\AI\miniconda3\envs\paddleocr_gpu\python.exe bench_com_probe.py
D:\AI\miniconda3\envs\paddleocr_gpu\python.exe bench_decompose.py
D:\AI\miniconda3\envs\paddleocr_gpu\python.exe bench_fix4.py
```

---

## 遗留事项

1. **真机回归未完成**。本轮全程没有 PDF 可用于验证 CMMFiller 预览窗口；
   UI 改动只做到静态验证 + 单测 + micro-benchmark。PCDMIS 连接 / 断开 /
   一键导出 / 多件连续测需在真机确认。
2. `main` 分支已 push 至 `origin/main`。
3. `tests/phase8_smoke.py::TestCrashLog::test_exception_written` 是**排查前就存在**
   的失败：断言字面量 `MODEL_MISSING`，但 `ToolboxError.__str__` 只输出
   `[E1003]`。与本文所有改动无关。
4. 连接流程中仍有 tasklist（`try_connect_with_app():437`、`check_elevation_match()`），
   一次性动作可接受，未改动。详见 4.9。
