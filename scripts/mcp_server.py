"""MCP server exposing the five Flow 1A tools (Task #16).

The tool logic lives in scripts/mcp_tools.py; this file only registers it.
Run from the repo root (stdio transport, which is what MCP clients launch):

    python -m scripts.mcp_server
"""
import sys
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts import mcp_tools
from scripts.recommender import DEFAULT_TOP_K

INSTRUCTIONS = (
    "Tools for a Miami neighborhood recommender. Answer only from what these tools return: "
    "never rank, score, or invent rents, ZIPs, listings or statistics. "
    "Call ethics when the user asks about limitations, fair housing or prohibited uses, "
    "and refuse demographic filtering or tenant scoring without calling recommend."
)

server = MCPServer("flow1a-neighborhoods", instructions=INSTRUCTIONS)


@server.tool()
def schema() -> dict[str, Any]:
    """Column names, types and notes for every dataset. Call when the user asks what data or columns exist."""
    return mcp_tools.schema()


@server.tool()
def area_stats(zip_code: str | None = None) -> dict[str, Any]:
    """Public Census/Zillow stats for a 5-digit Miami ZIP, or all ZIPs if zip_code is omitted.

    Suppressed or missing values come back as null and are listed under "unavailable".
    """
    return mcp_tools.area_stats(zip_code)


@server.tool()
def crowd_themes(zip_code: str, theme: str | None = None) -> dict[str, Any]:
    """Review snippets for a 5-digit Miami ZIP (what people say about it), optionally for one theme such as transit, social or quiet."""
    return mcp_tools.crowd_themes(zip_code, theme)


@server.tool()
def recommend(
    budget_max: float,
    household: str,
    housing_preference: str,
    tags: list[str],
    k: int = DEFAULT_TOP_K,
) -> dict[str, Any]:
    """Rank up to k Miami ZIPs for a user profile.

    household: "alone" or "with_co_leaser" (a co-leaser shares a private lease; it is not co-living).
    housing_preference: "own_apartment" or "co_living". Never infer it from household.
    tags: any of transit, social, quiet, walkable, pet_friendly, co_living.
    budget_max: monthly rent ceiling in USD.
    """
    return mcp_tools.recommend(budget_max, household, housing_preference, tags, k)


@server.tool()
def ethics() -> dict[str, Any]:
    """Fair-use rules, prohibited uses and data limitations. Call when the user asks about limitations, fair housing or prohibited uses."""
    return mcp_tools.ethics()


if __name__ == "__main__":
    server.run()
