# CONTEXT.md

> **Cross-machine continuity bridge.** Read this first when resuming work on this project from any machine — it travels with the repo via git. Detailed conversation memory (feedback, decisions, deeper history) is mirrored at `Obsidian/myKnowledge/project-memory/Snipping_tool/` in the shared Obsidian vault.

## What This Is
Snipping Tool for Linux — a full-featured screenshot + annotation tool for Linux Mint / GTK3 desktops, designed to match and surpass the Windows Snipping Tool.

## Stack
- Python + GTK3.

## Status (as of 2026-06-11)
- Branch: `main`
- Recent work: merged `feature/copy-closes-editor` (close editor after clipboard copy), unit tests for `EditorWindow` shortcuts, Ctrl+S save shortcut, removed `scst_` prefix from auto-generated filenames.

## Active Work / Next Steps
- Feature set is comprehensive: rectangular/freeform/window/fullscreen snip, pen/highlighter/text annotation, arrow/shapes, eraser, undo/redo, auto-copy, global hotkey (Ctrl+Shift+S).
- No open work items recorded.

## Notes
- Personal repo: `Lovepankie/snipping-tool`
- Memory mirror documents OS-freeze causes, overlay architecture rules, and multi-monitor positioning — read before touching the screenshot overlay code.
