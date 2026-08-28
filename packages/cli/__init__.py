"""Command-line entry point.

``reap`` drives the same objects the API uses. A demonstration that runs
through a special "demo mode" proves nothing about the platform, so this one
executes the real workflow, the real policy engine and the real writer.
"""

from cli.main import build_parser, main
from cli.scenarios import DemoScenario, get_scenario, load_scenarios

__all__ = ["DemoScenario", "build_parser", "get_scenario", "load_scenarios", "main"]
