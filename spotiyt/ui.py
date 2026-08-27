import os
import re
import sys
from typing import List, Optional, Tuple, Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    MofNCompleteColumn,
    TimeElapsedColumn,
)

console = Console(highlight=False)


def print_banner(title: str = "Spotify to YouTube Music", subtitle: Optional[str] = None):
    text = Text()
    text.append(f"  {title}  ", style="bold cyan")
    if subtitle:
        text.append(f"\n  {subtitle}  ", style="dim white")
    console.print(Panel(text, border_style="cyan", expand=False, padding=(0, 2)))


def print_success(msg: str):
    console.print(f"[bold green]✔[/bold green] {msg}")


def print_error(msg: str):
    console.print(f"[bold red]✖[/bold red] {msg}")


def print_warning(msg: str):
    console.print(f"[bold yellow]⚠[/bold yellow] {msg}")


def print_info(msg: str):
    console.print(f"[bold blue]ℹ[/bold blue] {msg}")


def extract_spotify_id(input_str: str) -> Optional[str]:
    if not input_str:
        return None
    input_str = input_str.strip()

    # URL format: https://open.spotify.com/playlist/37i9dQZF1E8MCNiiTgwMk8?si=...
    url_match = re.search(r'playlist/([a-zA-Z0-9]+)', input_str)
    if url_match:
        return url_match.group(1)

    # URI format: spotify:playlist:37i9dQZF1E8MCNiiTgwMk8
    uri_match = re.search(r'spotify:playlist:([a-zA-Z0-9]+)', input_str)
    if uri_match:
        return uri_match.group(1)

    # Raw ID format (usually alphanumeric 15-30 chars)
    if re.match(r'^[a-zA-Z0-9]{15,30}$', input_str):
        return input_str

    return None


def create_progress() -> Progress:
    return Progress(
        SpinnerColumn(spinner_name="dots"),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=30, style="cyan", complete_style="bold green"),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def print_summary_table(title: str, stats: Dict[str, Any]):
    table = Table(title=title, border_style="cyan", title_style="bold cyan", header_style="bold magenta")
    table.add_column("Metric", style="bold white", width=30)
    table.add_column("Value", style="cyan")
    for key, val in stats.items():
        table.add_row(key, str(val))
    console.print(table)


class CursesMenu:
    def __init__(self, items: List[Dict[str, Any]], title: str = "Select an option:", subtitle: str = ""):
        self.items = items
        self.title = title
        self.subtitle = subtitle

    def run(self) -> int:
        if not sys.stdin.isatty():
            return -1
        import curses
        return curses.wrapper(self._render)

    def _render(self, stdscr) -> int:
        import curses
        curses.curs_set(0)
        stdscr.keypad(True)

        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)     # Title
            curses.init_pair(2, curses.COLOR_GREEN, -1)    # Success / ON
            curses.init_pair(3, curses.COLOR_RED, -1)      # Danger / OFF
            curses.init_pair(4, curses.COLOR_YELLOW, -1)   # Warning
            curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_CYAN) # Highlight
            curses.init_pair(6, curses.COLOR_WHITE, -1)    # Standard Text
            curses.init_pair(7, 8 if curses.COLORS > 8 else curses.COLOR_WHITE, -1) # Dim

        selectable_indices = [i for i, item in enumerate(self.items) if not item.get("separator")]
        if not selectable_indices:
            return -1
        current_pos = 0

        while True:
            stdscr.clear()
            max_y, max_x = stdscr.getmaxyx()

            if max_y < 8 or max_x < 35:
                try:
                    stdscr.addstr(0, 0, "Terminal too small!")
                except curses.error:
                    pass
                stdscr.refresh()
                key = stdscr.getch()
                if key in (ord('q'), 27):
                    return -1
                continue

            try:
                stdscr.attron(curses.color_pair(1) | curses.A_BOLD if curses.has_colors() else curses.A_BOLD)
                stdscr.addstr(1, 2, f"◆ {self.title}"[:max_x - 4])
                stdscr.attroff(curses.color_pair(1) | curses.A_BOLD if curses.has_colors() else curses.A_BOLD)

                if self.subtitle:
                    stdscr.attron(curses.color_pair(7) if curses.has_colors() else curses.A_DIM)
                    stdscr.addstr(2, 4, self.subtitle[:max_x - 6])
                    stdscr.attroff(curses.color_pair(7) if curses.has_colors() else curses.A_DIM)

                divider = "─" * min(max_x - 4, 60)
                stdscr.attron(curses.color_pair(7) if curses.has_colors() else curses.A_NORMAL)
                stdscr.addstr(3, 2, divider)
                stdscr.attroff(curses.color_pair(7) if curses.has_colors() else curses.A_NORMAL)
            except curses.error:
                pass

            row = 4
            selected_item_idx = selectable_indices[current_pos]

            for i, item in enumerate(self.items):
                if row >= max_y - 3:
                    break

                if item.get("separator"):
                    try:
                        stdscr.attron(curses.color_pair(7) if curses.has_colors() else curses.A_NORMAL)
                        stdscr.addstr(row, 4, "──────────────────────────────────────"[:max_x - 6])
                        stdscr.attroff(curses.color_pair(7) if curses.has_colors() else curses.A_NORMAL)
                    except curses.error:
                        pass
                    row += 1
                    continue

                is_selected = (i == selected_item_idx)
                label = item.get("label", "")
                badge = item.get("badge", "")

                try:
                    if is_selected:
                        cursor = " ❯ "
                        item_text = f"{cursor}{label} "
                        if badge:
                            item_text += f"[{badge}] "
                        pad_len = max(min(max_x - 6, 56) - len(item_text), 0)
                        item_text += " " * pad_len

                        stdscr.attron(curses.color_pair(5) | curses.A_BOLD if curses.has_colors() else curses.A_REVERSE)
                        stdscr.addstr(row, 2, item_text[:max_x - 4])
                        stdscr.attroff(curses.color_pair(5) | curses.A_BOLD if curses.has_colors() else curses.A_REVERSE)
                    else:
                        cursor = "   "
                        stdscr.addstr(row, 2, cursor)
                        stdscr.addstr(row, 5, label[:max_x - 15])
                        if badge:
                            b_color = curses.color_pair(2) if badge in ("ON", "SYNC", "READY", "ACTIVE") else curses.color_pair(3)
                            stdscr.attron(b_color | curses.A_BOLD if curses.has_colors() else curses.A_NORMAL)
                            stdscr.addstr(f" [{badge}]")
                            stdscr.attroff(b_color | curses.A_BOLD if curses.has_colors() else curses.A_NORMAL)
                except curses.error:
                    pass
                row += 1

            try:
                footer_row = max_y - 2
                stdscr.attron(curses.color_pair(7) if curses.has_colors() else curses.A_DIM)
                footer_text = " [↑/↓, j/k] Navigate   [Enter] Select   [q/Esc] Exit"
                stdscr.addstr(footer_row, 2, footer_text[:max_x - 4])
                stdscr.attroff(curses.color_pair(7) if curses.has_colors() else curses.A_DIM)
            except curses.error:
                pass

            stdscr.refresh()

            key = stdscr.getch()
            if key in (curses.KEY_UP, ord('k')):
                current_pos = (current_pos - 1) % len(selectable_indices)
            elif key in (curses.KEY_DOWN, ord('j')):
                current_pos = (current_pos + 1) % len(selectable_indices)
            elif key in (curses.KEY_HOME, ord('g')):
                current_pos = 0
            elif key in (curses.KEY_END, ord('G')):
                current_pos = len(selectable_indices) - 1
            elif key in (10, 13, curses.KEY_ENTER):
                return selectable_indices[current_pos]
            elif key in (ord('q'), 27):
                return -1
