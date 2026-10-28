"""Data assembled once and shared by the profile page sections."""

from typing import Dict, List, NamedTuple, Optional

from gnomon.cli.period import Period
from gnomon.output.profile.brand import CAPTION
from gnomon.scoring.insights import _growth_edges_pool, _signature_moves_pool


class ProfileContext(NamedTuple):
    stats: dict
    archetype: str
    quote: str
    scores: Dict[str, float]
    voice: dict
    period: Period
    trend: Optional[dict]
    moves: List[dict]
    edges: List[dict]
    caption: str


def build_context(stats, archetype, quote, scores, voice, period, trend) -> ProfileContext:
    """Build the stable renderer context without changing scoring payloads."""
    moves = [dict(move) for move in _signature_moves_pool(stats)[:3]]
    edges = []
    for index, edge in enumerate(_growth_edges_pool(stats, scores)[:3], 1):
        item = dict(edge)
        item["n"] = f"{index:02d}"
        edges.append(item)
    if voice is None:
        voice = {"goto": None, "crashouts": [], "cryptics": []}
    return ProfileContext(stats, archetype, quote, scores, voice, period, trend,
                          moves, edges, CAPTION)
