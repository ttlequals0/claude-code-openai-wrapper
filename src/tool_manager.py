"""
Tool configuration and metadata management for Claude Code OpenAI Wrapper.

Provides tool metadata, per-session configuration, and management endpoints.
"""

import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from threading import Lock
from datetime import datetime

from src.constants import CLAUDE_TOOLS, DEFAULT_ALLOWED_TOOLS, DEFAULT_DISALLOWED_TOOLS

logger = logging.getLogger(__name__)


@dataclass
class ToolMetadata:
    """Metadata for a Claude tool."""

    name: str
    description: str
    category: str
    parameters: Dict[str, str] = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)
    is_safe: bool = True
    requires_network: bool = False


# Tool metadata database
TOOL_METADATA: Dict[str, ToolMetadata] = {
    "Agent": ToolMetadata(
        name="Agent",
        description="Spawn sub-agents for complex, multi-step tasks",
        category="agent",
        parameters={
            "description": "Short description of the task",
            "prompt": "Detailed task instructions for the agent",
            "subagent_type": "Type of specialized agent to use",
            "model": "Optional model override for the agent",
            "isolation": "Isolation mode (e.g., worktree)",
        },
        examples=[
            "Launch a general-purpose agent to refactor code",
            "Use Explore agent to find API endpoints",
        ],
        is_safe=False,
        requires_network=False,
    ),
    "Bash": ToolMetadata(
        name="Bash",
        description="Execute bash commands in a persistent shell session",
        category="system",
        parameters={
            "command": "The bash command to execute",
            "timeout": "Optional timeout in milliseconds",
            "run_in_background": "Run command in background",
            "description": "Description of what the command does",
        },
        examples=["Run npm install", "Execute git status", "List directory contents"],
        is_safe=False,  # Requires permission in Claude Code
        requires_network=False,
    ),
    "Glob": ToolMetadata(
        name="Glob",
        description="Fast file pattern matching with glob patterns",
        category="file",
        parameters={
            "pattern": "Glob pattern to match files (e.g., **/*.py)",
            "path": "Directory to search in",
        },
        examples=[
            "Find all Python files: **/*.py",
            "Find TypeScript components: src/components/**/*.tsx",
        ],
        is_safe=True,
        requires_network=False,
    ),
    "Grep": ToolMetadata(
        name="Grep",
        description="Search file contents using regex patterns",
        category="file",
        parameters={
            "pattern": "Regex pattern to search for",
            "path": "File or directory to search in",
            "output_mode": "content, files_with_matches, or count",
            "glob": "Filter files by glob pattern",
        },
        examples=[
            "Search for function definitions",
            "Find TODO comments",
            "Search for import statements",
        ],
        is_safe=True,
        requires_network=False,
    ),
    "Read": ToolMetadata(
        name="Read",
        description="Read files from the local filesystem",
        category="file",
        parameters={
            "file_path": "Absolute path to the file",
            "offset": "Line number to start reading from",
            "limit": "Number of lines to read",
        },
        examples=[
            "Read entire file",
            "Read specific lines from large file",
            "Read images and PDFs",
        ],
        is_safe=True,
        requires_network=False,
    ),
    "Edit": ToolMetadata(
        name="Edit",
        description="Perform exact string replacements in files",
        category="file",
        parameters={
            "file_path": "Absolute path to file to modify",
            "old_string": "Text to replace",
            "new_string": "Replacement text",
            "replace_all": "Replace all occurrences",
        },
        examples=[
            "Fix a bug by replacing code",
            "Rename a variable",
            "Update configuration values",
        ],
        is_safe=True,
        requires_network=False,
    ),
    "Write": ToolMetadata(
        name="Write",
        description="Write or overwrite files on the filesystem",
        category="file",
        parameters={
            "file_path": "Absolute path to file to write",
            "content": "Content to write to the file",
        },
        examples=["Create a new file", "Overwrite existing file", "Generate configuration file"],
        is_safe=True,
        requires_network=False,
    ),
    "NotebookEdit": ToolMetadata(
        name="NotebookEdit",
        description="Edit Jupyter notebook cells",
        category="file",
        parameters={
            "notebook_path": "Path to .ipynb file",
            "cell_id": "ID of cell to edit",
            "new_source": "New cell content",
            "cell_type": "code or markdown",
            "edit_mode": "replace, insert, or delete",
        },
        examples=[
            "Replace code in notebook cell",
            "Insert new markdown cell",
            "Delete notebook cell",
        ],
        is_safe=True,
        requires_network=False,
    ),
    "WebFetch": ToolMetadata(
        name="WebFetch",
        description="Fetch and process web content",
        category="web",
        parameters={"url": "URL to fetch content from", "prompt": "Prompt to process the content"},
        examples=["Fetch documentation page", "Extract information from website", "Read blog post"],
        is_safe=True,
        requires_network=True,
    ),
    "TodoWrite": ToolMetadata(
        name="TodoWrite",
        description="Create and manage task lists",
        category="productivity",
        parameters={"todos": "Array of todo items with content, status, and activeForm"},
        examples=[
            "Create task list for feature",
            "Update task status to completed",
            "Track multi-step implementation",
        ],
        is_safe=True,
        requires_network=False,
    ),
    "WebSearch": ToolMetadata(
        name="WebSearch",
        description="Search the web for current information",
        category="web",
        parameters={
            "query": "Search query",
            "allowed_domains": "Only search these domains",
            "blocked_domains": "Never search these domains",
        },
        examples=[
            "Search for latest documentation",
            "Find recent news or updates",
            "Research technical topics",
        ],
        is_safe=True,
        requires_network=True,
    ),
    "BashOutput": ToolMetadata(
        name="BashOutput",
        description="Retrieve output from background bash shells",
        category="system",
        parameters={
            "bash_id": "ID of the background shell",
            "filter": "Regex to filter output lines",
        },
        examples=["Check output of running process", "Monitor long-running command"],
        is_safe=True,
        requires_network=False,
    ),
    "KillShell": ToolMetadata(
        name="KillShell",
        description="Kill a running background bash shell",
        category="system",
        parameters={"shell_id": "ID of the shell to kill"},
        examples=["Stop long-running background process"],
        is_safe=True,
        requires_network=False,
    ),
    "Skill": ToolMetadata(
        name="Skill",
        description="Execute specialized skills",
        category="productivity",
        parameters={"command": "Skill name to execute"},
        examples=["Execute PDF processing skill", "Run Excel manipulation skill"],
        is_safe=True,
        requires_network=False,
    ),
    "SlashCommand": ToolMetadata(
        name="SlashCommand",
        description="Execute custom slash commands",
        category="productivity",
        parameters={"command": "Slash command with arguments"},
        examples=["Run custom code review command", "Execute project-specific workflow"],
        is_safe=True,
        requires_network=False,
    ),
    "SendMessage": ToolMetadata(
        name="SendMessage",
        description="Send messages to teammates or other agents",
        category="agent",
        parameters={"to": "Recipient agent or teammate", "message": "Message content"},
        examples=["Send status update to teammate"],
        is_safe=False,
        requires_network=False,
    ),
    "TaskCreate": ToolMetadata(
        name="TaskCreate",
        description="Create a new task for tracking work",
        category="task",
        parameters={"subject": "Task subject", "description": "Task description"},
        examples=["Create task to track implementation progress"],
        is_safe=True,
        requires_network=False,
    ),
    "TaskUpdate": ToolMetadata(
        name="TaskUpdate",
        description="Update an existing task status or details",
        category="task",
        parameters={"taskId": "Task ID", "status": "New status"},
        examples=["Mark task as completed"],
        is_safe=True,
        requires_network=False,
    ),
    "TaskGet": ToolMetadata(
        name="TaskGet",
        description="Get details of a specific task",
        category="task",
        parameters={"taskId": "Task ID to retrieve"},
        examples=["Get task details by ID"],
        is_safe=True,
        requires_network=False,
    ),
    "TaskList": ToolMetadata(
        name="TaskList",
        description="List all tasks",
        category="task",
        parameters={},
        examples=["List all active tasks"],
        is_safe=True,
        requires_network=False,
    ),
    "TaskOutput": ToolMetadata(
        name="TaskOutput",
        description="Get the output of a completed task",
        category="task",
        parameters={"taskId": "Task ID"},
        examples=["Retrieve output from finished task"],
        is_safe=True,
        requires_network=False,
    ),
    "TaskStop": ToolMetadata(
        name="TaskStop",
        description="Stop a running task",
        category="task",
        parameters={"taskId": "Task ID to stop"},
        examples=["Cancel a running background task"],
        is_safe=True,
        requires_network=False,
    ),
    "EnterPlanMode": ToolMetadata(
        name="EnterPlanMode",
        description="Enter plan mode for designing implementation approach",
        category="planning",
        parameters={},
        examples=["Enter plan mode before implementing a feature"],
        is_safe=True,
        requires_network=False,
    ),
    "ExitPlanMode": ToolMetadata(
        name="ExitPlanMode",
        description="Exit plan mode and present plan for approval",
        category="planning",
        parameters={},
        examples=["Exit plan mode after finishing design"],
        is_safe=True,
        requires_network=False,
    ),
    "EnterWorktree": ToolMetadata(
        name="EnterWorktree",
        description="Create an isolated git worktree for safe changes",
        category="git",
        parameters={"branch": "Branch name for the worktree"},
        examples=["Create isolated worktree for feature work"],
        is_safe=True,
        requires_network=False,
    ),
    "ExitWorktree": ToolMetadata(
        name="ExitWorktree",
        description="Exit and clean up a git worktree",
        category="git",
        parameters={},
        examples=["Clean up worktree after finishing work"],
        is_safe=True,
        requires_network=False,
    ),
    "ToolSearch": ToolMetadata(
        name="ToolSearch",
        description="Search for available tools by keyword or name",
        category="discovery",
        parameters={"query": "Search query for tools"},
        examples=["Find tools for file operations"],
        is_safe=True,
        requires_network=False,
    ),
    "AskUserQuestion": ToolMetadata(
        name="AskUserQuestion",
        description="Ask the user for input or clarification",
        category="interaction",
        parameters={"question": "Question to ask", "options": "Available choices"},
        examples=["Ask user to choose between approaches"],
        is_safe=True,
        requires_network=False,
    ),
    "CronCreate": ToolMetadata(
        name="CronCreate",
        description="Create a scheduled recurring task",
        category="scheduling",
        parameters={"schedule": "Cron schedule expression", "command": "Command to run"},
        examples=["Schedule a daily health check"],
        is_safe=False,
        requires_network=False,
    ),
    "CronDelete": ToolMetadata(
        name="CronDelete",
        description="Delete a scheduled task",
        category="scheduling",
        parameters={"cronId": "ID of the cron job to delete"},
        examples=["Remove a scheduled task"],
        is_safe=True,
        requires_network=False,
    ),
    "CronList": ToolMetadata(
        name="CronList",
        description="List all scheduled tasks",
        category="scheduling",
        parameters={},
        examples=["List all active cron jobs"],
        is_safe=True,
        requires_network=False,
    ),
    "RemoteTrigger": ToolMetadata(
        name="RemoteTrigger",
        description="Trigger remote agent execution",
        category="scheduling",
        parameters={"trigger": "Trigger configuration"},
        examples=["Trigger a remote agent to run a task"],
        is_safe=False,
        requires_network=True,
    ),
}

# Task is a backward-compatible alias for Agent -- share the same metadata
TOOL_METADATA["Task"] = TOOL_METADATA["Agent"]


@dataclass
class ToolConfiguration:
    """Tool configuration for a session or global context."""

    allowed_tools: Optional[List[str]] = None
    disallowed_tools: Optional[List[str]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def get_effective_tools(self) -> Set[str]:
        """
        Get the effective set of tools based on allowed/disallowed lists.

        Logic:
        - If allowed_tools is set, use that as the base set
        - If disallowed_tools is set, remove those from the base set
        - If neither is set, use DEFAULT_ALLOWED_TOOLS minus DEFAULT_DISALLOWED_TOOLS
        """
        if self.allowed_tools is not None:
            # Start with explicitly allowed tools
            effective = set(self.allowed_tools)
        else:
            # Start with all tools
            effective = set(CLAUDE_TOOLS)

        # Remove disallowed tools
        if self.disallowed_tools is not None:
            effective -= set(self.disallowed_tools)

        return effective

    def update(
        self,
        allowed_tools: Optional[List[str]] = None,
        disallowed_tools: Optional[List[str]] = None,
    ):
        """Update the configuration."""
        if allowed_tools is not None:
            self.allowed_tools = allowed_tools
        if disallowed_tools is not None:
            self.disallowed_tools = disallowed_tools
        self.updated_at = datetime.utcnow()


class ToolManager:
    """Manages tool configurations globally and per-session."""

    def __init__(self):
        self.global_config = ToolConfiguration(
            allowed_tools=list(DEFAULT_ALLOWED_TOOLS),
            disallowed_tools=list(DEFAULT_DISALLOWED_TOOLS),
        )
        self.session_configs: Dict[str, ToolConfiguration] = {}
        self.lock = Lock()

    def get_tool_metadata(self, tool_name: str) -> Optional[ToolMetadata]:
        """Get metadata for a specific tool."""
        return TOOL_METADATA.get(tool_name)

    def list_all_tools(self) -> List[ToolMetadata]:
        """List all available tools with metadata."""
        return list(TOOL_METADATA.values())

    def get_global_config(self) -> ToolConfiguration:
        """Get the global tool configuration."""
        with self.lock:
            return self.global_config

    def update_global_config(
        self,
        allowed_tools: Optional[List[str]] = None,
        disallowed_tools: Optional[List[str]] = None,
    ) -> ToolConfiguration:
        """Update the global tool configuration."""
        with self.lock:
            self.global_config.update(allowed_tools, disallowed_tools)
            logger.info(
                f"Updated global tool config: allowed={allowed_tools}, disallowed={disallowed_tools}"
            )
            return self.global_config

    def get_session_config(self, session_id: str) -> Optional[ToolConfiguration]:
        """Get tool configuration for a specific session."""
        with self.lock:
            return self.session_configs.get(session_id)

    def set_session_config(
        self,
        session_id: str,
        allowed_tools: Optional[List[str]] = None,
        disallowed_tools: Optional[List[str]] = None,
    ) -> ToolConfiguration:
        """Set tool configuration for a specific session."""
        with self.lock:
            if session_id not in self.session_configs:
                self.session_configs[session_id] = ToolConfiguration()

            self.session_configs[session_id].update(allowed_tools, disallowed_tools)
            logger.info(f"Updated session {session_id} tool config")
            return self.session_configs[session_id]

    def delete_session_config(self, session_id: str) -> bool:
        """Delete tool configuration for a session."""
        with self.lock:
            if session_id in self.session_configs:
                del self.session_configs[session_id]
                logger.info(f"Deleted tool config for session {session_id}")
                return True
            return False

    def get_effective_config(self, session_id: Optional[str] = None) -> ToolConfiguration:
        """
        Get effective tool configuration.

        If session_id is provided and has a config, use that.
        Otherwise, use global config.
        """
        with self.lock:
            if session_id and session_id in self.session_configs:
                return self.session_configs[session_id]
            return self.global_config

    def get_effective_tools(self, session_id: Optional[str] = None) -> List[str]:
        """Get the list of effective tools for a session or globally."""
        config = self.get_effective_config(session_id)
        return sorted(list(config.get_effective_tools()))

    def validate_tools(self, tool_names: List[str]) -> Dict[str, bool]:
        """
        Validate if tool names are valid.

        Returns dict mapping tool name to whether it's valid.
        """
        return {name: name in CLAUDE_TOOLS for name in tool_names}

    def get_stats(self) -> Dict:
        """Get statistics about tool usage and configuration."""
        with self.lock:
            return {
                "total_tools": len(CLAUDE_TOOLS),
                "global_allowed": (
                    len(self.global_config.allowed_tools) if self.global_config.allowed_tools else 0
                ),
                "global_disallowed": (
                    len(self.global_config.disallowed_tools)
                    if self.global_config.disallowed_tools
                    else 0
                ),
                "session_configs": len(self.session_configs),
                "tool_categories": {
                    category: len([t for t in TOOL_METADATA.values() if t.category == category])
                    for category in sorted(set(t.category for t in TOOL_METADATA.values()))
                },
            }


# Global tool manager instance
tool_manager = ToolManager()
