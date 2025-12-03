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

- Uses GNU parallel if available
- Falls back to xargs with concurrency
- Final fallback to sequential execution

### CLI Tool Integration

The system supports two modes for LLM calls:

**CLI Mode (Default):**
- Claude Code: `claude` command
- Gemini CLI: `gemini` command (if installed)
- Codex CLI: `codex` command (if installed)

**API Mode (Optional):**
- Direct API calls using Python SDKs (`anthropic`, `google-generativeai`, `openai`)
- Enabled via `--api-model` flag for headless stages
- Requires API keys in environment variables

### LLM CLI Bridge (`src/llm_caller.sh`)

A portable, future-proof shell script providing unified interface across all three CLI tools and API modes:

```bash
# Model-based (provider auto-resolved from model name)
./src/llm_caller.sh --model gemini-2.5-pro --prompt "Hello" --mode headless

# Provider-based (uses provider's default model)
./src/llm_caller.sh --provider claude --prompt "Hello" --mode headless

# API mode (direct API calls instead of CLI tools)
./src/llm_caller.sh --api-model gemini-2.5-flash --mode headless --prompt "Hello"

# With config file
./src/llm_caller.sh --config configs/config.yaml --prompt "Hello"

# Key options:
#   --model <name>                    Model name for CLI calls (provider auto-resolved)
#   --api-model <name>                Model for direct API calls (headless only)
#   --provider <claude|gemini|codex>  Explicit provider (optional if --model given)
#   --mode <interactive|headless>     Default: interactive
#   --prompt <text>                   The prompt
#   --prompt-file <file>              Read prompt from file
#   --auto-approve                    Skip permission prompts
#   --output <file>                   Capture output to file
```

Provider is auto-resolved from model names via `configs/models.yaml`.
See `docs/LLM_BRIDGE_STANDALONE.md` for integration patterns.

### API Mode Setup

To use direct API calls instead of CLI tools:

1. **Install Python SDKs:**
   ```bash
   pip install anthropic google-generativeai openai
   ```

2. **Set up API keys** in `.secrets/` directory:
   ```
   .secrets/
   ├── CLAUDE_API_KEY      # Claude/Anthropic (also supports ANTHROPIC_API_KEY for compatibility)
   ├── GEMINI_API_KEY      # Google/Gemini (also works as GOOGLE_API_KEY)
   └── OPENAI_API_KEY      # OpenAI
   ```
   Each file contains just the key value (no newlines).

3. **Load keys into environment:**
   ```bash
   source utils/load_api_keys.sh
   ```

4. **Use `--api-model` flag:**
   ```bash
   # Mixed workflow: API for headless stages, CLI for interactive
   ./mark_structured.sh assignments/lab1 --api-model gemini-2.5-flash

   # Full API workflow (all stages headless)
   ./mark_structured.sh assignments/lab1 --api-model gemini-2.5-flash --auto-approve
   ```

**Behavior:**
- `--api-model` only affects headless calls (`--mode headless`)
- Interactive stages always use CLI (needed for terminal interaction)
- With `--auto-approve`, all stages become headless and use API

### Prompt Caching

The API caller supports prompt caching to reduce costs when the same system prompt is used repeatedly (e.g., same rubric for all students):

```bash
# With system prompt for caching (used internally by marker agents)
python3 src/api/caller.py --model claude-sonnet-4-5 \
    --system-prompt-file processed/rubric.md \
    --prompt "Grade this student: ..."
```

**Provider-specific caching:**

| Provider | Type | Min Tokens | TTL | Savings | Notes |
|----------|------|------------|-----|---------|-------|
| Claude | Explicit | 1,024 | 5 min | 90% reads | Uses `cache_control` markers |
| Gemini 2.5 | Implicit | 1,024-4,096 | 60 min | 90% hits | Automatic, no code changes |
| OpenAI | Automatic | 1,024 | 5-10 min | 50% | Automatic, no code changes |

**Best practices:**
- Put static content (rubric, criteria) in `--system-prompt`
- Put variable content (student work) in `--prompt`
- System prompts should be >1024 tokens for caching benefit
- Caches auto-expire; no manual clearing typically needed

**Clear caches** (if process interrupted):
```bash
./utils/clear_caches.sh           # List cache status
./utils/clear_caches.sh --delete  # Delete explicit Gemini caches
```

### `utils/load_api_keys.sh`

Load API keys from `.secrets/` into environment variables:

```bash
source utils/load_api_keys.sh   # from project root
source load_api_keys.sh         # from utils/ directory
```

Must be **sourced** (not executed) for exports to persist in your shell.

### System Configuration (`configs/config.yaml`)

```yaml
default_provider: claude    # Used when --provider not specified
default_model:              # Optional, uses CLI default if empty
max_parallel: 4
verbose: true
```

### Model Configuration (`configs/models.yaml`)

Maps model names to providers and defines default models. **All models must be registered here** - unknown models will show an error with the list of available models.

```yaml
defaults:
  claude:           # Default model for Claude (blank = CLI default)
  gemini:           # Default model for Gemini
  codex:            # Default model for Codex/OpenAI

models:
  # Claude models (Anthropic)
  claude-opus-4-5: claude
  claude-sonnet-4-5: claude
  claude-haiku-4-5: claude

  # Gemini models (Google)
  gemini-3-pro-preview: gemini
  gemini-2.5-pro: gemini
  gemini-2.5-flash: gemini
  gemini-2.5-flash-lite: gemini

  # OpenAI/Codex models
  gpt-5.1: codex
  gpt-5-mini: codex
  gpt-5-nano: codex
  gpt-5-pro: codex

# Expensive models (require CLI confirmation, cannot be defaults)
expensive:
  - claude-opus-4-5
  - gpt-5-pro
```

**Model Resolution Priority:**
1. Command-line `--model` or `--provider` arguments
2. Assignment-specific settings in `overview.md` (`default_model`, `default_provider`)
3. Project defaults from `configs/config.yaml`

When an unknown model is specified, the system shows all available models and asks to update `configs/models.yaml`.

**Expensive Models:**
- Models in the `expensive` section have significantly higher costs
- Cannot be set as defaults in `config.yaml` or `overview.md`
- Must be explicitly specified via CLI argument (`--model` or `--api-model`)
- Require user confirmation before proceeding (default: no)

## Batch Marking Utilities

The `utils/` directory contains batch processing tools:

### `utils/batch_mark.sh`

Process multiple assignments in staged rounds (runs continuously without pauses):

```bash
# Run complete workflow (provider auto-resolved from model name)
./utils/batch_mark.sh assignments.txt --model gemini-2.5-pro

# Resume from a specific round
./utils/batch_mark.sh assignments.txt --model gemini-2.5-pro --start-round 3

# Or specify provider explicitly (useful for default model)
./utils/batch_mark.sh assignments.txt --provider claude

# Use API calls for headless stages (mixed mode)
./utils/batch_mark.sh assignments.txt --model gemini-2.5-pro --api-model gemini-2.5-flash

# Full API workflow with auto-approve
./utils/batch_mark.sh assignments.txt --api-model gemini-2.5-pro --auto-approve
```

**Automatic 5-round workflow (continuous):**
1. Round 1: Stages 1-2 (Preparation) for ALL
2. Round 2: Stage 3 (Pattern Design - INTERACTIVE) for ALL
3. Round 3: Stages 4-5 (Marking + Normalization) for ALL
4. Round 4: Stage 6 (Dashboard - INTERACTIVE) for ALL
5. Round 5: Stages 7-9 (Completion) for ALL

Either `--model` or `--provider` is required. Provider is auto-resolved from model names (see `configs/models.yaml`). The script automatically prompts to generate missing `overview.md` files.

Optional `--api-model` enables direct API calls for headless stages (requires API keys).

### `utils/translate_grades.sh`

Map graded students to gradebook entries:

```bash
./utils/translate_grades.sh \
    --assignment-dir "assignments/Lab 02" \
    --gradebooks "path/to/gradebook1.csv" "path/to/gradebook2.csv"
```

**Robust Name Matching:**

The translation system handles various name format inconsistencies:

- **BOM handling**: Strips UTF-8 BOM characters from Excel CSV exports (common in `\ufeffFirst name` columns)
- **Name normalization**: Handles "First,Last" vs "First Last" formats (LLM sometimes joins names with commas)
- **Whitespace normalization**: Normalizes multiple spaces and trims names
- **Case insensitivity**: All matching is case-insensitive
- **Separate vs combined name columns**: Automatically detects "First name"/"Last name" columns or combined "Student Name" column

### `utils/create_overview.sh`

Generate overview.md from a base notebook:

```bash
# Provider auto-resolved from model name
./utils/create_overview.sh assignments/new-assignment/base.ipynb --model claude-sonnet-4

# Or specify just the provider for default model
./utils/create_overview.sh assignments/new-assignment/base.ipynb --provider claude
```

Either `--model` or `--provider` is required.

### `utils/lock_assignment.sh`

Protect assignment files from accidental modification during marking:

```bash
# Lock submissions, notebooks, and overview.md (default)
./utils/lock_assignment.sh "assignments/Lab 01"

# Lock all files (except directories remain writable for new artifacts)
./utils/lock_assignment.sh "assignments/Lab 01" --lock-all

# Unlock when done
./utils/lock_assignment.sh "assignments/Lab 01" --unlock

# Preview changes without applying
./utils/lock_assignment.sh "assignments/Lab 01" --dry-run
```

### `utils/summarize_feedback.sh`

Condense detailed feedback cards into single plain-text paragraphs for gradebook comments:

```bash
# Summarize feedback from grades.csv
./utils/summarize_feedback.sh assignments/lab1/processed/final/grades.csv

# Use specific provider and model
./utils/summarize_feedback.sh grades.csv --provider gemini --model gemini-2.5-pro

# Specify total marks if not 100
./utils/summarize_feedback.sh grades.csv --total-marks 50

# Specify custom output file
./utils/summarize_feedback.sh grades.csv --output summaries.csv

# Preview without calling LLM
./utils/summarize_feedback.sh grades.csv --dry-run
```

Creates 3-4 sentence summaries focusing on key mistakes and positives. For very low marks (<40%), provides more detailed explanations. Output: `<input>_summarized.csv`.

### `utils/modify_feedback.sh`

Apply targeted modifications to feedback in CSV files:

```bash
# Remove specific content from all feedback
./utils/modify_feedback.sh grades.csv -i "Remove all mentions of random_state"

# Add a note to all feedback
./utils/modify_feedback.sh grades.csv -i "Add 'Late submission: -10%' at the end"

# Fix errors in feedback
./utils/modify_feedback.sh grades.csv -i "Replace 'Activity 5' with 'Activity 6' everywhere"

# Preview changes first
./utils/modify_feedback.sh grades.csv -i "Remove bonus point mentions" --dry-run

# Modify in-place with backup
./utils/modify_feedback.sh grades.csv -i "Remove random_state comments" --in-place
```

Preserves everything except the requested changes. Creates `.bak` backup when using `--in-place`.

### `utils/clean_artifacts.sh`

Remove LLM generation artifacts (like "YOLO mode is enabled...") from files:

```bash
# Clean artifacts from a file
./utils/clean_artifacts.sh input.md --artifacts configs/artifacts.jsonl

# Clean in-place
./utils/clean_artifacts.sh input.md --artifacts configs/artifacts.jsonl --in-place
```

Artifacts are defined in a JSONL file with `{"artifact": "text to remove"}` entries.

### `utils/clear_caches.sh`

Clear any explicit API caches that may be accumulating costs (use after interrupted processes):

```bash
# List cache status for all providers
./utils/clear_caches.sh

# Delete all explicit Gemini caches
./utils/clear_caches.sh --delete

# Preview what would be deleted
./utils/clear_caches.sh --dry-run
```

**Note**: Claude and OpenAI caches auto-expire (5-10 min). Only Gemini explicit caches need manual deletion, but this system uses implicit caching which is managed automatically by Google.

## Error Handling and Recovery

### Reviewing Errors After Failed Marking

When marking fails (e.g., due to API quota exhaustion, timeouts, or network errors), use `review_errors.sh` to get a consolidated error report:

```bash
# Review all errors for an assignment
./review_errors.sh "assignments/Lab 01"

# Check only marker stage errors
./review_errors.sh "assignments/Lab 01" --stage marker

# Check only unifier stage errors
./review_errors.sh "assignments/Lab 01" --stage unifier

# Export errors to JSON for programmatic analysis
./review_errors.sh "assignments/Lab 01" --json

# Quick check (exits 0 if no errors, 1 if errors found)
./review_errors.sh "assignments/Lab 01" --quiet
```

The script categorizes errors by type:
- **quota/rate_limit**: API capacity exhausted (wait and retry)
- **timeout**: Task took too long (retry or increase timeout)
- **network**: Connection issues (retry)
- **permission**: File access issues (check permissions)
- **llm_failure**: LLM-specific errors

### Force-Completing Failed Marking

When some students fail to process but you need to complete marking (e.g., deadline pressure), use `--force-complete`:

```bash
# Complete marking, assigning zero to failed students
./mark_structured.sh "assignments/Lab 01" --force-complete

# Same for freeform assignments
./mark_freeform.sh "assignments/Lab 01" --force-complete

# In batch mode
./utils/batch_mark.sh assignments.txt --provider gemini --model gemini-2.5-pro --force-complete
```

This generates placeholder feedback files for failed students with:
- Zero marks
- Error details explaining what went wrong
- Clear "REQUIRES MANUAL REVIEW" notice

**Important**: Activity-level failures are possible in structured assignments (marker stage creates per-activity files), but `--force-complete` currently operates at the student level. If only some activities failed, the student still gets a zero-mark placeholder requiring manual review.

### Failure Detection

The marking scripts detect failures by counting missing output files rather than checking stderr logs. This approach:

- **Avoids false positives** from stale logs left by previous runs
- **Is more reliable** since output presence is the true success indicator
- **Cleans up** old marker logs before starting new runs (both structured and freeform)

When `--api-model` is used, quota error detection correctly resolves the provider from the model name (e.g., `gpt-5.1` → `codex`, `claude-sonnet-4-5` → `claude`) rather than using the default provider from `overview.md`.

### `--force-complete` Behavior

The `--force-complete` flag ensures the marking workflow completes even when some tasks fail:

- **Continues past parallel failures**: Uses `|| true` after parallel_runner.sh calls to prevent `set -e` from exiting
- **Generates zero-mark placeholders**: Failed students receive feedback files with clear "REQUIRES MANUAL REVIEW" notices
- **Completes all stages**: Proceeds through aggregation, translation, and summarization even with failures
- **Works in batch mode**: `./utils/batch_mark.sh assignments.txt --force-complete`

### Error Handling Utilities

- **`src/utils/error_summary.py`**: Analyzes parallel task logs and generates categorized error reports
- **`src/utils/force_complete.py`**: Generates zero-mark feedback cards for failed students
- **`utils/show_errors.sh`**: Quick wrapper to show errors for a logs directory

## Testing

To test with the sample assignment:

```bash
./mark_structured.sh assignments/sample-assignment
```

All agent implementations in `src/agents/` are complete and functional. Each agent loads its corresponding prompt template from `src/prompts/` and calls the appropriate LLM CLI tool via `src/llm_caller.sh`.
