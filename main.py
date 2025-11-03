import sys
import os
import json
from pathlib import Path
from shutil import copyfile

from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMessageBox, QPlainTextEdit, QWidget,
    QVBoxLayout, QTabWidget, QTabBar, QDialog, QComboBox,
    QDialogButtonBox, QLabel, QLineEdit, QHBoxLayout, QPushButton, QStatusBar, QInputDialog
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, Qt, QSize, QEvent, QRegularExpression, QObject
from PySide6.QtGui import QMouseEvent, QTextCursor, QIcon, QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QAction
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
import qt_themes  # pip install qt-themes

# Config / paths
SETTINGS_FILE = "settings.json"
THEMES_FOLDER = "Themes"  # capital T — match repo folder
HERE = Path(__file__).parent


def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.abspath(os.path.join(HERE, relative_path))


# ------------------ Syntax highlighter ------------------
class CodeHighlighter(QSyntaxHighlighter):
    """
    Simple regex-based highlighter for multiple languages.
    Not exhaustive but provides clear coloring for keywords, strings, comments, numbers, tags.
    """

    def __init__(self, document, language="generic"):
        super().__init__(document)
        self.language = language.lower()
        self.rules = []  # list of (QRegularExpression, QTextCharFormat)
        self.multi_line_comment = None  # tuple(startExpr, endExpr, format) for C-style comments
        self._build_rules()

    def _fmt(self, color_name, bold=False, italic=False):
        f = QTextCharFormat()
        f.setForeground(QColor(color_name))
        if bold:
            f.setFontWeight(QFont.Bold)
        if italic:
            f.setFontItalic(True)
        return f

    def _word_pattern(self, words):
        # build a word-boundary regex for QRegularExpression
        escaped = [QRegularExpression.escape(w) for w in words]
        pattern = r"\b(?:" + "|".join(escaped) + r")\b"
        return pattern

    def _add_rule(self, pattern, fmt):
        self.rules.append((QRegularExpression(pattern), fmt))

    def _build_rules(self):
        # common formats
        kw_fmt = self._fmt("#569CD6", bold=True)  # keywords
        type_fmt = self._fmt("#4EC9B0", bold=True)  # types
        num_fmt = self._fmt("#B5CEA8")
        str_fmt = self._fmt("#CE9178")
        comment_fmt = self._fmt("#6A9955", italic=True)
        func_fmt = self._fmt("#DCDCAA")
        tag_fmt = self._fmt("#569CD6", bold=True)
        attr_fmt = self._fmt("#9CDCFE")
        html_str_fmt = self._fmt("#D69D85")

        lang = self.language

        if lang in ("python",):
            keywords = [
                "and", "as", "assert", "break", "class", "continue", "def", "del", "elif", "else", "except",
                "False", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "None",
                "nonlocal", "not", "or", "pass", "raise", "return", "True", "try", "while", "with", "yield"
            ]
            types = ["int", "float", "str", "list", "dict", "set", "tuple", "bool", "bytes"]
            self._add_rule(self._word_pattern(keywords), kw_fmt)
            self._add_rule(self._word_pattern(types), type_fmt)
            # functions (simple heuristic)
            self._add_rule(r"\b[A-Za-z_]\w*(?=\s*\()", func_fmt)
            # numbers
            self._add_rule(r"\b\d+(\.\d+)?\b", num_fmt)
            # strings (single and double)
            self._add_rule(r"\".*?\"", str_fmt)
            self._add_rule(r"'.*?'", str_fmt)
            # comments
            self._add_rule(r"#.*", comment_fmt)

        elif lang in ("cpp", "c", "c++", "cxx", "h", "hpp", "cc", "c++-header", "c-header", "java", "csharp", "c#"):
            # treat C-like languages together
            keywords = [
                "if", "else", "switch", "case", "for", "while", "do", "break", "continue", "return",
                "class", "struct", "public", "private", "protected", "virtual", "override", "static",
                "constexpr", "template", "typename", "using", "namespace", "new", "delete", "try", "catch", "throw"
            ]
            types = ["int", "long", "short", "float", "double", "char", "bool", "void", "size_t", "auto"]
            self._add_rule(self._word_pattern(keywords), kw_fmt)
            self._add_rule(self._word_pattern(types), type_fmt)
            self._add_rule(r"\b[A-Za-z_]\w*(?=\s*\()", func_fmt)
            self._add_rule(r"\".*?\"", str_fmt)
            self._add_rule(r"'.*?'", str_fmt)
            self._add_rule(r"\b\d+(\.\d+)?\b", num_fmt)
            # single-line comments //...
            self._add_rule(r"//.*", comment_fmt)
            # multi-line comments /* ... */
            self.multi_line_comment = (QRegularExpression(r"/\*"), QRegularExpression(r"\*/"), comment_fmt)

        elif lang in ("javascript", "js", "typescript", "ts", "jsx", "tsx"):
            keywords = [
                "var", "let", "const", "if", "else", "for", "while", "do", "switch", "case", "break", "continue",
                "function", "return", "class", "extends", "import", "from", "export", "new", "try", "catch", "finally",
                "await", "async"
            ]
            self._add_rule(self._word_pattern(keywords), kw_fmt)
            self._add_rule(r"\b[A-Za-z_]\w*(?=\s*\()", func_fmt)
            self._add_rule(r"\".*?\"", str_fmt)
            self._add_rule(r"'.*?'", str_fmt)
            self._add_rule(r"`.*?`", str_fmt)
            self._add_rule(r"\b\d+(\.\d+)?\b", num_fmt)
            self._add_rule(r"//.*", comment_fmt)
            self.multi_line_comment = (QRegularExpression(r"/\*"), QRegularExpression(r"\*/"), comment_fmt)

        elif lang in ("php",):
            keywords = [
                "echo", "array", "function", "if", "else", "foreach", "for", "while", "return", "class", "public",
                "private", "protected",
                "namespace", "use", "new", "try", "catch", "finally", "throw"
            ]
            self._add_rule(r"<\?php|<\?|/\*|\*/|\?>", comment_fmt)  # basic PHP tags detection as markup
            self._add_rule(self._word_pattern(keywords), kw_fmt)
            self._add_rule(r"\$[A-Za-z_]\w*", type_fmt)  # variables
            self._add_rule(r"\".*?\"", str_fmt)
            self._add_rule(r"'.*?'", str_fmt)
            self._add_rule(r"//.*", comment_fmt)
            self.multi_line_comment = (QRegularExpression(r"/\*"), QRegularExpression(r"\*/"), comment_fmt)

        elif lang in ("html", "htm"):
            # highlight tags, attributes and attribute values
            self._add_rule(r"</?[A-Za-z][^>]*>", tag_fmt)
            self._add_rule(r'\b[a-zA-Z-:]+(?=\=)', attr_fmt)
            self._add_rule(r"\".*?\"", html_str_fmt)
            self._add_rule(r"'.*?'", html_str_fmt)

        elif lang in ("css",):
            self._add_rule(r"[.#]?[A-Za-z0-9_\-]+(?=\s*\{)", func_fmt)  # selectors
            self._add_rule(r"\b[A-Za-z-]+\s*:", attr_fmt)  # properties
            self._add_rule(r":\s*[^;]+;", str_fmt)  # crude property values
            self._add_rule(r"/\*.*\*/", comment_fmt)

        elif lang in ("json",):
            self._add_rule(r"\"(\\.|[^\"])*\"(?=\s*:)", attr_fmt)
            self._add_rule(r"\"(\\.|[^\"])*\"", html_str_fmt)
            self._add_rule(r"\b(true|false|null)\b", kw_fmt)
            self._add_rule(r"\b\d+(\.\d+)?\b", num_fmt)

        elif lang in ("xml",):
            self._add_rule(r"</?[A-Za-z][^>]*>", tag_fmt)
            self._add_rule(r"\".*?\"", html_str_fmt)

        else:
            # generic: highlight strings, numbers, comments starting with // or #
            self._add_rule(r"\".*?\"", str_fmt)
            self._add_rule(r"'.*?'", str_fmt)
            self._add_rule(r"\b\d+(\.\d+)?\b", num_fmt)
            self._add_rule(r"//.*", comment_fmt)
            self._add_rule(r"#.*", comment_fmt)

    def highlightBlock(self, text):
        # apply simple rules
        for expr, fmt in self.rules:
            it = expr.globalMatch(text)
            while it.hasNext():
                m = it.next()
                start = m.capturedStart()
                length = m.capturedLength()
                if start >= 0 and length > 0:
                    self.setFormat(start, length, fmt)

        # handle multi-line C-style comments if configured
        if self.multi_line_comment:
            startExpr, endExpr, fmt = self.multi_line_comment
            startIndex = 0
            if self.previousBlockState() != 1:
                match = startExpr.match(text)
                startIndex = match.capturedStart() if match.hasMatch() else -1
            else:
                startIndex = 0

            while startIndex >= 0:
                endMatch = endExpr.match(text, startIndex)
                if endMatch.hasMatch():
                    endIndex = endMatch.capturedEnd()
                    length = endIndex - startIndex
                    self.setFormat(startIndex, length, fmt)
                    startIndex = startExpr.match(text, endIndex).capturedStart() if startExpr.match(text,
                                                                                                    endIndex).hasMatch() else -1
                    self.setCurrentBlockState(0)
                else:
                    # comment continues to next block
                    self.setFormat(startIndex, len(text) - startIndex, fmt)
                    self.setCurrentBlockState(1)
                    startIndex = -1


# helper to map extension -> language and attach highlighter
def apply_syntax_highlighting(editor: QPlainTextEdit, filepath: str):
    if not filepath or not editor:
        return
    ext = Path(filepath).suffix.lower()
    mapping = {
        ".py": "python",
        ".pyw": "python",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".hpp": "cpp",
        ".java": "java",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".cs": "csharp",
        ".php": "php",
        ".html": "html",
        ".htm": "html",
        ".css": "css",
        ".json": "json",
        ".xml": "xml",
        ".sh": "generic",
        ".bash": "generic",
        ".ps1": "generic",
        ".rs": "cpp",  # rough for Rust
        ".go": "cpp",  # rough for Go
        ".swift": "cpp",
        ".kt": "java",
        ".kts": "java",
    }
    lang = mapping.get(ext, None)
    if not lang:
        # not a recognized code file -> remove any existing highlighter (if any)
        # If editor has attribute 'highlighter', delete to allow GC and disable highlighting.
        if hasattr(editor, "highlighter"):
            try:
                del editor.highlighter
            except Exception:
                pass
        return
    # attach highlighter to editor (store on attribute so it isn't garbage-collected)
    try:
        editor.highlighter = CodeHighlighter(editor.document(), lang)
    except Exception:
        # safe fallback: ignore failures
        pass


# FIX: Custom QPlainTextEdit with proper Ctrl+Wheel zoom handling
class ZoomablePlainTextEdit(QPlainTextEdit):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app

    def wheelEvent(self, event):
        # Check if Ctrl is held - handle zoom
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.app.zoom_in_editor(self)
            else:
                self.app.zoom_out_editor(self)
            # Accept the event to prevent any scroll handling
            event.accept()
            return
        # Normal scroll behavior when Ctrl not held
        super().wheelEvent(event)


# ---------- Tabs ----------
class ModernTabBar(QTabBar):
    def tabSizeHint(self, index):
        s = super().tabSizeHint(index)
        if self.tabData(index) == "plus":
            return QSize(38, s.height())
        return s

    def mouseReleaseEvent(self, event: QMouseEvent):
        idx = self.tabAt(event.position().toPoint())
        if idx == self.count() - 1:
            if hasattr(self.parent_widget, "insert_new_tab"):
                self.parent_widget.insert_new_tab()
            return
        if event.button() == Qt.MiddleButton:
            if hasattr(self.parent_widget, "close_tab"):
                self.parent_widget.close_tab(idx)
            return
        super().mouseReleaseEvent(event)


class ModernTabWidget(QTabWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setTabBar(ModernTabBar())
        self.tabBar().parent_widget = self
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self.close_tab)
        self.setCornerWidget(QWidget(), Qt.BottomRightCorner)
        self.add_plus_tab()
        self.currentChanged.connect(self.on_tab_changed)

    def add_plus_tab(self):
        plus = QWidget()
        self.addTab(plus, "")
        icon = QIcon.fromTheme("list-add")
        self.setTabIcon(self.count() - 1, icon)
        self.tabBar().setTabText(self.count() - 1, "")
        self.tabBar().setTabData(self.count() - 1, "plus")
        self.tabBar().setTabButton(self.count() - 1, QTabBar.RightSide, None)

    def insert_new_tab(self, text="", title="Untitled"):
        cont = QWidget()
        layout = QVBoxLayout(cont)
        layout.setContentsMargins(2, 2, 2, 2)
        # FIX: Use ZoomablePlainTextEdit instead of QPlainTextEdit
        editor = ZoomablePlainTextEdit(self.app)
        editor.setPlainText(str(text))
        editor.setFont(QFont("Consolas", 11))

        try:
            editor.cursorPositionChanged.connect(lambda: self.app.update_status(editor))
        except Exception:
            pass
        layout.addWidget(editor)
        cont.setLayout(layout)
        cont.setProperty("filepath", None)
        idx = self.count() - 1
        self.insertTab(idx, cont, title)
        self.setCurrentIndex(idx)
        self.app.update_status(editor)
        self.app.update_window_title(idx)

    def close_tab(self, index):
        if index == self.count() - 1:
            return
        editor = self.get_editor(index)
        if editor and editor.document().isModified():
            choice = QMessageBox.question(self.app.window, "Unsaved Changes",
                                          "Save changes before closing?",
                                          QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if choice == QMessageBox.Yes:
                self.app.save_file(index)
            elif choice == QMessageBox.Cancel:
                return
        self.removeTab(index)
        self.app.update_status()
        self.app.update_window_title()

    def get_editor(self, index=None):
        if index is None:
            index = self.currentIndex()
        w = self.widget(index)
        if w:
            return w.findChild(QPlainTextEdit)
        return None

    def on_tab_changed(self, index):
        ed = self.get_editor(index)
        self.app.update_status(ed)
        self.app.update_window_title(index)


# ---------- UI loader / dialog helpers ----------
loader = QUiLoader()


def load_ui(path, parent=None):
    f = QFile(str(path))
    if not f.open(QFile.ReadOnly):
        raise FileNotFoundError(f"Cannot open UI file: " + str(path))
    w = loader.load(f, parent)
    f.close()
    if w is None:
        raise RuntimeError(f"QUiLoader failed to load {path}")
    return w


class DialogLoader:
    def __init__(self, parent, loader: QUiLoader):
        self.parent = parent
        self.loader = loader

    def load_settings_dialog(self):
        ui_path = resource_path("Themes.ui")
        if os.path.exists(ui_path):
            f = QFile(ui_path)
            if f.open(QFile.ReadOnly):
                dlg = self.loader.load(f, self.parent)
                f.close()
                combo = dlg.findChild(QComboBox, "TcomboBox") or dlg.findChild(QComboBox, "comboBox") or dlg.findChild(
                    QComboBox)
                return dlg, combo
        # fallback
        dlg = QDialog(self.parent)
        combo = QComboBox(dlg)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dlg)
        h = QHBoxLayout()
        h.addWidget(QLabel("Themes"))
        h.addWidget(combo)
        v = QVBoxLayout(dlg)
        v.addLayout(h)
        v.addWidget(box)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        return dlg, combo

    def load_replace_dialog(self):
        ui_path = resource_path("Replace.ui")
        if os.path.exists(ui_path):
            f = QFile(ui_path)
            if f.open(QFile.ReadOnly):
                dlg = self.loader.load(f, self.parent)
                f.close()
                # flexible lookups
                find_edit = dlg.findChild(QLineEdit, "lineEdit") or dlg.findChild(QLineEdit, "ReplacelineEdit") or None
                with_edit = dlg.findChild(QLineEdit, "lineEdit_2") or dlg.findChild(QLineEdit, "WithlineEdit") or None
                if (find_edit is None) or (with_edit is None):
                    edits = dlg.findChildren(QLineEdit)
                    if len(edits) >= 2:
                        find_edit, with_edit = edits[0], edits[1]
                return dlg, find_edit, with_edit
        # fallback (we will often use our custom dialog instead)
        return None, None, None

    def load_find_dialog(self, ui_name="Find.ui"):
        ui_path = resource_path(ui_name)
        if os.path.exists(ui_path):
            f = QFile(ui_path)
            if f.open(QFile.ReadOnly):
                dlg = self.loader.load(f, self.parent)
                f.close()
                le = dlg.findChild(QLineEdit, "lineEdit") or dlg.findChild(QLineEdit)
                return dlg, le
        return None, None


# ---------- Main app ----------
class NotepadApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.loader = loader
        self.dialogs = DialogLoader(None, loader)

        # encoding default
        self.current_theme = "atom_one"
        self.current_encoding = "UTF-8"
        self.load_settings()
        # try applying theme early
        self.apply_theme(self.current_theme)

        # load Main.ui (fallback minimal)
        main_ui_path = resource_path("Main.ui")
        if os.path.exists(main_ui_path):
            self.window = load_ui(main_ui_path)
        else:
            from PySide6.QtWidgets import QMainWindow, QMenuBar
            mw = QMainWindow()
            central = QWidget()
            mw.setCentralWidget(central)
            mw.setMenuBar(QMenuBar())
            mw.setStatusBar(QStatusBar())
            mw.resize(900, 600)
            self.window = mw

        self.dialogs.parent = self.window

        # replace QTabWidget with ModernTabWidget
        old_tab = self.window.findChild(QTabWidget, "tabWidget")
        self.tab_widget = ModernTabWidget(self)
        if old_tab is not None:
            parent_layout = old_tab.parentWidget().layout()
            if parent_layout:
                parent_layout.replaceWidget(old_tab, self.tab_widget)
                old_tab.setParent(None)
        else:
            central = getattr(self.window, "centralWidget", None)
            if central and central.layout():
                central.layout().addWidget(self.tab_widget)

        # statusbar & permanent labels
        self.statusbar = getattr(self.window, "statusbar", None) or self.window.findChild(
            QStatusBar) or self.window.statusBar()
        if self.statusbar is None:
            self.statusbar = QStatusBar()
            try:
                self.window.setStatusBar(self.statusbar)
            except Exception:
                pass

        self.lbl_left = QLabel("Ln:1 Col:1 Ch:0")
        self.lbl_zoom = QLabel("100%")
        self.lbl_enc = QLabel(self.current_encoding)
        self.statusbar.addWidget(self.lbl_left, 1)
        self.statusbar.addPermanentWidget(self.lbl_zoom)
        self.statusbar.addPermanentWidget(self.lbl_enc)

        # wire actions / features
        self.connect_actions()

        # drag & drop
        self.window.setAcceptDrops(True)
        self.window.dragEnterEvent = self.dragEnterEvent
        self.window.dropEvent = self.dropEvent

        # start with one tab
        self.tab_widget.insert_new_tab()
        self.window.setWindowTitle("Untitled - Notepad")
        self.window.show()

        # ensure encoding label reflects loaded value
        self.lbl_enc.setText(self.current_encoding)

    # drag & drop handling
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if os.path.isfile(path):
                    self._load_file_into_tab(path)
                    break
        event.acceptProposedAction()

    # settings persistence
    def load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    self.current_theme = data.get("theme", self.current_theme)
                    self.current_encoding = data.get("encoding", self.current_encoding)
        except Exception:
            pass

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
                json.dump({"theme": self.current_theme, "encoding": self.current_encoding}, fh, indent=2)
        except Exception:
            pass

    # theme application
    def apply_theme(self, theme_name):
        self.setStyleSheet("")
        local_file = Path(THEMES_FOLDER) / theme_name
        local_qss = Path(THEMES_FOLDER) / f"{theme_name}.qss"
        if local_file.exists() and local_file.suffix.lower() == ".qss":
            try:
                with open(local_file, "r", encoding="utf-8") as fh:
                    self.setStyleSheet(fh.read())
                    return True
            except Exception:
                pass
        if local_qss.exists():
            try:
                with open(local_qss, "r", encoding="utf-8") as fh:
                    self.setStyleSheet(fh.read())
                    return True
            except Exception:
                pass
        try:
            qt_themes.set_theme(theme_name)
            return True
        except Exception:
            try:
                import qt_themes as _qt
                pkg_dir = Path(_qt.__file__).parent
                candidates = list(pkg_dir.rglob(f"*{theme_name}*.qss"))
                if candidates:
                    with open(candidates[0], "r", encoding="utf-8") as fh:
                        self.setStyleSheet(fh.read())
                        return True
            except Exception:
                pass
            return False

    def _find_encoding_actions(self):
        acts = []
        for act in self.window.findChildren(QAction):
            if not act:
                continue
            name = (act.objectName() or "").lower()
            text = (act.text() or "").lower()
            if "utf" in name or "utf" in text:
                acts.append(act)
        return acts

    # connect actions
    def connect_actions(self):
        w = self.window

        def a(name):
            return w.findChild(QAction, name)

        # File
        if a("actionNew"): a("actionNew").triggered.connect(lambda: self.tab_widget.insert_new_tab())
        if a("actionOpen"): a("actionOpen").triggered.connect(self.open_file)
        if a("actionSave"): a("actionSave").triggered.connect(lambda: self.save_file())
        if a("actionSave_As"): a("actionSave_As").triggered.connect(lambda: self.save_file_as())
        if a("actionSave_All"): a("actionSave_All").triggered.connect(self.save_all)
        if a("actionPrint"): a("actionPrint").triggered.connect(self.print_file)
        if a("actionQuit"): a("actionQuit").triggered.connect(self.exit_app)
        if a("actionExit"): a("actionExit").triggered.connect(self.exit_app)

        # Edit / Find / Replace
        if a("actionFind"): a("actionFind").triggered.connect(self.find_text)
        if a("actionFind_Next"): a("actionFind_Next").triggered.connect(self.find_next)
        if a("actionFind_Previous"): a("actionFind_Previous").triggered.connect(self.find_previous)
        if a("actionReplace"): a("actionReplace").triggered.connect(self.replace_text)

        # Zoom
        if a("actionZoom_In"): a("actionZoom_In").triggered.connect(lambda: self.zoom_in_current(1))
        if a("actionZoom_Out"): a("actionZoom_Out").triggered.connect(lambda: self.zoom_out_current(1))
        if a("actionReset_Zoom"): a("actionReset_Zoom").triggered.connect(self.reset_zoom)

        # Settings / Themes
        settings_action = w.findChild(QAction, "actionSettings") or w.findChild(QAction, "actionThemes")
        if settings_action is None:
            settings_action = QAction("Themes", self.window)
            settings_action.setObjectName("actionThemes")
            settings_action.triggered.connect(self.open_settings)
            try:
                mb = w.menuBar()
                mb.addAction(settings_action)
            except Exception:
                pass
        else:
            settings_action.triggered.connect(self.open_settings)

        # Encoding actions
        enc_actions = self._find_encoding_actions()
        for act in enc_actions:
            try:
                act.setCheckable(True)
            except Exception:
                pass

            enc_text = (act.text() or "").strip()
            if not enc_text:
                enc_text = act.objectName().replace("action", "").replace("_", "-").strip()
            enc_text = enc_text or "UTF-8"

            try:
                act.triggered.connect(lambda checked, e=enc_text: self.set_encoding(e))
            except Exception:
                pass

        self._sync_encoding_action_checks()

        # fullscreen & always-on-top
        full_action = a("actionFullscreen") or a("actionFullScreen") or a("action_fullscreen")
        if full_action:
            full_action.triggered.connect(self.toggle_fullscreen)
        top_action = a("actionAlways_on_Top") or a("actionAlwaysOnTop") or a("action_always_on_top")
        if top_action:
            top_action.triggered.connect(self.toggle_always_on_top)

    def _sync_encoding_action_checks(self):
        enc_actions = self._find_encoding_actions()
        for act in enc_actions:
            enc_text = (act.text() or "").strip()
            if not enc_text:
                enc_text = act.objectName().replace("action", "").replace("_", "-").strip()
            try:
                act.setChecked(enc_text == self.current_encoding)
            except Exception:
                try:
                    act.setChecked(enc_text.lower() == self.current_encoding.lower())
                except Exception:
                    pass
        try:
            self.lbl_enc.setText(self.current_encoding)
        except Exception:
            pass

    def open_settings(self):
        dlg, combo = self.dialogs.load_settings_dialog()
        if combo is None:
            QMessageBox.information(self.window, "Themes",
                                    "Themes UI missing comboBox widget.")
            return

        themes = []
        try:
            themes = list(qt_themes.list_themes())
        except Exception:
            themes = []
        builtin_defaults = [
            "one_dark_two", "monokai", "nord",
            "catppuccin_latte", "catppuccin_frappe", "catppuccin_macchiato", "catppuccin_mocha",
            "atom_one", "github_dark", "github_light", "dracula"
        ]
        for d in builtin_defaults:
            if d not in themes:
                themes.append(d)
        if os.path.isdir(THEMES_FOLDER):
            for f in sorted(os.listdir(THEMES_FOLDER)):
                if f.lower().endswith((".qss", ".json")) and f not in themes:
                    themes.append(f)

        combo.clear()
        combo.addItems(themes)
        idx = combo.findText(self.current_theme)
        if idx >= 0:
            combo.setCurrentIndex(idx)

        bb = dlg.findChild(QDialogButtonBox, "buttonBox")
        if bb is None:
            res = dlg.exec()
            if res == QDialog.Accepted:
                chosen = combo.currentText()
                self._apply_chosen_theme(chosen)
            return

        try:
            bb.accepted.disconnect()
        except Exception:
            pass

        ok_btn = bb.button(QDialogButtonBox.Ok)
        if ok_btn:
            try:
                ok_btn.clicked.disconnect()
            except Exception:
                pass

            def on_ok_clicked():
                chosen = combo.currentText()
                self._apply_chosen_theme(chosen)
                dlg.accept()

            ok_btn.clicked.connect(on_ok_clicked)

        cancel_btn = bb.button(QDialogButtonBox.Cancel)
        if cancel_btn:
            try:
                cancel_btn.clicked.disconnect()
            except Exception:
                pass
            cancel_btn.clicked.connect(dlg.reject)

        dlg.setWindowTitle("Themes")
        dlg.exec()

    def _apply_chosen_theme(self, chosen):
        if not chosen:
            return
        if "." in chosen:
            p = Path(THEMES_FOLDER) / chosen
            if p.exists() and p.suffix.lower() == ".qss":
                try:
                    with open(p, "r", encoding="utf-8") as fh:
                        self.setStyleSheet(fh.read())
                    self.current_theme = chosen
                    self.save_settings()
                    self.show_status(f"Applied theme {chosen}")
                    return
                except Exception:
                    QMessageBox.warning(self.window, "Theme", f"Failed to apply theme file {chosen}")
                    return
            elif p.exists() and p.suffix.lower() == ".json":
                QMessageBox.information(self.window, "Theme",
                                        f"'{chosen}' is a JSON theme — not applied automatically.")
                return
            else:
                QMessageBox.warning(self.window, "Theme", f"Theme file {chosen} not found")
                return

        local_qss = Path(THEMES_FOLDER) / f"{chosen}.qss"
        if local_qss.exists():
            try:
                with open(local_qss, "r", encoding="utf-8") as fh:
                    self.setStyleSheet(fh.read())
                self.current_theme = chosen
                self.save_settings()
                self.show_status(f"Applied local theme {chosen}")
                return
            except Exception:
                pass

        applied = self.apply_theme(chosen)
        if applied:
            self.current_theme = chosen
            self.save_settings()
            self.show_status(f"Applied builtin theme {chosen}")
            return

        ans = QMessageBox.question(self.window, "Theme not found",
                                   f"Builtin theme '{chosen}' isn't available.\nSelect a .qss file?",
                                   QMessageBox.Yes | QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        qpath, _ = QFileDialog.getOpenFileName(self.window, "Select .qss", str(HERE),
                                               "Style Sheets (*.qss);;All Files (*)")
        if not qpath:
            return
        try:
            with open(qpath, "r", encoding="utf-8") as fh:
                self.setStyleSheet(fh.read())
            Path(THEMES_FOLDER).mkdir(exist_ok=True)
            dest = Path(THEMES_FOLDER) / Path(qpath).name
            if not dest.exists():
                copyfile(qpath, dest)
            self.current_theme = chosen
            self.save_settings()
            self.show_status(f"Applied theme from {qpath}")
        except Exception as e:
            QMessageBox.warning(self.window, "Theme", f"Failed to apply qss: {e}")

    def replace_text(self):
        ui_dlg, ui_find, ui_with = self.dialogs.load_replace_dialog()

        dlg = QDialog(self.window)
        dlg.setWindowTitle("Replace")
        find_le = QLineEdit()
        rep_le = QLineEdit()
        if ui_find and ui_with:
            try:
                find_le.setText(ui_find.text())
                rep_le.setText(ui_with.text())
            except Exception:
                pass

        replace_btn = QPushButton("Replace")
        replace_all_btn = QPushButton("Replace All")
        close_btn = QPushButton("Close")

        form = QHBoxLayout()
        form.addWidget(QLabel("Find:"))
        form.addWidget(find_le)
        form.addWidget(QLabel("With:"))
        form.addWidget(rep_le)

        btns = QHBoxLayout()
        btns.addWidget(replace_btn)
        btns.addWidget(replace_all_btn)
        btns.addWidget(close_btn)

        v = QVBoxLayout(dlg)
        v.addLayout(form)
        v.addLayout(btns)

        replace_btn.clicked.connect(lambda: self._do_replace_dialog(find_le, rep_le))
        replace_all_btn.clicked.connect(lambda: self._do_replace_all(find_le, rep_le))
        close_btn.clicked.connect(dlg.reject)

        dlg.exec()

    def _do_replace_dialog(self, find_le, rep_le):
        find_text = find_le.text()
        rep_text = rep_le.text()
        if not find_text:
            return
        ed = self.tab_widget.get_editor()
        if not ed:
            return

        cursor = ed.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == find_text:
            cursor.insertText(rep_text)
            ed.setTextCursor(cursor)
            if not ed.find(find_text):
                tmp = ed.textCursor()
                tmp.movePosition(QTextCursor.Start)
                ed.setTextCursor(tmp)
                if not ed.find(find_text):
                    QMessageBox.information(self.window, "Replace", f"No more occurrences of '{find_text}'")
            return

        if ed.find(find_text):
            c = ed.textCursor()
            c.insertText(rep_text)
            if not ed.find(find_text):
                tmp = ed.textCursor()
                tmp.movePosition(QTextCursor.Start)
                ed.setTextCursor(tmp)
                if not ed.find(find_text):
                    QMessageBox.information(self.window, "Replace", f"No more occurrences of '{find_text}'")
            return

        QMessageBox.information(self.window, "Replace", f"'{find_text}' not found")

    def _do_replace_all(self, find_le, rep_le):
        find_text = find_le.text()
        rep_text = rep_le.text()
        if not find_text:
            return
        ed = self.tab_widget.get_editor()
        if not ed:
            return

        cursor = ed.textCursor()
        cursor.movePosition(QTextCursor.Start)
        ed.setTextCursor(cursor)
        replaced_any = False
        while ed.find(find_text):
            c = ed.textCursor()
            c.insertText(rep_text)
            replaced_any = True

        if not replaced_any:
            QMessageBox.information(self.window, "Replace All", f"No occurrences of '{find_text}' found")
        else:
            QMessageBox.information(self.window, "Replace All", "Replace All complete")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self.window, "Open File", str(HERE),
                                              "Text Files (*.txt *.py *.cpp *.c *.h *.js *.java *.php *.html);;All Files (*)")
        if not path:
            return
        self._load_file_into_tab(path)

    def _load_file_into_tab(self, path):
        try:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    content = fh.read()
            except Exception:
                with open(path, "r", encoding="latin-1", errors="replace") as fh:
                    content = fh.read()
        except Exception as e:
            QMessageBox.warning(self.window, "Open failed", str(e))
            return
        replaced = False
        for i in range(self.tab_widget.count() - 1):
            w = self.tab_widget.widget(i)
            title = self.tab_widget.tabText(i)
            ed = self.tab_widget.get_editor(i)
            if title == "Untitled" and ed and ed.toPlainText() == "":
                ed.setPlainText(content)
                w.setProperty("filepath", path)
                self.tab_widget.setTabText(i, os.path.basename(path))
                self.tab_widget.setCurrentIndex(i)
                apply_syntax_highlighting(ed, path)
                replaced = True
                break
        if not replaced:
            self.tab_widget.insert_new_tab(content, os.path.basename(path))
            idx = self.tab_widget.currentIndex()
            self.tab_widget.widget(idx).setProperty("filepath", path)
            ed = self.tab_widget.get_editor(idx)
            apply_syntax_highlighting(ed, path)
        self.update_window_title()

    def save_file(self, index=None):
        if index is None:
            index = self.tab_widget.currentIndex()
        w = self.tab_widget.widget(index)
        if w is None:
            return
        ed = self.tab_widget.get_editor(index)
        path = w.property("filepath")
        if not path:
            return self.save_file_as(index)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(ed.toPlainText())
            ed.document().setModified(False)
            self.show_status(f"Saved {os.path.basename(path)}")
            self.update_window_title(index)
        except Exception as e:
            QMessageBox.warning(self.window, "Save failed", str(e))

    def save_file_as(self, index=None):
        if index is None:
            index = self.tab_widget.currentIndex()
        w = self.tab_widget.widget(index)
        if w is None:
            return
        ed = self.tab_widget.get_editor(index)
        path, _ = QFileDialog.getSaveFileName(self.window, "Save As", str(HERE), "Text Files (*.txt);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(ed.toPlainText())
            w.setProperty("filepath", path)
            self.tab_widget.setTabText(index, os.path.basename(path))
            ed.document().setModified(False)
            apply_syntax_highlighting(ed, path)
            self.show_status(f"Saved as {os.path.basename(path)}")
            self.update_window_title(index)
        except Exception as e:
            QMessageBox.warning(self.window, "Save failed", str(e))

    def save_all(self):
        for i in range(self.tab_widget.count() - 1):
            self.save_file(i)

    def find_text(self):
        dlg, le = self.dialogs.load_find_dialog("Find.ui")
        if dlg and le:
            dlg.setWindowTitle("Find")
            bb = dlg.findChild(QDialogButtonBox, "buttonBox")
            if bb:
                try:
                    bb.accepted.disconnect()
                except Exception:
                    pass
                ok_btn = bb.button(QDialogButtonBox.Ok)
                if ok_btn:
                    try:
                        ok_btn.clicked.disconnect()
                    except Exception:
                        pass
                    ok_btn.clicked.connect(lambda: self._do_find(le, forward=True))
                cancel_btn = bb.button(QDialogButtonBox.Cancel)
                if cancel_btn:
                    try:
                        cancel_btn.clicked.disconnect()
                    except Exception:
                        pass
                    cancel_btn.clicked.connect(dlg.reject)
            dlg.exec()
            return

        ed = self.tab_widget.get_editor()
        if not ed:
            return
        text, ok = QInputDialog.getText(self.window, "Find", "Text to find:")
        if not ok or not text:
            return
        found = ed.find(text)
        if not found:
            cursor = ed.textCursor()
            cursor.movePosition(QTextCursor.Start)
            ed.setTextCursor(cursor)
            if not ed.find(text):
                QMessageBox.information(self.window, "Find", f"'{text}' not found.")

    def find_next(self):
        dlg, le = self.dialogs.load_find_dialog("FindNext.ui")
        if dlg and le:
            dlg.setWindowTitle("Find Next")
            bb = dlg.findChild(QDialogButtonBox, "buttonBox")
            if bb:
                try:
                    bb.accepted.disconnect()
                except Exception:
                    pass
                ok_btn = bb.button(QDialogButtonBox.Ok)
                if ok_btn:
                    try:
                        ok_btn.clicked.disconnect()
                    except Exception:
                        pass
                    ok_btn.clicked.connect(lambda: self._do_find(le, forward=True))
                cancel_btn = bb.button(QDialogButtonBox.Cancel)
                if cancel_btn:
                    try:
                        cancel_btn.clicked.disconnect()
                    except Exception:
                        pass
                    cancel_btn.clicked.connect(dlg.reject)
            dlg.exec()
            return
        ed = self.tab_widget.get_editor()
        if not ed:
            return
        text, ok = QInputDialog.getText(self.window, "Find Next", "Text to find:")
        if not ok or not text:
            return
        if not ed.find(text):
            cursor = ed.textCursor()
            cursor.movePosition(QTextCursor.Start)
            ed.setTextCursor(cursor)
            if not ed.find(text):
                QMessageBox.information(self.window, "Find Next", f"'{text}' not found.")

    def find_previous(self):
        dlg, le = self.dialogs.load_find_dialog("FindPrev.ui")
        if dlg and le:
            dlg.setWindowTitle("Find Previous")
            bb = dlg.findChild(QDialogButtonBox, "buttonBox")
            if bb:
                try:
                    bb.accepted.disconnect()
                except Exception:
                    pass
                ok_btn = bb.button(QDialogButtonBox.Ok)
                if ok_btn:
                    try:
                        ok_btn.clicked.disconnect()
                    except Exception:
                        pass
                    ok_btn.clicked.connect(lambda: self._do_find(le, forward=False))
                cancel_btn = bb.button(QDialogButtonBox.Cancel)
                if cancel_btn:
                    try:
                        cancel_btn.clicked.disconnect()
                    except Exception:
                        pass
                    cancel_btn.clicked.connect(dlg.reject)
            dlg.exec()
            return
        ed = self.tab_widget.get_editor()
        if not ed:
            return
        text, ok = QInputDialog.getText(self.window, "Find Previous", "Text to find:")
        if not ok or not text:
            return
        full = ed.toPlainText()
        cursor = ed.textCursor()
        pos = cursor.selectionStart() if cursor.hasSelection() else cursor.position()
        idx = full.rfind(text, 0, max(0, pos - 1))
        if idx == -1:
            QMessageBox.information(self.window, "Find Previous", f"'{text}' not found")
            return
        new_cursor = ed.textCursor()
        new_cursor.setPosition(idx)
        new_cursor.setPosition(idx + len(text), mode=QTextCursor.KeepAnchor)
        ed.setTextCursor(new_cursor)

    def _do_find(self, line_edit, forward=True):
        if not line_edit:
            return
        text = line_edit.text()
        if not text:
            return
        ed = self.tab_widget.get_editor()
        if not ed:
            return
        if forward:
            found = ed.find(text)
            if not found:
                cursor = ed.textCursor()
                cursor.movePosition(QTextCursor.Start)
                ed.setTextCursor(cursor)
                if not ed.find(text):
                    QMessageBox.information(self.window, "Find", f"'{text}' not found")
        else:
            full = ed.toPlainText()
            cursor = ed.textCursor()
            pos = cursor.selectionStart() if cursor.hasSelection() else cursor.position()
            idx = full.rfind(text, 0, max(0, pos - 1))
            if idx == -1:
                idx = full.rfind(text)
                if idx == -1:
                    QMessageBox.information(self.window, "Find Previous", f"'{text}' not found")
                    return
            new_cursor = ed.textCursor()
            new_cursor.setPosition(idx)
            new_cursor.setPosition(idx + len(text), mode=QTextCursor.KeepAnchor)
            ed.setTextCursor(new_cursor)

    def update_status(self, editor=None):
        editor = editor or self.tab_widget.get_editor()
        if editor:
            c = editor.textCursor()
            line = c.blockNumber() + 1
            col = c.columnNumber() + 1
            chars = len(editor.toPlainText())
            try:
                self.lbl_left.setText(f"Ln:{line} Col:{col} Ch:{chars}")
            except Exception:
                pass
        else:
            try:
                self.lbl_left.setText("Ln:1 Col:1 Ch:0")
            except Exception:
                pass

    def show_status(self, message, timeout=5000):
        try:
            self.statusbar.showMessage(message, timeout)
        except Exception:
            pass

    def update_window_title(self, index=None):
        if index is None:
            index = self.tab_widget.currentIndex()
        w = self.tab_widget.widget(index)
        if w is None:
            self.window.setWindowTitle("Notepad")
            return
        path = w.property("filepath")
        if path:
            name = os.path.basename(path)
        else:
            name = self.tab_widget.tabText(index)
        self.window.setWindowTitle(f"{name} - Notepad")

    def zoom_in_editor(self, editor, step=1):
        if not editor:
            return
        f = editor.font()
        size = max(6, f.pointSize() + step)
        f.setPointSize(size)
        editor.setFont(f)
        if editor == self.tab_widget.get_editor():
            self.lbl_zoom.setText(f"{round(size / 11 * 100)}%")

    def zoom_out_editor(self, editor, step=1):
        if not editor:
            return
        f = editor.font()
        size = max(6, f.pointSize() - step)
        f.setPointSize(size)
        editor.setFont(f)
        if editor == self.tab_widget.get_editor():
            self.lbl_zoom.setText(f"{round(size / 11 * 100)}%")

    def zoom_in_current(self, step=1):
        ed = self.tab_widget.get_editor()
        self.zoom_in_editor(ed, step)

    def zoom_out_current(self, step=1):
        ed = self.tab_widget.get_editor()
        self.zoom_out_editor(ed, step)

    def reset_zoom(self):
        ed = self.tab_widget.get_editor()
        if not ed:
            return
        f = ed.font()
        f.setPointSize(11)
        ed.setFont(f)
        self.lbl_zoom.setText("100%")

    def toggle_fullscreen(self):
        if self.window.isFullScreen():
            self.window.showNormal()
        else:
            self.window.showFullScreen()

    def toggle_always_on_top(self):
        current = bool(self.window.windowFlags() & Qt.WindowStaysOnTopHint)
        self.window.setWindowFlag(Qt.WindowStaysOnTopHint, not current)
        self.window.show()

    def print_file(self):
        ed = self.tab_widget.get_editor()
        if not ed:
            return
        printer = QPrinter()
        dlg = QPrintDialog(printer, self.window)
        if dlg.exec() == QDialog.Accepted:
            ed.print(printer)

    def set_encoding(self, encoding_name):
        if not encoding_name:
            return
        encoding_name = encoding_name.replace("&", "").strip()
        self.current_encoding = encoding_name
        enc_actions = self._find_encoding_actions()
        for act in enc_actions:
            enc_text = (act.text() or "").strip()
            if not enc_text:
                enc_text = act.objectName().replace("action", "").replace("_", "-").strip()
            try:
                act.setChecked(enc_text == self.current_encoding)
            except Exception:
                try:
                    act.setChecked(enc_text.lower() == self.current_encoding.lower())
                except Exception:
                    pass
        try:
            self.lbl_enc.setText(self.current_encoding)
        except Exception:
            pass
        self.save_settings()

    def exit_app(self):
        unsaved = False
        for i in range(self.tab_widget.count() - 1):
            ed = self.tab_widget.get_editor(i)
            if ed and ed.document().isModified():
                unsaved = True
                break
        if unsaved:
            c = QMessageBox.question(self.window, "Exit", "You have unsaved changes. Exit anyway?",
                                     QMessageBox.Yes | QMessageBox.No)
            if c == QMessageBox.No:
                return
        self.quit()


if __name__ == "__main__":
    app = NotepadApp(sys.argv)
    sys.exit(app.exec())
