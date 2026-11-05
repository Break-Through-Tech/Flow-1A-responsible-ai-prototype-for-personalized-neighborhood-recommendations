"""MCP server exposing the five Flow 1A tools (Task #16).

The tool logic lives in scripts/mcp_tools.py and the JSON contracts in
scripts/tool_contracts.py; this file registers the tools and enforces the contracts.
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

from scripts import mcp_tools, tool_contracts

INSTRUCTIONS = (
    "Tools for a Miami neighborhood recommender. Answer only from what these tools return: "
    "never rank, score, or invent rents, ZIPs, listings or statistics. "
    "Call ethics when the user asks about limitations, fair housing or prohibited uses, "
    "and refuse demographic filtering or tenant scoring without calling recommend."
)

server = MCPServer("flow1a-neighborhoods", instructions=INSTRUCTIONS)


# Parameters are typed Any so the SDK passes every argument through and
# tool_contracts.call_tool() can validate it: a malformed call then gets a
# structured invalid_input result instead of a free-text SDK error. What the
# client sees as the input and output schema is set from tool_contracts by
# _publish_contracts() below.
#
# A null argument is treated as not sent, which every tool already treats as
# omitted. Arguments the contract does not name are dropped by the SDK before
# this code sees them, so they are ignored rather than rejected.


def _arguments(**kwargs) -> dict[str, Any]:
    """Drop arguments the client did not send, so "required" is checked properly."""
    return {name: value for name, value in kwargs.items() if value is not None}


@server.tool()
def schema() -> dict[str, Any]:
    """Column names, types and notes for every dataset. Call when the user asks what data or columns exist."""
    return tool_contracts.call_tool("schema", mcp_tools.schema, {})


@server.tool()
def area_stats(zip_code: Any = None) -> dict[str, Any]:
    """Public Census/Zillow stats for a 5-digit Miami ZIP, or all ZIPs if zip_code is omitted.

    Suppressed or missing values come back as null and are listed under "unavailable".
    """
    return tool_contracts.call_tool("area_stats", mcp_tools.area_stats, _arguments(zip_code=zip_code))


@server.tool()
def crowd_themes(zip_code: Any = None, theme: Any = None) -> dict[str, Any]:
    """Review snippets for a 5-digit Miami ZIP (what people say about it), optionally for one theme such as transit, social or quiet."""
    return tool_contracts.call_tool(
        "crowd_themes", mcp_tools.crowd_themes, _arguments(zip_code=zip_code, theme=theme)
    )


@server.tool()
def recommend(
    budget_max: Any = None,
    household: Any = None,
    housing_preference: Any = None,
    tags: Any = None,
    k: Any = None,
) -> dict[str, Any]:
    """Rank up to k Miami ZIPs for a user profile. Each match carries ranking_reasons and a summary built only from the data.

    household: "alone" or "with_co_leaser" (a co-leaser shares a private lease; it is not co-living).
    housing_preference: "own_apartment" or "co_living". Never infer it from household.
    tags: any of transit, social, quiet, walkable, pet_friendly, co_living.
    budget_max: monthly rent ceiling in USD.
    """
    arguments = _arguments(
        budget_max=budget_max, household=household, housing_preference=housing_preference, tags=tags, k=k
    )
    return tool_contracts.call_tool("recommend", mcp_tools.recommend, arguments)


@server.tool()
def ethics() -> dict[str, Any]:
    """Fair-use rules, prohibited uses and data limitations. Call when the user asks about limitations, fair housing or prohibited uses."""
    return tool_contracts.call_tool("ethics", mcp_tools.ethics, {})


def _publish_contracts() -> None:
    """Advertise the tool_contracts schemas instead of the SDK's Any-typed ones.

    The SDK has no public hook for this, so it sets the registered tool's fields
    directly; test_tool_contracts.py checks that list_tools returns them.
    """
    for name in tool_contracts.INPUT_SCHEMAS:
        tool = server._tool_manager.get_tool(name)
        tool.parameters = tool_contracts.INPUT_SCHEMAS[name]
        tool.fn_metadata.output_schema = tool_contracts.OUTPUT_SCHEMAS[name]
        tool.__dict__.pop("output_schema", None)  # drop the cached copy


_publish_contracts()


if __name__ == "__main__":
    server.run()
