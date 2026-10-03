# Example: the `### Stages and tasks` section

Illustrative only — the task is invented, the shape is what matters. Each stage is a bold
heading `**SN. Name.**` with one sentence on what the stage lays down, a `- [ ]` task list,
and a `Done when: …` line naming an observable result. A short paragraph before the stages
says how the work splits and why in this order. Prose and references to code only, no code
blocks.

---

### Stages and tasks

Three stages, each ending in a working, verified piece. Each one builds on the one before.
Inside a stage the test is written first and fails first.

**S1. Storing notes.** The foundation: a note needs a place before it can be shown.

- [ ] A notes table per database: text, author, creation time; migration through the generator.
- [ ] Deleting a database deletes its notes.
- [ ] Reading and writing notes in the data layer, with a permission check on the database.

Done when: running every migration against an empty database passes, and a note written by a
user without rights on the database is refused with a clear error.

**S2. An endpoint for the screen.** The screen gets notes through the API, never touching the
data layer.

- [ ] A route: list a database's notes and add a note.
- [ ] Empty text and text over the limit return an error that names the cause.
- [ ] Route tests: list, add, both errors.

Done when: a request to the route on the live stand returns the note just added, and empty text
is refused with its cause.

**S3. The notes panel.** What the user sees.

- [ ] A panel on the database page: the list, an input, an add button.
- [ ] States: empty, loading, error with the server's own text.
- [ ] An end-to-end test of "added a note, still see it after a reload".

Done when: on the stand a note is added, survives a page reload, and a server error shows its
own text.
