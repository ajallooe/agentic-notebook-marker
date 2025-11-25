# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **Agentic Notebook Marker System** - a CLI-based automated marking system for Jupyter notebook assignments using LLM agents. The system supports two assignment types:

1. **Fill-in-the-blank (structured)**: Students complete pre-structured notebooks with clearly marked sections
2. **Free-form**: Students build solutions from scratch based on assignment descriptions

## Assignment Directory Structure

All assignments follow this structure:

```text
assignments/
├── <assignment_name>/
│   ├── <base_file>.ipynb          # Base notebook (structured assignments only)
│   ├── overview.md                # Assignment metadata and configuration
│   ├── submissions/
│   │   ├── <section_name>/
│   │   │   ├── <student_name>.ipynb
│   │   │   └── <nested_subdirs>/  # Submissions can be nested with spaces in names
│   │   │       └── <student_name>.ipynb
│   └── processed/                 # All generated artifacts go here
│       ├── rubric/
│       ├── activities/
│       ├── markings/
│       ├── normalized/
│       └── final/
```

**Important**: Submission files may:

- Be deeply nested in subdirectories
- Contain spaces in filenames
- Be located at any depth within a section directory

Always use quoted paths when handling files via shell commands.

## Structured Assignment Format

In fill-in-the-blank notebooks, student work areas are delimited by:

- Activity markers: `**[A1]**`, `**[A2]**`, etc. in markdown cells
- Input boundaries: Text cells containing `*Start student input* ↓` and `*End student input ↑*`
- Multiple delimited sections may exist per activity
- Students may add cells within delimited areas
- Both code and markdown cells can appear in student input sections

See `dev/examples/structured_assignment_example.ipynb` for reference.

## Agent-Based Workflow

The system orchestrates multiple specialized LLM agents:

### 1. Marking Pattern Designer Agent (Interactive)

- Analyzes assignment requirements
- Creates detailed per-activity marking criteria
- Generates or validates rubrics
- Interacts with instructor for clarifications
- **Output**: `processed/activities/A<i>_criteria.md` and `processed/rubric.md`

### 2. Marker Agents (Headless, Parallel)

- One agent per activity per student (structured) OR one per student (free-form)
- Identifies mistakes and positive points qualitatively
- Does NOT assign numerical scores
- **Output**: `processed/markings/<student>_A<i>.md` or `processed/markings/<student>.md`

### 3. Normalizer Agent (Headless)

- One per activity (structured) OR one total (free-form)
- Aggregates all markings for an activity
- Creates unified mistake/positive tables with severity (1-10 scale)
- Suggests mark deductions and bonuses
- **Output**: `processed/normalized/A<i>_scoring.md` or `processed/normalized/scoring.md`

### 4. Instructor Review

- Presents aggregated scoring in editable format (Excel/Google Sheets)
- Shows live histogram of mark distribution
- Allows numerical adjustments with immediate distribution updates

### 5. Unifier Agents (Headless, Parallel)

- One per student after instructor approval
- Applies final marking scheme
- Detects broader patterns and potential academic integrity issues
- Suggests rare adjustments (requires instructor approval)
- **Output**: `processed/final/<student>_feedback.md`

### 6. Aggregator Agent (Interactive)

- Consolidates all feedback into CSV format
- Columns: Student Name, Total Mark, Feedback Card, Activity Marks
- Can merge with base CSV (e.g., Moodle gradebook export)
- **Output**: `processed/final/grades.csv`

## overview.md Configuration

Each assignment's `overview.md` should specify:

- **default_provider**: `claude`, `gemini`, or `codex`
- **default_model**: e.g., `claude-sonnet-4`, `gemini-3-pro-preview`, `gpt-5.1`
- **base_file**: Name of starter notebook (structured assignments only)
- **assignment_type**: `structured` or `free-form`
- Assignment description and any supplementary materials

## Progress Reporting

The system provides console output with:

- Current activity: `<current_activity_index>/<total_activities>`
- Current student: `<current_student_index>/<total_students>`
- Percentage completion
- Status updates when tasks start/complete

Example: `[A2/7] [Student 15/42] (35.7%) Marking student_name...`

## Development Tools

The `/dev` directory contains:

- `agentic-notebook-marker.prompt.md`: Original detailed project specification
- `examples/structured_assignment_example.ipynb`: Reference structured notebook
- `dev.log`: Development session transcripts

## Key Implementation Notes

1. **Context Optimization**: Extract only student-modified cells per activity to reduce token usage in marker agent prompts
2. **Session Management**: Interactive agents use `script` command or equivalent to capture full session transcripts
3. **Headless Execution**: Marker, normalizer, and unifier agents run non-interactively with output redirection
4. **Path Handling**: Always quote paths containing spaces in shell commands
5. **Token Limits**: Be mindful of maximum context sizes when crafting agent prompts
6. **Academic Integrity**: Unifier agents assess likelihood of LLM usage and other integrity concerns

## Agent Invocation Pattern

The system should provide a unified caller interface that accepts:

- `--prompt <text>`: Initial prompt for the agent
- `--mode <interactive|headless>`: Execution mode (default: interactive)
- `--provider <claude|gemini|codex>`: LLM provider (optional, uses default)
- `--model <model_name>`: Specific model (optional, provider inferred from name)
- Agent type can have default provider/model overrides per assignment

## Project Setup

### Quick Setup

```bash
# 1. Create virtual environment and install dependencies
make install

# 2. Enable Jupyter widgets
make enable-widgets

# 3. Check prerequisites
make check-prereqs

# 4. Activate virtual environment
source .venv/bin/activate

# 5. Test with sample assignment
./mark_structured.sh assignments/sample-assignment
```

### Configuration Files

- **requirements.txt**: Python dependencies (pandas, numpy, matplotlib, ipywidgets, jupyter)
- **Makefile**: Automation for setup, testing, and cleanup
- **.gitignore**: Excludes generated files, processed artifacts, and all assignments except sample
- **assignments/overview_template.md**: Template for creating assignment configuration files

### Sample Assignment

The `assignments/sample-assignment/` directory contains example submissions demonstrating the expected directory structure and nested file organization.

## Implementation Components

### Core Infrastructure (`src/`)

**Utilities** (`src/utils/`):

- `logger.py`: Error tracking, state management, reproducibility (checksums, state files)
- `progress.py`: Real-time progress reporting with activity/student counters

**Tools**:

- `llm_caller.sh`: Unified CLI router for Claude Code, Gemini CLI, OpenAI CLI
- `parallel_runner.sh`: Parallel task execution with configurable concurrency
- `extract_activities.py`: Extract student input per activity with graceful error handling
- `find_submissions.py`: Recursively find and validate notebook submissions
- `create_dashboard.py`: Generate interactive Jupyter notebook for mark adjustment

**Agent Prompts** (`src/prompts/`):

- Pattern Designer: `pattern_designer_structured.md`, `pattern_designer_freeform.md`
- Marker: `marker_structured.md`, `marker_freeform.md`
- Normalizer: `normalizer_structured.md`, `normalizer_freeform.md`
- Unifier: `unifier.md`
- Aggregator: `aggregator.md`

**Orchestrators** (root directory):

- `mark_structured.sh`: Main workflow for fill-in-the-blank assignments
- `mark_freeform.sh`: Main workflow for free-form assignments

### Workflow Stages

1. **Submission Discovery**: `find_submissions.py` → `submissions_manifest.json`
2. **Activity Extraction**: `extract_activities.py` → per-activity JSON (structured only)
3. **Pattern Design**: Interactive agent → `activities/A*_criteria.md`, `rubric.md`
4. **Parallel Marking**: Marker agents (via `parallel_runner.sh`) → `markings/`
5. **Normalization**: Normalizer agents → `normalized/A*_scoring.md`
6. **Adjustment Dashboard**: `create_dashboard.py` → `adjustment_dashboard.ipynb`
7. **Instructor Approval**: Jupyter notebook → `approved_scheme.json`
8. **Parallel Unification**: Unifier agents → `final/*_feedback.md`
9. **Aggregation**: Interactive agent → `final/grades.csv`

### Error Handling Strategy

**Graceful Failures**:

- Schema violations: Log error, skip student, continue with others
- Missing files: Log warning, continue
- Agent failures: Retry once, log error, continue
- Invalid notebooks: Validate early, mark as failed, continue

**Error Tracking**:

- All errors logged to `processed/logs/errors_*.json`
- Failed students tracked separately
- Detailed error context (student, activity, file path, exception)

**Reproducibility**:

- State tracking in `processed/logs/state.json`
- File checksums recorded
- Completed activities/students tracked
- Resume from last checkpoint possible

### Parallel Execution

**Configurable Concurrency** (via `overview.md`):

- `max_parallel`: Number of simultaneous agent tasks
- Recommendation: Match CPU core count

**Parallel Stages**:

- Marker agents: n_students × n_activities tasks (structured) or n_students (free-form)
- Unifier agents: n_students tasks

**Implementation**:

- Uses GNU parallel if available (best performance and features)
- Falls back to xargs with concurrency
- Final fallback to sequential execution

**ARG_MAX Handling**:

The xargs implementation uses a line-number approach to avoid command-line length limits:
- Passes line numbers (1, 2, 3, ... N) through xargs instead of full command lines
- Workers read actual commands from file using `sed -n "${line_num}p"`
- Avoids ARG_MAX errors when processing hundreds of tasks with long file paths
- Critical for large structured assignments (e.g., 7 activities × 32 students = 224 tasks)

**Testing xargs (Debug Option)**:

To force xargs usage even when GNU parallel is available (useful for testing):
```bash
./mark_structured.sh assignments/lab1 --force-xargs
./mark_freeform.sh assignments/project1 --force-xargs
```

This bypasses parallel detection and uses xargs, allowing verification that the
ARG_MAX fix works correctly.

### CLI Tool Integration

The system uses CLI tools, NOT API calls:

- Claude Code: `claude` command
- Gemini CLI: `gemini` command (if installed)
- OpenAI CLI: `openai` command (if installed)

Interactive mode uses `script` for session capture.
Headless mode pipes input and captures output.

## Testing

To test with the sample assignment:

```bash
./mark_structured.sh assignments/sample-assignment
```

All agent implementations in `src/agents/` are complete and functional. Each agent loads its corresponding prompt template from `src/prompts/` and calls the appropriate LLM CLI tool via `src/llm_caller.sh`.
