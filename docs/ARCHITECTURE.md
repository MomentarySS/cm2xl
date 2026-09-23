# cm2xl 架构设计

> **当前实现说明（2026-09-07）**：本文主体记录迁移期设计与历史目录映射；当前可执行项目根为 `pcdmis_toolbox/`，版本为 v1.0.12。实际依赖文件位于 `pcdmis_toolbox/requirements/`，打包规格为 `pcdmis_toolbox/pcdmis_toolbox.spec`，管理员启动器为 `pcdmis_toolbox/run_as_admin.bat`。

> **目标**：新建一个功能壳，将 `CMMFiller` 和 `pc to excel` 两个项目整合为统一的工具箱，同时保留各模块独立运行能力。
>
> **支持范围**：
> - PC-DMIS **2017 R2–2026.1**（COM 自动发现 ProgID，优先附着正在运行的实例；主测环境 2024.1）
> - Python **64 位**（PC-DMIS 2017 R2+ 要求）
> - Windows 7/10/11 64-bit
> - 测量房 **无网环境**（所有依赖必须打包）
> - 打包后整体体积 **600-700MB**

---

## 目录索引

### 离线部署约束
- 打包体积 / OCR 模型路径 / 环境变量 / 多进程 / fix_dist / ffmpeg DLL

### 一、现状分析
- 1.1 两个项目概况 / 1.2 关键发现

### 二、目录结构

### 三、核心设计决策（50 个子节）
- 3.0 依赖分条件安装 / 3.1 模块独立性 / 3.2 tkinterdnd2 挂载 / 3.3 模块接口协议
- 3.4 主题统一策略 / 3.5 路径管理 / **3.6 日志系统（统一 + 轮转 + GUI Handler）**
- 3.7 ~~BAS 脚本部署~~（2026-09-23 取消）/ 3.8 版本文件统一 / 3.9 配置迁移 / 3.9.1 版本升级 / 3.9.2 降级回退
- 3.10 PyInstaller spec / 3.11 fix_dist.py / 3.12 PaddleOCR 环境变量 / 3.13 自定义 Hook
- 3.14 admin 启动器 / 3.15 Python 64 位 / 3.16 COM Apartment
- 3.17 模板向导 / 3.18 用户文档 / 3.19 PCDMIS 状态轮询 / 3.20 freeze_support / 3.21 默认配置 / 3.22 测试套件
- 3.23 可扩展点 / 3.24 关键数据模型 / 3.25 命令 ID 常量 / 3.26 threading / 3.27 tkinter vs ctk
- 3.28 Inno Setup / 3.29 CLI 入口 / 3.30 三种运行模式 / 3.31 CLAUDE.md / 3.32 LICENSE + CI/CD / 3.33 测试样本 / 3.34 subprocess 安全
- **3.35 错误码体系** / **3.36 审计日志**
- **3.38 OCR 缓存清理**（3.37 删除因重复） / **3.39 PDF 大小写敏感**
- **3.40 原子写** / **3.41 文件锁** / **3.42 线程取消** / **3.43 PDF 句柄泄漏** / **3.44 资源管理清单**
- **3.45 主题冲突** / **3.46 相对 vs 绝对导入** / **3.47 启动参数入口**
- **3.48 PaddleOCR patch 完整性** / **3.49 PCDMIS 报告列** / **3.50 数据流 pipeline** / **3.51 数据提取重构（拆分 + 常量隔离 + 注册层解耦）**

### 四、壳主窗口设计
- 4.1 布局 / 4.2 导航 / 4.3 状态栏 / 4.4 独立入口兼容 / 4.5 全局异常处理

### 五、配置文件策略

### 六、模块适配层示例

### 七、PyInstaller 打包

### 八、实施路线图（与 11.3 同步）

### 九、风险点（24 项）

### 十、后续扩展

### 十一、迁移计划
- 11.1 目标结构 / 11.2 文件映射 / 11.3 分 Phase 步骤（含 5.5 应用层修复）
- 11.4 全局验证清单 / 11.5 风险回滚 / 11.6 时间估算（30-37 小时）

---

## 离线部署约束

测量房无网环境，所有依赖与 OCR 模型必须在打包时一并打入。

| 项 | 约束 |
|----|------|
| 打包体积 | 约 600–700 MB（PaddlePaddle + cv2/lmdb/lxml + OCR 模型 18MB） |
| OCR 模型 | 预下载到 `modules/cmm_filler/models/paddleocr/`（兼容旧路径 `CMMFiller/models/paddleocr/`），打包进 `_internal/models/paddleocr/` |
| 环境变量 | `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION` 由 `modules/cmm_filler/ocr/engine.py` 的 `PaddleOCREngine.__init__()` 局部 `setdefault` |
| 多进程 | `multiprocessing.freeze_support()` 必须在 `main.py` 最顶部、所有 import 之前 |
| 后处理 | `build/fix_dist.py` 复制完整 paddleocr 源码并 patch 4 个文件 |
| ffmpeg DLL | 打包后删除 `opencv_videoio_ffmpeg*.dll`（约 58–82 MB，OCR 不需要） |

---

## 一、现状分析

### 1.1 两个项目概况

| 项目 | 技术栈 | 入口文件 | 主要功能 |
|------|--------|----------|----------|
| **CMMFiller** | CustomTkinter + PaddleOCR + pymupdf + openpyxl | `cmm_filler_gui.py` | CMM 报告 OCR 识别 + Excel 自动填充 |
| **pc to excel** | CustomTkinter + pywin32 + openpyxl | `main.py` | PCDMIS 数据提取 + 公差判定 + 报告导出 |

### 1.2 关键发现

- **两个项目均已预留挂载模式**：`CMMFillerGUI.__init__(parent=None)` 和 `MainWindow.__init__(parent=None)` 支持传入父容器，这是为集成预留的设计
- **均使用 CustomTkinter**：主题可统一
- **依赖有重叠**：`customtkinter`, `openpyxl` 两者共用
- **仅 Windows 平台**：兼容性问题少

---

## 二、目录结构

```
pcdmis_toolbox/
├── main.py                         # 统一入口
├── requirements.txt                # 合并后的依赖
├── pyproject.toml                  # 项目元数据
│
├── toolbox/                        # 功能壳核心
│   ├── __init__.py
│   ├── shell.py                    # 壳主窗口：左侧导航 + 内容切换
│   ├── app_meta.py                 # 统一版本/标题/路径
│   └── protocol.py                 # 模块接口协议定义
│
├── modules/                        # 功能模块（独立子包）
│   ├── __init__.py
│   │
│   ├── cmm_filler/                 # 从 CMMFiller 移入
│   │   ├── __init__.py
│   │   ├── gui.py                  # 适配层：实现 ModuleProtocol
│   │   ├── main.py                 # 独立运行入口（保留）
│   │   ├── core/                   # 原 cmm_filler_v10.py 等核心逻辑
│   │   │   ├── __init__.py
│   │   │   └── filler.py
│   │   ├── ocr/                    # OCR 引擎
│   │   │   ├── __init__.py
│   │   │   └── engine.py
│   │   └── templates/              # 模板文件
│   │
│   └── pc_to_excel/                # 从 pc to excel 移入
│       ├── __init__.py
│       ├── gui.py                  # 适配层：实现 ModuleProtocol
│       ├── main.py                 # 独立运行入口（保留）
│       ├── connector/              # PCDMIS COM 连接
│       ├── core/                   # 公差判定/数据提取
│       ├── export/                 # 报告导出
│       └── inject/                 # 命令注入
│
├── utils/                          # 共享工具
│   ├── __init__.py
│   ├── paths.py                    # 统一路径管理
│   ├── logging.py                  # 统一日志配置
│   ├── settings.py                 # 统一配置读写
│   └── theme.py                    # 共享主题常量
│
└── resources/                      # 共享资源
    ├── icons/
    └── styles/
```

---

## 三、核心设计决策

### 3.0 依赖分条件安装策略

两个模块的依赖差异很大，不能用单一 requirements.txt 强制安装所有依赖。

```
requirements/
├── base.txt          # 两模块共用：customtkinter, openpyxl
├── cmm_filler.txt    # CMMFiller 专用（含 PaddleOCR、pymupdf、tkinterdnd2）
└── pc_to_excel.txt   # pc to excel 专用（含 pywin32）
```

| 文件 | 内容 |
|------|------|
| `base.txt` | `customtkinter>=6.0`, `openpyxl>=3.1.5`, `pyinstaller>=6.0` |
| `cmm_filler.txt` | `paddlepaddle==2.6.2; platform_system=="Windows"`, `paddleocr==2.10.0`, `pymupdf==1.28.0`, `tkinterdnd2>=0.4` |
| `pc_to_excel.txt` | `pywin32>=306; platform_system=="Windows"` |

安装方式：
```bash
# 全部功能
pip install -r requirements/base.txt -r requirements/cmm_filler.txt -r requirements/pc_to_excel.txt

# 仅 CMMFiller
pip install -r requirements/base.txt -r requirements/cmm_filler.txt

# 仅 pc to excel
pip install -r requirements/base.txt -r requirements/pc_to_excel.txt
```

**重要**：`paddlepaddle` 必须打包进 exe。**实际打包后 `dist/CMMFiller/` = 628MB**（含 PaddleOCR 模型 18MB + PaddlePaddle ~200MB + cv2/lmdb/lxml ~150MB + 其他依赖）。测量房为无网环境，所有依赖和模型必须在打包时全部包含，不存在运行时下载的条件。

---

### 3.1 模块独立性保留

每个模块必须同时支持：
1. **独立运行**：`python -m modules.cmm_filler`
2. **集成运行**：作为 `Shell` 的子模块被挂载

```python
# modules/cmm_filler/main.py
if __name__ == "__main__":
    from modules.cmm_filler.gui import CMMFillerGUI
    app = CMMFillerGUI(parent=None)  # 独立窗口模式
    app.root.mainloop()
```

### 3.2 tkinterdnd2 挂载模式注意事项

CMMFiller 使用 `tkinterdnd2` 实现文件拖拽。`TkinterDnD._require()` 在两种模式（独立 + 挂载）下都必须调用；`self.root` 在两种模式下都指向 CTk window（挂载时 `parent.winfo_toplevel()`），保证 `.after()` / clipboard 等 API 行为一致。失败时写 WARNING 日志，不中断启动。

```python
try:
    self.root.TkdndVersion = TkinterDnD._require(self.root)
except Exception as e:
    logging.getLogger('CMMFiller').warning(f'TkinterDnD 初始化失败，拖放功能将不可用: {e}')
```

**Shell 层**：不做任何 Tkdnd 初始化。

---

### 3.3 模块接口协议

```python
# toolbox/protocol.py
from typing import Protocol, runtime_checkable
import customtkinter as ctk

@runtime_checkable
class ModuleProtocol(Protocol):
    """所有功能模块必须实现的接口"""
    
    @property
    def title(self) -> str:
        """模块显示名称（用于导航）"""
        ...
    
    @property
    def icon(self) -> str:
        """模块图标（emoji 或资源路径）"""
        ...
    
    @property
    def version(self) -> str:
        """模块版本号"""
        ...
    
    def mount(self, parent: ctk.CTkFrame) -> None:
        """挂载到壳的内容区"""
        ...
    
    def unmount(self) -> None:
        """从壳的内容区卸载"""
        ...
    
    def on_activate(self) -> None:
        """模块被选中时调用（可选）"""
        ...
```

### 3.4 主题统一策略

```python
# utils/theme.py

# 测房友好：青绿主色，避免默认紫系
TOOLBOX_THEME = {
    # 基础色
    "accent": "#0F766E",          # 主强调色
    "accent_hover": "#14B8A6",    # 强调色悬停
    "primary": "#115E59",
    "primary_hover": "#0F766E",
    
    # 状态色
    "ok": "#15803D",              # 通过
    "warn": "#C2410C",            # 警告
    "bad": "#B91C1C",             # 失败/超差
    
    # 界面色
    "muted": "#64748B",
    "card_bg": "#FFFFFF",         # 卡片背景
    "card_border": "#E2E8F0",
    "page_bg": "#F1F5F9",         # 页面背景
    
    # 文字
    "text": "#1E293B",
    "text_muted": "#64748B",
}

# 各模块必须引用这里的常量，避免硬编码颜色
```

**实现细节**：CustomTkinter 对主题 JSON 字段要求严格（所有 key 必须存在），
实际 `_build_theme_json()` 生成完整的 19-key 主题 JSON，基于 `customtkinter/assets/themes/green.json`
字段表，包含 `border_width`、`text_color_disabled` 等 ARCH 初稿未注明的字段。
`TOOLBOX_THEME` dict 保留供其他模块引用颜色常量。
```

### 3.5 路径管理

```python
# utils/paths.py
from pathlib import Path
import sys
import os

class PathManager:
    """统一管理各模块的路径，区分开发/打包/Frozen 模式"""
    
    def __init__(self):
        self._frozen = getattr(sys, "frozen", False)
        if self._frozen:
            self._bundle = Path(sys._MEIPASS)
            self._root = Path(sys.executable).resolve().parent
            # 打包后用户数据放 LocalAppData，避免 Program Files 无写权限
            self._user_data = Path(os.environ.get("LOCALAPPDATA", "")) / "cm2xl"
        else:
            self._bundle = Path(__file__).resolve().parent.parent
            self._root = self._bundle
            self._user_data = self._root / "data"
    
    @property
    def root(self) -> Path:
        return self._root
    
    @property
    def bundle(self) -> Path:
        return self._bundle
    
    @property
    def data_dir(self) -> Path:
        """用户数据目录（可写）：dev 为项目 data/，frozen 为 %LOCALAPPDATA%/cm2xl/"""
        return self._user_data
    
    @property
    def config_dir(self) -> Path:
        """配置文件目录"""
        return self.data_dir / "config"
    
    @property
    def log_dir(self) -> Path:
        """日志目录"""
        return self.data_dir / "logs"
    
    @property
    def cmm_filler_templates(self) -> Path:
        return self._bundle / "modules" / "cmm_filler" / "templates"
    
    @property
    def pc_excel_reports(self) -> Path:
        return self.data_dir / "reports"


# 全局单例
paths = PathManager()
```

### 3.6 日志系统（统一 + 轮转 + GUI Handler）

**完整方案**（初版 + 集成后增强，已合并）：

```python
# utils/logging.py
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

def setup_logging(
    module_name: str,
    log_dir: Optional[Path] = None,
    *,
    level: int = logging.DEBUG,
    max_bytes: int = 5 * 1024 * 1024,   # 5 MB 单文件
    backup_count: int = 3,                # 主日志保留 3 个备份
    audit_backup_count: int = 30,         # 审计日志保留 30 天
    when: str = "midnight",               # 审计日志每天切分
) -> logging.Logger:
    """
    统一日志配置：控制台 + 按大小轮转主日志 + 按天切分审计日志 + GUI Handler。

    日志目录: {data_dir}/logs/
    主日志:   {module_name}.log          (5MB × 3)
    审计日志: {module_name}.audit.log    (每天切 × 30天)
    """
    logger = logging.getLogger(module_name)
    logger.setLevel(level)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        '%(asctime)s [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # 1. 控制台 handler（开发模式可见）
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # 2. 主日志：按 5MB 轮转
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            log_dir / f'{module_name}.log',
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8',
        )
        fh.setLevel(level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        # 3. 审计日志：按天切分（用于审计追踪，详见 3.36）
        ah = TimedRotatingFileHandler(
            log_dir / f'{module_name}.audit.log',
            when=when,
            backupCount=audit_backup_count,
            encoding='utf-8',
        )
        ah.setLevel(level)
        ah.setFormatter(formatter)
        logger.addHandler(ah)

    return logger


class GuiLogHandler(logging.Handler):
    """
    将日志实时推送到 GUI 日志区的 Handler。
    CMMFiller 使用此 Handler 把 OCR/填充过程输出到界面日志面板。

    使用方式（模块内）：
        from utils.logging import GuiLogHandler
        h = GuiLogHandler(gui_instance, root_after_fn)
        h.setLevel(logging.DEBUG)
        logger.addHandler(h)

    其中 root_after_fn 通常是 gui.root.after，
    负责把日志消息派发到 GUI 线程的安全队列。
    """
    def __init__(self, gui_instance, root_after_fn=None, level=logging.DEBUG):
        super().__init__()
        self._gui = gui_instance
        self._root_after = root_after_fn or (lambda delay, fn: fn())
        self.setLevel(level)
        self.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))

    def emit(self, record):
        try:
            msg = self.format(record)
            self._root_after(0, lambda m=msg: self._gui._log(m))
        except Exception:
            self.handleError(record)
```

**日志清理策略**：
- 应用启动时检查 `log_dir` 大小 > 100MB → 删除最旧
- Shell 提供"清理日志"菜单
- Inno Setup 卸载时强制清空

---

### 3.7 ~~BAS 脚本部署路径约束（pc to excel 专用）~~

> 🗑 **已取消**（2026-09-23，commit `76657ac`）。原保留为历史描述。

~~pc to excel 通过 COM 连接 PCDMIS，再注入 BAS 脚本执行数据导出。BAS 脚本必须部署到固定路径供 PCDMIS 调用。~~

```
DEPLOY_DIR = LocalAppData/PCDMIS_ExcelExporter/scripts/
```

**约束**：
- ~~BAS 脚本文件名固定为 `export_current.bas`（由 PCDMIS 菜单项引用）~~
- ~~`DEPLOY_DIR` 路径不能含空格，不能在 `Program Files` 等需要权限的目录~~
- ~~打包后，BAS 脚本通过 PyInstaller `binaries` 注入到 `DEPLOY_DIR`~~
- ~~Shell 无需感知 BAS 脚本，仅 pc_to_excel 模块内部处理~~

**取消原因**：连续三轮真机下来脚本始终报 `执行 BASIC 脚本时出错`，用户判断「脚本输出本身就是为了锦上添花」 ⇒ 整 feature 移除。9 个 commit (`4ef50eb` ~ `fcf8bad`) 保留为历史记录。当前替代：从 cm2xl GUI 用「一键导出 Excel」直接抽数到 xlsx。

---

### 3.8 版本文件统一策略

两个模块目前各自维护版本信息：

| 文件 | 字段 |
|------|------|
| `CMMFiller/version.py` | `__version__`, `APP_NAME`, `APP_TITLE`, `APP_DESCRIPTION` |
| `CMMFiller/cmm_version.json` | 内部构建号 |
| `pc to excel/pcdmis_version.json` | 内部构建号 |

**策略**：迁移后统一到 `toolbox/app_meta.py`，各模块的 `version.py` 改为从 `toolbox.app_meta` 导入：

```python
# modules/cmm_filler/version.py（迁移后）
from toolbox.app_meta import APP_TITLE, APP_VERSION
__version__ = APP_VERSION
APP_NAME = 'CMMFiller'
APP_DESCRIPTION = 'CMM 三坐标测量报告 OCR 识别 + Excel 自动填充'
```

```python
# toolbox/app_meta.py
APP_TITLE = "cm2xl"
APP_VERSION = "1.0.2"
APP_BUILD = "1"  # 内部构建号
# 配置 schema 版本在 utils/settings.py 的 CONFIG_SCHEMA_VERSION = "2.0.0"，与 APP_VERSION 独立
TOOLBOX_THEME = { ... }  # 与 utils/theme.py 保持一致
```

---

### 3.9 配置文件迁移策略

两套系统已有独立配置文件：

| 模块 | 旧路径（独立运行时） | 新路径（集成后） |
|------|---------------------|-----------------|
| CMMFiller settings.json | `{APP_DATA}/CMMFiller/settings.json` | `{config_dir}/cmm_filler/settings.json` |
| CMMFiller template_config.json | `{APP_DATA}/CMMFiller/template_config.json` | `{config_dir}/cmm_filler/template_config.json` |
| pc to excel settings.json | `{ROOT_DIR}/data/settings.json` | `{config_dir}/pc_to_excel/settings.json` |

**迁移步骤**（在 Shell 首次启动时执行）：
1. 检测旧路径是否存在 settings.json
2. 若新路径不存在，将旧文件复制到新路径
3. 若新旧均存在，以新路径为准（旧路径备份为 `.bak`）
4. 迁移完成后删除旧路径文件

```python
# utils/settings.py 辅助函数
def migrate_settings_if_needed(module_name: str, old_path: Path, new_path: Path) -> dict:
    """配置文件迁移，返回最终使用的 settings dict"""
    if new_path.exists():
        return load_json(new_path)
    if old_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(old_path, new_path)
        old_path.rename(old_path.with_suffix('.bak'))  # 备份
        return load_json(new_path)
    return {}
```

---

### 3.9.1 配置版本升级方案（1.x → 2.x 长期演进）

**背景**：除了整合时的 1.x → 2.0 迁移，**后续版本升级**也需要类似机制。否则每次改 schema 都得写一遍迁移代码。

**核心设计**：

1. **每个 settings.json 带 `_version` 字段**

```json
{
  "_version": "2.0.0",
  "_schema": "cmm_filler.settings",
  "_updated_at": "2026-08-26T15:30:00",
  ... 实际字段 ...
}
```

2. **迁移函数注册表**

```python
# utils/settings.py
from typing import Callable

# 配置 schema 版本（与 toolbox/app_meta.APP_VERSION 独立）
CONFIG_SCHEMA_VERSION = "2.0.0"

# 迁移函数签名：old_data → new_data
Migration = Callable[[dict], dict]

# 注册表：module_name -> {from_version: migration_fn}
_MIGRATIONS: dict[str, dict[str, Migration]] = {
    "cmm_filler": {
        "1.0.0": migrate_cmm_filler_1_0_to_2_0,
        "2.0.0": migrate_cmm_filler_2_0_to_2_1,  # 未来
    },
    "pc_to_excel": {
        "1.4.5": migrate_pc_to_excel_1_4_to_2_0,
        "2.0.0": migrate_pc_to_excel_2_0_to_2_1,
    },
}
```

3. **迁移主流程**

> **实现偏差（2026-08-26）**：实际实现不再用 `_next_version` 末段+1 链式步进（缺中间版本会抛 RuntimeError），改为「每个 from_version 的迁移函数一次性升到当前 schema 版本」；无 `_version` 字段的旧文件按模块默认旧版本（cmm_filler 1.0.0 / pc_to_excel 1.4.5）走迁移。详情见 MIGRATION_ARCHIVE.md。

```python
def load_and_migrate_settings(module_name: str, config_path: Path) -> dict:
    """加载 settings.json，必要时执行迁移链"""
    if not config_path.is_file():
        return _default_settings(module_name)

    data = json.loads(config_path.read_text(encoding="utf-8"))
    file_version = data.get("_version", "0.0.0")  # 旧文件没版本字段 → 视为 0

    if file_version == CONFIG_SCHEMA_VERSION:
        return data  # 已是最新版本

    # 升级前先备份
    backup_path = config_path.with_suffix(f".v{file_version}.bak")
    if not backup_path.exists():
        shutil.copy2(config_path, backup_path)
        log.info(f"[settings] 备份 {config_path} → {backup_path}")

    # 沿迁移链一路升级
    migrations = _MIGRATIONS.get(module_name, {})
    current = data
    current_version = file_version

    while current_version != CONFIG_SCHEMA_VERSION:
        if current_version not in migrations:
            raise SettingsMigrationError(
                f"{module_name}: 没有从 v{current_version} 升级的迁移函数"
            )
        migration = migrations[current_version]
        try:
            current = migration(current)
            current["_version"] = _next_version(current_version)
            current["_updated_at"] = datetime.now().isoformat()
            current_version = current["_version"]
            log.info(f"[settings] {module_name} 升级 → v{current_version}")
        except Exception as e:
            # 迁移失败：恢复到备份
            log.error(f"[settings] 迁移失败: {e}，从备份恢复")
            current = json.loads(backup_path.read_text(encoding="utf-8"))
            break

    # 写回文件
    config_path.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return current
```

4. **实际迁移函数示例**

```python
def migrate_cmm_filler_1_0_to_2_0(old: dict) -> dict:
    """CMMFiller 1.0.0 → 2.0.0: 拆 template_config + path 记忆合并"""
    # 旧 settings.json 只有路径记忆
    new = _default_settings("cmm_filler")
    if "template_path" in old:
        new["paths"]["template"] = old["template_path"]
    if "pdf_folder" in old:
        new["paths"]["pdf_folder"] = old["pdf_folder"]
    if "output_folder" in old:
        new["paths"]["output"] = old["output_folder"]
    return new


def migrate_pc_to_excel_1_4_to_2_0(old: dict) -> dict:
    """pc to excel 1.4.5 → 2.0.0: AppSettings → 嵌套 ToolboxSettings"""
    new = _default_settings("pc_to_excel")
    # 顶层字段直接复制
    for key in ("export_dir", "filename_pattern", "export_scope", "require_marked"):
        if key in old:
            new[key] = old[key]
    # tolerance 嵌套结构保持不变
    if "tolerance" in old:
        new["tolerance"] = old["tolerance"]
    # form_fill 嵌套结构保持不变
    if "form_fill" in old:
        new["form_fill"] = old["form_fill"]
    return new


def _default_settings(module_name: str) -> dict:
    """返回模块默认 settings（含 _version 和 _schema 字段）"""
    return {
        "_version": CONFIG_SCHEMA_VERSION,
        "_schema": f"{module_name}.settings",
        "_updated_at": datetime.now().isoformat(),
        # ... 其他默认值 ...
    }
```

5. **错误处理策略**

| 场景 | 处理 |
|------|------|
| 文件不存在 | 返回默认 settings（不写文件）|
| JSON 解析失败 | 备份为 `.corrupt-{时间}.bak`，返回默认 |
| `_version` 字段缺失 | 视为 v0，按最新迁移链逐步升级 |
| 迁移函数抛异常 | 恢复备份，提示用户手动处理 |
| 迁移链中断（找不到中间版本）| 抛出 `SettingsMigrationError`，不修改文件 |
| 升级后字段缺失 | 用默认值补全（from_dict 容错）|

6. **用户感知**

```python
# utils/settings.py 提供用户友好提示
def get_migration_history(config_dir: Path) -> list[dict]:
    """返回所有 .bak 文件清单，供"关于"页面展示"""
    history = []
    for bak in config_dir.rglob("*.bak"):
        stat = bak.stat()
        history.append({
            "path": bak,
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return sorted(history, key=lambda x: x["created"], reverse=True)
```

Shell "设置 → 关于" 页面可以显示迁移历史，让用户知道哪些配置被升级过。

---

### 3.9.2 降级与回退（Downgrade）

**场景**：用户升级到 Toolbox 2.0 后，想回退到旧的 CMMFiller 1.0 单独使用。

**问题**：
- 新代码把 settings 升级到 2.0 schema，旧 CMMFiller 读不懂新格式
- 旧 CMMFiller 找不到 `paths.template` 这种嵌套字段（它期待顶层 `template_path`）

**策略**：

1. **保留旧 settings 备份永不删除**
   - 首次迁移时 `.bak` 备份放到 `{config_dir}/archive/`，不删
   - 测房用户的 settings 价值 > 几 KB 磁盘空间

2. **导出工具**：Shell 提供"导出旧版配置"菜单

```python
def export_legacy_settings(module_name: str, target_path: Path) -> None:
    """把 2.0 配置降级回 1.x 格式，导出给旧工具用"""
    new = load_and_migrate_settings(module_name, _config_path(module_name))
    if module_name == "cmm_filler":
        legacy = {
            "template_path": new["paths"]["template"],
            "pdf_folder": new["paths"]["pdf_folder"],
            "output_folder": new["paths"]["output"],
        }
    elif module_name == "pc_to_excel":
        legacy = {k: v for k, v in new.items() if not k.startswith("_")}
    target_path.write_text(
        json.dumps(legacy, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
```

3. **不做自动降级** — 用户主动导出更安全

---

### 3.10 PyInstaller 打包 spec 合并策略

两个项目各有独立的 spec 文件，打包策略差异较大：

| 项目 | spec 关键特点 |
|------|--------------|
| CMMFiller | 有 `dist/CMMFiller/_internal/`（paddle/cv2/lmdb/lxml 等），大量 hiddenimports |
| pc to excel | `binaries` 注入 BAS 脚本到 `DEPLOY_DIR`，`datas` 包含模板 |

**实际打包大小（已验证）**：CMMFiller 打包后 `dist/CMMFiller/` = **628MB**（含 PaddleOCR 模型 18MB、PaddlePaddle ~200MB、cv2/lmdb/lxml ~150MB）。

**合并方案**：

```python
# build.spec 关键配置
a = Analysis(
    ['main.py'],
    hiddenimports=[
        # CMMFiller（条件导入）
        'paddleocr', 'paddlepaddle', 'pymupdf', 'paddle',
        'tkinterdnd2', 'lmdb', 'cffi',
        'scipy', 'scipy.special', 'scipy.ndimage', 'scipy.io',
        'shapely', 'shapely.geometry', 'pyclipper',
        'rapidfuzz', 'lxml', 'yaml', 'requests', 'tqdm', 'cv2',
        'paddle.base', 'paddle.base.core', 'paddle.inference',
        'ppocr.postprocess.*', 'ppocr.utils.*',
        'tools.infer.*',  # paddleocr 静态分析看不到的依赖
        # pc to excel
        'win32com', 'win32com.client', 'pythoncom', 'pywintypes',
        # shared
        'customtkinter', 'openpyxl',
    ],
    datas=[
        # 模板
        ('modules/cmm_filler/templates', 'templates'),
        ('modules/cmm_filler/models/paddleocr', 'models/paddleocr'),
        # BAS 脚本（部署到 LocalAppData）
        ('modules/pc_to_excel/scripts/export_current.bas', 'scripts'),
        ('modules/pc_to_excel/scripts/export_current.bas.template', 'scripts'),
    ],
    runtime_hooks=['build/rth_paddleocr_fix.py'],  # 见 3.13
)

# 打包说明：
# - 全部依赖打包为一个 exe（含 CMMFiller + pc to excel）
# - 测量房无网环境，整体约 **600-700MB**（CMMFiller 628MB + pc to excel ~80MB），无分离分发需求
# - 若 exe 体积过大，可考虑：exe + data/ 文件夹分离（BAS脚本、模板等静态数据）
#   但 PaddlePaddle 必须和 exe 在同一级目录，不单独分离
```

**关键**：测量房无网环境，paddlepaddle（含 PaddleOCR 模型文件）必须全部打包进 exe 或同目录的 `_internal` 文件夹，打包完成后整个目录可离线使用。

**Phase 6 实际实现（2026-08-27）**：
- spec 文件：`pcdmis_toolbox/pcdmis_toolbox.spec`（统一两个模块的 hiddenimports + datas）
- hooks：`pcdmis_toolbox/build/hooks/`（`hook-customtkinter.py` 普通 hook + `hook-paddleocr_pre.py` 作 runtime hook）。paddleocr 的 4 个 patch 由 `fix_dist.py` 打到 dist 副本，**不要**在 hook 里回写 site-packages
- 后处理：`pcdmis_toolbox/build/fix_dist.py`（从 CMMFiller 搬移并简化）
- build 脚本：`pcdmis_toolbox/build.bat`（含 fix_dist + 清 ffmpeg DLL；清理只删 `build\pcdmis_toolbox`）
- 安装包：`pcdmis_toolbox/installer/cm2xl.iss` + `build_installer.bat`
- BAS 脚本：`pcdmis_toolbox/scripts/`（从 `pc to excel/scripts/` 复制）
- theme.json：`pcdmis_toolbox/utils/theme.json` 打包到 `_internal/utils/`
- 模块 `__init__.py`：全部加进 datas 列表，确保 `pkgutil.iter_modules` 在打包后能识别子包

**打包实测**：总大小 601 MB（清完 ffmpeg 后从 683 MB 降下，节省 82 MB），exe 30 MB。两个模块均能正常加载和切换。

**注意**：
- `dist/CMMFiller/_internal/` 是早期 PyInstaller 缓存，**不要删除**，其内含 cv2/lmdb/lxml 等真实依赖，打包时应以其为准（用 `pyi-makespec --onefile` 生成后检查 collect-submodules）
- BAS 脚本不直接写入 exe 同目录，而是通过 `install_helper.py` 在首次运行时部署到 `DEPLOY_DIR`

---

### 3.11 CMMFiller 打包特殊处理（fix_dist.py）

PyInstaller 对 PaddleOCR 的打包有缺陷（archive 加载、源码 submodules 不全等），CMMFiller 通过一个**后处理脚本**绕过：

**流程**（`build.bat` 完整顺序）：
```bat
python -m PyInstaller build.spec --noconfirm
python fix_dist.py                # 关键：后处理 paddleocr 源码到 _internal/paddleocr/
copy /Y run_as_admin.bat dist\    # 管理员启动器（PCDMIS admin 用）
copy /Y 使用说明.txt dist\        # 用户文档
copy /Y 用户手册.md dist\
```

**`fix_dist.py` 的工作**：
1. 把完整 paddleocr 源码从 `import paddleocr.__file__` 复制到 `_internal/paddleocr/`
2. **不要**复制到 `_internal/tools/`（与外部 `tools` 模块命名冲突）
3. Patch 四个文件：
   - `_patch_paddleocr_source(paddleocr.py)`
   - `_patch_postprocess_init(ppocr/postprocess/__init__.py)`
   - `_patch_imaug_init(ppocr/data/imaug/__init__.py)`
   - `_patch_data_init(ppocr/data/__init__.py)`

**集成后**：上述 `fix_dist.py` 需要保留并适配到 `toolbox/build/` 目录。

---

### 3.12 PaddleOCR 环境变量与 bootstrap

CMMFiller 使用 PaddleOCR 必须设置 `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION`，否则会**触发联网下载模型**（测量房无网会失败）：

```python
# ocr/engine.py — PaddleOCREngine.__init__() 内部局部设置（不影响其他模块）：
os.environ.setdefault('PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION', 'python')
```

`multiprocessing.freeze_support()` 保留在 `core/filler.py` 模块顶层（PyInstaller 多进程必需）。

```python
# ocr_engine.py 初始化时（早于 from paddleocr import PaddleOCR）：
def _resolve_bundled_model_base() -> Path | None:
    """从多个候选路径定位内置模型"""
    candidates = []
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            exe_dir / '_internal' / 'models' / 'paddleocr',
            exe_dir / 'models' / 'paddleocr',
        ])
    else:
        candidates.append(Path(__file__).resolve().parent / 'models' / 'paddleocr')
    for base in candidates:
        if base.exists() and any(base.rglob('inference.pdmodel')):
            return base
    return None

_bundled_models = _resolve_bundled_model_base()
if _bundled_models:
    os.environ['PADDLE_OCR_BASE_DIR'] = str(_bundled_models)
```

**PaddleOCR bootstrap 函数**（`_bootstrap_paddleocr_for_frozen()`）：
PyInstaller 打包后 paddleocr 通过 archive 加载会失败。需要在 import 之前从 `_internal/paddleocr/` 文件系统加载：

```python
def _bootstrap_paddleocr_for_frozen():
    """从 _internal/paddleocr 文件系统加载，绕过 PyInstaller 归档缺陷"""
    if not getattr(sys, 'frozen', False):
        return
    # 详见 ocr_engine.py 实现
    # 关键点：
    #   1. 清空 sys.modules 中已缓存的 paddleocr.* 模块
    #   2. 用 importlib.util.spec_from_file_location 注册 paddleocr/tools/ppocr/ppstructure
    #   3. 把 _internal/paddleocr 加入 sys.path[0]
```

**集成后约束**：
- `main.py` 启动前必须调用 `multiprocessing.freeze_support()`（全局副作用，必须最早）
- `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION` 由 `ocr/engine.py` 的 `PaddleOCREngine.__init__()` 局部设置（`setdefault`），各模块不再需要全局设置

---

### 3.13 PyInstaller 自定义 Hook（CMMFiller 现有）

CMMFiller 现有一套自定义 PyInstaller hook，集成后必须保留：

| 文件 | 类型 | 作用 |
|------|------|------|
| `build/hooks/hook-customtkinter.py` | 普通 hook | customtkinter 的 assets 资源打包 |
| `build/hooks/hook-paddleocr_pre.py` | runtime hook（spec `runtime_hooks`） | frozen 下 `PADDLE_OCR_BASE_DIR` + `tools` 路径 |

paddleocr 源码 4 个 patch 由 `build/fix_dist.py` 打到 `dist/` 副本。**禁止**分析阶段 hook 回写 site-packages 的 `paddleocr.py`。

集成后路径：`pcdmis_toolbox/build/hooks/`（不是 `toolbox/build/hooks/`）。

---

### 3.14 管理员权限启动器（run_as_admin.bat）

PCDMIS 2022+ 启动后必须与本工具**权限级别一致**才能通过 COM 连接：
- 若 PCDMIS 是**管理员**启动，本工具也必须 admin
- 若 PCDMIS 是**普通用户**，本工具也必须普通用户
- 权限不一致 → COM 附着失败，提示 `0x80070005` 类错误

**现有方案**（`pc to excel/run_as_admin.bat`）：
```bat
@echo off
chcp 65001 >nul
set "EXE=%~dp0PCDMIS按需Excel报告.exe"
set "ROOT=%~dp0"

if exist "%EXE%" (
    powershell -NoProfile -Command "Start-Process -FilePath '%EXE%' -WorkingDirectory '%ROOT%' -Verb RunAs"
    exit /b 0
)
echo 未找到 exe，改用源码: python main.py
cd /d "%~dp0"
python main.py
```

**集成后**：整个 Toolbox 共用一个 `run_as_admin.bat`（分发到 dist 根目录）。admin 启动 = 整个 Shell 是 admin 权限运行。CMMFiller 在 admin 模式下也能正常工作（仅读写本地文件）。

---

### 3.15 Python 位数限制（PCDMIS 要求）

PC-DMIS 2022+ 是 **64 位应用**，COM 客户端也必须是 64 位：

```python
# pc to excel/connector/com_detector.py
def python_bitness() -> int:
    return struct.calcsize("P") * 8

# 在 _format_connect_error() 中检查：
if python_bitness() != 64:
    hints.append(f"当前 Python 为 {python_bitness()} 位，PC-DMIS 2022+（64-bit）需 64 位 Python。")
```

**集成后约束**：
- 打包必须用 64 位 Python（`--target-arch=64bit`）
- `pyproject.toml` / `requirements.txt` 不强制，但应在 README 提示
- 启动时 `main.py` 可加 32 位检测并硬阻断

---

### 3.16 COM Apartment 线程初始化

`pc to excel/connector/com_detector.py` 定义了 `com_apartment()` 上下文管理器：

```python
@contextmanager
def com_apartment():
    """后台线程调用 COM 前必须初始化 apartment（否则 CO_E_NOTINITIALIZED）。"""
    import pythoncom
    pythoncom.CoInitialize()
    try:
        yield
    finally:
        pythoncom.CoUninitialize()
```

**使用方式**：
```python
def extract_features(self):
    with com_apartment():
        app = self._bind_app()
        return app.ActivePartProgram
```

**集成后约束**：
- Shell 不需要初始化 apartment（主线程自动有 STA）
- 各模块调 COM 的工作线程**必须**用 `with com_apartment()` 包裹
- 这个约束写在 `protocol.py` 模块接口注释里，提醒模块作者

**COM 串行化（1.0.12）**：PC-DMIS COM 是 STA。后台抽数与主线程 `session_alive()` / `GetActiveObject` 同时进行会互锁，界面假死；工作线程里 `root.after` 刷进度还会触发 `main thread is not in main loop`，旧逻辑误当成 COM 失效去 `EnsureDispatch`（重建 gencache），第二次导出可卡住数十秒。

- 全进程 `com_call_lock`（`RLock`）串行化 COM
- PC-DMIS **已在运行**时只用 `GetActiveObject` / `Dispatch`，**禁止 `EnsureDispatch`**
- `extract_features` 持锁抽数；`session_alive` / `get_active_part_name` 非阻塞拿锁失败则跳过或返回缓存
- GUI 导出/填入在工作线程 `ensure_session`，抽数期间 `progress_cb=None`；状态轮询在 `_busy` 时跳过
- `_is_com_session_error` 只认 RPC/COM 断开，不认 Tk `RuntimeError`

---

### 3.17 模板向导（template_wizard.py）

`CMMFiller/template_wizard.py` 是独立的 tkinter 工具（注意是 tkinter，不是 customtkinter），用于配置新模板的列映射：

```python
# CMMFiller/cmm_filler_gui.py:1188
from template_wizard import TemplateWizard
TemplateWizard(self.root.winfo_toplevel()).run()
```

**集成后归属**：作为 CMMFiller 模块内的子工具，挂在"模板设置"按钮上弹出。保持低耦合。

---

### 3.18 用户文档分发

CMMFiller 现有 `使用说明.txt`、pc to excel 现有 `使用说明.txt` 和 `用户手册.md`，打包时通过 `build.bat` 复制到 `dist/`。

**集成后**：合并文档到 `toolbox/docs/`：
```
toolbox/
└── docs/
    ├── README.md          # Toolbox 总览
    ├── cmm_filler.md      # CMMFiller 模块说明
    └── pc_to_excel.md     # pc to excel 模块说明
```

打包脚本 copy 到 dist/ 同名位置。

---

### 3.19 PCDMIS 状态主动轮询机制

`modules/pc_to_excel/connector/pcdmis_connector.py` 的 `session_alive()` 用于检测 COM 会话是否仍然可用。

**集成后状态更新机制**：
- 模块激活时（`on_activate`）调用 `connector.session_alive()` → 更新状态栏
- 模块运行时用 `root.after(30000)` 轮询（不是独立线程抢 COM），发现失效立即通知 Shell
- **导出/填入进行中（`_busy`）跳过本轮探测**，避免与抽数互锁
- `session_alive` 拿不到 `com_call_lock` 时视为仍存活（不抢抽数）
- 断开连接时模块主动调 `shell.update_pcdmis_status(False)`

```python
# modules/pc_to_excel/gui/main_window.py
def _start_status_watcher(self) -> None:
    self._status_watcher_running = True
    self._schedule_status_watch()  # root.after(30000, ...)

def _status_watcher_tick(self) -> None:
    if self._busy:
        return  # 抽数中不探测
    if self.connector.is_connected() and not self.connector.session_alive():
        self.connector.disconnect()
```

---

### 3.20 multiprocessing.freeze_support()

`cmm_filler_v10.py:16` 在文件顶层调用 `multiprocessing.freeze_support()`，这是 PyInstaller 打包后使用多进程的必需调用。

**集成后约束**：
- `main.py` 启动入口**最早处**必须保留此调用（在所有 import 之前）
- 在开发模式下是 no-op，不影响

```python
# main.py
import multiprocessing
multiprocessing.freeze_support()  # 必须在最前

# 此后才 import customtkinter / paddleocr 等
import customtkinter as ctk
```

---

### 3.21 初始默认配置 vs 用户配置

pc to excel 的 `build.spec` 把 `data/settings.json` 复制到 `dist/data/settings.json`：
```python
datas=[
    (str(ROOT / "data" / "settings.json"), "data"),
    ...
]
```

**注意**：这里的 `data/settings.json` 是**初始默认值**（开发者提供的默认配置），不是用户的当前配置。**用户配置**应该在 `%APPDATA%/PCDMIS_ExcelExporter/settings.json` 或集成后的 `{config_dir}/pc_to_excel/settings.json`。

**集成后**：
- `toolbox/data/defaults/settings.json` → 打包时作为默认配置（首次启动时复制到用户配置目录）
- `{config_dir}/pc_to_excel/settings.json` → 用户实际配置

---

### 3.22 测试套件组织

现有测试分布：

| 模块 | 测试文件 |
|------|---------|
| CMMFiller | `test_summary_export.py`（核心层 + GUI 冒烟）|
| pc to excel | `tests/test_dimension_pairing.py`、`test_gdt_extraction.py`、`test_inspection_form_fill.py`、`test_pcdmis_style_report.py`、`test_tolerance.py` |

**集成后策略**：每个模块自管测试 `modules/<name>/tests/`。运行方式：`python -m pytest modules/cmm_filler/tests/`。

---

### 3.23 可扩展点（未来新模块/新引擎的接入位置）

| 扩展点 | 现有抽象 | 添加位置 | 示例 |
|--------|----------|----------|------|
| 新测量软件连接器 | `connector/base.py:MeasurementConnector` | `modules/pc_to_excel/connector/` 或新模块 | Calypso / PolyWorks / 三坐标其他品牌 |
| 新 OCR 引擎 | `ocr_engine.py:OCREngine` | `modules/cmm_filler/ocr/` | PaddleOCR 已稳定，但保留切换能力 |
| 新报告格式导出 | `export/*.py` 各 dataclass | `modules/<name>/export/` | Word / PDF 报告 |
| 新 GDT 符号 | `connector/pcdlrn_constants.py` `_FallbackConstants` | 扩展 enum | 圆度/平面度/圆柱度等 |
| 新记录分类 | `core/classification.py:RecordCategory` | `modules/<name>/core/` | 自定义业务分类 |

**集成后约束**：所有扩展点必须放在 `modules/<name>/` 内部，不得直接改 `toolbox/` 或 `utils/` 共享层。

---

### 3.24 关键数据模型（不可轻易改动）

| 模型 | 文件 | 字段数 | 用途 |
|------|------|--------|------|
| `FeatureRecord` | `pc to excel/core/models.py:143` | 19 个字段 | 单条测量记录（特征/尺寸/形位） |
| `AxisValues` | `pc to excel/core/models.py:32` | 11 个轴 | 名义/实测/偏差（x/y/z/d/length/...） |
| `PassStatus` | `pc to excel/core/models.py:10` | 3 个枚举 | PASS/FAIL/NA 公差判定 |
| `ToleranceConfig` | `pc to excel/core/models.py:97` | 6 个公差限 | 6 个轴向的上下限 |
| `FormFillConfig` | `pc to excel/export/inspection_form_fill.py:25` | 18 个字段 | 出货表填入配置 |
| `ReportHeaderInfo` | `pc to excel/core/models.py:86` | 5 个字段 | 报告页眉 |
| `CMMReportFiller` | `CMMFiller/cmm_filler_v10.py:213` | 核心类 | CMM 报告 OCR 填充逻辑 |

**集成后约束**：这些 dataclass 是模块对外契约，重构时**保持字段名和 to_dict/from_dict 接口不变**，否则 settings 迁移会失败。

---

### 3.25 ~~注入命令的 PCDMIS 命令 ID 常量~~

> 🗑 **已取消**（2026-09-23，commit `76657ac`）。原保留为历史描述。

~~`pc to excel/config.py:EXPORT_CMD_ID = "PC2XL_EXPORT"` 是 PCDMIS BASIC SCRIPT 命令的固定 ID，植入后命令在 PRG 内的显示名为 `PC2XL_EXPORT`。~~

~~`OBTYPE_BASIC_SCRIPT` 来自 `pcdlrn_constants.get_const("OBTYPE_BASIC_SCRIPT")`，用于 `cmds.Add(OBTYPE_BASIC_SCRIPT, True)` 插入 BASIC SCRIPT 命令类型。~~

~~**集成后约束**：常量统一从 `toolbox/app_meta.py` 引用，避免硬编码分散在多处。~~

**取消说明**：`EXPORT_CMD_ID` 已从 `toolbox/app_meta.py` + `modules/pc_to_excel/app_meta.py` + `toolbox/__init__.py` 的 re-export 中移除；`OBTYPE_BASIC_SCRIPT` 一并移除。原因见 §3.7。

---

### 3.26 threading 模式

两个 GUI 都用相同的模式：工作线程跑业务逻辑，通过 `root.after(0, lambda: ...)` 把 UI 更新派发回主线程：

```python
def work():
    try:
        result = self.connector.do_something()
        self.root.after(0, lambda: self._on_done(result))
    except Exception as exc:
        self.root.after(0, lambda: self._on_error(...))

threading.Thread(target=work, daemon=True).start()
```

**集成后约束**：所有模块的耗时操作（OCR、COM 调用、文件读写）必须走这个模式，禁止在主线程同步阻塞。

---

### 3.27 tkinter vs customtkinter 混用

CMMFiller 模块内嵌的 `template_wizard.py` 用了**原生 tkinter**（`import tkinter as tk`），不是 customtkinter：

```python
# CMMFiller/template_wizard.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
```

集成后通过 Toplevel 弹出时主题不一致（青绿色 vs 系统默认）。**集成后约束**：作为 CMMFiller 内部子工具接受视觉差异；若要统一需重写为 customtkinter（工作量较大）。

---

### 3.28 Inno Setup 安装包（CMMFiller 现有）

CMMFiller 已有一个完整的 Inno Setup 安装包脚本 `CMMFiller/installer/CMMFiller.iss` + `build_installer.bat`，生产环境真正分发的是安装包，不是单文件 exe：

**安装包特性**：
- AppId：`{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}`
- `PrivilegesRequired=admin`（安装时需要 admin）
- `ArchitecturesInstallIn64BitMode=x64compatible`（**只支持 64 位**）
- `Compression=lzma2/ultra64`（最高压缩）
- 默认安装路径：`{autopf}\CMMFiller`（即 `C:\Program Files\CMMFiller`）
- 输出：`installer\output\CMMFiller_Setup_2.0.0.exe`

**安装时操作**：
- 复制 `dist\CMMFiller\*` 到 `{app}`
- 复制 `docs\CMMFiller_安装与使用说明.pdf` 到 `{app}\docs`
- 创建开始菜单快捷方式（CMMFiller / 使用说明 / 卸载）
- 可选创建桌面图标（默认勾选）
- 安装完成提示"启动 CMMFiller"

**卸载时清理**：
- `[UninstallDelete]` 删除 `%localappdata%\CMMFiller\cache`

**集成后策略**（实际文件，2026-08-27）：
- 脚本：`pcdmis_toolbox/installer/cm2xl.iss`
- AppId：`{A1B2C3D4-E5F6-7890-ABCD-EF1234567891}`（与旧版 CMMFiller `{...7890}` 区分）
- AppName = "cm2xl"
- AppVersion = "1.0.2"
- 复制 `dist\cm2xl\*` 到 `{app}`
- **`PrivilegesRequired=admin`**
- Inno Setup 6 默认无 `ChineseSimplified.isl`，语言包用 `compiler:Default.isl`；自定义 Tasks/MsgBox 仍为中文

---

### 3.29 CLI 命令行入口（pc to excel 现有）

`pc to excel/cli.py` 是一个 **argparse 命令行入口**，提供批量操作能力（与 GUI 并存）。命令大致：

```python
# pc to excel/cli.py
import argparse
# 子命令：export / fill-form / dump-tols
# （原 inject 子命令已于 2026-09-23 随脚本输出功能取消，commit 76657ac）

def cmd_export(args): ...
def cmd_fill_form(args): ...
def cmd_dump_tols(args): ...
```

**集成后策略**：
- 选项 A：保留 `modules/pc_to_excel/cli.py` 作为 **Shell 集成下的批处理入口**（用户可 `python -m modules.pc_to_excel.cli export`）
- 选项 B：删除 CLI，只保留 GUI
- 选项 C：写一个 `toolbox/cli.py` 统一两个模块的命令行

**建议**：选项 A，保留 CLI。CLI 在测房环境下可能有用（脚本化、无人值守）。

---

### 3.30 三种运行模式并存

整合后工具箱有 **三种运行方式**：

| 模式 | 入口命令 | 用途 |
|------|---------|------|
| **Shell 集成模式**（新） | `python main.py` 或 Toolbox.exe | 默认模式，左侧导航切换模块 |
| **模块独立 GUI 模式** | `python -m modules.cmm_filler` 或 `python -m modules.pc_to_excel` | 绕过 Shell 单独启动某个模块 |
| **模块 CLI 模式**（仅 pc_to_excel） | `python -m modules.pc_to_excel.cli export ...` | 批量/无人值守 |

**互斥约束**：
- 同一时刻一个进程只能挂载一个模块
- 但可同时跑两个进程（CMMFiller 一个 + pc_to_excel 一个），互不干扰（不同的 GUI 窗口）
- CLI 模式与 GUI 模式可在不同进程同时跑

---

### 3.31 项目指令文件（CLAUDE.md / AGENTS.md）

`CMMFiller/CLAUDE.md` 是一个 Claude 指令文件（类似 ZCode 的 AGENTS.md），包含：
- 项目简介和目录结构
- 当前配置（sheet_name、列映射、样品列）
- 关键约束（OCR 模型内置、完全离线）

**集成后策略**：
- 在 `pcdmis_toolbox/` 根写一个 `CLAUDE.md`（或 `AGENTS.md`），内容覆盖：
  - Toolbox 总览
  - 两个模块的入口
  - 关键约束（paddlepaddle 必打包、64 位、admin 启动等）
  - 常见任务指引（加新模块、修 bug、打包）

---

### 3.32 LICENSE 与 CI/CD

**现状**：
- 两个项目都**没有 LICENSE 文件**
- 没有 CI/CD 配置（`.github/workflows/`、`.gitlab-ci.yml`、`.circleci/` 等）

**集成后约束**：
- **LICENSE**：建议加 MIT 或 Apache-2.0，但需要用户确认
- **CI/CD**：可选。最低限度可以加：
  - `.github/workflows/test.yml`：跑 `pytest modules/*/tests/`
  - `.github/workflows/build.yml`：跑 `build.bat` 生成 exe
  - 但需要 Windows runner（GitHub Actions 付费 or 自托管）

**建议**：
- Phase 0 暂不处理 LICENSE / CI/CD
- Phase 8 测试时再补 GitHub Actions 配置（用 `windows-latest` runner）

---

### 3.33 测试样本与文档生成

**CMMFiller 有 50 个测试 PDF** 在 `samples/` 目录（`0624-001 ~ 0709-002`）。

**集成后策略**：
- `samples/` 跟着 CMMFiller 模块走：`modules/cmm_filler/samples/`
- 测试用：`modules/cmm_filler/tests/test_summary_export.py` 已经有 samples 引用
- **注意**：`samples/` 体积较大（50 个 PDF），不应进 git，应加 `.gitignore`

**用户文档生成**（CMMFiller 已有 `docs/generate_user_guide.py`）：
- 自动生成 `CMMFiller_安装与使用说明.pdf`
- 集成后整合到 `toolbox/docs/`：
  ```
  toolbox/docs/
  ├── README.md              # Toolbox 总览
  ├── cmm_filler.md
  ├── pc_to_excel.md
  └── COM_命令读取原理.md     # PCDMIS 已有
  ```

---

### 3.34 subprocess 调用安全模式

`pc to excel/connector/com_detector.py` 调用 `reg` 和 `tasklist` 时都做了安全处理：

```python
result = subprocess.run(
    ["reg", *args],
    capture_output=True,
    text=True,
    timeout=timeout,                    # 限时（10-60 秒）
    creationflags=subprocess.CREATE_NO_WINDOW,  # 不弹黑窗
)
```

**集成后约束**：所有 subprocess 调用必须遵循此模式：
1. 用列表形式（不 shell=True）
2. 设置 `timeout`
3. 设置 `CREATE_NO_WINDOW`
4. 捕获异常（`subprocess.TimeoutExpired`、`FileNotFoundError`、`OSError`）

---

### 3.35 错误码体系（**集成后新增**）

**现状（两项目都没有真正的错误码）**：

- 使用 Python 内置异常（`RuntimeError`、`FileNotFoundError`、`ValueError` 等）
- 错误信息是**自然语言字符串**（中文），可读但不便程序化处理
- pc to excel 有 `utils/action_hints.py` 的"伪错误码"系统（基于 8 组关键字匹配）

**集成后策略**：引入真正的错误码系统：

```python
# utils/error_codes.py
class ErrorCode:
    UNKNOWN = "E0000"
    ELEVATION_MISMATCH = "E1001"
    PYTHON_BITNESS_WRONG = "E1002"
    MODEL_MISSING = "E1003"
    PCDMIS_NOT_RUNNING = "E2001"
    PCDMIS_CONNECT_FAIL = "E2002"
    PCDMIS_PART_NOT_OPEN = "E2003"
    PCDMIS_NO_DATA = "E2004"
    PCDMIS_SAVE_FAIL = "E2005"
    PDF_NOT_FOUND = "E3001"
    TEMPLATE_INVALID = "E3002"
    OCR_FAIL = "E3003"
    OUTPUT_DIR_INVALID = "E4001"
    OUTPUT_FILE_LOCKED = "E4002"
    BAS_NOT_DEPLOYED = "E5001"
    INJECT_FAIL = "E5002"

class ToolboxError(Exception):
    def __init__(self, code: ErrorCode, message: str, *, hint: str = ""):
        self.code = code
        self.message = message
        self.hint = hint
        super().__init__(f"[{code}] {message}")
```

**集成后约束**：
1. 所有抛出的业务异常必须用 `ToolboxError(code, message)`，不用裸 `RuntimeError`
2. `format_user_error()` 改为接收 `ToolboxError`，先按 code 查表，再 fall back 到关键字匹配
3. 日志记录 error code + 完整堆栈
4. 测房无网环境不允许在线查询 → 必须本地有完整提示表

---

### 3.36 审计日志（**完全缺失**）

> **注意**：3.36 原计划讲日志系统，但内容已并入 3.6（统一 + 轮转 + GUI Handler）。本节现在讲审计日志系统（之前误编为 3.37）。

**现状**：所有用户操作只有 messagebox 弹窗，关窗即丢失，无持久记录。

**集成后策略**：新增 `utils/audit.py`：

```python
import logging
from datetime import datetime

AUDIT_LOG_NAME = "toolbox.audit"

def audit(action: str, **fields) -> None:
    """记录一次用户操作。"""
    logger = logging.getLogger(AUDIT_LOG_NAME)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    field_str = ' '.join(f'{k}={v!r}' for k, v in fields.items())
    logger.info(f"[{timestamp}] {action} | {field_str}")

# 使用示例：
# audit("export_excel", count=123, path="/path/to.xlsx", duration_s=2.3)
# audit("pcdmis_connect", prog_id="PCDLRN.Application.19.1", version="2024.1")
```

**记录范围**：启动/切换模块/连接PCDMIS/导出/填入/植入/BAS/CMMFiller处理/全局异常。

**约束**：所有用户可见操作必须调 `audit()`；格式固定 `[时间] action | k=v`；与普通日志分离（通过 `setup_logging` 第三个 handler）。

---

### 3.38 CMMFiller OCR 缓存清理（升级版）

**现状 bug**：`_cleanup_cache()` 只清 PNG，**没清 `ocr_cache.json` 本体**：

```python
# cmm_filler_v10.py:482
def _cleanup_cache(self, max_age_days=30):
    """清理超过指定天数的缓存图片"""
    cutoff = time.time() - max_age_days * 86400
    for f in CACHE_DIR.glob('*.png'):    # ← 只清 PNG
        if f.stat().st_mtime < cutoff:
            f.unlink()
    # ← ocr_cache.json 永久累积，没清理
```

**集成后**：补全清理策略：
- PNG：按时间（30 天）
- ocr_cache.json：按数量（> 10000 条则按 key 字母序删旧）
- 启动时清理 + GUI"清理 OCR 缓存"菜单

---

### 3.39 PDF 文件扫描大小写敏感（潜在 Bug）

**现状**：
```python
# cmm_filler_v10.py:670
pdfs = sorted(Path(pdf_folder).glob('*.PDF'))   # ← 只匹配大写！
```

**问题**：用户若有 `001.pdf`（小写）会被静默漏掉。

**集成后修复**：改大小写不敏感：
```python
pdfs = sorted(
    f for f in Path(pdf_folder).iterdir()
    if f.is_file() and f.suffix.lower() == '.pdf'
)
```

---

### 3.40 配置文件原子写（防止损坏）

**现状 bug**：`json.dump` 直接写，异常中断留下半截文件。

**集成后策略**：用临时文件 + `os.replace` 实现原子写：

```python
def save_settings_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + '.tmp')
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)  # rename 是原子的
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
```

---

### 3.41 文件锁与多进程防护

**现状**：双击 Toolbox 两次会同时读写 settings.json，可能损坏。

**集成后策略**：`utils/settings.py`（FileLock 类）：

```python
class FileLock:
    """基于 O_EXCL 的简单文件锁（Windows + Linux 通用）"""
    def __init__(self, lock_path, timeout=5.0, retry_interval=0.1): ...
    def __enter__(self): ...  # 超时检查 + 死 PID 清理
    def __exit__(self, *args): ...  # 释放
```

**Shell 启动时检测**：
- 锁超过 5s → 弹窗"已有 Toolbox 在运行，是否启动第二个？"
- 用户选择"是" → 跳过 FileLock（仍共用 settings）

---

### 3.42 线程取消与资源清理

**现状问题**：`daemon=True` 启动线程，无 cancel 机制，关窗时正在处理的任务丢失。

**集成后策略**：引入 `CancellableWorker`：

```python
class CancellableWorker:
    def __init__(self):
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, target, *args, **kwargs):
        self._cancel_event.clear()
        self._thread = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
        self._thread.start()

    def request_cancel(self): self._cancel_event.set()
    def is_cancelled(self) -> bool: return self._cancel_event.is_set()
    def wait(self, timeout=5.0) -> bool:
        if self._thread:
            self._thread.join(timeout=timeout)
            return not self._thread.is_alive()
        return True
```

**业务线程检查取消点**：
```python
def _run_export(self, ...):
    for i, pdf in enumerate(pdfs):
        if self._worker.is_cancelled():
            logger.info('用户已取消')
            return
        self._process_pdf(pdf)
```

**Shell on_close 流程**：
1. 提示用户确认（有进行中的任务）
2. request_cancel + wait(10s)
3. disconnect PCDMIS
4. root.destroy()

**atexit 注册**：
```python
def cleanup_on_exit():
    for tmp_pdf in paths.cache_dir.glob('*.tmp.pdf'):
        tmp_pdf.unlink(missing_ok=True)
    logging.shutdown()
atexit.register(cleanup_on_exit)
```

---

### 3.43 PDF 文件句柄泄漏

**现状 bug**：
```python
# cmm_filler_v10.py:554
doc = fitz.open(pdf_path)   # ← 没 with，没 doc.close()
# 中间抛异常时 doc 句柄不释放
```

**集成后修复**：用 context manager：
```python
def _extract_text(self, pdf_path: str) -> str:
    with fitz.open(pdf_path) as doc:
        text = ""
        for page in doc:
            text += page.get_text()
        return text
```

---

### 3.44 资源管理补充清单

| 资源 | 现有处理 | 集成后处理 |
|------|---------|----------|
| PDF 文件（fitz） | 无 close | `with fitz.open(...) as doc:` |
| PCDMIS COM 连接 | `connector.disconnect()` | + `pythoncom.CoUninitialize()` in finally |
| 临时 PDF 渲染 | `cache/*.png`（30 天清理）| + atexit 兜底 |
| OCR JSON 缓存 | 只清 PNG | + 按数量清（见 3.38） |
| 线程 | `daemon=True` 无 join | + `CancellableWorker` 模式（见 3.42） |
| 日志文件 | `FileHandler` 无限追加 | + `RotatingFileHandler`（见 3.36） |
| settings.json | 直接 `json.dump` | + `save_settings_json_atomic`（见 3.40） |
| 进程间冲突 | 无锁 | + `FileLock`（见 3.41） |
| 进程退出 | 无 atexit | + `atexit.register(cleanup_on_exit)` |

---

### 3.45 CustomTkinter 主题冲突（严重）

**现状 bug**：

```python
# CMMFiller/cmm_filler_gui.py:25-26
ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")    # ← 蓝

# pc to excel/gui/main_window.py:35-36
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("green")   # ← 绿
```

**问题**：
- 两模块都在**模块导入时**调用全局 `ctk.set_default_color_theme(...)`
- 在 Shell 集成模式下，先后加载哪个模块，主题就被改成哪个
- 用户切到另一个模块会看到颜色突变

**集成后约束**：
1. **Shell 层统一调用一次主题设置**（`main.py` 启动时）
2. **删除各模块的 `ctk.set_default_color_theme()` 调用**（保留 `ctk.set_appearance_mode()` 作为模块默认）
3. 写入文档：`utils/theme.py` 是**唯一**的主题定义点

```python
# main.py 启动最早处（before all imports）
import customtkinter as ctk
ctk.set_appearance_mode("system")
ctk.set_default_color_theme("green")  # 与 pc to excel 一致，避免颜色跳变
```

**替代方案**：写自定义主题 JSON（`utils/theme.json`）作为 `set_default_color_theme(custom_json_path)`，完全摆脱 blue/green 二选一：

```python
# utils/theme.py
TOOLBOX_THEME_PATH = Path(__file__).parent / "theme.json"

# theme.json
{
  "CTk": {
    "fg_color": ["#F1F5F9", "#0F172A"],
    "button_color": ["#0F766E", "#14B8A6"],
    ...
  }
}
```

---

### 3.46 相对 vs 绝对导入冲突

**现状**：

```python
# pc to excel/connector/pcdmis_connector.py:1-9
from connector.base import ConnectionInfo, MeasurementConnector   # ← 绝对
from connector.com_detector import (...)
from core.models import FeatureRecord

# 每个文件顶部都有 sys.path.insert(0, _ROOT) 强制把根目录加进 path
# pc to excel/utils/settings.py:
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
```

**问题**：
- 集成到 `pcdmis_toolbox/modules/pc_to_excel/` 后，绝对导入全部失效
- `from connector.base import ...` 找不到（应该是 `from .connector.base import ...` 或 `from modules.pc_to_excel.connector.base`）

**集成后约束**：批量改导入为相对路径：

> **实现偏差（2026-08-26）**：指向 toolbox 共享层的导入统一用 0 连点（`from utils.paths import paths`，要求 pcdmis_toolbox 在 sys.path 上，与 `main.py`/`cmm_filler` 一致），未采用 4 连点（`....utils.*`）——两者在任意单一运行方式下互斥。详情见 MIGRATION_ARCHIVE.md。

```python
# modules/pc_to_excel/connector/pcdmis_connector.py（迁移后）
from .base import ConnectionInfo, MeasurementConnector
from .com_detector import (...)
from ..core.models import FeatureRecord
```

**注意**：
- CMMFiller 内部导入 `from cmm_filler_v10 import ...`、`from template_wizard import ...` 也是绝对路径，同样要改
- 改完用 `python -m modules.cmm_filler` 验证相对导入能解析
- 删除所有 `sys.path.insert(0, _ROOT)` 副作用代码

---

### 3.47 启动参数入口分散

**现状**：

```python
# CMMFiller/cmm_filler_v10.py:1206-1209
parser.add_argument('--gui', action='store_true')
parser.add_argument('--wizard', action='store_true')
parser.add_argument('--export-template', action='store_true')
parser.add_argument('--version', action='version', version=f'CMMFiller {__version__}')

# pc to excel/cli.py:43+
def cmd_export(args): ...
def cmd_inject(args): ...   # ← 2026-09-23 取消（脚本输出功能整 feature 移除，commit 76657ac）

# CMMFiller/main.py (迁移后) — 顶层 GUI
# pc to excel/main.py (迁移后) — 顶层 GUI
# toolbox/main.py — Shell
```

**集成后约束**：入口策略：

| 入口 | 命令 | 模式 |
|------|------|------|
| Toolbox Shell | `python main.py` 或双击 `cm2xl.exe` | 集成 |
| 模块独立 GUI | `python -m modules.cmm_filler` | 独立 |
| 模块 CLI | `python -m modules.pc_to_excel.cli export ...` | 独立批处理 |
| 模板向导 | `python -m modules.cmm_filler.wizard` | 独立子工具 |

**禁止**：把 CLI 参数塞到模块 `main.py` 里（避免冲突），统一放 `cli.py`。
**禁止**：`--gui` / `--wizard` 这种 flag 在 `modules/<name>/main.py` 里用，统一由子命令入口处理。

---

### 3.48 PaddleOCR 4 个文件 patch 完整性

**fix_dist.py 必须打的 4 个 patch**（迁移后保留）：

| Patch | 文件 | 作用 |
|-------|------|------|
| `_patch_paddleocr_source` | `_internal/paddleocr/paddleocr.py` | 修改主入口 |
| `_patch_postprocess_init` | `_internal/paddleocr/ppocr/postprocess/__init__.py` | 跳过 skimage/scipy 可选导入 |
| `_patch_imaug_init` | `_internal/paddleocr/ppocr/data/imaug/__init__.py` | 跳过训练增强 |
| `_patch_data_init` | `_internal/paddleocr/ppocr/data/__init__.py` | 跳过数据集 |

**集成后约束**：
1. `build/fix_dist.py` 必须保留
2. 每次 PyInstaller 重新打包后**必须**跑 fix_dist.py
3. 在 `build.bat` 里强制串联：`pyinstaller → fix_dist → copy docs`
4. 用 checksum 验证 patch 已打过（避免重复 patch 引入问题）：

```python
# fix_dist.py 开头加检查
PATCH_MARKER = "# TOOLBOX_PATCHED_v2"
for patch_file in (_patch_paddleocr_source, _patch_postprocess_init, ...):
    if PATCH_MARKER in patch_file.read_text(encoding='utf-8'):
        print(f'  {patch_file.name} 已打过 patch，跳过')
        continue
    patch_file()
    patch_file.write_text(PATCH_MARKER + '\n' + patch_file.read_text(encoding='utf-8'), encoding='utf-8')
```

---

### 3.49 PCDMIS 报告列格式对照（PC-DMIS 内置 Excel）

**PC-DMIS 内置 Excel 报告 10 列**（`pcdmis_style_report.py:_HEADER`）：

| 列 | 含义 | 来源 |
|----|------|------|
| 尺寸 | 命令 ID | `rec.name`（如 FAI_10） |
| 描述 | 类型 + 特征 | `feature_type (feat1, feat2)` |
| 轴 | 字母 | `write_axis`（X/Y/Z/D/L/W/H/A/MD） |
| NOMINAL | 名义值 | `rec.nominal.<axis>` |
| MEAS | 实测值 | `rec.measured.<axis>` |
| +TOL | 上公差 | `rec.plus_tol` |
| -TOL | 下公差 | `rec.minus_tol` |
| BONUS | 奖励公差 | `rec.bonus` |
| DEV | 偏差 | `rec.measured - rec.nominal` |
| OUTTOL | 超差量 | `deviation - plus_tol` 或 PC-DMIS 直接给 |

**GDT 符号映射**（11 个）：位置度/轮廓度/圆柱度/圆度/平行度/垂直度/倾斜度/同轴度/对称度/跳动/全跳动

**集成后约束**：
- `main_window.py` 提示文案"尺寸 · 描述 · NOMINAL · MEAS · +TOL · −TOL · BONUS · DEV · OUTTOL" 与代码完全一致
- 列名修改必须同步修改**三处**：`_HEADER` / GUI 提示文案 / 用户文档

---

### 3.50 数据流（PC to Excel 完整 pipeline）

```
PCDMIS COM (PCDLRN.Application)
    │
    ▼
core/data_extractor.py:extract_from_application()
    │   ├─ _extract_features()      ← 特征（圆、平面等）
    │   ├─ _extract_dimensions()    ← 评价尺寸
    │   ├─ _extract_tolerance_commands()  ← 形位公差（2022.2+）
    │   ├─ _extract_fcf_commands()  ← Legacy FCF
    │   ├─ _extract_datum_markers() ← 基准
    │   └─ _extract_assign_commands() ← 计算/赋值
    ▼
list[FeatureRecord]  (含 nominal/measured/deviation/tolerance/status)
    │
    ▼
core/tolerance.py:apply_tolerance()
    │   └─ 判定 PASS/FAIL（（UP/±公差/outtol）
    ▼
list[FeatureRecord] with status
    │
    ├─→ export/pcdmis_style_report.py:export_pcdmis_excel()  ← "一键导出 Excel"
    ├─→ export/pcdmis_style_report.py:export_pcdmis_csv()    ← CSV 导出（**当前零调用**，见下方注）
    └─→ export/inspection_form_fill.py:fill_inspection_form() ← "填入出货表"
```

> **注（2026-09-23）**：`export_pcdmis_csv()` 是**定义但零调用**的死函数（不在
> `export/__init__.py` 的 `__all__` 里，全仓无 call site、无测试）。它与本次取消的
> BAS 脚本**无关** —— BAS 脚本用自己的 `saveCsv` 写 CSV，不经过 Python。
> 原图把它标成「BAS 脚本导出」是**归因错误**，实际从未被 BAS 路径调用。
> 已登记为独立清理项（见 `docs/CORE_DEFECT_PLAN.md`），**未删除**。

**集成后约束**：
- 这条 pipeline 是 pc_to_excel 的**核心业务逻辑**，迁移时严禁改动
- `core/` 改名建议保留原名（`core/`、`connector/`、`export/`、`inject/`），方便代码对比
- `Shell` 不直接调用 pipeline，只通过 ModuleProtocol 挂载 GUI，GUI 内部驱动 pipeline

---

### 3.51 数据提取重构（2026-08-27：拆分 + 常量隔离 + 注册层解耦）

**背景**：`core/data_extractor.py` 一度膨胀到 1940 行 / 70+ 函数，混合了命令遍历、尺寸读取、形位公差、特征提取、分类统计五类职责。

**拆分结果**（入口 `data_extractor.py` 压缩到 ~150 行，只做组合 + 统一导出）：

```
core/
├── __init__.py           # from .data_extractor import extract_from_application
├── data_extractor.py     # 入口：extract_from_application / extract_from_part_program + re-export
├── _common.py            # 共享工具 + COM 字段访问（_field_value/_safe_float/_axis_values_for_letter 等）
├── _command_cache.py     # _build_command_cache / _iter_commands / _get_command_at
├── _dimension.py         # Legacy 评价尺寸读取与配对合并
├── _tolerance.py         # 形位公差（ToleranceCommand + Legacy FCF）
├── feature.py            # 特征提取 + 几何参数（_build_geometry_values）
├── _datum.py             # 基准 / 赋值
├── classification.py     # 分类统计（RecordCategory / classify_record / summarize*）
└── models.py             # 数据模型（未动）
```

**约束**：
- `extract_from_application()` 签名与返回值**不变**（`pcdmis_connector` 依赖）；`from core.data_extractor import extract_from_application` 与测试的 `from ..core.data_extractor import _extract_*` 均保持有效
- 所有内部函数 `_` 前缀命名保留；`report_filter.py` 的 `from .data_extractor import RecordCategory, classify_record` 经 re-export 继续可用
- `_common.py` 不在最初规划内——为消除尺寸/公差/特征/基准四簇之间的循环导入而补（共享工具集中于此）

**常量缓存按 ProgID 隔离**（`connector/pcdlrn_constants.py`）：
- 旧 `_CONSTANTS_SINGLETON` 全局单例加载后永不更新 → 改为 `_CONSTANTS_BY_PROGID: dict[str, object]`，`load_pcdlrn_constants(prog_id)` 按版本隔离
- `get_const(name, prog_id=None, default=None)` 二级缓存键改为 `(prog_id, name)`
- `PcdmisConnector.connect()` 成功后调 `set_active_prog_id(prog_id)`；data_extractor 因 `extract_from_application` 签名冻结，`get_const(field)` 回退到 `_ACTIVE_PROG_ID`；`command_injector` 链则显式透传 `prog_id`

**注册层解耦**（`module.py`）：
- `PCToExcelModule` 不在模块顶层 import GUI/connector；`mount()` 经 `_create_window()` 工厂方法延迟 import `MainWindow`
- 未加 `_create_connector()`：`MainWindow.__init__` 内部自建 `PcdmisConnector()`，注入 connector 会改变行为

---

## 四、壳主窗口设计

### 4.1 布局结构

```
┌─────────────────────────────────────────────────────────┐
│  cm2xl 1.0.2                            [版本] [_][□][X] │
├──────────┬──────────────────────────────────────────────┤
│          │                                              │
│  📊 CMM报告填充 │         模块内容区                       │
│          │         (挂载当前选中模块的 GUI)               │
│  📐 PCDMIS导出 │                                          │
│          │                                              │
│  ⚙️ 设置   │                                              │
│          │                                              │
├──────────┴──────────────────────────────────────────────┤
│  状态栏: 连接状态 | 当前模块 | 提示信息                   │
└─────────────────────────────────────────────────────────┘
```

### 4.2 导航设计

- 左侧固定宽度导航栏（约 160px）
- 垂直排列模块项，当前选中项高亮
- 点击切换模块，自动调用 `module.mount()` / `module.unmount()`
- "设置" 项可跳转到全局设置面板

### 4.3 状态栏与模块状态通知机制

状态栏显示三类信息：PCDMIS 连接状态 | 当前模块 | 操作提示。

**PCDMIS 连接状态**（pc to excel 模块需要）：
- pc_to_excel 模块在内部维护 `connector.status`，变化时通过回调通知 Shell
- Shell 不主动轮询，而是由模块主动推送状态更新

```python
# toolbox/shell.py 状态通知接口
class Shell(Protocol):
    def update_status(self, text: str, level: Literal['info', 'ok', 'warn', 'error']) -> None: ...
    def update_pcdmis_status(self, connected: bool, version: str | None = None) -> None: ...

# modules/pc_to_excel/gui.py 模块激活时
def on_activate(self) -> None:
    self.shell = self._module.shell  # 由 Shell 在 mount 时注入
    self.connector.on_status_change = self._on_connector_status_change

def _on_connector_status_change(self, connected: bool, version: str | None):
    self.shell.update_pcdmis_status(connected, version)
```

**操作提示**：各模块通过 `shell.update_status("处理中...", "warn")` 更新右下角提示。

---

### 4.4 独立入口兼容策略（保留原启动方式）

重构后，原有入口文件保留为"兼容入口"，通过重定向到新模块实现：

```
CMMFiller/cmm_filler_gui.py     → 兼容入口，重定向到 modules.cmm_filler.gui
pc to excel/main.py              → 兼容入口，重定向到 modules.pc_to_excel.gui
```

```python
# CMMFiller/cmm_filler_gui.py（保留，兼容老用户）
"""CMMFiller 兼容入口 — 内部重定向到 toolbox 模块"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'toolbox_parent'))
# 重定向到新模块
from modules.cmm_filler.gui import CMMFillerGUI
if __name__ == '__main__':
    app = CMMFillerGUI(parent=None)
    app.root.mainloop()
```

**推荐做法**：将原入口文件内容改为 import 导向新模块，保留原文件不动。

---

### 4.5 全局异常处理

Shell 层统一捕获未处理异常，避免程序崩溃无提示：

```python
# main.py
import sys
import traceback
from tkinter import messagebox

def global_exception_handler(exc_type, exc_val, exc_tb):
    msg = ''.join(traceback.format_exception(exc_type, exc_val, exc_tb))
    # 写日志
    with open(paths.log_dir / 'crash.log', 'a', encoding='utf-8') as f:
        f.write(msg)
    # 弹窗提示
    messagebox.showerror("程序异常", f"发生未知错误，详情已写入日志。\n\n{exc_val}")
    sys.exit(1)

sys.excepthook = global_exception_handler
```

**注意**：各模块自己的 `try/except` 自己消化，只在真正无法恢复时才触发全局处理。

---

## 五、配置文件策略

```
{config_dir}/
├── settings.json              # 全局设置（壳层）
├── cmm_filler/
│   └── settings.json          # CMMFiller 专用设置
│       └── template_path, pdf_folder, output_folder
└── pc_to_excel/
    └── settings.json          # PCDMIS导出 专用设置
        └── tolerance, export_dir, form_fill 等
```

**原则**：保留各模块原有的配置文件格式，只统一存放目录，避免大规模改造。

---

## 六、模块适配层示例

> **实现偏差（2026-08-26）**：`modules/pc_to_excel/gui.py`（适配层）与 `gui/` 子包同名冲突，Python 优先解析包导致适配层成死代码、模块永不注册。实际实现：适配层改名为 `modules/pc_to_excel/module.py`，`modules/__init__.py` 发现逻辑支持 `gui.py`/`module.py` 双入口。详情见 MIGRATION_ARCHIVE.md。

```python
# modules/cmm_filler/gui.py
"""CMMFiller 模块适配层 — 实现 ModuleProtocol"""
import customtkinter as ctk
from toolbox.protocol import ModuleProtocol
from .core.gui import CMMFillerGUI  # 原核心类

class CMMFillerModule(ModuleProtocol):
    """CMM报告填充模块"""
    
    title = "CMM报告填充"
    icon = "📊"
    version = "1.0.0"
    
    def __init__(self):
        self._instance: CMMFillerGUI | None = None
        self._container: ctk.CTkFrame | None = None
    
    def mount(self, parent: ctk.CTkFrame) -> None:
        """挂载到壳的内容区"""
        self._container = parent
        # 清除容器内容
        for widget in parent.winfo_children():
            widget.destroy()
        # 创建模块实例
        self._instance = CMMFillerGUI(parent=parent)
    
    def unmount(self) -> None:
        """卸载模块"""
        if self._instance:
            # 清理工作（如果有）
            if hasattr(self._instance, '_log'):
                self._instance._log_textbox = None
            self._instance = None
        if self._container:
            for widget in self._container.winfo_children():
                widget.destroy()
            self._container = None
    
    def on_activate(self) -> None:
        """模块被选中时调用"""
        # 可以在这里刷新数据或显示提示
        pass
```

```python
# modules/pc_to_excel/gui.py
"""PCDMIS导出 模块适配层"""
import customtkinter as ctk
from toolbox.protocol import ModuleProtocol
from .gui.main_window import MainWindow  # 原核心类

class PCToExcelModule(ModuleProtocol):
    """PCDMIS数据导出模块"""
    
    title = "PCDMIS导出"
    icon = "📐"
    version = "1.4.5"
    
    def __init__(self):
        self._instance: MainWindow | None = None
        self._container: ctk.CTkFrame | None = None
    
    def mount(self, parent: ctk.CTkFrame) -> None:
        self._container = parent
        for widget in parent.winfo_children():
            widget.destroy()
        self._instance = MainWindow(parent=parent)
    
    def unmount(self) -> None:
        if self._container:
            for widget in self._container.winfo_children():
                widget.destroy()
            self._instance = None
            self._container = None
    
    def on_activate(self) -> None:
        # 刷新连接状态
        pass
```

---

## 七、PyInstaller 打包

> 完整 spec 示例见 3.10 / 11.3 Phase 6。本节列出关键决策。

```python
# build.spec 关键配置
a = Analysis(
    ['main.py'],
    hiddenimports=[
        # CMMFiller（PaddleOCR 全套 + 子模块）
        'paddleocr', 'paddlepaddle', 'pymupdf', 'paddle',
        'paddle.base', 'paddle.base.core', 'paddle.inference',
        'tkinterdnd2', 'lmdb', 'cffi',
        'scipy', 'scipy.special', 'scipy.ndimage', 'scipy.io',
        'shapely', 'shapely.geometry', 'pyclipper',
        'rapidfuzz', 'lxml', 'yaml', 'requests', 'tqdm', 'cv2',
        'ppocr.postprocess.*', 'ppocr.utils.*',
        'tools.infer.*',
        # pc to excel
        'win32com', 'win32com.client', 'pythoncom', 'pywintypes',
        # shared
        'customtkinter', 'openpyxl',
    ],
    datas=[
        # CMMFiller 模板 + OCR 模型
        ('modules/cmm_filler/templates', 'templates'),
        ('modules/cmm_filler/models/paddleocr', 'models/paddleocr'),
        # pc to excel BAS 脚本
        ('modules/pc_to_excel/scripts/export_current.bas', 'scripts'),
        ('modules/pc_to_excel/scripts/export_current.bas.template', 'scripts'),
    ],
    runtime_hooks=['build/rth_paddleocr_fix.py'],  # 见 3.13
)
```

**打包流程**（build.bat 完整顺序）：
```
1. python -m PyInstaller build.spec --noconfirm
2. python build/fix_dist.py              # 4 个 patch（详见 3.11 + 3.48）
3. copy /Y run_as_admin.bat dist\
4. copy /Y docs\*.md dist\docs\
5. python build_installer.bat            # Inno Setup 编译（见 3.28）
```

---

## 八、实施路线图（与 11.3 迁移计划同步）

| 阶段 | 任务 | 产出 | 优先级 |
|------|------|------|--------|
| **Phase 0** | 创建 `toolbox/` 骨架（protocol、app_meta、paths、logging、theme、audit、error_codes）| 共享基础设施就绪 | P0 |
| **Phase 1** | 搭建壳主窗口 `toolbox/shell.py`（导航、状态栏、模块挂载/卸载）+ 主题统一调用一次 | 可运行的空壳 | P0 |
| **Phase 2** | 创建 `modules/` 包结构和 `__init__.py` 模块注册 | 模块注册机制 | P0 |
| **Phase 3** | 迁移 CMMFiller（改相对导入、PDF 大小写、OCR 缓存、PDF with、CancellableWorker）| CMM报告填充集成 | P1 |
| **Phase 4** | 迁移 pc_to_excel（改相对导入、错误码、线程取消、Shell 状态回调）| PCDMIS导出集成 | P1 |
| **Phase 5** | 配置迁移（3 子阶段：基础迁移 + 版本升级 + 降级导出）| 配置兼容 1.x → 2.x 升级 | P1 |
| **Phase 5.5** | 应用层修复（原子写、文件锁、PDF 大小写、PDF 句柄、OCR 缓存、线程取消、主题冲突、atexit）| 8 个修复点 | P1 |
| **Phase 6** | 合并 requirements + build.spec + Inno Setup | 可打包的完整项目 | P2 |
| **Phase 7** | 保留原入口 + README 重写 + CLAUDE.md | 独立运行兼容 + 文档 | P2 |
| **Phase 8** | 测试两种模式 + 新增机制验收 | 验收 | P2 |

**完整 Phase 步骤详见 11.3（含任务清单、验收、回滚、风险点）**。

---

## 九、风险点与注意事项

| 风险 | 应对措施 | 章节 |
|------|---------|------|
| PaddleOCR 体积大（628MB 打包后） | 必须打包（含 PaddlePaddle），测量房无网环境无法运行时下载 | 3.10 |
| COM 连接权限冲突 | pc_to_excel 权限检查与 CMMFiller 隔离；Shell 不初始化任何 COM | 3.14 |
| 配置文件迁移 | 用 `migrate_settings_if_needed` 自动迁移并备份旧文件 | 3.9 |
| 配置版本升级 | 用 `_version` 字段 + 迁移函数注册表 + 备份 | 3.9.1 |
| 配置降级 | 不自动降级；提供"导出旧版配置"菜单 | 3.9.2 |
| 打包体积过大（600-700MB） | 单 exe 全部打包，无分离分发；测量房无网 | 3.10 |
| 两模块同时激活 | Shell 确保同时只有一个模块在内存中（mount 前先 unmount）| 4.3 |
| `tkinterdnd2` 在挂载模式下不稳定 | Shell 层不初始化 Tkdnd；CMMFiller 模块自行在独立窗口模式下初始化 | 3.2 |
| BAS 脚本路径含空格或权限不足 | 固定使用 `LocalAppData/PCDMIS_ExcelExporter`，避开空格和权限问题 | 3.7 |
| CMMFiller GUI 日志无法在 Shell 状态栏显示 | 通过 `GuiLogHandler` + `shell.update_status()` 路由 | 3.6 |
| **CustomTkinter 主题冲突**（严重）| Shell 层统一调用 `set_default_color_theme`，删除模块内调用 | 3.45 |
| **绝对路径导入失效**（迁移后）| 批量改相对导入，删除 `sys.path.insert` | 3.46 |
| **多进程并发写配置损坏** | `FileLock` 锁 + 检测机制 | 3.41 |
| **线程无 cancel 机制** | 引入 `CancellableWorker` 模式 + atexit cleanup | 3.42 |
| **PDF 文件大小写敏感**（潜在 Bug）| 改 `suffix.lower() == '.pdf'` 扫描 | 3.39 |
| **JSON 写非原子**（断电损坏）| tmp + `os.replace` 原子写 | 3.40 |
| **OCR 缓存 JSON 无限累积** | 按数量（10000 条）限制 | 3.38 |
| **PDF 文件句柄泄漏**（异常时）| `with fitz.open(...)` 形式 | 3.43 |
| **PaddleOCR 4 个 patch 重复执行** | 加 `PATCH_MARKER` 防重复 | 3.48 |
| **PC-DMIS 必须 64 位** | 启动时硬阻断 32 位 Python | 3.15 |
| **打包后无审计追溯** | `utils/audit.py` + TimedRotatingFileHandler | 3.36 |
| **错误信息无法程序化处理** | `ErrorCode` enum + `ToolboxError` | 3.35 |
| **GUI 卡顿（同步阻塞）** | 工作线程 + `root.after(0, ...)` 派发 | 3.26 |
| **claude/AGENTS 指令文件分散** | 整合到 toolbox 根的 `CLAUDE.md` | 3.31 |

---

## 十、后续扩展

- **未来可扩展**：增加新模块（如影像仪、轮廓仪数据导入）
- **模块注册**：在 `modules/__init__.py` 中统一注册，支持自动发现
- **插件机制**：可考虑用 `importlib` 实现运行时加载

---

## 十一、迁移计划（Migration Plan）

### 11.1 目标目录结构

在 `D:\AI\work\a1\` 下新建目录 `pcdmis_toolbox\`，作为整合后的项目根：

```
D:\AI\work\a1\
├── CMMFiller/                    ← 旧项目，迁移源 1
├── pc to excel/                  ← 旧项目，迁移源 2
├── docs/ARCHITECTURE.md               ← 当前文档
└── pcdmis_toolbox/               ← 新建，整合后项目根
    ├── main.py
    ├── pyproject.toml
    ├── requirements/
    │   ├── base.txt
    │   ├── cmm_filler.txt
    │   └── pc_to_excel.txt
    ├── toolbox/
    │   ├── __init__.py
    │   ├── shell.py
    │   ├── app_meta.py
    │   ├── protocol.py
    │   └── paths.py
    ├── utils/
    │   ├── __init__.py
    │   ├── logging.py     ← 含 GuiLogHandler
    │   ├── settings.py    ← 含 migrate_settings_if_needed
    │   └── theme.py
    ├── modules/
    │   ├── __init__.py    ← 模块注册表
    │   ├── cmm_filler/
    │   └── pc_to_excel/
    └── build/
        ├── build.spec
        ├── fix_dist.py
        └── hooks/         ← PyInstaller 自定义 hooks
```

---

### 11.2 文件迁移映射表

#### 11.2.1 pc to excel 模块

| 旧路径 | 新路径 | 操作 |
|--------|--------|------|
| `pc to excel/main.py` | `pcdmis_toolbox/modules/pc_to_excel/main.py` | 改写为重定向入口 |
| `pc to excel/gui/main_window.py` | `pcdmis_toolbox/modules/pc_to_excel/gui/main_window.py` | 保留大部分代码，添加 ModuleProtocol 适配层在 `gui.py` |
| `pc to excel/connector/base.py` | `pcdmis_toolbox/modules/pc_to_excel/connector/base.py` | 直接搬移 |
| `pc to excel/connector/com_detector.py` | 同上 | 搬移 |
| `pc to excel/connector/pcdmis_connector.py` | 同上 | 搬移 |
| `pc to excel/connector/pcdlrn_constants.py` | 同上 | 搬移 |
| `pc to excel/core/data_extractor.py` | `pcdmis_toolbox/modules/pc_to_excel/core/data_extractor.py` | 搬移（**禁止重构核心逻辑**）|
| `pc to excel/core/models.py` | 同上 | 搬移 |
| `pc to excel/core/report_filter.py` | 同上 | 搬移 |
| `pc to excel/core/tolerance.py` | 同上 | 搬移 |
| `pc to excel/export/inspection_form_fill.py` | `pcdmis_toolbox/modules/pc_to_excel/export/` | 搬移 |
| `pc to excel/export/pcdmis_style_report.py` | 同上 | 搬移 |
| `pc to excel/export/template_report.py` | 同上 | 搬移 |
| `pc to excel/inject/command_injector.py` | `pcdmis_toolbox/modules/pc_to_excel/inject/` | 搬移 |
| `pc to excel/inject/save_helper.py` | 同上 | 搬移 |
| `pc to excel/utils/admin.py` | **不在模块内**，挪到 `pcdmis_toolbox/utils/admin.py` | 共享化 |
| `pc to excel/utils/action_hints.py` | `pcdmis_toolbox/modules/pc_to_excel/utils/` | 搬移 |
| `pc to excel/utils/settings.py` | 重命名为 `local_settings.py` 放模块内 | 避免与 `utils/settings.py` 重名 |
| `pc to excel/config.py` | 拆分为：常量部分 → `modules/pc_to_excel/app_meta.py`；路径 → `utils/paths.py` | 拆分 |
| `pc to excel/scripts/export_current.bas` | `pcdmis_toolbox/modules/pc_to_excel/scripts/` | 搬移 |
| `pc to excel/scripts/export_current.bas.template` | 同上 | 搬移 |
| `pc to excel/run_as_admin.bat` | `pcdmis_toolbox/build/` | 搬移 |
| `pc to excel/build.spec` | `pcdmis_toolbox/build/build.spec` | 合并 |
| `pc to excel/build.bat` | `pcdmis_toolbox/build.bat` | 重写为完整流程 |
| `pc to excel/data/settings.json` | 模板 → `pcdmis_toolbox/build/default_settings/pc_to_excel.json` | 标识为初始默认 |
| `pc to excel/requirements.txt` | `pcdmis_toolbox/requirements/pc_to_excel.txt` | 拆条件 |
| `pc to excel/tests/*.py` | `pcdmis_toolbox/modules/pc_to_excel/tests/` | 搬移 |

#### 11.2.2 CMMFiller 模块

| 旧路径 | 新路径 | 操作 |
|--------|--------|------|
| `CMMFiller/cmm_filler_gui.py` | `pcdmis_toolbox/modules/cmm_filler/main.py` | 改写为入口（重定向）|
| `CMMFiller/cmm_filler_v10.py` | `pcdmis_toolbox/modules/cmm_filler/core/filler.py` | 搬移 |
| `CMMFiller/ocr_engine.py` | `pcdmis_toolbox/modules/cmm_filler/ocr/engine.py` | 搬移 |
| `CMMFiller/template_wizard.py` | `pcdmis_toolbox/modules/cmm_filler/template_wizard.py` | 搬移 |
| `CMMFiller/version.py` | `pcdmis_toolbox/modules/cmm_filler/app_meta.py` | 改写为从 toolbox 导入 |
| `CMMFiller/templates/模板1.xlsx` | `pcdmis_toolbox/modules/cmm_filler/templates/模板1.xlsx` | 搬移 |
| `CMMFiller/templates/模板2.xlsx` | 同上 | 搬移 |
| `CMMFiller/models/paddleocr/` | `pcdmis_toolbox/modules/cmm_filler/models/paddleocr/` | 搬移（18MB）|
| `CMMFiller/hooks/*.py` | `pcdmis_toolbox/build/hooks/` | 搬移 |
| `CMMFiller/fix_dist.py` | `pcdmis_toolbox/build/fix_dist.py` | 搬移 |
| `CMMFiller/CMMFiller.spec` | 合并到 `pcdmis_toolbox/build/build.spec` | 合并 |
| `CMMFiller/run_as_admin.bat` | 不需要，pc to excel 已有一个，toolbox 共用 | 不搬 |
| `CMMFiller/template_config.json` | 模板 → `pcdmis_toolbox/build/default_settings/cmm_filler.json` | 标识为初始默认 |
| `CMMFiller/cmm_version.json` | 暂不使用，可选放 `toolbox/app_meta.py` | 决策 |
| `CMMFiller/requirements.txt` | `pcdmis_toolbox/requirements/cmm_filler.txt` | 拆条件 |
| `CMMFiller/test_summary_export.py` | `pcdmis_toolbox/modules/cmm_filler/tests/test_summary_export.py` | 搬移 |

---

### 11.3 分阶段迁移步骤

#### Phase 0：建基础设施（预计 3-4 小时）

**任务清单**：
1. 创建 `pcdmis_toolbox/` 目录及子目录骨架
2. 写 `toolbox/app_meta.py`：APP_TITLE、APP_VERSION、APP_BUILD、EXPORT_CMD_ID 等常量
3. 写 `toolbox/protocol.py`：ModuleProtocol 定义（含 `shell: Shell` 注入约定）
4. 写 `utils/theme.py`：TOOLBOX_THEME 调色板 + **自定义 theme.json**（3.45）
5. 写 `utils/paths.py`：PathManager（frozen + dev 模式）
6. 写 `utils/logging.py`：setup_logging（含 RotatingFileHandler + TimedRotatingFileHandler）+ GuiLogHandler（见 3.6 完整版）
7. 写 `utils/audit.py`：audit() 函数（3.36）
8. 写 `utils/error_codes.py`：ErrorCode 枚举 + ToolboxError 异常（3.35）
9. 写 `main.py`：启动入口（含 `multiprocessing.freeze_support()` + 环境变量 + `ctk.set_default_color_theme` **只调一次** + 32 位检测 + 全局异常处理）
10. 写 `requirements/base.txt`（customtkinter + openpyxl + pyinstaller）

**验收**：
```bash
cd pcdmis_toolbox
pip install -r requirements/base.txt
python -c "from toolbox.app_meta import APP_VERSION; print(APP_VERSION)"
python -c "from utils.logging import GuiLogHandler; print('OK')"
python -c "from utils.audit import audit; print('OK')"
python -c "from utils.error_codes import ErrorCode, ToolboxError; print('OK')"
```

**回滚**：删除 `pcdmis_toolbox/` 整个目录。

---

#### Phase 1：搭壳主窗口（预计 3-4 小时）

**任务清单**：
1. 写 `toolbox/shell.py`：Shell 类（左侧导航 + 内容区 + 状态栏 + `update_status()` / `update_pcdmis_status()` 接口）
2. 写 `utils/settings.py`：`save_settings_json_atomic()`（3.40）+ `FileLock`（3.41）+ `migrate_settings_if_needed()`（3.9）
3. 写 `utils/threading_utils.py`：`CancellableWorker` 类（3.42）
4. 写 `toolbox/paths.py`：frozen 路径解析（含 `%LOCALAPPDATA%/PCDMIS_ExcelExporter/scripts/`）
5. 写 `utils/file_io.py`：fitz.open 上下文管理器（3.43）、PDF 大小写不敏感 glob（3.39）
6. Shell 全局异常处理（4.5）+ atexit cleanup 注册（3.42）
7. **删除**各模块的 `ctk.set_default_color_theme()` 调用（3.45）

**验收**：
```bash
python main.py
# 出现空壳窗口，左侧有 2 个导航项（暂时空白），右侧"未选择模块"提示
# 32 位系统应硬阻断并提示
```

**回滚**：git checkout 上一 commit（建议每 phase 提交一次）。

---

#### Phase 2：模块注册机制（预计 1 小时）

**任务清单**：
1. 写 `modules/__init__.py`：**pkgutil 自动发现** + `_discover_modules()` 加载 `modules/<name>/gui.py`，底部 import 执行 `register_module()`
2. 写 `modules/cmm_filler/__init__.py`：空文件（注册在 gui.py 底部）
3. 写 `modules/pc_to_excel/__init__.py`：空文件
4. 写 `modules/<name>/gui.py` 适配层骨架（Phase 1 stub，Phase 3/4 替换为真实实现）

**验收**：
```bash
python -c "from modules import REGISTRY; print(list(REGISTRY.keys()))"
# 输出: ['cmm_filler', 'pc_to_excel']
```

---

#### Phase 3：CMMFiller 迁移（预计 4-5 小时）

**任务清单**：
1. 搬移 `cmm_filler_v10.py` → `modules/cmm_filler/core/filler.py`
   - **批量改绝对导入为相对导入**（3.46）：`from ocr_engine` → `from ..ocr.engine`
   - 删除所有 `sys.path.insert(0, _ROOT)`（3.46）
   - 修 PDF glob 大小写不敏感（3.39）
   - 修 `fitz.open` 改 `with` 形式（3.43）
   - 补全 `_cleanup_cache()` 清 ocr_cache.json（3.38）
2. 搬移 `ocr_engine.py` → `modules/cmm_filler/ocr/engine.py`
   - 修 import 路径
3. 搬移 `template_wizard.py` → `modules/cmm_filler/template_wizard.py`
4. 搬移 `templates/`、`models/paddleocr/`（18MB）
5. 写 `modules/cmm_filler/gui.py`：CMMFillerModule 实现 ModuleProtocol
6. 写 `modules/cmm_filler/main.py`：独立运行入口
7. 写 `modules/cmm_filler/app_meta.py`：从 toolbox.app_meta 导入
8. 写 `modules/cmm_filler/cli.py`：保留 CLI 模式（3.29）
9. 写 `requirements/cmm_filler.txt`
10. 删除模块内 `ctk.set_default_color_theme("blue")` 调用（3.45）
11. 用 `CancellableWorker` 替换 `threading.Thread(target=..., daemon=True)`（3.42）

**验收**：
```bash
# 独立运行
python -m modules.cmm_filler
# 应该打开 CMMFiller GUI，行为与旧版一致

# 集成运行
python main.py
# 切换到"CMM 报告填充"模块，UI 与独立运行一致

# OCR 测试（用样例 PDF）
# 跑 test_summary_export.py

# PDF 大小写测试
mkdir test_pdfs && cp samples/001.PDF test_pdfs/001.pdf
python -m modules.cmm_filler  # 应该能处理 test_pdfs/001.pdf
```

**回滚**：删除 `pcdmis_toolbox/modules/cmm_filler/`。

**风险点**：
- 内部 `import cmm_filler_v10` 路径要改成 `from .core.filler import ...`
- `template_path` 默认值可能找不到（路径从 BASE_DIR 改为 modules/cmm_filler/）
- tkinterdnd2 在挂载模式下的初始化
- PDF 大小写修复后老用户的小写 PDF 才能被处理

---

#### Phase 4：pc_to_excel 迁移（预计 5-6 小时）

**任务清单**：
1. 搬移 `core/`、`connector/`、`export/`、`inject/` → `modules/pc_to_excel/`
   - **批量改绝对导入为相对导入**（3.46）：`from connector.base import ...` → `from .connector.base import ...`
   - 删除所有 `sys.path.insert(0, _ROOT)`（3.46）
2. 拆分 `config.py`：常量到 `app_meta.py`，路径部分改用 `utils/paths.py`
3. 搬移 `utils/admin.py` → `utils/admin.py`（共享化）
4. 搬移 `utils/action_hints.py` → `modules/pc_to_excel/utils/`
5. 重命名 `utils/settings.py` → `modules/pc_to_excel/utils/local_settings.py`
6. 搬移 `scripts/`（BAS 脚本 + 模板）
7. 写 `modules/pc_to_excel/gui.py`：PCToExcelModule 实现 ModuleProtocol
8. 写 `modules/pc_to_excel/main.py`：独立运行入口
9. 写 `modules/pc_to_excel/app_meta.py`
10. 写 `modules/pc_to_excel/cli.py`：保留 CLI 模式（3.29）
11. 写 `requirements/pc_to_excel.txt`
12. 删除模块内 `ctk.set_default_color_theme("green")` 调用（3.45）
13. 用 `CancellableWorker` 替换所有 `threading.Thread(..., daemon=True)`（3.42）
14. `format_user_error` 改为接收 `ToolboxError`（3.35）

**验收**：
```bash
# 独立运行（需要 PCDMIS 安装）
python -m modules.pc_to_excel

# 集成运行
python main.py
# 切换到"PCDMIS 导出"模块

# 测试（需要 PCDMIS）
pytest modules/pc_to_excel/tests/ -v
```

**回滚**：删除 `pcdmis_toolbox/modules/pc_to_excel/`。

**风险点**：
- `from config import ...` 全部要改成从新位置导入
- 测试文件 `from config import SETTINGS_FILE` 等
- BAS 脚本部署路径
- 错误码系统接入后旧 `RuntimeError` 调用点要批量替换

---

#### Phase 5：配置迁移与版本管理（预计 2-3 小时）

**任务清单**：

**Phase 5a：基础迁移**（3.9）
1. 完善 `utils/settings.py` 的 `migrate_settings_if_needed()` 函数
2. 在 Shell 启动时调用迁移逻辑
3. 添加首次启动引导（检测到旧路径时弹窗告知）

**Phase 5b：版本升级方案**（3.9.1）
1. 在所有 settings.json 加 `_version` / `_schema` / `_updated_at` 字段
2. 写 `migrate_cmm_filler_1_0_to_2_0()`（路径嵌套化）
3. 写 `migrate_pc_to_excel_1_4_to_2_0()`（顶层字段 + tolerance + form_fill 复制）
4. 实现 `load_and_migrate_settings()` 主流程（备份 + 沿迁移链升级 + 写回）
5. 错误处理：corrupted JSON、缺失迁移函数、超时等

**Phase 5c：降级导出工具**（3.9.2）
1. 写 `export_legacy_settings(module_name, target_path)`：2.0 → 1.x 降级
2. Shell 提供"导出旧版配置"菜单（弹文件选择器）
3. 不做自动降级（用户主动）

**验收**：
```bash
# 模拟旧环境：创建旧 settings.json 在 CMMFiller 同级
# 运行 Toolbox
# 应该自动迁移到新位置，旧文件改名为 .v{old_version}.bak

# 验证版本字段
cat ~/.pcdmis_toolbox/cmm_filler/settings.json | python -m json.tool | grep _version
# 输出: "_version": "2.0.0"

# 降级导出
python -c "from utils.settings import export_legacy_settings; export_legacy_settings('cmm_filler', Path('legacy.json'))"
```

---

#### Phase 5.5：应用层修复（预计 4-5 小时）

> **新增阶段**：集成过程中发现的 8 个修复点，集中处理。

**任务清单**：
1. **原子写**（3.40）：`save_settings_json_atomic()` 替换所有 `json.dump` 直接写
2. **文件锁**（3.41）：`utils/file_lock.py` 实现 `FileLock` 类，Shell 启动时检测并发
3. **OCR 缓存 JSON 清理**（3.38）：`_cleanup_cache()` 补全按数量清 ocr_cache.json
4. **PDF 大小写**（3.39）：CMMFiller 模块修 `glob('*.PDF')` → `suffix.lower() == '.pdf'`
5. **PDF 句柄**（3.43）：所有 `fitz.open()` 改 `with` 形式
6. **线程取消**（3.42）：所有 `daemon=True` 线程改用 `CancellableWorker`，Shell on_close 时 cancel
7. **主题统一**（3.45）：Shell 主入口调一次 `ctk.set_default_color_theme`，模块内删除
8. **atexit cleanup**（3.42）：注册 `cleanup_on_exit()` 处理 tmp.pdf + logging.shutdown

**验收**：
```bash
# 原子写：kill -9 进程中途模拟，写文件不会被破坏
# 文件锁：同时启动两个 Toolbox，第二个应提示
# OCR 缓存：跑 10000+ OCR 后 cache 文件应被限制
# PDF 大小写：samples/*.pdf（小写）也能被处理
# PDF 句柄：异常情况下查看 lsof/handle 无残留
# 线程取消：开始处理后立即关窗，应在 < 10s 内退出
# 主题：切换模块无颜色跳变
# atexit：kill -9 不会留下 tmp 文件
```

---

#### Phase 6：合并 requirements + 整合 build（预计 4-5 小时）

**任务清单**：
1. 创建 `requirements/` 目录，三个 txt 文件（3.0）
2. 创建 `pyproject.toml`
3. 写 `build/build.spec`：合并两个 spec（3.10）
4. 搬移 `fix_dist.py` → `build/fix_dist.py`
   - 加 `PATCH_MARKER = "# TOOLBOX_PATCHED_v2"` 防止重复 patch（3.48）
5. 搬移 `hooks/` → `build/hooks/`
6. 写 `build.bat`：pyinstaller → fix_dist → copy 资源
7. **写 Inno Setup 脚本** `installer/cm2xl.iss`（3.28；规划稿曾用名 `PCDMIS_Toolbox.iss`）
   - AppId 用新 GUID（与 CMMFiller `{...7890}` 区分）
   - `PrivilegesRequired=admin`
   - `ArchitecturesInstallIn64BitMode=x64compatible`
   - 安装时复制 dist/cm2xl + run_as_admin.bat
   - 卸载时清 %localappdata%\cm2xl\cache
8. 写 `build_installer.bat` 调用 Inno Setup 编译

**验收**：
```bash
cd pcdmis_toolbox
pip install -r requirements/base.txt -r requirements/cmm_filler.txt -r requirements/pc_to_excel.txt
python build.bat
# 应该生成 dist/cm2xl/ 目录，包含 exe 和 _internal/

# 安装包
python build_installer.bat
# 生成 installer/output/cm2xl_Setup_1.0.2.exe
```

---

#### Phase 7：保留独立入口（预计 1 小时）

**任务清单**：
1. `CMMFiller/cmm_filler_gui.py` 改为重定向到 `modules.cmm_filler.main`
2. `pc to excel/main.py` 改为重定向到 `modules.pc_to_excel.main`
3. **重写 `pcdmis_toolbox/README.md`**（替换 `CMMFiller/README.md` + `pc to excel/README.md`）
   - 删除旧的 build 教程（指向 `build.bat`）
   - 写新的目录结构、使用说明
4. 删除旧 `CMMFiller/CLAUDE.md`（指向 toolbox 根的 `CLAUDE.md`）

**验收**：
```bash
cd CMMFiller
python cmm_filler_gui.py  # 应该仍然打开 GUI
cd "../pc to excel"
python main.py  # 应该仍然打开 GUI

# 新 README
cat pcdmis_toolbox/README.md  # 内容齐全，链接到 docs/
```

---

#### Phase 8：测试两种模式（预计 3-4 小时）

**任务清单**：
1. 独立运行：CMMFiller、PCDMIS 分别单独跑
2. 集成运行：Toolbox 切换模块
3. 异常处理：制造崩溃看弹窗 + crash.log
4. 状态栏：观察 PCDMIS 连接状态更新
5. admin 启动：用 admin 启动 Toolbox，跑两个模块
6. **新增机制验证**（来自 Phase 5.5 验收项）：
   - 原子写：kill -9 进程中途
   - 文件锁：同时启动两个 Toolbox
   - OCR 缓存：10000+ OCR 后清理
   - PDF 大小写：小写文件处理
   - 线程取消：开始处理后立即关窗
   - 主题：切换模块无颜色跳变
   - 配置版本：升级 2.0.0 → 模拟 2.1.0 → 走迁移链
   - 降级导出：用户主动导出 1.x 格式
   - 审计日志：11 类操作都产生记录
   - 错误码：所有 ToolboxError 带 code 字段

---

### 11.4 全局验证清单

迁移完成后，必须逐项验证：

| 验证项 | 命令 | 期望结果 |
|--------|------|---------|
| CMMFiller 独立运行 | `python -m modules.cmm_filler` | GUI 正常打开 |
| pc_to_excel 独立运行 | `python -m modules.pc_to_excel` | GUI 正常打开（需 PCDMIS）|
| Toolbox 集成运行 | `python main.py` | 壳窗口 + 模块切换 |
| CMMFiller OCR 跑通 | 加载 samples/001-005.PDF | 输出 5 个 sheet |
| PCDMIS 连接 | admin 启动 → 切换模块 → 点连接 | 显示版本号 |
| 一键导出 Excel | 测完一件 → 点导出 | 生成 xlsx 文件 |
| 出货表填入 | 选出货表 → 填入 | 生成新 xlsx |
| BAS 部署 | 点部署 → 检查 LocalAppData | export_current.bas 存在 |
| 命令植入 | 打开 PRG → 植入 | PRG 末尾有 PC2XL_EXPORT |
| 旧入口兼容 | 旧 `python cmm_filler_gui.py` | 仍能打开 GUI |
| 配置迁移 | 放旧 settings.json 到 CMMFiller/ | 迁移到新位置，旧文件备份 |
| 异常处理 | kill -9 主进程 | 弹窗 + crash.log |
| 状态栏 | admin 启动 Toolbox | 显示"管理员" |

---

### 11.5 风险与回滚

| 风险 | 概率 | 回滚方案 |
|------|------|---------|
| CMMFiller 核心类被破坏 | 中 | 保留 `cmm_filler_v10.py` 备份，迁移失败时直接 revert |
| pc_to_excel dataclass 字段被改 | 中 | 保持原字段名，迁移后跑 `tests/` 验证 |
| PaddleOCR 模型丢失 | 低 | 单独备份 `models/paddleocr/`，再打包 |
| BAS 脚本找不到 | 中 | 保留原 `scripts/`，跑 `deploy_bas_script()` 重新部署 |
| 旧用户设置丢失 | 中 | 迁移逻辑加 `.bak` 备份，永不删除 |
| 打包失败 | 中 | 保留旧 spec 文件独立打包，直到新 spec 通过 |

**最终回滚方案**：每个 Phase 提交一次 git commit，失败时 `git reset --hard <last_good_phase>`。

---

### 11.6 迁移时间估算

| Phase | 内容 | 工作量 |
|-------|------|--------|
| 0 | 基础设施（含 theme/audit/error_codes） | 3-4 小时 |
| 1 | 壳主窗口（含 CancellableWorker、原子写、文件锁） | 3-4 小时 |
| 2 | 模块注册 | 1 小时 |
| 3 | CMMFiller 迁移（含相对导入、tk vs ctk） | 4-5 小时 |
| 4 | pc_to_excel 迁移（含相对导入、错误码、线程取消） | 5-6 小时 |
| 5 | 配置迁移 +版本管理 +降级 | 2-3 小时 |
| 5.5 | 应用层修复（8 个修复点） | 4-5 小时 |
| 6 | 打包整合（含 Inno Setup） | 4-5 小时 |
| 7 | 兼容入口 + README 重写 | 1 小时 |
| 8 | 测试（含新增机制验证） | 3-4 小时 |
| **合计** | | **30-37 小时** |

---

## 附录 A：可参考的迁移前快照

迁移前建议：
1. `git init`（如果还没有 git）并提交当前状态
2. 给每个旧 spec 文件（`CMMFiller.spec`、`build.spec`）保留一份
3. 给 `dist/` 目录外的 `models/paddleocr/`、`templates/`、`scripts/` 单独备份
4. 记录当前各模块的版本号：
   - CMMFiller `__version__ = '1.0.0'`
   - pc to excel `APP_VERSION = '1.4.5'`
   - 整合后应用版本 `APP_VERSION = '1.0.2'`（`toolbox/app_meta.py`）；配置 schema `CONFIG_SCHEMA_VERSION = '2.0.0'`（独立）
