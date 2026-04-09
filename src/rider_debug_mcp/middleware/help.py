"""Help system for the Rider Debug MCP tool."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rider_debug_mcp.middleware.router import CommandRouter

# Command metadata: {command_name: {syntax, description, examples}}
COMMAND_HELP: dict[str, dict[str, str]] = {
    "add_breakpoint": {
        "syntax": "add_breakpoint <file> <line> [--condition \"<expr>\"]",
        "description": "Add a breakpoint at the specified file and line number. Optionally set a condition.",
        "examples": (
            "add_breakpoint PlayerController.cs 42\n"
            "add_breakpoint PlayerController.cs 42 --condition \"health <= 0\""
        ),
        "group": "Breakpoint",
    },
    "remove_breakpoint": {
        "syntax": "remove_breakpoint <id>",
        "description": "Remove a breakpoint by its ID.",
        "examples": "remove_breakpoint bp-1",
        "group": "Breakpoint",
    },
    "enable_breakpoint": {
        "syntax": "enable_breakpoint <id>",
        "description": "Enable a disabled breakpoint.",
        "examples": "enable_breakpoint bp-1",
        "group": "Breakpoint",
    },
    "disable_breakpoint": {
        "syntax": "disable_breakpoint <id>",
        "description": "Disable a breakpoint without removing it.",
        "examples": "disable_breakpoint bp-1",
        "group": "Breakpoint",
    },
    "list_breakpoints": {
        "syntax": "list_breakpoints",
        "description": "List all current breakpoints.",
        "examples": "list_breakpoints",
        "group": "Breakpoint",
    },
    "clear_breakpoints": {
        "syntax": "clear_breakpoints",
        "description": "Remove all breakpoints.",
        "examples": "clear_breakpoints",
        "group": "Breakpoint",
    },
    "start_debug": {
        "syntax": "start_debug [config_name]",
        "description": "Start a debug session with an optional run configuration name.",
        "examples": "start_debug\nstart_debug MyApp",
        "group": "Debug Control",
    },
    "stop_debug": {
        "syntax": "stop_debug",
        "description": "Stop the current debug session.",
        "examples": "stop_debug",
        "group": "Debug Control",
    },
    "pause": {
        "syntax": "pause",
        "description": "Pause execution of the running debug session.",
        "examples": "pause",
        "group": "Debug Control",
    },
    "resume": {
        "syntax": "resume",
        "description": "Resume execution after a pause or breakpoint.",
        "examples": "resume",
        "group": "Debug Control",
    },
    "step_over": {
        "syntax": "step_over",
        "description": "Step over the current line.",
        "examples": "step_over",
        "group": "Debug Control",
    },
    "step_into": {
        "syntax": "step_into",
        "description": "Step into the function call on the current line.",
        "examples": "step_into",
        "group": "Debug Control",
    },
    "step_out": {
        "syntax": "step_out",
        "description": "Step out of the current function.",
        "examples": "step_out",
        "group": "Debug Control",
    },
    "get_variables": {
        "syntax": "get_variables [frame_index]",
        "description": "Get local variables for the given stack frame (default: top frame).",
        "examples": "get_variables\nget_variables 2",
        "group": "Inspection",
    },
    "evaluate": {
        "syntax": "evaluate <expression>",
        "description": "Evaluate an expression in the current debug context.",
        "examples": "evaluate player.Health\nevaluate player.Health + 10",
        "group": "Inspection",
    },
    "get_stack_trace": {
        "syntax": "get_stack_trace [thread_id]",
        "description": "Get the call stack for the given thread (default: current thread).",
        "examples": "get_stack_trace\nget_stack_trace 1",
        "group": "Inspection",
    },
    "get_threads": {
        "syntax": "get_threads",
        "description": "Get the list of threads in the debug session.",
        "examples": "get_threads",
        "group": "Inspection",
    },
    "analyze_crash": {
        "syntax": "analyze_crash",
        "description": "Analyze the latest crash or exception.",
        "examples": "analyze_crash",
        "group": "Analysis",
    },
    "crash_report": {
        "syntax": "crash_report",
        "description": "Get the most recent crash analysis report.",
        "examples": "crash_report",
        "group": "Analysis",
    },
    "crash_history": {
        "syntax": "crash_history",
        "description": "List all crash reports from the current session.",
        "examples": "crash_history",
        "group": "Analysis",
    },
}


def get_help_text(router: CommandRouter, command_name: str | None = None) -> str:
    """Generate help text.

    Args:
        router: The command router (to list registered commands).
        command_name: If provided, return detailed help for this command.

    Returns:
        Formatted help text string.
    """
    if command_name:
        return _command_help(command_name)
    return _all_commands_help(router)


def _command_help(command_name: str) -> str:
    """Return detailed help for a single command."""
    info = COMMAND_HELP.get(command_name)
    if info is None:
        return f"Unknown command: {command_name}\n\nUse 'help' to list all available commands."

    lines = [
        f"## {command_name}",
        "",
        f"**Group:** {info.get('group', 'Unknown')}",
        f"**Syntax:** `{info['syntax']}`",
        "",
        info["description"],
        "",
        "**Examples:**",
        "```",
        info["examples"],
        "```",
    ]
    return "\n".join(lines)


def _all_commands_help(router: CommandRouter) -> str:
    """Return help listing all commands grouped by domain."""
    # Group commands
    groups: dict[str, list[str]] = {}
    for cmd_name in router.registered_commands:
        info = COMMAND_HELP.get(cmd_name, {})
        group = info.get("group", "Other")
        groups.setdefault(group, []).append(cmd_name)

    lines = ["# Rider Debug MCP – Available Commands", ""]
    for group_name in ["Breakpoint", "Debug Control", "Inspection", "Analysis", "Other"]:
        cmds = groups.get(group_name)
        if not cmds:
            continue
        lines.append(f"## {group_name}")
        lines.append("")
        for cmd in cmds:
            info = COMMAND_HELP.get(cmd, {})
            desc = info.get("description", "")
            syntax = info.get("syntax", cmd)
            lines.append(f"  `{syntax}`")
            lines.append(f"    {desc}")
            lines.append("")
        lines.append("")

    lines.append("Use `help <command>` for detailed help on a specific command.")
    return "\n".join(lines)
