# Style Directions

Use this file when the task needs sharper visual direction than the core skill body provides.

## Quick audit

Check these in order:

1. Is there a visible visual concept, or does the UI feel generic?
2. Are colors doing too much work because typography and spacing are too weak?
3. Do surfaces belong to the same system?
4. Do cards, buttons, forms, and tables feel related?
5. Is there a clear primary action on each screen?
6. Does mobile preserve hierarchy instead of merely shrinking it?

## Token checklist

Define or normalize:

- background
- surface
- elevated surface
- text primary
- text secondary
- accent
- accent strong
- success
- warning
- danger
- divider or hairline
- radius scale
- spacing scale
- shadow language
- animation timings

If the codebase has repeated literal values, convert the repeated ones into shared tokens first.

## Direction recipes

### Control room

Use when the product is operational, analytical, or system-heavy.

- Dark or neutral base with selective warm highlights
- Dense but readable spacing
- Strong panel separation
- Compact badges and metrics
- Precise, restrained motion

### Editorial product

Use when the UI should feel premium, content-forward, or thoughtful.

- Higher whitespace budget
- Larger type scale
- Softer surfaces and quieter borders
- Fewer simultaneous accent colors
- More emphasis on reading rhythm than chrome

### Bright utility

Use when the interface should feel friendly and fast rather than intense.

- Light background or high-luminance surfaces
- Strong action color with plenty of neutral support
- Rounded controls
- Clear inline feedback
- Subtle shadows rather than heavy depth

## Anti-patterns

Avoid these common mistakes:

- mixing multiple accent families without a clear semantic reason
- using different radii on every component type
- making panels and page background too similar
- relying on saturated color instead of hierarchy
- giving every element a shadow
- adding animation everywhere
- introducing local style hacks before fixing the shared layer

## Minimal upgrade plan

If the user wants a fast improvement, do only this:

1. Establish a stronger color and surface token set.
2. Improve heading, body, and meta text hierarchy.
3. Normalize panels, buttons, and inputs.
4. Tighten the main responsive breakpoint.

This small pass often produces a much bigger perceived redesign than scattered page-specific tweaks.
