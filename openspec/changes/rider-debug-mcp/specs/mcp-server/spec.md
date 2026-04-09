## ADDED Requirements

### Requirement: MCP Server SHALL expose rider_cli tool
The MCP server SHALL register a `rider_cli` tool that accepts a `command` string parameter. The tool SHALL parse multi-line input as batch commands (one command per line). Lines starting with `#` SHALL be treated as comments and ignored. Lines starting with `@` SHALL set context target for subsequent commands.

#### Scenario: Single CLI command execution
- **WHEN** AI calls `rider_cli` with command `add_breakpoint PlayerController.cs 42`
- **THEN** the server SHALL parse the command, route it to the breakpoint handler, and return a success/failure result

#### Scenario: Batch command execution
- **WHEN** AI calls `rider_cli` with multi-line commands containing `add_breakpoint File.cs 10\nadd_breakpoint File.cs 20`
- **THEN** the server SHALL execute each command in sequence and return aggregated results in a single response

#### Scenario: Context target with @
- **WHEN** AI calls `rider_cli` with `@PlayerController.cs\nadd_breakpoint 42\nadd_breakpoint 55`
- **THEN** the server SHALL apply `PlayerController.cs` as the file context for both `add_breakpoint` commands

#### Scenario: Comment lines are ignored
- **WHEN** AI calls `rider_cli` with `# Set breakpoints\nadd_breakpoint File.cs 10`
- **THEN** the server SHALL ignore the comment line and execute only the `add_breakpoint` command

### Requirement: MCP Server SHALL expose rider_query tool
The MCP server SHALL register a `rider_query` tool that accepts a `query` string parameter for read-only information retrieval. The query tool SHALL NOT modify any state.

#### Scenario: Query help information
- **WHEN** AI calls `rider_query` with query `help`
- **THEN** the server SHALL return a grouped list of all available commands

#### Scenario: Query specific command help
- **WHEN** AI calls `rider_query` with query `help add_breakpoint`
- **THEN** the server SHALL return the command syntax, parameters, and examples

#### Scenario: Query debug session status
- **WHEN** AI calls `rider_query` with query `context`
- **THEN** the server SHALL return current debug session state, active breakpoints, and recent operations

### Requirement: MCP Server SHALL use stdio transport
The MCP server SHALL communicate via stdio transport (stdin/stdout) following the MCP protocol specification. The server SHALL handle JSON-RPC messages properly.

#### Scenario: Server starts with stdio transport
- **WHEN** the MCP server process is started
- **THEN** it SHALL listen on stdin for JSON-RPC requests and write responses to stdout

### Requirement: MCP Server SHALL provide tool descriptions
Each registered tool SHALL include a comprehensive description with syntax examples, available commands overview, and usage patterns to guide AI assistants.

#### Scenario: rider_cli tool description
- **WHEN** AI requests tool listing from the MCP server
- **THEN** the `rider_cli` tool SHALL include a description with CLI syntax, context target usage, and batch execution examples
