# Frontend — conventions

Loaded automatically (Claude Code's nested-memory convention, verified against
code.claude.com/docs/en/memory) whenever a file under this directory is read —
supplements the root [[CLAUDE.md]], doesn't replace it.

## Stack

React + Vite + TypeScript strict + Tailwind. **shadcn/ui** primitives are
vendored into `frontend/src/components/ui/` (reviewable code in the repo, not
a black-box dependency), plus **sonner** for toasts and **recharts** for
dashboard charts (phase 2 amendment, rules in DESIGN.md §6 — `recharts` is
flagged for removal in [[docs/phases/PHASE6.md]] step 5: ~351 KB, 42% of the bundle, for
one simple grouped bar chart a hand-rolled SVG component replaces).

- Vendored `components/ui/` files are generated starting points: type-checked
  and buildable, but exempt from the 300-line cap and slop review; edit them
  only for theme integration, keep app logic out of them.
- Everything else in `frontend/src` is held to the same standard as the
  backend (see root CLAUDE.md's Code Quality section).
- **No animation library.** `motion` was dropped in [[docs/phases/PHASE5.md]] step 4:
  used in exactly one place (`AnimatedNumber.tsx`'s stat-card count-up),
  pulled in the full `framer-motion/dom` build (gesture/layout/SVG-path
  engines never touched), and its `motion/mini` subpath wasn't a safe
  swap (confirmed by a real failed build — `animateMini` only animates a DOM
  element/selector, not a plain number). Replaced with a hand-rolled
  `requestAnimationFrame` tween (~15 lines, cubic ease-out). Animation is
  still seasoning, not sauce — transitions on drawers/dialogs, a pulse on
  the running badge — but reach for a plain CSS transition or a small
  hand-rolled tween before adding a library back.
- **No state library** — server data via plain `fetch` + a small `useApi`
  hook.
- **Lint via `oxlint`, format via `prettier`** — `oxlint` (Rust, ESLint-rule-
  compatible, already fast enough to run on every check) is this project's
  linter; don't add real ESLint alongside it, that's just a redundant
  second linter for the same job. `prettier` (`.prettierrc.json` at the
  frontend root: `semi: false`, `singleQuote: true`, `printWidth: 100` —
  matching the style every file already used, and backend's own `ruff`
  line length) is the one formatter; run `npm run format` to fix, `npm run
  format:check` to verify.

## Testing

TypeScript strict mode is the safety net; no unit tests — the UI is thin
(fetch → render) and all logic lives behind the tested API (revisit if
UI-side logic grows). Any change touching `frontend/` must pass `npm run
lint` (oxlint), `npm run format:check` (prettier), and `npm run build`
(strict `tsc` + Vite build) as part of the definition of done — this is
the frontend's actual type gate, referenced from root CLAUDE.md's Testing
section. All three run automatically via `./validate.sh` (repo root),
wired as a `Stop` hook.
