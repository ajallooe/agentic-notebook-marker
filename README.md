# Agentic Notebook Marker

An automated marking system for Jupyter notebook assignments using LLM agents coordinated via CLI tools.

**Repository**: [https://github.com/ajallooe/agentic-notebook-marker](https://github.com/ajallooe/agentic-notebook-marker)

## Quick Start

### For Structured (Fill-in-the-Blank) Assignments

```bash
./mark_structured.sh assignments/your-assignment-name
```

### For Free-form Assignments

```bash
./mark_freeform.sh assignments/your-assignment-name
```

## What This System Does

This system semi-automates the marking of Jupyter notebook assignments through a multi-agent workflow:

1. **Marking Pattern Designer** - Analyzes assignment and creates detailed marking criteria
2. **Marker Agents** - Evaluate each student's work qualitatively (in parallel)
3. **Normalizer Agent** - Aggregates assessments and creates unified scoring scheme
4. **Instructor Review** - Interactive dashboard for adjusting marks and viewing distribution
5. **Unifier Agents** - Apply final scheme and create student feedback cards (in parallel)
6. **Aggregator Agent** - Consolidates everything into a CSV for grade upload

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

## Assignment Structure

Create your assignment directory as follows:

```text
assignments/
└── assignment-name/
    ├── overview.md                    # Assignment config and description
    ├── base_notebook.ipynb            # Base notebook (structured only)
    ├── submissions/
    │   ├── section-1/
    │   │   ├── student1.ipynb
    │   │   └── nested/
    │   │       └── student2.ipynb
    │   └── section-2/
    │       └── student3.ipynb
    └── processed/                     # Auto-generated artifacts
```

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
---

# Assignment Description

[Your assignment description here...]
```

## Generating overview.md Automatically

You can automatically generate an `overview.md` file from an existing Jupyter notebook using the `create_overview.py` utility:

```bash
python3 src/create_overview.py <notebook_path> --model <model_name>
```

**Examples:**

```bash
# Using Claude Sonnet
python3 src/create_overview.py assignments/lab1/notebook.ipynb --model claude-sonnet-4-5

# Using Gemini
python3 src/create_overview.py assignments/lab2/notebook.ipynb --model gemini-2.5-pro

# Using Codex
python3 src/create_overview.py assignments/lab3/notebook.ipynb --model gpt-5.1
```

**What it does:**

- Analyzes the notebook structure and content
- Detects activity markers (`**[A1]**`, `**[A2]**`, etc.) for structured assignments
- Generates a properly formatted `overview.md` with:
  - YAML frontmatter (provider, model, assignment type, total marks)
  - Assignment overview and description
  - Learning objectives
  - Assignment structure
  - Grading criteria
- Places the file in the same directory as the notebook

**Notes:**

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

Real-time console output shows:

```text
[A2/7] [Student 15/42] (35.7%) |███████████░░░░░░░| Processing Alice Smith...
```

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

## Using Different LLM Providers

The system supports multiple providers via CLI:

- **Claude Code**: `claude` command (default)
- **Gemini**: `gemini` command (requires Gemini CLI)
- **OpenAI/Codex**: `codex` command (requires Codex CLI)

### Available Providers and Models

#### Claude Code Provider

Command: `claude`

**Supported Models:**

- `claude-sonnet-4-5` - Latest Sonnet (balanced performance and cost)
- `claude-opus-4-5` - Most capable model (slower, more expensive)
- `claude-haiku-4-5` - Fastest model (lower cost)

**Model Aliases:**

- `sonnet` → `claude-sonnet-4-5`
- `opus` → `claude-opus-4-5`
- `haiku` → `claude-haiku-4-5`

#### Gemini Provider

Command: `gemini`

**Supported Models:**

- `gemini-2.5-pro` - Most capable Gemini model
- `gemini-2.5-flash` - Fast and efficient
- `gemini-2.0-flash` - Legacy model (still supported)

**Note:** Model availability depends on your Gemini CLI version and API access.

#### Codex/OpenAI Provider

Command: `codex`

**Supported Models:**

- `gpt-5.1` - Latest GPT model
- `gpt-5.1-codex-max` - Maximum reasoning capability
- `gpt-5.1-codex-mini` - Faster, cost-effective

**Important:** Codex CLI requires a real terminal (TTY) for interactive mode. When using Codex:

- Interactive agents (Pattern Designer, Aggregator) require running from a real terminal
- Headless agents (Marker, Normalizer, Unifier) work in all contexts
- Session capture is limited for interactive mode
- For fully automated workflows, consider using Claude or Gemini instead

### Configuration Examples

Specify in `overview.md`:

**Claude (default):**

```markdown
default_provider: claude
default_model: claude-sonnet-4-5
```

**Gemini:**

```markdown
default_provider: gemini
default_model: gemini-2.5-pro
```

**Codex:**

```markdown
default_provider: codex
default_model: gpt-5.1
```

**Using aliases:**

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

### LLM CLI errors (e.g., "Error: 'i'" or command not found)

- Verify the CLI tool is installed: `which claude codex gemini`
- Test the CLI directly: `codex exec "test"` or `claude --print "test"`
- Ensure the provider name in `overview.md` matches the installed CLI tool
- For Codex: use `codex` (not `openai`) as the command name
- Review individual agent logs in `processed/logs/*/`
- Verify LLM CLI tools are working: `claude --version`

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

1. **Create assignment directory:**

   ```bash
   mkdir -p assignments/lab1/submissions
   ```

2. **Add your base notebook:**

   ```bash
   cp your_base_notebook.ipynb assignments/lab1/base_notebook.ipynb
   ```

   Ensure your base notebook uses the proper format:

   - Activity markers: `**[A1]**`, `**[A2]**`, etc. in markdown cells
   - Student input delimiters: `*Start student input* ↓` and `*End student input ↑*` in markdown cells
   - See `dev/examples/structured_assignment_example.ipynb` for reference

3. **Create overview.md:**

   ```bash
   cp assignments/overview_template.md assignments/lab1/overview.md
   ```

   Edit `assignments/lab1/overview.md` and fill in:

   - Configuration (YAML front matter at top)
   - Assignment description
   - Learning objectives
   - Grading criteria
   - See template comments for guidance

4. **Add student submissions:**

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
[A2/7] [Student 15/42] (35.7%) |███████████░░░░░░░| Processing Alice Smith...
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
# [A1/7] [Student 1/5] (2.9%) |█░░░░░░░░░| Processing John Doe...
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
# [Student 3/5] (60%) |██████████████░░░| Creating feedback for Jane Smith...
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
| 8. Aggregator | 2-3 minutes | Interactive |
| **Total** | **~1-1.5 hours** | Mix |

*Times vary based on class size, complexity, and max_parallel setting.*

## License

MIT License - See LICENSE file

## Support

For issues or questions:

- Check logs in `processed/logs/`
- Review error reports in `processed/logs/errors_*.json`
- See `CLAUDE.md` for implementation details
