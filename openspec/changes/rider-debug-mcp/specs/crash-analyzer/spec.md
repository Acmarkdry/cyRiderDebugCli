## ADDED Requirements

### Requirement: CrashAnalyzer SHALL auto-detect crashes and exceptions
The CrashAnalyzer SHALL automatically detect when a crash or unhandled exception occurs during a debug session by subscribing to the EventListener's exception and process-exit events.

#### Scenario: Detect unhandled exception
- **WHEN** an unhandled exception event is received from the EventListener
- **THEN** the CrashAnalyzer SHALL automatically trigger a full crash analysis workflow

#### Scenario: Detect abnormal process termination
- **WHEN** the debugged process terminates with a non-zero exit code
- **THEN** the CrashAnalyzer SHALL record the termination and trigger analysis if a crash pattern is detected

### Requirement: CrashAnalyzer SHALL collect crash context
Upon detecting a crash, the CrashAnalyzer SHALL collect: full stack trace, local variables at each frame, exception type and message, thread information, and recent breakpoint hit history.

#### Scenario: Collect full crash context
- **WHEN** a crash is detected
- **THEN** the analyzer SHALL collect stack trace, variables, exception details, thread info, and recent breakpoint history into a CrashContext object

#### Scenario: Handle partial data collection
- **WHEN** some crash context data is unavailable (e.g., variables cannot be read)
- **THEN** the analyzer SHALL collect what is available and mark missing fields as `unavailable` with a reason

### Requirement: CrashAnalyzer SHALL generate structured crash reports
The CrashAnalyzer SHALL produce structured crash reports containing a summary, root cause analysis section, stack trace with annotations, variable state, and suggested investigation steps.

#### Scenario: Generate crash report
- **WHEN** crash context collection is complete
- **THEN** the analyzer SHALL generate a CrashReport with: summary (1-2 sentences), exception chain, annotated stack trace, variable snapshot, and investigation suggestions

#### Scenario: Query crash report via rider_query
- **WHEN** AI calls `rider_query` with query `crash_report`
- **THEN** the system SHALL return the most recent crash report in a structured format

#### Scenario: Query crash history
- **WHEN** AI calls `rider_query` with query `crash_history`
- **THEN** the system SHALL return a list of all crash reports from the current session with timestamps and summaries

### Requirement: CrashAnalyzer SHALL parse and annotate stack traces
The CrashAnalyzer SHALL parse raw stack traces into structured frames, identify user code vs framework code, and annotate frames with source file and line information.

#### Scenario: Parse .NET stack trace
- **WHEN** a raw .NET stack trace string is provided
- **THEN** the analyzer SHALL parse it into a list of StackFrame objects with namespace, class, method, file, and line number

#### Scenario: Distinguish user code from framework code
- **WHEN** a stack trace is parsed
- **THEN** each frame SHALL be tagged as `user_code` or `framework_code` based on configurable namespace patterns
