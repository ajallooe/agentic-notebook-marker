# Gemini Error and Progress Display Fixes

## Issue 1: Gemini Failing - File Access Errors

### Problem

When using Gemini as the provider for pattern_designer, the following errors occurred:

```
[ERROR] [IDEClient] Failed to connect to IDE companion extension in IDE
Error executing tool read_file: File path '...' is ignored by configured ignore patterns
Error executing tool run_shell_command: Tool "run_shell_command" not found in registry
```

### Root Cause

The `pattern_designer_structured.md` prompt instructed the LLM to:
> "**Read the base notebook** thoroughly from start to finish"

And provided only the file path:
```
**Base Notebook**: `/path/to/notebook.ipynb`
```

When Gemini saw this instruction, it attempted to use its built-in agentic tools:
- `read_file` - to read the notebook
- `run_shell_command` - to access files via shell
- `codebase_investigator` - to explore the workspace

However:
1. These tools are not available in the marker system's LLM calling context
2. Gemini's workspace boundary and ignore patterns block the file access
3. The file paths may be outside Gemini's configured workspace

### Solution

**Embed the notebook content directly in the prompt** instead of asking the LLM to read it.

#### Changes Made

**1. `src/agents/pattern_designer.py`** - Load notebook content:

```python
# Load base notebook content if provided (structured assignments)
base_notebook_content = ""
if args.base_notebook and Path(args.base_notebook).exists():
    with open(args.base_notebook, 'r') as f:
        base_notebook_content = f.read()
```

And pass it to the prompt:

```python
prompt = prompt_template.format(
    base_notebook_path=args.base_notebook or "N/A (free-form assignment)",
    base_notebook_content=base_notebook_content if base_notebook_content else "N/A (free-form assignment)",
    assignment_overview=overview_content,
    ...
)
```

**2. `src/prompts/pattern_designer_structured.md`** - Include content in prompt:

```markdown
## Assignment Context

**Base Notebook Path**: `{base_notebook_path}`

**Base Notebook Content**:
```json
{base_notebook_content}
```

## Your Tasks

### Phase 1: Analysis

1. **Analyze the base notebook content above** thoroughly from start to finish
```

### Benefits

✅ **Works with all providers** - Claude, Gemini, Codex all receive content directly
✅ **No tool dependencies** - LLM doesn't need file access tools
✅ **No workspace boundaries** - Content is in the prompt, not external files
✅ **More reliable** - No risk of file access errors or permission issues

### Testing

Test with all three providers:

```bash
# Test with Gemini
./mark_structured.sh assignments/lab1 --clean
# (Configure overview.md with default_provider: gemini)

# Test with Codex
# (Configure overview.md with default_provider: codex)

# Test with Claude
# (Configure overview.md with default_provider: claude)
```

All should successfully read and analyze the base notebook.

---

## Issue 2: Progress Display Mixed With Output

### Problem

Progress updates were getting mixed with command output, making them hard to see:

```
85% 24:4=0s python3 '/Volumes/Mac Storage/...'python3 '/Volumes/Mac Storage/...'/stdout
```

The user wanted:
```
<previous output>

[85%] Completed 190/224 tasks

<next output>
```

### Root Cause

1. **GNU parallel's `--bar`** - Progress bar updates in-place using ANSI escape codes, gets mixed with task output on stderr
2. **xargs custom progress** - Used `\r\033[K` (carriage return + clear line) for in-place updates

Both approaches resulted in progress appearing on the same line as other output.

### Solution

Add newlines before and after progress updates for clear visual separation.

#### Changes Made

**1. xargs Progress (`src/parallel_runner.sh` line 220)**:

Before:
```bash
printf "\r\033[K[%3d%%] Completed %d/%d tasks" "$percent" "$completed" "$TOTAL_TASKS" >&2
```

After:
```bash
# Show progress on new line with clear separation
printf "\n[%3d%%] Completed %d/%d tasks\n\n" "$percent" "$completed" "$TOTAL_TASKS" >&2
```

**2. xargs Initial Progress (`src/parallel_runner.sh` line 248)**:

Before:
```bash
printf "[  0%%] Completed 0/%d tasks" "$TOTAL_TASKS" >&2
```

After:
```bash
# Show initial progress with clear separation
printf "\n[  0%%] Completed 0/%d tasks\n\n" "$TOTAL_TASKS" >&2
```

**3. GNU parallel Progress (`src/parallel_runner.sh` lines 166-180)**:

Added newlines before and after parallel execution:

```bash
# Execute with parallel
if [[ $VERBOSE == true ]]; then
    echo "" >&2  # Newline before progress starts
fi

if [[ -n "$COMMAND" ]]; then
    cat "$TASKS_FILE" | eval "$PARALLEL_CMD" "$COMMAND" 2>&1 | grep -v '^parallel:'
else
    cat "$TASKS_FILE" | eval "$PARALLEL_CMD" 2>&1 | grep -v '^parallel:'
fi

EXIT_CODE=${PIPESTATUS[0]}

if [[ $VERBOSE == true ]]; then
    echo "" >&2  # Newline after progress completes
fi
```

### Expected Output

Now progress updates appear with clear separation:

```
[previous command output]

[ 42%] Completed 94/224 tasks

[next command output]

[ 85%] Completed 190/224 tasks

[next command output]
```

### Benefits

✅ **Clear visibility** - Progress stands out from command output
✅ **Easy to scan** - Blank lines make progress updates obvious
✅ **Works with both parallel and xargs** - Consistent formatting
✅ **Better debugging** - Easier to correlate progress with task output

---

## Files Changed

### Created
- `dev/GEMINI_FIXES.md` - This documentation

### Modified
- `src/agents/pattern_designer.py` - Load and embed notebook content
- `src/prompts/pattern_designer_structured.md` - Include content in prompt
- `src/parallel_runner.sh` - Add newlines around progress updates

## Testing Checklist

- [ ] Test pattern_designer with Gemini - should not get file access errors
- [ ] Test pattern_designer with Claude - should work as before
- [ ] Test pattern_designer with Codex - should work as before
- [ ] Test marker stage with parallel - progress should have clear separation
- [ ] Test marker stage with xargs - progress should have clear separation
- [ ] Verify progress updates are readable and not mixed with output

## Migration Notes

- No breaking changes
- All providers now receive notebook content directly
- Progress display is clearer and easier to read
- Existing assignments continue to work unchanged
