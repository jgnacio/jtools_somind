#!/usr/bin/env python3
"""somind — fast task manager with Textual TUI"""

import json
import os
import re
import sys
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.coordinate import Coordinate
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

STORAGE_PATH = os.path.expanduser("~/.sotaks")

# ── backend ───────────────────────────────────────────────────────────────────

def load_tasks():
    if not os.path.exists(STORAGE_PATH):
        return []
    try:
        with open(STORAGE_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def save_tasks(tasks):
    with open(STORAGE_PATH, "w") as f:
        json.dump(tasks, f, indent=2)


def parse_deadline(d_str):
    if not d_str or d_str == "N/A":
        return "N/A"
    if len(d_str) > 10 and "/" in d_str:
        return d_str
    try:
        clean = d_str.replace("-d", "").strip()
        if len(clean) != 4:
            return d_str
        month = int(clean[:2])
        day = int(clean[2:4])
        now = datetime.now()
        target = datetime(now.year, month, day, 23, 59)
        if target < now:
            target = target.replace(year=now.year + 1)
        return target.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return d_str


def get_remaining_rich(deadline_str: str, done: bool = False) -> str:
    if done:
        return "[#2a2a44]Completado[/#2a2a44]"
    if deadline_str == "N/A":
        return "[#2a2a44]Sin límite[/#2a2a44]"
    try:
        dt = datetime.strptime(deadline_str, "%d/%m/%Y %H:%M")
        diff = dt - datetime.now()
        if diff.total_seconds() < 0:
            return "[bold #ff2d6b blink]¡VENCIDA![/bold #ff2d6b blink]"
        days = diff.days
        hours, rem = divmod(diff.seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        s = f"{days}d {hours:02}h {minutes:02}m {seconds:02}s"
        if diff.total_seconds() < 86_400:
            return f"[bold #ff2d6b]{s}[/bold #ff2d6b]"
        elif diff.total_seconds() < 259_200:
            return f"[#ffe000]{s}[/#ffe000]"
        return f"[#00ffcc]{s}[/#00ffcc]"
    except Exception:
        return "[#ff2d6b]Formato inválido[/#ff2d6b]"


# priority: 0 = none, 1 = high, 2 = medium
PRIORITY_CYCLE = {0: 1, 1: 2, 2: 0}
PRIORITY_LABEL = {
    1: "[bold #ff2d6b]▲▲[/bold #ff2d6b]",
    2: "[bold #ffe000]▲[/bold #ffe000]",
    0: "[#2a2a40]·[/#2a2a40]",
}
PRIORITY_SORT = {1: 0, 2: 1, 0: 2}

_KW_COLORS: dict[str, str] = {
    r"\bFIX\b":           "bold #ff2d6b",
    r"\bTESTING\b":       "bold #ffe000",
    r"\bFUNCIONALIDAD\b": "bold #cc44ff",
    r"\bTODO\b":          "bold #00f0ff",
    r"\bagregar\b":       "bold #00ffcc",
    r"\bAgregar\b":       "bold #00ffcc",
}


def highlight_task(text: str, is_done: bool = False) -> str:
    if is_done:
        return f"[#2a2a44 strike]{text}[/#2a2a44 strike]"
    result = text
    for pattern, style in _KW_COLORS.items():
        result = re.sub(
            pattern,
            lambda m, s=style: f"[{s}]{m.group(0)}[/{s}]",
            result,
        )
    return result


def get_visible_tasks() -> list[tuple[int, dict]]:
    tasks = load_tasks()
    now = datetime.now()
    modified = False
    for t in tasks:
        original = t.get("deadline", "N/A")
        fixed = parse_deadline(original)
        if original != fixed:
            t["deadline"] = fixed
            modified = True
    if modified:
        save_tasks(tasks)

    def should_show(task):
        if not task.get("done", False):
            return True
        completed_at = task.get("completed_at")
        if not completed_at:
            return True
        try:
            return (now - datetime.strptime(completed_at, "%Y-%m-%d %H:%M:%S")).days < 7
        except Exception:
            return True

    visible = [(i + 1, t) for i, t in enumerate(tasks) if should_show(t)]
    visible.sort(key=lambda x: (
        x[1].get("done", False),
        PRIORITY_SORT[x[1].get("priority", 0)],
        x[1].get("deadline") == "N/A",
    ))
    return visible


# ── modals ────────────────────────────────────────────────────────────────────

class AddTaskModal(ModalScreen):
    DEFAULT_CSS = """
    AddTaskModal {
        align: center middle;
        background: #080810 70%;
    }
    #dialog {
        padding: 1 2;
        background: #0d0d1e;
        border: double #00ffcc;
        width: 64;
        height: auto;
    }
    #title {
        margin-bottom: 1;
        color: #00ffcc;
        text-style: bold;
    }
    Input {
        margin-bottom: 1;
        background: #080810;
        color: #e0e0ff;
        border: tall #1e1e36;
    }
    Input:focus {
        border: tall #00ffcc;
    }
    #buttons {
        align-horizontal: right;
        margin-top: 1;
    }
    Button {
        margin-left: 1;
        border: none;
    }
    #cancel {
        background: #161628;
        color: #444466;
    }
    #cancel:hover {
        background: #1e1e38;
        color: #8888aa;
    }
    #confirm {
        background: #00332a;
        color: #00ffcc;
        text-style: bold;
    }
    #confirm:hover {
        background: #004438;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Nueva tarea", id="title")
            yield Input(placeholder="Descripción de la tarea...", id="task_input")
            yield Input(placeholder="Deadline opcional — formato MMDD (ej: 0430)", id="deadline_input")
            with Horizontal(id="buttons"):
                yield Button("Cancelar", variant="default", id="cancel")
                yield Button("Agregar", variant="primary", id="confirm")

    def on_mount(self) -> None:
        self.query_one("#task_input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
        else:
            self._submit()

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
        elif event.key == "enter" and isinstance(self.focused, Input):
            self._submit()

    def _submit(self) -> None:
        task_text = self.query_one("#task_input", Input).value.strip()
        deadline_raw = self.query_one("#deadline_input", Input).value.strip() or None
        if task_text:
            self.dismiss((task_text, deadline_raw))
        else:
            self.query_one("#task_input", Input).focus()


class ConfirmModal(ModalScreen):
    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
        background: #080810 70%;
    }
    #dialog {
        padding: 1 2;
        background: #0d0d1e;
        border: double #ff2d6b;
        width: 52;
        height: auto;
    }
    #msg {
        margin-bottom: 1;
        color: #e0e0ff;
    }
    #buttons {
        align-horizontal: right;
        margin-top: 1;
    }
    Button {
        margin-left: 1;
        border: none;
    }
    #cancel {
        background: #161628;
        color: #444466;
    }
    #cancel:hover {
        background: #1e1e38;
        color: #8888aa;
    }
    #confirm {
        background: #330011;
        color: #ff2d6b;
        text-style: bold;
    }
    #confirm:hover {
        background: #440022;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._message, id="msg")
            with Horizontal(id="buttons"):
                yield Button("Cancelar", variant="default", id="cancel")
                yield Button("Eliminar", variant="error", id="confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)


# ── main app ──────────────────────────────────────────────────────────────────

class SomindApp(App):
    TITLE = "somind"
    SUB_TITLE = "task manager"

    DEFAULT_CSS = """
    Screen {
        background: #080810;
    }

    Header {
        background: #080810;
        color: #00ffcc;
        text-style: bold;
        dock: top;
    }

    Footer {
        background: #0b0b18;
        dock: bottom;
    }

    Footer > .footer--key {
        background: #161628;
        color: #00ffcc;
        text-style: bold;
    }

    Footer > .footer--description {
        color: #333355;
    }

    Footer > .footer--highlight {
        background: #00332a;
        color: #00ffcc;
    }

    DataTable {
        height: 1fr;
        background: #080810;
        color: #c0c0d8;
    }

    DataTable > .datatable--header {
        background: #0e0e1e;
        color: #00ffcc;
        text-style: bold;
    }

    DataTable > .datatable--cursor {
        background: #002a20;
        color: #00ffcc;
        text-style: bold;
    }

    DataTable > .datatable--hover {
        background: #111122;
        color: #ffffff;
    }

    DataTable > .datatable--odd-row {
        background: #0a0a16;
    }

    DataTable > .datatable--even-row {
        background: #080810;
    }

    #status_bar {
        height: 1;
        background: #0b0b18;
        color: #333355;
        padding: 0 1;
        content-align: left middle;
    }
    """

    BINDINGS = [
        Binding("a", "add_task", "Agregar"),
        Binding("c", "complete_task", "Completar"),
        Binding("r", "remove_task", "Remover"),
        Binding("p", "toggle_priority", "Prioridad"),
        Binding("q", "quit", "Salir"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="tasks_table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="status_bar")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#tasks_table", DataTable)
        table.add_columns("ID", "P", "Tarea", "Deadline", "Faltan", "")
        self._rebuild_table()
        self.set_interval(1, self._tick)

    # called every second — only updates the time column, never touches cursor
    def _tick(self) -> None:
        table = self.query_one("#tasks_table", DataTable)
        if table.row_count == 0:
            return
        visible = get_visible_tasks()
        for row_idx, (_, t) in enumerate(visible):
            remaining = get_remaining_rich(t.get("deadline", "N/A"), t.get("done", False))
            try:
                table.update_cell_at(Coordinate(row_idx, 4), remaining, update_width=False)
            except Exception:
                pass

    # called after mutations (add / complete / remove)
    def _rebuild_table(self) -> None:
        table = self.query_one("#tasks_table", DataTable)
        table.clear()
        visible = get_visible_tasks()
        for orig_idx, t in visible:
            done = t.get("done", False)
            status = "[bold green]✔[/bold green]" if done else "[bold red]✘[/bold red]"
            deadline = t.get("deadline", "N/A")
            deadline_cell = f"[dim]{deadline}[/dim]" if done else deadline
            remaining = get_remaining_rich(deadline, done)
            task_cell = highlight_task(t.get("task", ""), is_done=done)
            priority_cell = PRIORITY_LABEL[t.get("priority", 0)]
            table.add_row(str(orig_idx), priority_cell, task_cell, deadline_cell, remaining, status, key=str(orig_idx))

        total = len(visible)
        done_count = sum(1 for _, t in visible if t.get("done", False))
        pending = total - done_count
        self.query_one("#status_bar", Static).update(
            f"[bold]{pending}[/bold] pendientes  ·  [dim]{done_count} completadas · {total} total[/dim]"
        )

    def _cursor_task_id(self) -> int | None:
        table = self.query_one("#tasks_table", DataTable)
        if table.row_count == 0:
            return None
        try:
            return int(str(table.get_row_at(table.cursor_row)[0]))
        except Exception:
            return None

    def action_add_task(self) -> None:
        def on_result(result):
            if result is None:
                return
            task_text, deadline_raw = result
            tasks = load_tasks()
            tasks.append({
                "task": task_text,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "deadline": parse_deadline(deadline_raw),
                "done": False,
            })
            save_tasks(tasks)
            self._rebuild_table()

        self.push_screen(AddTaskModal(), on_result)

    def action_complete_task(self) -> None:
        task_id = self._cursor_task_id()
        if task_id is None:
            return
        tasks = load_tasks()
        try:
            task = tasks[task_id - 1]
            if task.get("done", False):
                return
            task["done"] = True
            task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_tasks(tasks)
            self._rebuild_table()
        except Exception:
            pass

    def action_toggle_priority(self) -> None:
        task_id = self._cursor_task_id()
        if task_id is None:
            return
        tasks = load_tasks()
        try:
            t = tasks[task_id - 1]
            t["priority"] = PRIORITY_CYCLE[t.get("priority", 0)]
            save_tasks(tasks)
            self._rebuild_table()
        except Exception:
            pass

    def action_remove_task(self) -> None:
        task_id = self._cursor_task_id()
        if task_id is None:
            return
        tasks = load_tasks()
        try:
            preview = tasks[task_id - 1].get("task", "")[:50]
        except Exception:
            return

        def on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            t = load_tasks()
            try:
                t.pop(task_id - 1)
                save_tasks(t)
                self._rebuild_table()
            except Exception:
                pass

        self.push_screen(
            ConfirmModal(f"¿Eliminar tarea [bold]#{task_id}[/bold]?\n[dim]{preview}[/dim]"),
            on_confirm,
        )


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args:
        SomindApp().run()
        return

    deadline_val = None
    action = None
    task_desc = ""
    target_id = None

    i = 0
    while i < len(args):
        if args[i].startswith("-d"):
            deadline_val = args[i][2:] if len(args[i]) > 2 else args[i + 1]
            if len(args[i]) <= 2:
                i += 1
        elif args[i] == "-a":
            action = "add"
            task_desc = " ".join(args[i + 1:])
            break
        elif args[i] == "-c":
            action = "complete"
            if i + 1 < len(args):
                target_id = int(args[i + 1])
        elif args[i] == "-r":
            action = "remove"
            if i + 1 < len(args):
                target_id = int(args[i + 1])
        elif args[i] == "-l":
            action = "list_once"
        elif args[i] == "-rall":
            action = "remove_all"
        i += 1

    if action == "add":
        tasks = load_tasks()
        dt = parse_deadline(deadline_val)
        tasks.append({
            "task": task_desc,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "deadline": dt,
            "done": False,
        })
        save_tasks(tasks)
        print(f"✅ Tarea añadida: {task_desc} (deadline: {dt})")

    elif action == "complete":
        tasks = load_tasks()
        try:
            tasks[target_id - 1]["done"] = True
            tasks[target_id - 1]["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_tasks(tasks)
            print(f"🔥 Tarea {target_id} completada.")
        except Exception:
            print("ID inválido")

    elif action == "remove":
        tasks = load_tasks()
        try:
            tasks.pop(target_id - 1)
            save_tasks(tasks)
            print("🗑️ Tarea eliminada.")
        except Exception:
            print("ID inválido")

    elif action == "list_once":
        visible = get_visible_tasks()
        if not visible:
            print("No hay tareas pendientes.")
        for orig_idx, t in visible:
            mark = "✔" if t.get("done", False) else "✘"
            print(f"{orig_idx:>3} {mark} {t['task'][:60]:<60}  {t.get('deadline', 'N/A')}")

    elif action == "remove_all":
        save_tasks([])
        print("Lista vaciada.")


if __name__ == "__main__":
    main()
