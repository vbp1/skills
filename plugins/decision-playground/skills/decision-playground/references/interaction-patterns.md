# Interaction Patterns

Choose the page shape based on the decision the user must make.

## Questionnaire

Use `templates/questionnaire.html` when the user must answer many structured questions before work can continue.

Good for:

- Product requirements intake.
- Architecture discovery.
- Long setup questions.
- Multi-step project scoping.

Controls:

- Radio cards for mutually exclusive choices.
- Checkboxes for additive scope.
- Text areas for constraints and notes.
- Required markers only for decisions that truly block progress.

Use sections when there are more than 6 questions.

## Tradeoff Matrix

Use `templates/tradeoff-matrix.html` when the user must choose between architecture or implementation alternatives.

Good for:

- Build vs buy.
- Local implementation vs external dependency.
- Migration strategies.
- Data model alternatives.
- Compatibility vs speed tradeoffs.

Controls:

- Select one option per decision.
- Compare cost, risk, reversibility, user impact, and implementation effort.
- Show recommended option, but keep rejected options visible.

## Code Approaches

Use `templates/code-approaches.html` when the user must choose between concrete
coding strategies before implementation starts.

Good for:

- Inline local code vs shared helper vs external dependency.
- Quick patch vs reusable abstraction.
- Compatibility-preserving change vs deeper refactor.
- Test-first implementation vs implementation-first spike.

Controls:

- One selected approach.
- Scores for effort, risk, reuse, and reversibility.
- Small representative code snippet for each option.
- Notes for project rules, dependency policy, and compatibility constraints.

Keep snippets illustrative. Do not use this template as a full implementation
plan; use `implementation-brief-builder.html` when the user must select
milestones and quality gates too.

## Option Gallery

Use `templates/option-gallery.html` when visual or experiential differences matter.

Good for:

- UI layouts.
- Dashboard density.
- Empty states.
- Copy tone.
- Navigation patterns.
- Interaction models.

Controls:

- Clickable preview cards.
- Density, tone, and emphasis selectors.
- Side-by-side comparison.
- Notes for "combine these ideas" feedback.

The preview must show the actual selected direction, not decorative placeholder cards.

## Component Variants

Use `templates/component-variants.html` when the decision is about one component
rather than an entire screen.

Good for:

- Card, button, modal, table row, panel, or alert variants.
- Size, density, state, and emphasis decisions.
- Selecting a treatment that should map back to existing design-system props.

Controls:

- Clickable variant matrix.
- Density, state, and emphasis selectors.
- Live component sample for each variant.
- Code-like snippet that Codex can adapt to the project's real component API.

Use this instead of `option-gallery.html` when the user is choosing a reusable
component treatment, not an overall page direction.

## Flow Prototype

Use `templates/flow-prototype.html` when the user needs to feel an interaction
path instead of reading a written sequence.

Good for:

- Multi-step flows.
- Wizard vs single-screen decisions.
- Confirmation, review, and rollback interactions.
- Navigation or onboarding choices.

Controls:

- Clickable screen steps.
- Primary and secondary actions.
- A recorded visited path.
- Export of the selected flow and notes about friction.

Keep the prototype low fidelity. Its job is to validate the interaction path,
not final visual design.

## Triage Board

Use `templates/triage-board.html` when the user must rank or sort work.

Good for:

- Must-have / later / drop scope.
- Risk triage.
- Issue ordering.
- MVP definition.
- Review finding prioritization.

Controls:

- Columns with clear meaning.
- Move buttons or direct status selectors.
- Counts per column.
- Export grouped by priority.

## Implementation Brief Builder

Use `templates/implementation-brief-builder.html` when several choices should
be converted into an agent-ready implementation brief.

Good for:

- Selecting delivery mode before planning.
- Choosing milestones for a slice.
- Deciding the quality gate.
- Preventing scope expansion before implementation.

Controls:

- Delivery mode radio cards.
- Milestone checkboxes.
- Quality gate radio cards.
- Timeline preview.

Use this after enough context exists to form a work slice. If the user is still
choosing between implementation strategies, start with `code-approaches.html`.

## Config Editor

Use a custom adaptation of `questionnaire.html` when the output is a policy, config, or feature-flag set.

Good for:

- Agent policy options.
- Project conventions.
- Runtime feature flags.
- Review rubric settings.

Controls:

- Toggles for binary flags.
- Selects for modes.
- Sliders or number inputs for thresholds.
- Inline preview of the resulting config or policy.

## Prompt Builder

Use a custom adaptation of `questionnaire.html` when the output is an instruction to another agent.

Good for:

- Review prompts.
- Research prompts.
- Implementation briefs.
- Handoff instructions.

Controls:

- Scope selectors.
- Tone and depth selectors.
- Required evidence toggles.
- Output preview as Markdown.
