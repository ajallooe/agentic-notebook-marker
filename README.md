# Agentic Notebook Marker

An automated marking system for Jupyter notebook assignments using LLM agents coordinated via CLI tools.

**Repository**: [https://github.com/ajallooe/agentic-notebook-marker](https://github.com/ajallooe/agentic-notebook-marker)

## Quick Start

### For Structured (Fill-in-the-Blank) Assignments

```bash
# Optional: Place gradebook CSVs for automatic translation
mkdir -p assignments/your-assignment-name/gradebooks
cp ~/Downloads/*.csv assignments/your-assignment-name/gradebooks/

# Run marking workflow
./mark_structured.sh assignments/your-assignment-name
```

### For Free-form Assignments

```bash
# Optional: Place gradebook CSVs for automatic translation
mkdir -p assignments/your-assignment-name/gradebooks
cp ~/Downloads/*.csv assignments/your-assignment-name/gradebooks/

# Run marking workflow
./mark_freeform.sh assignments/your-assignment-name
```

### Command-Line Options

```bash
# Override max parallel tasks
./mark_structured.sh assignments/your-assignment-name --parallel 8

# Stop after completing a specific stage (useful for debugging)
./mark_structured.sh assignments/your-assignment-name --stop-after 3

# Skip artifact cleaning (keep LLM generation artifacts in output files)
./mark_structured.sh assignments/your-assignment-name --no-clean-artifacts

# Force use of xargs instead of GNU parallel (for testing)
./mark_structured.sh assignments/your-assignment-name --force-xargs

# Combine multiple options
./mark_structured.sh assignments/your-assignment-name --parallel 2 --stop-after 4 --no-clean-artifacts
```

**Available flags**:

- `--parallel N`: Override max parallel tasks (overrides overview.md and config.yaml)
- `--stop-after N`: Stop after completing stage N (1-9 for structured, 1-8 for freeform)
- `--no-clean-artifacts`: Skip cleaning LLM artifacts from grades.csv
- `--no-resume`: Start from scratch, ignoring previous progress
- `--clean`: Remove processed directory and start completely fresh
- `--force-xargs`: Force use of xargs instead of GNU parallel (for testing)

### Resume Options

The marking scripts automatically resume from where they left off by default. If a stage or task has already been completed, it will be skipped.

```bash
# Resume from previous run (default behavior)
./mark_structured.sh assignments/your-assignment-name

# Start from scratch, ignoring previous progress
./mark_structured.sh assignments/your-assignment-name --no-resume

# Remove all processed files and start completely fresh
./mark_structured.sh assignments/your-assignment-name --clean
```

**What gets preserved**:

- Completed stages (e.g., submission discovery, activity extraction)
- Completed marker tasks (e.g., 196 out of 224 students already marked)
- Completed normalizer outputs
- Approved marking schemes
- Generated feedback files

**When to use each option**:

- **Default (resume)**: When errors occur mid-process or you want to continue after stopping
- **`--no-resume`**: When you want to regenerate everything from existing processed files
- **`--clean`**: When you want to completely start over (deletes `processed/` directory)

**Example**: Recovering from errors

```bash
# First run - processes 196/224 students before error
./mark_structured.sh assignments/lab1

# Second run - only processes the 28 failed students
./mark_structured.sh assignments/lab1
# Output: "Generated 28 marker tasks (skipped 196 already completed)"
```

## What This System Does

This system semi-automates the marking of Jupyter notebook assignments through a carefully designed multi-agent workflow:

### Workflow Stages

1. **Submission Discovery** - Finds and validates all student notebooks
2. **Activity Extraction** - Extracts student work from structured assignments (structured only)
3. **Marking Pattern Designer** - Analyzes assignment and creates detailed marking criteria
4. **Marker Agents** - Evaluate each student's work qualitatively (in parallel)
5. **Normalizer Agent** - Aggregates assessments and creates unified scoring scheme
6. **Instructor Review** - Interactive dashboard for adjusting marks and viewing distribution
7. **Unifier Agents** - Apply final scheme and create student feedback cards (in parallel)
8. **Group Feedback Duplication** - Distributes group marks to individual members (group assignments only)
9. **Aggregator** - Consolidates everything into a CSV for grade upload
10. **Artifact Cleaning** - Removes LLM generation artifacts from output (optional, automatic)
11. **Gradebook Translation** - Transfers grades back to LMS gradebooks with intelligent name matching (optional, automatic)

### Why This Multi-Stage Approach?

The system deliberately separates **qualitative evaluation** from **quantitative scoring** for several key reasons:

**1. Consistency Through Calibration**

- Early marker agents evaluate work qualitatively (identifying mistakes, positive points)
- The normalizer agent then sees ALL student work patterns before assigning point values
- This ensures similar mistakes receive consistent deductions across all students
- Prevents the "first student penalty" where early evaluations may be harsher or more lenient

**2. Instructor Control**

- The interactive dashboard shows the full distribution of marks before finalization
- Instructors can adjust the severity of deductions to achieve desired grade distribution
- Changes are immediately reflected in a histogram showing impact on class marks
- Final approval required before individual feedback is generated

**3. Scalability Without Quality Loss**

- Parallelizes the most time-intensive steps (marker and unifier agents)
- Each student gets detailed, individualized feedback
- Human instructor focuses only on high-level scoring decisions, not repetitive evaluation
- Can process 200+ students with the same attention to detail as 20 students

**4. Reduced Bias**

- LLMs evaluate code/work objectively without names attached
- Aggregation happens after qualitative assessment, not during
- Academic integrity concerns flagged for instructor review rather than automatic penalties
- Consistent criteria applied across all submissions

## Prerequisites

- Python 3.8+
- One or more LLM CLI tools: Claude Code (`claude`), Gemini CLI (`gemini`), or Codex CLI (`codex`)
- Optional but recommended: GNU Parallel, jq

## Installation

### Quick Setup (Recommended)

```bash
# 1. Create virtual environment and install dependencies
make install

# 2. Enable Jupyter widgets
make enable-widgets

# 3. Check that CLI tools are available
make check-prereqs

# 4. Activate virtual environment
source .venv/bin/activate
```

### Manual Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Enable Jupyter widgets
jupyter nbextension enable --py widgetsnbextension
```

## System Configuration

### Global Defaults (`configs/config.yaml`)

The system-wide configuration file defines fallback defaults for all assignments:

```yaml
# configs/config.yaml
default_provider: claude    # Options: claude, gemini, codex
default_model:              # Optional: specific model (e.g., gpt-5.1, claude-sonnet-4)
max_parallel: 4             # Number of parallel tasks
verbose: true               # Enable detailed logging
```

**Configuration hierarchy**:

1. **Command-line flags** (`--parallel N`) - highest priority
2. **Assignment-specific** (`assignments/*/overview.md`)
3. **System-wide** (`configs/config.yaml`) - fallback defaults
4. **Hardcoded fallbacks** - if config.yaml is missing

**Example**:

```yaml
# configs/config.yaml - your preferred defaults
default_provider: codex
default_model: gpt-5.1
max_parallel: 4

# assignments/lab1/overview.md - override for this assignment only
default_provider: gemini
default_model: gemini-2.0-flash-exp
max_parallel: 2
```

```bash
# Further override with command-line flag
./mark_structured.sh assignments/lab1 --parallel 8
# Will use: Gemini 2.0, 8 parallel tasks
```

This assignment will use Gemini with 8 parallel tasks, while others use Codex by default.

## Assignment Structure

### Directory Layout

Create your assignment directory as follows:

```text
assignments/
└── assignment-name/
    ├── overview.md                    # Assignment config and description
    ├── base_notebook.ipynb            # Base notebook (structured only)
    ├── groups.csv                     # Optional: Group membership (group assignments)
    ├── submissions/
    │   ├── section-1/
    │   │   ├── student1.ipynb         # Individual submission
    │   │   ├── Team Alpha.ipynb       # Or group submission
    │   │   └── nested/
    │   │       └── student2.ipynb
    │   └── section-2/
    │       └── student3.ipynb
    ├── gradebooks/                    # Optional: For automatic translation
    │   ├── section1.csv               # LMS gradebook exports (e.g., Moodle)
    │   └── section2.csv
    └── processed/                     # Auto-generated artifacts
```

### Key File Locations Reference

| File/Directory | Location | Required? | Purpose |
|----------------|----------|-----------|---------|
| `overview.md` | `assignments/<name>/` | **Required** | Assignment config and description |
| `base_notebook.ipynb` | `assignments/<name>/` | Structured only | Starter notebook with activity markers |
| `groups.csv` | `assignments/<name>/` | Group assignments | Group membership (group_name,student_name) |
| `problem.md` | `assignments/<name>/submissions/<section>/<group>/` | Different-problems only | Each group's specific problem description |
| `gradebooks/*.csv` | `assignments/<name>/gradebooks/` | Optional | LMS gradebook exports for auto-translation |
| `processing_artifacts.jsonl` | `configs/` | Optional | LLM artifact strings to remove from output |
| `config.yaml` | `configs/` | Optional | System-wide default settings |

**Notes**:

- For **different-problems** group assignments: Each group's submission should be in a subdirectory containing both their notebook and `problem.md`
- For **regular** group assignments: Group submissions can be directly in the section directory (e.g., `Team Alpha.ipynb`)
- The `gradebooks/` directory is only needed if using the `translate_grades.sh` utility
- Edit `processing_artifacts.jsonl` to add custom LLM artifacts to clean from feedback

## Configuration (overview.md)

Your `overview.md` should include:

```markdown
---
default_provider: claude
default_model: claude-sonnet-4
max_parallel: 4
base_file: lab1_base.ipynb
assignment_type: structured
total_marks: 100
group_assignment: false  # Set to true for group assignments

# Per-stage model overrides (optional)
stage_models:
  pattern_designer: claude-sonnet-4-5
  marker: claude-sonnet-4
  normalizer: claude-sonnet-4-5
  unifier: claude-sonnet-4
  aggregator: claude-sonnet-4-5
---

# Assignment Description

[Your assignment description here...]
```

### Per-Stage Model Configuration

The system supports specifying different models for each stage of the marking workflow. This allows you to optimize cost and performance by using more capable models for complex tasks (like Pattern Designer) and faster models for repetitive tasks (like parallel Marker agents).

**Configuration Priority** (highest to lowest):

1. **Stage-specific model** - Defined in `stage_models` section of overview.md
2. **Assignment default model** - Defined in `default_model` field of overview.md
3. **Project config default** - Defined in `config.yaml` at project root

**Available Stages**:

- `pattern_designer` - Interactive agent that creates rubric and marking criteria (Stage 1)
- `marker` - Parallel agents that evaluate student work (Stage 2, runs many times)
- `normalizer` - Agent that aggregates and normalizes markings (Stage 3)
- `unifier` - Parallel agents that create final student feedback (Stage 4, runs many times)
- `aggregator` - Interactive agent that generates final CSV (Stage 5)

### Group Assignments

For assignments where students work in teams, the system supports group-based marking to avoid evaluating duplicate submissions:

**Setup**:

1. **Mark as group assignment** in `overview.md`:

```yaml
---
group_assignment: true
assignment_type: structured  # or freeform
total_marks: 100
---
```

2. **Create `groups.csv`** in assignment directory:

```csv
group_name,student_name
Team Alpha,John Smith
Team Alpha,Jane Doe
Team Beta,Bob Johnson
Team Beta,Alice Williams
```

3. **Submit group work** with group names:
   - Submissions should be named after groups: `Team Alpha.ipynb`, `Team Beta.ipynb`
   - Place in the usual `submissions/` directory structure

**How it works**:

1. Stages 1-7: System marks group submissions only (not individual students)
2. Stage 7.5 (automatic): Group feedback is duplicated to each team member
   - `Team Alpha_feedback.md` → `John Smith_feedback.md`, `Jane Doe_feedback.md`
3. Stage 8: Aggregator creates individual student rows in grades.csv

**Notes**:

- Each student receives their own row in the final CSV with the group's mark
- Individual feedback files are created via symlinks (efficient) or copies
- Students in multiple groups will trigger a warning during processing
- Group membership is only needed for final grade distribution, not during marking

### Different-Problem Group Assignments

For group assignments where **each group solves a different problem** (e.g., different datasets, different case studies), the system supports **abstract marking criteria** with problem-specific context:

**Requirements**:

- Must be a `group_assignment: true`
- Must be `assignment_type: freeform`
- Set `different_problems: true` in `overview.md`

**Setup**:

1. **Configure in `overview.md`**:

```yaml
---
group_assignment: true
assignment_type: freeform
different_problems: true
total_marks: 100
---

# Assignment Description

Your abstract assignment description goes here. Describe the **skills and techniques**
students should demonstrate, not specific problem details.

Example:
- Apply appropriate machine learning techniques to solve a classification problem
- Demonstrate proper data preprocessing and feature engineering
- Evaluate model performance using appropriate metrics
```

1. **Structure submissions** with problem descriptions:

```text
assignments/assignment-name/submissions/section-name/
├── Team Alpha/
│   ├── Team Alpha.ipynb         # Group's solution
│   └── problem.md               # Their specific problem description
├── Team Beta/
│   ├── Team Beta.ipynb
│   └── problem.md               # Different problem
```

Each group's `problem.md` should contain their specific problem, dataset description, and any supplementary materials.

1. **Create `groups.csv`** (same as regular group assignments):

```csv
group_name,student_name
Team Alpha,John Smith
Team Alpha,Jane Doe
Team Beta,Bob Johnson
```

**How it works**:

1. **Stage 1.5**: System extracts each group's `problem.md` and supplementary files into `problem_contexts.json`
2. **Stage 2**: Pattern designer creates **abstract criteria** (e.g., "Correctly applied preprocessing" instead of "Correctly handled Titanic dataset")
3. **Stage 3**: Each marker agent receives:
   - Abstract marking criteria (same for all groups)
   - Group's specific problem description
   - Group's solution notebook
4. **Stages 4-8**: Normal workflow with problem-aware feedback

**Best practices for abstract criteria**:

✅ **Good (abstract)**:

- "Correctly identified and handled missing values"
- "Applied appropriate feature scaling techniques"
- "Selected suitable evaluation metrics for the problem type"

❌ **Bad (problem-specific)**:

- "Correctly predicted housing prices"
- "Used the Titanic survival column as target"
- "Achieved >80% accuracy on iris classification"

**Example Configurations**:

**Option 1: Use project defaults for all stages** (no model specified in overview.md)

```yaml
---
default_provider: claude
max_parallel: 4
# No default_model specified - uses project config default
# No stage_models specified - all stages use project config default
---
```

**Option 2: Use assignment default for all stages**

```yaml
---
default_provider: claude
default_model: claude-sonnet-4
max_parallel: 4
# No stage_models specified - all stages use claude-sonnet-4
---
```

**Option 3: Optimize per stage** (recommended for cost/performance balance)

```yaml
---
default_provider: claude
default_model: claude-sonnet-4     # Fallback for stages without overrides
max_parallel: 4

stage_models:
  pattern_designer: claude-sonnet-4-5  # Use most capable for rubric design
  marker: claude-sonnet-4              # Use faster model for parallel marking
  normalizer: claude-sonnet-4-5        # Use capable model for aggregation
  unifier: claude-sonnet-4             # Use faster model for parallel feedback
  aggregator: claude-sonnet-4-5        # Use capable model for final CSV
---
```

**Mixed Provider Example**:

You can even use different providers for different stages:

```yaml
---
default_provider: claude
default_model: claude-sonnet-4
max_parallel: 4

stage_models:
  pattern_designer: claude-sonnet-4-5  # Claude for interactive design
  marker: gemini-2.5-flash             # Fast Gemini for parallel marking
  normalizer: claude-sonnet-4-5        # Claude for aggregation
  unifier: gemini-2.5-flash            # Fast Gemini for parallel feedback
  aggregator: claude-sonnet-4-5        # Claude for final aggregation
---
```

**Tips**:

- Use more capable models (e.g., `claude-sonnet-4-5`, `gpt-5.1`) for stages requiring reasoning: pattern_designer, normalizer, aggregator
- Use faster/cheaper models (e.g., `claude-sonnet-4`, `gemini-2.5-flash`) for parallel stages: marker, unifier
- The `marker` and `unifier` stages run many times (once per student or per activity-student pair), so using faster models here saves significant time and cost
- All stages are optional in `stage_models` - only specify overrides where needed

## Generating overview.md Automatically

You can automatically generate an `overview.md` file from an existing Jupyter notebook using the overview generator:

```bash
# Using the shell wrapper (recommended)
./create_overview.sh <notebook_path> --model <model_name>

# Or call Python directly
python3 src/create_overview.py <notebook_path> --model <model_name>
```

**Examples**:

```bash
# Using Claude Sonnet
./create_overview.sh assignments/lab1/notebook.ipynb --model claude-sonnet-4-5

# Using Gemini
./create_overview.sh assignments/lab2/notebook.ipynb --model gemini-2.5-pro

# Using Codex
./create_overview.sh assignments/lab3/notebook.ipynb --model gpt-5.1
```

**What it does**:

- Analyzes the notebook structure and content
- Detects activity markers (`**[A1]**`, `**[A2]**`, etc.) for structured assignments
- Generates a properly formatted `overview.md` with:
  - YAML frontmatter (provider, model, assignment type, total marks)
  - Assignment overview and description
  - Learning objectives
  - Assignment structure
  - Grading criteria
- Places the file in the same directory as the notebook

**Notes**:

- The utility will not overwrite existing `overview.md` files
- Both the notebook path and model are mandatory arguments
- This should be run **before** the marking workflow
- You should review and adjust the generated overview as needed

## For Structured Assignments

Students complete notebooks with sections marked by:

- Activity markers: `**[A1]**`, `**[A2]**`, etc.
- Input delimiters: `*Start student input* ↓` and `*End student input ↑*`

See `dev/examples/structured_assignment_example.ipynb` for reference.

## Error Handling

The system gracefully handles:

- Broken notebook schemas (logs error, skips student, continues)
- Missing files (logs and continues)
- Agent failures (retries once, then logs and continues)
- Invalid JSON notebooks (logs error, marks as failed)

All errors are logged to `processed/logs/errors_*.json`

## Reproducibility

The system maintains state in `processed/logs/state.json`:

- Tracks completed activities and students
- Records file checksums
- Allows resuming interrupted runs
- Enables re-running specific stages

## Progress Tracking

The system provides clear, real-time progress tracking during parallel execution:

**With GNU parallel (recommended)**:

- Visual progress bar with percentage and ETA
- Clean, easy-to-read format

**With xargs (fallback)**:

```text
[ 45%] Completed 100/224 tasks
```

Progress updates show:

- Current percentage complete
- Number of tasks completed vs. total
- Updates in real-time as tasks finish

## Output Files

After completion, find:

- `processed/rubric.md` - Final rubric
- `processed/activities/A*_criteria.md` - Per-activity criteria (structured)
- `processed/markings/*` - Individual marker assessments
- `processed/normalized/*` - Normalized scoring tables
- `processed/adjustment_dashboard.ipynb` - Interactive adjustment tool
- `processed/approved_scheme.json` - Instructor-approved marking scheme
- `processed/final/*_feedback.md` - Per-student feedback cards
- `processed/final/grades.csv` - Final CSV for upload
- `processed/translation/*` - Gradebook translation results (if gradebooks provided)
- `processed/logs/*` - Complete logs and error reports

## Customizing Agent Behavior

Edit prompts in `src/prompts/` to change agent behavior:

- `pattern_designer_structured.md` / `pattern_designer_freeform.md`
- `marker_structured.md` / `marker_freeform.md`
- `normalizer_structured.md` / `normalizer_freeform.md`
- `unifier.md`
- `aggregator.md`

## Parallel Execution

Adjust `max_parallel` in `overview.md` to control concurrency:

- Marker agents: One per activity-student pair (structured) or per student (free-form)
- Unifier agents: One per student
- Recommendation: Set to number of CPU cores

**Execution Methods**:

- **GNU parallel** (recommended): Install with `brew install parallel` on macOS or `apt install parallel` on Linux
- **xargs** (fallback): Built into all Unix systems, automatically used if parallel not available
- **Sequential** (fallback): Used only if neither parallel nor xargs available

Both parallel and xargs show clear progress tracking with percentages and task counts.

## Using Different LLM Providers

The system supports multiple providers via CLI:

- **Claude Code**: `claude` command (default)
- **Gemini**: `gemini` command (requires Gemini CLI)
- **Codex**: `codex` command (requires Codex CLI)

### Available Providers and Models

#### Claude Code Provider

Command: `claude`

**Supported Models**:

- `claude-sonnet-4-5` - Latest Sonnet (balanced performance and cost)
- `claude-opus-4-5` - Most capable model (slower, more expensive)
- `claude-haiku-4-5` - Fastest model (lower cost)

**Model Aliases**:

- `sonnet` → `claude-sonnet-4-5`
- `opus` → `claude-opus-4-5`
- `haiku` → `claude-haiku-4-5`

#### Gemini Provider

Command: `gemini`

**Supported Models**:

- `gemini-2.5-pro` - Most capable Gemini model
- `gemini-2.5-flash` - Fast and efficient
- `gemini-2.0-flash` - Legacy model (still supported)

**Note**: Model availability depends on your Gemini CLI version and API access.

#### Codex/OpenAI Provider

Command: `codex`

**Supported Models**:

- `gpt-5.1` - Latest GPT model
- `gpt-5.1-codex-max` - Maximum reasoning capability
- `gpt-5.1-codex-mini` - Faster, cost-effective

**Important**: Codex CLI requires a real terminal (TTY) for interactive mode. When using Codex:

- Interactive agents (Pattern Designer, Aggregator) require running from a real terminal
- Headless agents (Marker, Normalizer, Unifier) work in all contexts
- Session capture is limited for interactive mode
- For fully automated workflows, consider using Claude or Gemini instead

### Configuration Examples

Specify in `overview.md`:

**Claude (default)**:

```markdown
default_provider: claude
default_model: claude-sonnet-4-5
```

**Gemini**:

```markdown
default_provider: gemini
default_model: gemini-2.5-pro
```

**Codex**:

```markdown
default_provider: codex
default_model: gpt-5.1
```

**Using aliases**:

```markdown
default_provider: claude
default_model: sonnet
```

### Provider Auto-Detection

You can omit the `default_provider` field - the system will auto-detect from the model name:

```markdown
default_model: claude-sonnet-4-5  # Auto-detects claude provider
default_model: gemini-2.5-pro     # Auto-detects gemini provider
default_model: gpt-5.1            # Auto-detects codex provider
```

### Verify CLI Tools

Test each provider:

```bash
# Test Claude
claude --print "test"

# Test Gemini
gemini "test"

# Test Codex
codex exec "test"
```

## Utilities

The system includes several standalone utilities in the `utils/` directory:

### Gradebook Translation (`utils/translate_grades.sh`)

Transfers grades from `processed/final/grades.csv` to LMS gradebook CSVs with intelligent name matching:

```bash
# Automatic translation (if gradebooks/ directory exists)
# Run happens automatically after marking completes

# Manual translation
./utils/translate_grades.sh \
  --assignment-dir assignments/lab1 \
  --gradebooks assignments/lab1/gradebooks/*.csv
```

**Features**:
- LLM-powered fuzzy name matching (handles different name formats)
- Two-stage workflow: LLM mapping + deterministic application
- Creates backups before modifying gradebooks
- Generates translation report with match details

### Artifact Cleaner (`utils/clean_artifacts.sh`)

Removes LLM generation artifacts from text files:

```bash
# Clean a specific file in-place
./utils/clean_artifacts.sh path/to/grades.csv --in-place

# Preview changes without modifying
./utils/clean_artifacts.sh path/to/file.txt --dry-run

# Clean and save to new file
./utils/clean_artifacts.sh input.txt --output cleaned.txt
```

**What it removes**:

- "YOLO mode is enabled. All tool calls will be automatically approved."
- "Loaded cached credentials."
- Other LLM tool artifacts listed in `configs/processing_artifacts.jsonl`

**Adding custom artifacts**:

Edit `configs/processing_artifacts.jsonl` to add artifacts specific to your LLM tools. Format is one JSON object per line:

```jsonl
{"artifact": "Text to remove exactly as it appears"}
{"artifact": "Multi-line artifacts\nwork too"}
```

Example - adding a custom artifact:

```bash
# Add new artifact to the database
echo '{"artifact": "This response was generated by..."}' >> configs/processing_artifacts.jsonl

# Test what would be cleaned
./utils/clean_artifacts.sh processed/final/grades.csv --dry-run

# Clean the file
./utils/clean_artifacts.sh processed/final/grades.csv --in-place
```

### Overview Generator (`utils/create_overview.sh`)

Creates `overview.md` template for new assignments:

```bash
./utils/create_overview.sh assignments/new-assignment
```

### Batch Marking (`utils/batch_mark.sh`)

Process multiple assignments in stages to optimize instructor workflow. This groups all interactive steps together across assignments to minimize waiting time.

**Setup:**

Create a text file listing assignment directories (one per line):

```text
# my_assignments.txt
assignments/lab1
assignments/lab2
assignments/project-phase1
```

**Recommended Workflow:**

```bash
# Round 1: Submission Discovery - Verify submissions found
./utils/batch_mark.sh my_assignments.txt --stop-after 1
# → Verify ALL student/group submissions were found correctly
# → Check submissions_manifest.json for each assignment

# Round 2: Pattern Design - Review marking criteria
./utils/batch_mark.sh my_assignments.txt --stop-after 2
# → Instructor reviews ALL rubrics and marking criteria
# → Verify criteria are appropriate before any marking begins

# Round 3: Normalization - Review scoring schemes
./utils/batch_mark.sh my_assignments.txt --stop-after 4
# → Review normalized scoring schemes from marker aggregation
# → Verify mistake/positive point categorization looks reasonable

# Round 4: Dashboard Review - Approve final marking
./utils/batch_mark.sh my_assignments.txt --stop-after 5
# → Instructor reviews ALL adjustment dashboards
# → Approve final marking schemes with distribution preview

# Round 5: Completion - Generate final grades
./utils/batch_mark.sh my_assignments.txt
# → Unification, aggregation, artifact cleaning, gradebook translation
# → grades.csv ready for upload to LMS
```

**Benefits:**

- **Quality checkpoints**: Verify submissions (Stage 1), criteria (Stage 2), scoring (Stage 4), schemes (Stage 5)
- **Minimizes context switching**: Review similar tasks across all assignments at once
- **Reduces idle time**: No waiting between stages for individual assignments
- **Consistency**: Spot patterns and ensure uniform standards across assignments
- **Automatic resume**: Uses `--resume` by default to skip completed work
- **Auto-detection**: Automatically detects structured vs freeform assignments

**Options:**

```bash
# Override parallel tasks for all assignments
./utils/batch_mark.sh assignments.txt --parallel 8

# Start fresh (ignore previous progress)
./utils/batch_mark.sh assignments.txt --no-resume

# Custom stopping point
./utils/batch_mark.sh assignments.txt --stop-after 3
```

See `assignments/assignments.txt.example` for file format.

## Troubleshooting

### "No submissions found"

- Check `submissions/` directory structure
- Verify `.ipynb` files exist
- Check file permissions

### "Pattern designer didn't create rubric"

- Ensure interactive session completed
- Check `processed/sessions/pattern_designer.log`
- Manually create `processed/rubric.md` if needed

### "Dashboard won't load"

- Install: `pip install ipywidgets jupyter`
- Enable widgets: `jupyter nbextension enable --py widgetsnbextension`
- Try: `jupyter lab` instead of `jupyter notebook`

### Agents failing

- Check `processed/logs/errors_*.json`

### LLM CLI errors or permission issues

- Verify the CLI tool is installed: `which claude codex gemini`
- Test the CLI directly: `codex exec "test"` or `claude --print "test"`
- Ensure the provider name in `overview.md` matches the installed CLI tool
- For Codex: use `codex` (not `openai`) as the command name
- Review individual agent logs in `processed/logs/*/`
- Verify LLM CLI tools are working: `claude --version`

### "xargs: command line cannot be assembled, too long"

This has been fixed. If you see this error:

- Update to the latest version of the code
- The system now uses line numbers instead of full command lines to avoid ARG_MAX limits

### Progress not showing or cryptic messages

- Install GNU parallel for best experience: `brew install parallel` (macOS) or `apt install parallel` (Linux)
- xargs fallback now shows clear progress: `[ 45%] Completed 100/224 tasks`
- Parallel progress uses `--bar` for clean visual display

## Development

See `CLAUDE.md` for detailed architecture and development guidance.

## Getting Started: Step-by-Step Guide

### Step 1: Install Prerequisites

```bash
# Install required Python packages
pip install pandas numpy matplotlib ipywidgets jupyter

# Enable Jupyter widgets (if not already enabled)
jupyter nbextension enable --py widgetsnbextension

# Verify Claude Code CLI is installed
claude --version
```

### Step 2: Prepare Your Assignment

#### Structured Assignment Setup

1. **Create assignment directory**:

   ```bash
   mkdir -p assignments/lab1/submissions
   ```

2. **Add your base notebook**:

   ```bash
   cp your_base_notebook.ipynb assignments/lab1/base_notebook.ipynb
   ```

   Ensure your base notebook uses the proper format:

   - Activity markers: `**[A1]**`, `**[A2]**`, etc. in markdown cells
   - Student input delimiters: `*Start student input* ↓` and `*End student input ↑*` in markdown cells
   - See `dev/examples/structured_assignment_example.ipynb` for reference

3. **Create overview.md**:

   ```bash
   cp assignments/overview_template.md assignments/lab1/overview.md
   ```

   Edit `assignments/lab1/overview.md` and fill in:

   - Configuration (YAML front matter at top)
   - Assignment description
   - Learning objectives
   - Grading criteria
   - See template comments for guidance

4. **Add student submissions**:

   Copy student notebooks to `assignments/lab1/submissions/`. The system handles:
   - Nested subdirectories (any depth)
   - Spaces in filenames
   - Multiple sections/groups

   Example structure:

   ```text
   assignments/lab1/submissions/
   ├── section-A/
   │   ├── John Doe.ipynb
   │   ├── Jane Smith.ipynb
   │   └── subdir/
   │       └── Bob Johnson.ipynb
   └── section-B/
       └── Alice Williams.ipynb
   ```

#### Free-form Assignment Setup

Same as above, but:

- **No base notebook needed** (skip step 2)
- Set `assignment_type: freeform` in overview.md
- Provide detailed requirements in overview.md (used by Pattern Designer)

### Step 3: Run the Marking Process

```bash
# For structured assignments
./mark_structured.sh assignments/lab1

# For free-form assignments
./mark_freeform.sh assignments/project1
```

The system will proceed through multiple stages (detailed below).

### Step 4: Interactive Pattern Designer Session

**What happens**:

- The Pattern Designer agent analyzes your assignment
- Creates or validates a rubric
- Creates detailed marking criteria

**Your tasks**:

1. Read the agent's analysis and rubric proposal
2. Answer any clarification questions (e.g., "Can I assume students know pandas?")
3. Review and approve the proposed rubric
4. Wait for criteria file generation
5. **When agent says "complete"**, type `/exit` or close terminal

**Files created**:

- `processed/rubric.md` - Final rubric
- `processed/activities/A*_criteria.md` - Per-activity criteria (structured)
- `processed/marking_criteria.md` - Overall criteria (free-form)

### Step 5: Automatic Marker Agents (Parallel)

**What happens**:

- Marker agents run in parallel (automatically)
- Each evaluates student work qualitatively
- Progress shown in real-time

**Your tasks**:

- Watch the progress bar
- Wait for completion (may take 10-30 minutes depending on class size)

**Example output**:

```text
Using GNU parallel for task execution
[=====>                    ] 35% ETA: 2m 15s

# Or with xargs:
Using xargs for task execution
[ 35%] Completed 78/224 tasks
```

**Files created**:

- `processed/markings/StudentName_A1.md` (one per student-activity)
- `processed/logs/marker_logs/` (execution logs)

### Step 6: Automatic Normalizer Agent

**What happens**:

- Normalizer aggregates all marker assessments
- Creates unified tables of mistakes and positives
- Assigns severity ratings and suggests mark deductions

**Your tasks**:

- Wait for completion

**Files created**:

- `processed/normalized/A*_scoring.md` (one per activity)

### Step 7: Interactive Adjustment Dashboard

**What happens**:

- System generates a Jupyter notebook with interactive controls
- Script pauses and prompts you to open the dashboard

**Your tasks**:

1. **Open the dashboard**:

   ```bash
   jupyter notebook assignments/lab1/processed/adjustment_dashboard.ipynb
   ```

2. **Review the marking scheme**:
   - Scroll through mistake and positive tables
   - Note suggested deductions/bonuses

3. **Adjust marks using sliders**:
   - Each mistake/positive has a slider
   - Adjust deduction amounts as needed

4. **Click "Update Distribution"**:
   - Histogram updates in real-time
   - Shows grade distribution with your adjustments
   - Review statistics (mean, median, grade bands)

5. **Iterate until satisfied**:
   - Adjust sliders
   - Update distribution
   - Repeat until you're happy with the distribution

6. **Run the final cell to save**:
   - Executes the cell that calls `save_approved_scheme()`
   - Saves to `processed/approved_scheme.json`

7. **Close Jupyter and return to terminal**:
   - Press Enter in the terminal when prompted

**Files created**:

- `processed/adjustment_dashboard.ipynb` - Interactive notebook
- `processed/approved_scheme.json` - Your approved marking scheme

### Step 8: Automatic Unifier Agents (Parallel)

**What happens**:

- Unifier agents run in parallel (automatically)
- Each creates final feedback for one student
- Applies your approved marking scheme
- Detects academic integrity concerns
- Suggests rare adjustments (requires your approval later if needed)

**Your tasks**:

- Wait for completion

**Files created**:

- `processed/final/StudentName_feedback.md` (one per student)

### Step 9: Interactive Aggregator Session

**What happens**:

- The Aggregator agent compiles all feedback into final CSV
- Calculates statistics
- Handles name matching if you provided a base CSV

**Your tasks**:

1. Interact with the agent as it works
2. Review any discrepancies (if merging with base CSV)
3. Confirm CSV looks correct
4. **When agent says "complete"**, type `/exit` or close terminal

**Files created**:

- `processed/final/grades.csv` - **FINAL GRADES FOR UPLOAD**
- `processed/final/summary_report.txt` - Statistics
- `processed/final/discrepancies.txt` - Name matching issues (if any)

### Step 10: Upload Grades

1. **Review the CSV**:

   ```bash
   head assignments/lab1/processed/final/grades.csv
   ```

2. **Upload to your LMS**:
   - Moodle: Use CSV import in gradebook
   - Canvas: Use CSV upload
   - Blackboard: Use Grade Center import
   - Manual: Copy-paste as needed

3. **Send feedback to students**:
   - Individual feedback cards are in `processed/final/*_feedback.md`
   - You can email these or post to LMS

## Complete Example Workflow

Here's a complete walkthrough marking a lab with 5 students:

```bash
# 1. Create and setup assignment
mkdir -p assignments/lab2/submissions/section-A
cp my_base_notebook.ipynb assignments/lab2/base_notebook.ipynb
cp assignments/overview_template.md assignments/lab2/overview.md
# Edit overview.md...

# 2. Add student submissions
cp ~/Downloads/student_submissions/*.ipynb assignments/lab2/submissions/section-A/

# 3. Start marking
./mark_structured.sh assignments/lab2

# 4. Pattern Designer (interactive)
# - Agent analyzes notebook
# - Proposes rubric
# - You approve
# - Type /exit when done

# 5. Marker agents (automatic)
# [ 14%] Completed 5/35 tasks
# ... wait for all students ...

# 6. Normalizer (automatic)
# ✓ Normalization complete

# 7. Adjustment Dashboard
# Terminal prompts: "Press Enter when you have saved the approved scheme..."
jupyter notebook assignments/lab2/processed/adjustment_dashboard.ipynb
# - Adjust sliders
# - Save approved scheme
# - Close Jupyter
# - Press Enter in terminal

# 8. Unifier agents (automatic)
# [ 60%] Completed 3/5 tasks
# ... wait for all students ...

# 9. Aggregator (interactive)
# - Agent creates CSV
# - You confirm
# - Type /exit when done

# 10. Upload
head assignments/lab2/processed/final/grades.csv
# Upload to Moodle/Canvas/etc.
```

## Expected Timeline

For a typical lab (7 activities, 40 students):

| Stage | Duration | Type |
| ------- | ---------- | ------ |
| 1. Submission Discovery | 10 seconds | Automatic |
| 2. Activity Extraction | 5 seconds | Automatic |
| 3. Pattern Designer | 5-10 minutes | Interactive |
| 4. Marker Agents | 15-30 minutes | Automatic (parallel) |
| 5. Normalizer | 2-5 minutes | Automatic |
| 6. Adjustment Dashboard | 10-15 minutes | Interactive |
| 7. Unifier Agents | 10-20 minutes | Automatic (parallel) |
| 8. Aggregator | 2-3 minutes | Automatic |
| 9. Translation (optional) | 3-5 minutes | Interactive |
| **Total** | **~1-1.5 hours** | Mix |

*Times vary based on class size, complexity, and max_parallel setting.*

**Note**: Stage 9 (Translation) only runs if you placed gradebook CSV files in `assignments/<name>/gradebooks/` before starting the workflow. Otherwise, you can run translation manually later using `./translate_grades.sh`.

## Gradebook Translation

After marking is complete, you can transfer grades back to your section gradebook CSVs (e.g., Moodle exports) using the gradebook translator.

### What It Does

The translator handles the complex task of matching students between your `grades.csv` and section gradebooks, even when:
- Student names are formatted differently ("Doe, John" vs "John Doe")
- Names include middle initials or nicknames
- There are minor spelling variations
- Students are split across multiple section files

### Two Usage Modes

#### Automatic Mode (Recommended)

Place your gradebook CSV files in the `gradebooks/` directory **before** running the marking workflow:

```bash
# 1. Setup your assignment with gradebooks
mkdir -p "assignments/Lab 02/gradebooks"
cp ~/Downloads/section*.csv "assignments/Lab 02/gradebooks/"

# 2. Run marking workflow as normal
./mark_structured.sh "assignments/Lab 02"

# The workflow will automatically:
# - Complete all marking stages (1-8)
# - Detect gradebook CSVs in gradebooks/ directory
# - Create translation mapping (Stage 9)
# - Show you the mapping summary
# - Prompt you to review and apply
# - Update gradebooks and create backups
```

**Benefits**:
- One complete workflow from start to finish
- No need to remember to run translator separately
- Gradebooks ready immediately after marking

**Directory structure**:
```text
assignments/Lab 02/
├── gradebooks/
│   ├── COMP3510_Section1.csv    # Your Moodle exports
│   └── COMP3510_Section2.csv
├── submissions/
│   └── ...
└── processed/
    ├── final/
    │   └── grades.csv
    └── translation/              # Auto-created by Stage 9
        ├── translation_mapping.json
        ├── translation_report.txt
        ├── COMP3510_Section1.csv      # Updated gradebooks
        ├── COMP3510_Section1_backup.csv
        ├── COMP3510_Section2.csv
        └── COMP3510_Section2_backup.csv
```

#### Manual Mode

Run the translator separately after marking is complete:

```bash
./translate_grades.sh \
  --assignment-dir "assignments/Lab 02" \
  --gradebooks section1.csv section2.csv section3.csv \
  --dry-run

# After reviewing the mapping, apply the changes:
./translate_grades.sh \
  --assignment-dir "assignments/Lab 02" \
  --gradebooks section1.csv section2.csv section3.csv \
  --skip-mapping \
  --apply
```

**Use when**:
- You don't have gradebooks ready at marking time
- You want more control over the translation process
- You need to re-run translation with different gradebooks

### Two-Stage Process

**Stage 1: Mapping Creation (LLM Agent)**
- Analyzes the structure of each gradebook CSV
- Uses intelligent fuzzy matching to pair students
- Identifies which columns to update (total mark, feedback, activities)
- Creates a detailed mapping file: `processed/translation/translation_mapping.json`

**Stage 2: Application (Deterministic)**
- Applies the mapping to update gradebook CSVs
- Creates backups of original files
- Adds/updates columns as needed
- Generates application report

### Options

**Required**:
- `--assignment-dir <dir>` - Assignment directory containing `processed/final/grades.csv`
- `--gradebooks <csv1> <csv2> ...` - One or more section gradebook CSV files

**Optional**:
- `--dry-run` - Preview changes without modifying files (default)
- `--apply` - Actually update the gradebook files
- `--skip-mapping` - Use existing mapping file (skip LLM stage)
- `--provider <provider>` - LLM provider (default: from overview.md)
- `--model <model>` - Specific model (default: from overview.md)

### Workflow

1. **Create mapping** (uses LLM for fuzzy matching):
   ```bash
   ./translate_grades.sh \
     --assignment-dir "assignments/lab1" \
     --gradebooks section1.csv section2.csv \
     --dry-run
   ```

2. **Review mapping**:
   ```bash
   # Check the mapping file
   cat "assignments/lab1/processed/translation/translation_mapping.json"

   # Review match confidence scores
   # Check for unmatched students
   ```

3. **Apply updates**:
   ```bash
   ./translate_grades.sh \
     --assignment-dir "assignments/lab1" \
     --gradebooks section1.csv section2.csv \
     --skip-mapping \
     --apply
   ```

### Output Files

- `processed/translation/translation_mapping.json` - Complete mapping with confidence scores
- `processed/translation/translation_report.txt` - Application summary
- `processed/translation/section_name.csv` - Updated gradebook files
- `processed/translation/section_name_backup.csv` - Original backups

### Matching Strategies

The translator uses multiple strategies in order of preference:

1. **Exact match** - Names match exactly (case insensitive)
2. **Reverse match** - "Last, First" vs "First Last"
3. **Initials match** - "John A. Doe" matches "John Doe"
4. **Nickname match** - "Mike" matches "Michael", etc.
5. **Fuzzy match** - Handles typos (Levenshtein distance)
6. **Partial match** - "John Doe" matches "John Michael Doe"

Only high-confidence matches (>80%) are made automatically. Low-confidence matches are flagged for review.

### Example

```bash
# After completing marking for Lab 02
./translate_grades.sh \
  --assignment-dir "assignments/Lab 02 - Decision Tree Classifier" \
  --gradebooks ~/Downloads/COMP3510_Section1.csv ~/Downloads/COMP3510_Section2.csv \
  --dry-run

# Review output:
# MATCHING SUMMARY:
# Total students in grades.csv: 32
# Total students in gradebooks: 35
# Successfully matched: 30
# Unmatched from grades: 2
# Unmatched from gradebooks: 5
# Low confidence matches: 3

# If satisfied, apply:
./translate_grades.sh \
  --assignment-dir "assignments/Lab 02 - Decision Tree Classifier" \
  --gradebooks ~/Downloads/COMP3510_Section1.csv ~/Downloads/COMP3510_Section2.csv \
  --skip-mapping \
  --apply

# Upload updated gradebooks to Moodle
```

### Troubleshooting

**"No matching student in gradebook"**:
- Student may have dropped the course
- Check for name variations in the mapping file
- Manually add the student to the gradebook and re-run

**"Low confidence matches"**:
- Review the mapping file for these students
- Check confidence scores and match methods
- Consider manual adjustments if needed

**"Column already exists"**:
- Existing columns will be overwritten with new values
- Backups are created automatically

## License

MIT License - See LICENSE file

## Support

For issues or questions:

- Check logs in `processed/logs/`
- Review error reports in `processed/logs/errors_*.json`
- See `CLAUDE.md` for implementation details
