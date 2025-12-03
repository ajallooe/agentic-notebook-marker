#!/usr/bin/env python3
"""
Cache Clearing Utility

Clears any explicit caches that may be accumulating costs on API providers.
Use this utility when processes are interrupted before natural cache expiration.

Cache Behavior by Provider:
  - Claude: Automatic 5-minute TTL, no manual clearing needed
  - Gemini (implicit): Google-managed, no manual clearing needed
  - Gemini (explicit): Needs manual deletion via API
  - OpenAI: Automatic 5-10 minute TTL, no manual clearing needed

This utility only affects Gemini explicit caches (if any exist).

Usage:
  python3 clear_caches.py              # List all caches
  python3 clear_caches.py --delete     # Delete all explicit caches
  python3 clear_caches.py --dry-run    # Show what would be deleted

Environment variables:
  - GOOGLE_API_KEY or GEMINI_API_KEY (for Gemini cache operations)
"""

import argparse
import os
import sys
from datetime import datetime


def list_gemini_caches() -> list[dict]:
    """List all Gemini explicit caches."""
    try:
        import google.generativeai as genai
    except ImportError:
        print("Note: google-generativeai not installed, skipping Gemini cache check")
        return []

    api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("Note: No Gemini API key found, skipping Gemini cache check")
        return []

    genai.configure(api_key=api_key)

    caches = []
    try:
        # List all cached contents
        for cache in genai.caching.CachedContent.list():
            cache_info = {
                'name': cache.name,
                'model': cache.model,
                'display_name': getattr(cache, 'display_name', 'N/A'),
                'create_time': str(getattr(cache, 'create_time', 'N/A')),
                'expire_time': str(getattr(cache, 'expire_time', 'N/A')),
                'usage_metadata': getattr(cache, 'usage_metadata', {}),
            }
            caches.append(cache_info)
    except Exception as e:
        print(f"Warning: Could not list Gemini caches: {e}")

    return caches


def delete_gemini_cache(cache_name: str) -> bool:
    """Delete a specific Gemini cache by name."""
    try:
        import google.generativeai as genai
    except ImportError:
        return False

    api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return False

    genai.configure(api_key=api_key)

    try:
        cache = genai.caching.CachedContent.get(cache_name)
        cache.delete()
        return True
    except Exception as e:
        print(f"Warning: Could not delete cache {cache_name}: {e}")
        return False


def report_cache_status():
    """Report cache status for all providers."""
    print("=" * 60)
    print("CACHE STATUS REPORT")
    print("=" * 60)
    print(f"Time: {datetime.now().isoformat()}")
    print()

    # Claude
    print("CLAUDE (Anthropic):")
    print("  Caching type: Explicit with cache_control markers")
    print("  TTL: 5 minutes (automatic expiration)")
    print("  Action needed: None (auto-expires)")
    print("  Cost: Write +25%, Read 10% of base price")
    print()

    # Gemini
    print("GEMINI (Google):")
    print("  Caching type: Implicit (auto) + Explicit (manual)")
    print("  Implicit TTL: Managed by Google (no cost if unused)")
    print("  Explicit TTL: 60 minutes default")
    print("  Action needed: Delete explicit caches if created")

    caches = list_gemini_caches()
    if caches:
        print(f"  Active explicit caches: {len(caches)}")
        for cache in caches:
            print(f"    - {cache['name']}")
            print(f"      Model: {cache['model']}")
            print(f"      Expires: {cache['expire_time']}")
    else:
        print("  Active explicit caches: 0")
    print()

    # OpenAI
    print("OPENAI:")
    print("  Caching type: Automatic")
    print("  TTL: 5-10 minutes (automatic expiration)")
    print("  Action needed: None (auto-expires)")
    print("  Cost: 50% discount on cached tokens")
    print()

    print("=" * 60)
    return caches


def main():
    parser = argparse.ArgumentParser(
        description='Clear explicit API caches to avoid accumulating costs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Cache expiration by provider:
  Claude:  5 minutes (automatic, no action needed)
  Gemini:  60 minutes for explicit caches (can be deleted)
  OpenAI:  5-10 minutes (automatic, no action needed)

Only Gemini explicit caches need manual deletion. Implicit caching
(used by this system) is managed automatically by each provider.
"""
    )
    parser.add_argument('--delete', action='store_true',
                       help='Delete all explicit Gemini caches')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be deleted without deleting')
    parser.add_argument('--quiet', action='store_true',
                       help='Only show errors and cache counts')
    args = parser.parse_args()

    if not args.quiet:
        caches = report_cache_status()
    else:
        caches = list_gemini_caches()
        if caches:
            print(f"Found {len(caches)} Gemini explicit cache(s)")

    if args.delete or args.dry_run:
        if not caches:
            print("No explicit caches to delete.")
            return 0

        print()
        print("DELETING GEMINI EXPLICIT CACHES:")
        print("-" * 40)

        deleted = 0
        for cache in caches:
            if args.dry_run:
                print(f"  [DRY-RUN] Would delete: {cache['name']}")
            else:
                if delete_gemini_cache(cache['name']):
                    print(f"  [DELETED] {cache['name']}")
                    deleted += 1
                else:
                    print(f"  [FAILED] {cache['name']}")

        if args.dry_run:
            print(f"\nDry run complete. Would delete {len(caches)} cache(s).")
        else:
            print(f"\nDeleted {deleted}/{len(caches)} cache(s).")

    return 0


if __name__ == '__main__':
    sys.exit(main())
