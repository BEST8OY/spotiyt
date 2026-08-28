import re
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

console = Console(highlight=False)


def print_banner(title: str = "Spotify to YouTube Music", subtitle: str | None = None):
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


def extract_spotify_id(input_str: str) -> str | None:
    if not input_str:
        return None
    input_str = input_str.strip()

    # URL format: https://open.spotify.com/playlist/37i9dQZF1E8MCNiiTgwMk8?si=...
    url_match = re.search(r"playlist/([a-zA-Z0-9]+)", input_str)
    if url_match:
        return url_match.group(1)

    # URI format: spotify:playlist:37i9dQZF1E8MCNiiTgwMk8
    uri_match = re.search(r"spotify:playlist:([a-zA-Z0-9]+)", input_str)
    if uri_match:
        return uri_match.group(1)

    # Raw ID format (usually alphanumeric 15-30 chars)
    if re.match(r"^[a-zA-Z0-9]{15,30}$", input_str):
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


def print_summary_table(title: str, stats: dict[str, Any]):
    table = Table(title=title, border_style="cyan", title_style="bold cyan", header_style="bold magenta")
    table.add_column("Metric", style="bold white", width=30)
    table.add_column("Value", style="cyan")
    for key, val in stats.items():
        table.add_row(key, str(val))
    console.print(table)
