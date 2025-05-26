from mcp.server.fastmcp import FastMCP
import sys
import logging
import math
import random

# Create an MCP server
mcp = FastMCP("Calculator")

# Add an addition tool
@mcp.tool()
def calculator(python_expression: str) -> dict:
    """For mathamatical calculation, always use this tool to calculate the result of a python expression. `math` and `random` are available."""
    result = eval(python_expression)
    logging.info(f"Calculating formula: {python_expression}, result: {result}")
    return {"success": True, "result": result}

# Start the server
if __name__ == "__main__":
    mcp.run(transport="stdio")
