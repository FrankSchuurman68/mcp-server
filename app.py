"""Centrale FastMCP-instantie. Tool-modules importeren dit object om
via de @mcp.tool decorator hun functies te registreren."""

from fastmcp import FastMCP

mcp = FastMCP("HomeLab Manager")
