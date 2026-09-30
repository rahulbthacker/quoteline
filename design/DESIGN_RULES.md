# Quoteline design rules

Library: shadcn/ui on Tailwind v4 (Radix primitives), TanStack Table v8 for the grid, Recharts, Lucide icons, Sonner toasts. Fonts: Geist and Geist Mono from Google Fonts with system fallbacks. Wire Tailwind's theme to the CSS variables in `tokens.css`; never hardcode a hex in a component.

## Principles (each maps to a brief requirement)
1. Uncertainty is a rendered state, not a hidden number. Cell states: confident, lowest-on-line, needs-review, not-quoted, overridden. Not-quoted is hatched text "not quoted", never 0, never blank.
2. Every figure is one click from its source. Any grid cell opens a provenance popover: source file and locator, verbatim snippet with the value highlighted, both model readings, agreement, the conversion arithmetic, actions (accept, override, ask vendor, exclude).
3. The system's assumptions are always on screen. Assumptions bar at the top of Compare, Analyse and Award: base unit, FX with source and date, freight treatment, tax.
4. One job per screen. Compare, Review queue, Analyse, Award are separate routes reached from the stage stepper. No stacked panels.
5. Colour carries meaning only. Monochrome surfaces; accent for the current stage and primary action; warning, danger, success, info for states. States are also distinguished by lightness and pattern, never hue alone.

## Density
Compact (34px rows, 12px mono numbers, 8px 12px cell padding) inside the comparison grid only. Comfortable (40px) everywhere else. Page padding 20px to 28px.

## Components and their rules
- App shell: 52px top bar (product mark, breadcrumb with status pill, persona switcher, Run inspector, avatar). 212px left rail with the six-stage stepper (done, active, todo states), Review queue count, Vendor inbox, Attachments, and a "this run" cost/agreement readout.
- Stepper item: 20px dot, label 13/500, sub-label 11 ink-faint. Active gets accent-bg.
- Segmented control: surface-2 track, active segment surface-1 with 1px border-strong ring.
- Pills: 11/500, 999px radius, semantic bg and ink pairs. Mono pills for counts and confidence.
- Buttons: primary (accent, on-accent text), secondary (surface-1, border-strong), ghost (transparent, ink-muted), danger (danger-bg, danger-ink). 6px radius, 12px text.
- Grid: header surface-2, vendor header carries name, format pill, lines-quoted mono pill, quality pill. Numbers right-aligned in Geist Mono. Footer: extended total row with exclusion note, freight row as stated by vendor.
- Provenance popover: 420px, warning header when flagged, one soft shadow, sections in order: source, readings, why flagged, arithmetic, actions.
- Review card: three columns (identity and confidence, reasoning and evidence, stacked actions). One primary action per card.
- Analyst: user message right-aligned bubble; answer as prose, then table and chart side by side, then the open-items caveat in warning colours, then the collapsed "Query I ran" details element, then actions. Query is collapsed by default, expandable, never hidden.
- Award: four stat cards (recommended total, vs single vendor, vs last year, still open in warning), allocation table, rules applied with success ticks, exclusions with alert icons and the cost of the rule, audit log, approver box that is blocked while review items are open.
- Run inspector: right drawer listing every model call with role, model, prompt version, tokens, latency, cost, agreement.

## Dark mode
`tokens.css` declares color-scheme and provides the dark theme under both `prefers-color-scheme: dark` and `[data-theme="dark"]`. Add a theme toggle in the top bar that sets `data-theme`. Verify every screen in both themes before the demo.

## Reference
`reference/` holds the mockup screens as self-contained HTML: open them in a browser. They are the visual target for the first five screens.
