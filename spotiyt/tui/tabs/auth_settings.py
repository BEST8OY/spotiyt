"""Auth & Settings tab module for SpotiYT."""

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Button, Input, Label, Static, TabPane

from spotiyt.config import COOKIES_JSON, EXPORTS_DIR, REGISTRY_FILE


class AuthSettingsTab(TabPane):
    """Auth & Settings Tab Pane for YouTube Music & Spotify credentials."""

    def __init__(self) -> None:
        super().__init__("Auth & Settings", id="tab-auth")

    def compose(self) -> ComposeResult:
        with Vertical(classes="auth-grid"):
            with Vertical(classes="auth-card"):
                yield Label("YouTube Music Auth", classes="auth-title")
                yield Static("Manages credentials for YouTube Music API.", classes="auth-desc")
                yield Label("", id="lbl-ytm-cookies-status")
                yield Label("", id="lbl-ytm-auth-status")
                yield Button(
                    "Generate auth.json from cookies",
                    variant="primary",
                    id="btn-auth-generate",
                    classes="btn-primary",
                )

            with Vertical(classes="auth-card"):
                yield Label("Spotify Personalized Token", classes="auth-title")
                yield Static("Stores 'sp_dc' cookie for private/algorithmic Spotify playlists.", classes="auth-desc")
                yield Label("", id="lbl-spotify-sp-dc-status")
                yield Input(placeholder="Paste sp_dc cookie string here...", password=True, id="input-sp-dc-cookie")
                yield Button("Save sp_dc Cookie", variant="default", id="btn-save-sp-dc", classes="btn-secondary")

        with ScrollableContainer(classes="guide-box"):
            yield Label("Quick Setup Guide & Instructions", classes="auth-title")
            yield Static(
                "1. [bold cyan]YouTube Music Setup:[/bold cyan]\n"
                "   • Log into [underline]music.youtube.com[/underline] in your browser.\n"
                "   • Use a browser extension (like 'Export Cookies' or 'EditThisCookie') to export cookies as JSON.\n"
                f"   • Save the file to [bold yellow]{COOKIES_JSON}[/bold yellow].\n"
                "   • Click '[bold green]Generate auth.json from cookies[/bold green]' above.\n\n"
                "2. [bold cyan]Spotify Setup (Optional for Personalized Playlists):[/bold cyan]\n"
                "   • Log into [underline]open.spotify.com[/underline].\n"
                "   • Open Developer Tools (F12) ➔ Application/Storage ➔ Cookies ➔ https://open.spotify.com.\n"
                "   • Copy the value of the cookie named [bold]sp_dc[/bold] and paste it into the field above.\n\n"
                "3. [bold cyan]Data Storage Locations:[/bold cyan]\n"
                f"   • Registry file: [dim]{REGISTRY_FILE}[/dim]\n"
                f"   • Exports folder: [dim]{EXPORTS_DIR}[/dim]\n"
            )
