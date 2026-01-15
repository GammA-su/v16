from __future__ import annotations

from rich.console import Console
from rich.table import Table

from eidolon_v16.ucr.models import WitnessPacket


def render_witness(packet: WitnessPacket, console: Console | None = None) -> None:
    console = console or Console()
    console.print(f"Episode: {packet.episode_id}")
    console.print(f"Final: {packet.final_response}")
    table = Table(title="Verification")
    table.add_column("Lane")
    table.add_column("Status")
    for lane in packet.verification:
        table.add_row(lane.lane, lane.status)
    console.print(table)
