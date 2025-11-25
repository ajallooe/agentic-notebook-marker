#!/usr/bin/env bash
#
# Parallel Task Runner - Execute tasks in parallel with configurable concurrency
# Usage: parallel_runner.sh --tasks tasks.txt --concurrency N --output-dir dir [--command "cmd {}"]
#

set -euo pipefail

# Default values
TASKS_FILE=""
CONCURRENCY=4
OUTPUT_DIR=""
COMMAND=""
VERBOSE=false
FORCE_XARGS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --tasks)
            TASKS_FILE="$2"
            shift 2
            ;;
        --concurrency|-j)
            CONCURRENCY="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --command)
            COMMAND="$2"
            shift 2
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --force-xargs)
            FORCE_XARGS=true
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$TASKS_FILE" ]]; then
    echo "Error: --tasks is required" >&2
    echo "Usage: parallel_runner.sh --tasks tasks.txt --concurrency N [--output-dir dir] [--command \"cmd {}\"]" >&2
    exit 1
fi

if [[ ! -f "$TASKS_FILE" ]]; then
    echo "Error: Tasks file not found: $TASKS_FILE" >&2
    exit 1
fi

# Create output directory if specified
if [[ -n "$OUTPUT_DIR" ]]; then
    mkdir -p "$OUTPUT_DIR"
fi

# Count total tasks
TOTAL_TASKS=$(wc -l < "$TASKS_FILE" | tr -d ' ')

if [[ $VERBOSE == true ]]; then
    echo "Parallel Task Runner"
    echo "===================="
    echo "Tasks file: $TASKS_FILE"
    echo "Total tasks: $TOTAL_TASKS"
    echo "Concurrency: $CONCURRENCY"
    echo "Output directory: ${OUTPUT_DIR:-none}"
    echo ""
fi

# Function to execute a single task
execute_task() {
    local task="$1"
    local task_id="$2"
    local output_dir="$3"
    local command="$4"

    # Create output file if directory specified
    local output_file=""
    if [[ -n "$output_dir" ]]; then
        output_file="$output_dir/task_${task_id}.log"
    fi

    # Execute task
    if [[ -n "$command" ]]; then
        # Use custom command (replace {} with task)
        local cmd="${command//\{\}/$task}"
        if [[ -n "$output_file" ]]; then
            eval "$cmd" > "$output_file" 2>&1
        else
            eval "$cmd"
        fi
    else
        # Execute task directly as shell command
        if [[ -n "$output_file" ]]; then
            eval "$task" > "$output_file" 2>&1
        else
            eval "$task"
        fi
    fi

    local exit_code=$?

    # Record result
    if [[ -n "$output_file" ]]; then
        echo "EXIT_CODE=$exit_code" >> "$output_file"
    fi

    return $exit_code
}

# Wrapper function that reads task from file by line number
# This avoids ARG_MAX issues with long command lines
execute_task_by_line() {
    local line_num="$1"
    local tasks_file="$2"
    local output_dir="$3"
    local command="$4"

    # Read the specific line from the tasks file
    local task=$(sed -n "${line_num}p" "$tasks_file")

    if [[ -n "$task" ]]; then
        execute_task "$task" "$line_num" "$output_dir" "$command"
    fi
}

# Export functions for use in subshells
export -f execute_task
export -f execute_task_by_line

# Check if GNU parallel is available
if command -v parallel &> /dev/null && [[ $FORCE_XARGS == false ]]; then
    # Use GNU parallel for better progress tracking
    if [[ $VERBOSE == true ]]; then
        echo "Using GNU parallel for task execution"
        echo ""
    fi

    # Build parallel command
    PARALLEL_CMD="parallel"
    PARALLEL_CMD+=" --jobs $CONCURRENCY"
    PARALLEL_CMD+=" --line-buffer"

    if [[ $VERBOSE == true ]]; then
        # Use --bar for cleaner progress display instead of cryptic --progress
        PARALLEL_CMD+=" --bar"
        PARALLEL_CMD+=" --tag"
    fi

    if [[ -n "$OUTPUT_DIR" ]]; then
        PARALLEL_CMD+=" --results '$OUTPUT_DIR'"
    fi

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

elif command -v xargs &> /dev/null; then
    # Fallback to xargs with concurrency
    if [[ $VERBOSE == true ]]; then
        if [[ $FORCE_XARGS == true ]]; then
            echo "Using xargs for task execution (forced via --force-xargs)"
        else
            echo "Using xargs for task execution (install GNU parallel for better features)"
        fi
        echo ""
    fi

    # Use xargs with line numbers to avoid ARG_MAX issues
    # Instead of passing the command line through xargs, we pass line numbers
    # and read the actual command from the file inside the worker
    EXIT_CODE=0

    # Create a progress tracking mechanism for xargs
    if [[ $VERBOSE == true ]]; then
        PROGRESS_DIR=$(mktemp -d)
        PROGRESS_COUNTER="$PROGRESS_DIR/counter"
        PROGRESS_LOCK="$PROGRESS_DIR/lock"
        echo "0" > "$PROGRESS_COUNTER"

        # Function to update progress with directory-based locking (portable)
        update_progress() {
            # Use mkdir for atomic locking (works on all Unix systems)
            local lockdir="$PROGRESS_LOCK"
            local max_attempts=100
            local attempt=0

            while ! mkdir "$lockdir" 2>/dev/null && [ $attempt -lt $max_attempts ]; do
                sleep 0.01
                attempt=$((attempt + 1))
            done

            if [ $attempt -ge $max_attempts ]; then
                # Couldn't get lock, skip this update
                return 0
            fi

            # We have the lock
            local current=$(cat "$PROGRESS_COUNTER" 2>/dev/null || echo "0")
            local completed=$((current + 1))
            echo "$completed" > "$PROGRESS_COUNTER"
            local percent=$((completed * 100 / TOTAL_TASKS))
            # Show progress on new line with clear separation (goes to stderr, separate from task output)
            printf "\n[%3d%%] Completed %d/%d tasks\n\n" "$percent" "$completed" "$TOTAL_TASKS" >&2

            # Release lock
            rmdir "$lockdir" 2>/dev/null
        }
        export -f update_progress
        export PROGRESS_COUNTER
        export PROGRESS_LOCK
        export TOTAL_TASKS

        # Wrapper that calls task and updates progress
        task_with_progress() {
            execute_task_by_line "$@"
            local result=$?
            update_progress
            return $result
        }
        export -f task_with_progress

        # Show initial progress with clear separation
        printf "\n[  0%%] Completed 0/%d tasks\n\n" "$TOTAL_TASKS" >&2

        if [[ -n "$COMMAND" ]]; then
            seq 1 "$TOTAL_TASKS" | xargs -P "$CONCURRENCY" -I {} bash -c 'task_with_progress "{}" "'"$TASKS_FILE"'" "'"$OUTPUT_DIR"'" "'"$COMMAND"'"' || EXIT_CODE=$?
        else
            seq 1 "$TOTAL_TASKS" | xargs -P "$CONCURRENCY" -I {} bash -c 'task_with_progress "{}" "'"$TASKS_FILE"'" "'"$OUTPUT_DIR"'" ""' || EXIT_CODE=$?
        fi

        # Clean progress line and remove temp directory
        echo "" >&2
        rm -rf "$PROGRESS_DIR"
    else
        # Non-verbose mode - no progress tracking
        if [[ -n "$COMMAND" ]]; then
            seq 1 "$TOTAL_TASKS" | xargs -P "$CONCURRENCY" -I {} bash -c 'execute_task_by_line "{}" "'"$TASKS_FILE"'" "'"$OUTPUT_DIR"'" "'"$COMMAND"'"' || EXIT_CODE=$?
        else
            seq 1 "$TOTAL_TASKS" | xargs -P "$CONCURRENCY" -I {} bash -c 'execute_task_by_line "{}" "'"$TASKS_FILE"'" "'"$OUTPUT_DIR"'" ""' || EXIT_CODE=$?
        fi
    fi

else
    # Sequential fallback if neither parallel nor xargs available
    echo "Warning: Neither GNU parallel nor xargs found. Running sequentially." >&2
    echo ""

    task_num=0
    EXIT_CODE=0

    while IFS= read -r task; do
        ((task_num++))

        if [[ $VERBOSE == true ]]; then
            echo "[$task_num/$TOTAL_TASKS] Executing: $task"
        fi

        if ! execute_task "$task" "$task_num" "$OUTPUT_DIR" "$COMMAND"; then
            echo "Error: Task $task_num failed" >&2
            EXIT_CODE=1
        fi

    done < "$TASKS_FILE"
fi

# Check for quota/rate limit errors
check_quota_errors() {
    local output_dir="$1"
    local quota_errors=0

    if [[ ! -d "$output_dir" ]]; then
        return 0
    fi

    # Search for quota error patterns in stderr files
    for stderr_file in "$output_dir"/*/stderr; do
        if [[ -f "$stderr_file" && -s "$stderr_file" ]]; then
            local content=$(cat "$stderr_file" 2>/dev/null)
            # Check for quota patterns
            if echo "$content" | grep -qi "limit reached\|quota exceeded\|rate limit\|usage limit\|too many requests\|resets 3am\|/upgrade to max\|/extra-usage"; then
                ((quota_errors++))
            fi
        fi
    done

    return $quota_errors
}

# Summary
if [[ $VERBOSE == true ]]; then
    echo ""
    echo "===================="
    if [[ $EXIT_CODE -eq 0 ]]; then
        echo "✓ All $TOTAL_TASKS tasks completed successfully"
    else
        echo "✗ Some tasks failed (exit code: $EXIT_CODE)"
    fi

    if [[ -n "$OUTPUT_DIR" ]]; then
        # Count successful and failed tasks
        success_count=0
        fail_count=0

        for log_file in "$OUTPUT_DIR"/*.log; do
            if [[ -f "$log_file" ]] && grep -q "EXIT_CODE=0" "$log_file" 2>/dev/null; then
                ((success_count++))
            elif [[ -f "$log_file" ]]; then
                ((fail_count++))
            fi
        done

        echo "Successful: $success_count"
        echo "Failed: $fail_count"
        echo "Logs saved to: $OUTPUT_DIR"

        # Check for quota errors
        check_quota_errors "$OUTPUT_DIR"
        quota_count=$?

        if [[ $quota_count -gt 0 ]]; then
            echo ""
            echo -e "\033[1;31m========================================================================================================\033[0m"
            echo -e "\033[1;31m╔══════════════════════════════════════════════════════════════════════════════════════════════════╗\033[0m"
            echo -e "\033[1;31m║                                                                                                  ║\033[0m"
            echo -e "\033[1;31m║  ⚠️  API QUOTA/RATE LIMIT REACHED - $quota_count task(s) failed due to quota exhaustion  ⚠️               ║\033[0m"
            echo -e "\033[1;31m║                                                                                                  ║\033[0m"
            echo -e "\033[1;31m╚══════════════════════════════════════════════════════════════════════════════════════════════════╝\033[0m"
            echo -e "\033[1;31m========================================================================================================\033[0m"
            echo ""
            echo -e "\033[1;33mWhat this means:\033[0m"
            echo "  • Your LLM provider has run out of quota or hit a rate limit"
            echo "  • All completed work ($success_count tasks) has been preserved"
            echo ""
            echo -e "\033[1;33mTo continue:\033[0m"
            echo "  1. Wait for quota reset (typically resets hourly/daily, or 3am for Codex)"
            echo "  2. Re-run the same command - resume will pick up where it left off"
            echo "  3. Only the $quota_count failed tasks will be re-processed"
            echo ""
            echo -e "\033[1;33mAlternative options:\033[0m"
            echo "  • Upgrade your LLM provider plan for higher limits"
            echo "  • Switch to a different provider by editing overview.md"
            echo ""
            echo -e "\033[1;33mExample:\033[0m"
            echo "  # Wait for reset, then simply re-run:"
            echo "  ./mark_structured.sh assignments/your-assignment"
            echo "  # Output: \"Generated $quota_count tasks (skipped $success_count already completed)\""
            echo ""
            echo -e "\033[1;31m========================================================================================================\033[0m"
            echo ""
        fi
    fi
fi

exit $EXIT_CODE
