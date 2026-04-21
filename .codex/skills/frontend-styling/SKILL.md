---
name: frontend-styling
description: Improve frontend visual design, styling systems, UI polish, and layout presentation for websites, dashboards, landing pages, and product interfaces. Use when Codex needs to restyle an existing frontend, introduce a clearer visual direction, build or refine design tokens, improve component aesthetics, tighten spacing and typography, or make a UI feel more intentional without drifting away from the product's existing structure.
---

# Frontend Styling

Define the visual direction in one sentence before editing. Name the mood, the intended user impression, and the level of change. Example: "Shift this dashboard toward a calm control-room feel with sharper hierarchy and warmer highlights, while keeping the current layout intact."

Start from the system layer, not one-off selectors. Prefer this order:

1. Audit the current styling entry points, shared layout primitives, and reusable components.
2. Decide whether to preserve the current design language or deliberately reset it.
3. Introduce or clean up design tokens first: colors, typography, spacing, radius, borders, shadows, and motion.
4. Adjust page-level composition next: density, section rhythm, whitespace, panel hierarchy, and responsive behavior.
5. Restyle reusable components before touching page-specific exceptions.
6. Verify hover, focus, empty, loading, error, and mobile states before finishing.

## Workflow

### 1. Build context

Inspect the frontend stack and locate the styling sources before changing anything:

- Global CSS or theme files
- Layout shells and page wrappers
- Reusable components such as cards, pills, buttons, tables, and forms
- Existing fonts, gradients, shadows, and spacing conventions

For React projects, prefer editing the shared style layer before adding local overrides. Keep styling decisions centralized whenever the codebase already has a token file, root stylesheet, theme object, or component variant system.

### 2. Choose the right level of change

Preserve the current visual language when the app already has a recognizable system and the user only wants refinement.

Push for a stronger redesign when the interface is visually flat, inconsistent, generic, or unclear.

Use a limited move set when time is tight:

- Stronger type hierarchy
- Cleaner spacing rhythm
- Better panel contrast
- One accent color family
- More deliberate hover and focus states

### 3. Create or tighten a style system

Prefer shared tokens over raw literals.

Include, at minimum:

- `--bg-*`, `--surface-*`, `--text-*`, `--accent-*`, `--line-*`
- a compact spacing scale
- a radius scale
- one shadow language
- one motion timing language

Avoid mixing unrelated visual metaphors. If surfaces are glassy and soft, keep borders, blur, and shadows aligned with that. If the product is industrial and dense, use firmer edges, clearer dividers, and restrained gradients.

### 4. Improve hierarchy

Use typography and spacing to show importance before using more color.

Prefer:

- distinct page title, section title, and supporting text sizes
- slightly quieter secondary text
- larger gaps between sections than between items within a section
- stronger contrast on primary actions than on passive controls

Do not solve hierarchy by making everything bold or bright.

### 5. Style components by role

Make repeated components feel like part of one family.

- Cards should share surface treatment, radius, border logic, and internal spacing.
- Buttons should communicate priority through fill, contrast, and motion.
- Status badges should use a consistent structure across success, warning, danger, and neutral states.
- Tables and forms should feel compatible with the surrounding panels rather than looking like browser defaults.

When a page still looks messy, reduce the number of component treatments instead of adding more.

### 6. Handle responsive behavior intentionally

Do not stop at desktop. Re-check:

- stacked layouts
- page header wrapping
- button groups
- card grids
- table overflow
- oversized hero or login panels

Prefer deliberate breakpoint behavior over accidental collapse.

### 7. Finish with polish

Before wrapping up, check:

- focus visibility
- hover affordance
- readable contrast
- loading and empty states
- consistent border radii
- animation restraint
- duplicated colors or shadows that should become tokens

## Guardrails

- Preserve the established product language unless the user clearly asks for a redesign.
- Avoid default-looking UIs. Pick a direction and commit to it.
- Avoid adding new dependencies for styling unless the repository already uses them or the gain is clear.
- Avoid scattering magic numbers and hex values through many files.
- Prefer CSS variables, theme objects, or shared utility layers.
- Keep accessibility intact: color contrast, focus styles, and readable font sizes still matter after the redesign.

## React and dashboard notes

In React dashboards, a good first pass is usually:

1. Update root variables and background treatment.
2. Tune shell, sidebar, page header, and panel styling.
3. Normalize cards, tables, forms, and badges.
4. Fix the mobile breakpoint last.

When the repository already has a central stylesheet, start there. Only move styling into component-level files when a component genuinely owns a unique treatment.

## Reference file

Use [references/style-directions.md](references/style-directions.md) when you need concrete style directions, a visual audit checklist, or quick recipes for dashboards, admin tools, and product pages.
