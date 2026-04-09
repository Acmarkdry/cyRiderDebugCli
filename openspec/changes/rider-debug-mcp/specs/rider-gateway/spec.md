## ADDED Requirements

### Requirement: RiderClient SHALL connect to Rider Built-in Server
The RiderClient SHALL establish HTTP connections to the Rider IDE built-in server. It SHALL auto-discover the Rider port by scanning the default port range (63342+) or accept a configured port.

#### Scenario: Auto-discover Rider port
- **WHEN** RiderClient initializes without explicit port configuration
- **THEN** it SHALL scan ports 63342-63352 to find a responding Rider instance

#### Scenario: Connect with explicit port
- **WHEN** RiderClient initializes with port `63342`
- **THEN** it SHALL connect directly to `http://localhost:63342`

#### Scenario: Handle connection failure
- **WHEN** no Rider instance is found on any scanned port
- **THEN** the client SHALL raise a ConnectionError with a message indicating Rider is not running or the built-in server is disabled

### Requirement: RiderClient SHALL manage breakpoints
The RiderClient SHALL support adding, removing, enabling, disabling, and listing breakpoints through Rider's API.

#### Scenario: Add a line breakpoint
- **WHEN** `add_breakpoint` is called with file path `PlayerController.cs` and line `42`
- **THEN** the client SHALL send the appropriate API request to Rider and return the created breakpoint ID

#### Scenario: Add a conditional breakpoint
- **WHEN** `add_breakpoint` is called with file, line, and condition `"health <= 0"`
- **THEN** the client SHALL create a breakpoint with the specified condition expression

#### Scenario: Remove a breakpoint
- **WHEN** `remove_breakpoint` is called with a breakpoint ID
- **THEN** the client SHALL remove the breakpoint from Rider and confirm removal

#### Scenario: List all breakpoints
- **WHEN** `list_breakpoints` is called
- **THEN** the client SHALL return all current breakpoints with their file, line, enabled status, and condition

### Requirement: RiderClient SHALL control debug execution
The RiderClient SHALL support debug control operations: start debug, stop debug, pause, resume, step over, step into, step out.

#### Scenario: Start debug session
- **WHEN** `start_debug` is called with a run configuration name
- **THEN** the client SHALL start a debug session in Rider and return the session ID

#### Scenario: Step over
- **WHEN** `step_over` is called during a paused debug session
- **THEN** the client SHALL advance execution by one line and return the new position

#### Scenario: Resume execution
- **WHEN** `resume` is called during a paused debug session
- **THEN** the client SHALL resume execution until the next breakpoint or program end

### Requirement: RiderClient SHALL inspect runtime state
The RiderClient SHALL support reading variables, evaluating expressions, and inspecting stack frames during a paused debug session.

#### Scenario: Read local variables
- **WHEN** `get_variables` is called during a paused session
- **THEN** the client SHALL return all local variables with names, types, and values for the current stack frame

#### Scenario: Evaluate expression
- **WHEN** `evaluate` is called with expression `player.Health`
- **THEN** the client SHALL evaluate the expression in the current context and return the result

#### Scenario: Get stack trace
- **WHEN** `get_stack_trace` is called during a paused session
- **THEN** the client SHALL return the complete call stack with frame index, method name, file, and line number

### Requirement: EventListener SHALL monitor debug events via WebSocket
The EventListener SHALL connect to Rider's debug event stream and emit structured events for breakpoint hits, exceptions, and process termination.

#### Scenario: Receive breakpoint hit event
- **WHEN** execution hits a breakpoint in Rider
- **THEN** the EventListener SHALL emit a `breakpoint_hit` event with file, line, thread ID, and stack frame info

#### Scenario: Receive exception event
- **WHEN** an unhandled exception occurs during debugging
- **THEN** the EventListener SHALL emit an `exception` event with exception type, message, and stack trace

#### Scenario: Handle WebSocket disconnection
- **WHEN** the WebSocket connection to Rider is lost
- **THEN** the EventListener SHALL attempt reconnection with exponential backoff (max 5 retries)

### Requirement: Gateway data models SHALL use Pydantic
All data models for breakpoints, debug sessions, variables, stack frames, and events SHALL be defined as Pydantic models for validation and serialization.

#### Scenario: Validate breakpoint model
- **WHEN** a breakpoint response is received from Rider API
- **THEN** it SHALL be parsed into a `Breakpoint` Pydantic model with validated fields (id, file, line, enabled, condition)
