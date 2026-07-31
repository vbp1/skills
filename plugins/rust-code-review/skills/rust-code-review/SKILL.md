---
name: rust-code-review
description: |
  Review Rust code and Rust diffs for subtle correctness hazards that often
  survive cargo build, cargo test, and ordinary clippy runs. Use when reviewing
  Rust changes, especially AI-generated Rust, async Tokio code, unsafe blocks,
  public trait/API changes, lifetime-heavy code, manual Send/Sync, lock-heavy
  code, transaction/RAII flows, or large buffer allocation paths.
---

# Rust Code Review

Review Rust with a bias toward hidden correctness bugs, not surface style.
This skill is inspired by recurring LLM-generated Rust failure modes: lifetime
contracts, async cancellation, unsafe invariants, public API compatibility, and
allocator/stack behavior.

## Workflow

1. Read repository instructions first: `AGENTS.md`, `CLAUDE.md`, contribution
   docs, test guidelines, and any Rust-specific policies.
2. Establish scope from the user request, `git status`, `git diff`, changed
   files, PR metadata, or named paths. Keep findings limited to that scope.
3. Do not review a tiny Rust diff in isolation when it touches lifetimes,
   async side effects, unsafe code, public traits, locks, transactions, or
   allocation strategy. Widen the reading context to callers, tests, trait
   impls, feature flags, and adjacent invariants while keeping reported
   findings tied to the requested scope.
4. Inspect `Cargo.toml`, `Cargo.lock` when present, `rust-toolchain.toml`, and
   feature flags relevant to the changed code.
5. If a finding depends on a crate or tool contract, verify the crate version
   and consult current documentation before reporting it.
6. Review the changed code with the hazard checklist below.
7. Run or recommend the narrowest meaningful checks for the changed surface.
8. Report findings first, ordered by severity, with file/line references,
   concrete failure mode, and the smallest practical fix.

## Hazard Checklist

### Lifetimes And Borrowed Data

Look for signatures that make a local implementation look elegant while
creating an unusable or over-constrained contract for callers.

- One lifetime reused for logically different relationships, such as input data
  and cache storage.
- Borrowed values stored in maps, caches, structs, tasks, or callbacks when the
  owner may not live long enough.
- Returned references whose validity depends on caller-side control flow the
  function cannot enforce.
- Lifetime fixes that only satisfy the current test but make normal calling
  code impossible.

When suspicious, require a realistic caller example. Prefer owned data,
separate lifetimes, or clearer ownership boundaries when the contract crosses a
storage or async boundary.

### Async, Send, Sync, And Locks

Treat `Arc`, `Mutex`, `RwLock`, atomics, channels, `tokio::spawn`, manual
`Send`/`Sync`, and shared mutable state as high-risk review areas.

- `std::sync::Mutex` or `std::sync::RwLock` used in async code where blocking
  can stall the runtime.
- Any guard, borrow, transaction, or critical section that may live across
  `.await`, including through closures, `if let`, early returns, or helper
  functions.
- Futures passed to `tokio::spawn` that are not actually `Send`, or rely on
  captured references with fragile lifetimes.
- Manual `unsafe impl Send` or `unsafe impl Sync` without a complete invariant
  proof.
- Lock ordering changes that can introduce deadlocks.

Do not accept "it compiles" as proof of async safety. Check the runtime,
features, and caller context.

### Drop Order And RAII

Review cleanup semantics when code touches transactions, files, locks, guards,
temporary directories, spans, connection leases, or other RAII resources.

- Errors from `commit`, `flush`, `close`, `finish`, or equivalent calls that
  leave a value to be cleaned up by `Drop`.
- `Drop` behavior that performs blocking work, spawns background cleanup, logs
  and swallows errors, or depends on an async runtime still being alive.
- Refactors that move resource owners across `match`, `?`, `return`, `select!`,
  or cancellation boundaries.
- Hidden ordering changes caused by tuple destructuring, temporary values, or
  moving code into helper functions.

If behavior depends on a crate such as `sqlx`, `deadpool`, `fuser`, or a storage
client, verify its documented cleanup contract for the project version.

### Unsafe Rust

Every `unsafe` block or `unsafe impl` needs an explicit, local safety argument.
If it is missing or vague, that is a review finding.

Check for:

- Alignment and unaligned reads from byte buffers, network data, mmap, packed
  structs, or FFI memory.
- Pointer provenance, aliasing, Stacked Borrows violations, and out-of-bounds
  pointer arithmetic.
- `transmute`, `from_raw_parts`, `set_len`, raw allocation/deallocation layout,
  `MaybeUninit`, `ManuallyDrop`, `Pin`, and self-referential data.
- `repr(C)` or layout assumptions that are not guaranteed by the type.
- FFI ownership, callback threading, panics crossing FFI boundaries, and null or
  dangling pointers.
- Unsafe code that is only tested on x86 or only with naturally aligned data.

Prefer reporting a precise missing invariant over a generic "unsafe is risky"
comment. Suggest `cargo miri` for executable unsafe paths when feasible, and
name unsupported areas such as FFI when Miri cannot cover them. If FFI blocks
Miri coverage, consider `cargo-careful` or report the uncovered unsafe risk
explicitly instead of treating ordinary tests as enough.

### Async Cancellation

Rust futures can be dropped at any `.await`. Review async code as if it may run
inside `tokio::select!`, `timeout`, request cancellation, shutdown, or retry
logic unless the caller contract proves otherwise.

- Partial side effects between await points: database write without ack,
  reservation without release, file rename without metadata update, lock update
  without notification.
- Non-idempotent operations inside retryable or cancellable flows.
- Cleanup that only happens after an `.await` that may never resume.
- Functions whose cancel-safety is undocumented but important to callers.
- Use of `read_exact`, buffered writes, or protocol operations whose
  cancel-safety differs from superficially similar APIs.

For critical async functions, require an explicit `cancel-safe` or
`NOT cancel-safe` contract and verify it against the caller path. For critical
sections that must not be cancelled mid-effect, consider isolating the
non-cancellable part behind `tokio::spawn` plus joining the handle, and call out
the tradeoff: this can sacrifice cooperative cancellation and must be justified
by the operation's consistency requirements.

### Public API And Trait Compatibility

Treat public Rust API changes as semver-sensitive even when the local crate
still compiles.

- New or changed blanket implementations such as `impl<T: Foo> Bar for T`.
- Public traits designed without a sealed-trait strategy when downstream
  implementations are possible.
- Trait hierarchy changes generated from local convenience rather than a stable
  external contract.
- New default methods, associated types, trait bounds, feature-gated impls, or
  orphan-rule interactions that can break downstream crates.
- Public type changes that leak private implementation details or make invalid
  states representable.

Prefer explicit impls unless the trait is intentionally sealed and the semver
surface is understood. Do not accept a new public trait hierarchy merely because
it is locally convenient: require an explicit contract, documentation, and
caller/downstream examples before implementation. If public API changed, suggest
an API diff check when the project has one.

### Allocation, Stack, And Large Values

Review code that creates or returns large arrays, buffers, generated tables, or
proc-macro output.

- Large `[T; N]` locals or return values that can overflow stack in debug or in
  unoptimized paths.
- `Box::new([value; N])` assumed to allocate directly on the heap.
- Accidental copies or moves of large arrays through intermediate locals.
- Code generation that emits large stack values repeatedly.

Prefer heap allocation patterns that do not require a large temporary stack
object, such as `Vec`-backed buffers or project-approved buffer abstractions.

### Panic And Error Boundaries

The article's high-risk token list included `unwrap`; review those sites, but
do not report every `unwrap` mechanically.

- `unwrap`, `expect`, indexing, `todo!`, or `unreachable!` in code reachable
  from external input, filesystem state, network data, FUSE callbacks, or public
  APIs.
- Error handling that drops context needed to debug production failures.
- Panics that can poison locks or abort background workers.
- Conversions from typed errors to strings too early.

Report only panics and error handling issues that create a credible failure mode
for the changed scope.

## Validation Guidance

Prefer project-defined quality gates. If absent or insufficient, choose from:

- `cargo fmt --check` for formatting.
- `cargo clippy --all-targets --all-features` for lint coverage.
- `cargo test` or a narrower test package/module for behavior.
- `cargo miri test` for executable unsafe logic when installed and compatible.
- For AI-heavy Rust changes, consider extra clippy groups such as `pedantic` or
  `nursery`; treat them as advisory unless the project already requires them or
  the user approves a stricter gate.
- Public API comparison tooling only if the project already has it or the user
  approves adding/installing it.

When a check cannot run, report the reason and the residual risk. Do not claim a
hazard is fixed or absent without checking the real path that matters.

## Reporting

Use a code-review stance:

- Findings first, ordered by severity.
- Every finding needs file/line, concrete failure mode, confidence, and a
  practical fix.
- Separate confirmed bugs from "needs verification" risks.
- Avoid generic Rust advice, style nits, and broad rewrites outside scope.
- Mention relevant validation performed and any gaps.

For AI-generated Rust, apply extra scrutiny to `unsafe`, `unwrap`, `transmute`,
`Arc`, `Mutex`, blanket impls, manual `Send`/`Sync`, custom lifetimes, and async
functions with side effects.
