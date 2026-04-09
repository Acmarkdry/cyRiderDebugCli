## ADDED Requirements

### Requirement: CommandParser SHALL parse CLI syntax
The CommandParser SHALL parse command strings into structured command objects. It SHALL support positional arguments, named arguments (`--key value`), context targets (`@target`), and comments (`# comment`).

#### Scenario: Parse simple command with positional args
- **WHEN** parser receives `add_breakpoint PlayerController.cs 42`
- **THEN** it SHALL produce a ParsedCommand with name `add_breakpoint` and positional args `["PlayerController.cs", "42"]`

#### Scenario: Parse command with named arguments
- **WHEN** parser receives `add_breakpoint PlayerController.cs 42 --condition "health <= 0"`
- **THEN** it SHALL produce a ParsedCommand with positional args and named arg `condition` set to `"health <= 0"`

#### Scenario: Parse context target
- **WHEN** parser receives `@PlayerController.cs`
- **THEN** it SHALL set the context target to `PlayerController.cs` for subsequent commands in the batch

#### Scenario: Parse multi-line batch
- **WHEN** parser receives a multi-line string with 3 commands
- **THEN** it SHALL return a list of 3 ParsedCommand objects, preserving order

#### Scenario: Handle invalid command syntax
- **WHEN** parser receives an empty or malformed command string
- **THEN** it SHALL raise a ParseError with a descriptive message

### Requirement: CommandRouter SHALL dispatch commands to correct handlers
The CommandRouter SHALL maintain a registry of command handlers and dispatch parsed commands to the appropriate handler based on command name.

#### Scenario: Route breakpoint command
- **WHEN** router receives a ParsedCommand with name `add_breakpoint`
- **THEN** it SHALL dispatch to the BreakpointHandler

#### Scenario: Route debug control command
- **WHEN** router receives a ParsedCommand with name `step_over`
- **THEN** it SHALL dispatch to the DebugHandler

#### Scenario: Route unknown command
- **WHEN** router receives a ParsedCommand with an unregistered command name
- **THEN** it SHALL return an error response indicating the command is not found, with a suggestion of similar commands

### Requirement: SessionManager SHALL track debug session state
The SessionManager SHALL maintain the current debug session state including active breakpoints, current execution position, and debug mode (running/paused/stopped).

#### Scenario: Track session start
- **WHEN** a debug session starts
- **THEN** the SessionManager SHALL record the session ID, start time, and set status to `running`

#### Scenario: Track breakpoint cache
- **WHEN** a breakpoint is added via the middleware
- **THEN** the SessionManager SHALL cache the breakpoint details and update the breakpoint count

#### Scenario: Provide session context for queries
- **WHEN** `rider_query` requests context
- **THEN** the SessionManager SHALL return current session state, cached breakpoints, and recent operation history

### Requirement: Middleware SHALL format responses consistently
All responses from the middleware layer SHALL follow a consistent format with status (success/error), structured data payload, and optional human-readable message.

#### Scenario: Successful command response
- **WHEN** a command executes successfully
- **THEN** the response SHALL contain `status: "success"`, the relevant data payload, and an optional summary message

#### Scenario: Error command response
- **WHEN** a command fails
- **THEN** the response SHALL contain `status: "error"`, an error code, a descriptive error message, and optional suggestions for resolution
