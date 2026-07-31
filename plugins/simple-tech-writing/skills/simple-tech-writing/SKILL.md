---
name: simple-tech-writing
description: |
  Write or rewrite technical text so that a tired reader cannot misread it, in
  Russian or in English. Structural rules from ASD-STE100 Simplified Technical
  English plus a Russian rule set for the same goal: short sentences, one
  instruction per sentence, condition before command, one term per concept,
  active voice, no filler.
  Use for documentation, READMEs, runbooks, procedures, error messages, release
  notes, incident reports, commit bodies, agent instructions, and for normative
  documents: specifications, requirements, design docs, ADRs, PRDs, API
  contracts.
  Triggers (EN): "simple english", "STE", "plain technical English", "de-slop",
  "make this readable", "write for non-native readers", "rewrite these docs",
  "write a spec", "write the requirements", "design doc", "ADR", "PRD".
  Triggers (RU): "напиши документацию", "перепиши по-человечески", "убери воду",
  "почисти текст", "простым языком", "техписательский стиль", "без канцелярита",
  "инструкция для дежурного", "текст ошибки", "описание аварии", "напиши спеку",
  "опиши требования", "техзадание", "дизайн-док", "проектное решение".
license: MIT
metadata:
  origin: structural rules paraphrased from ASD-STE100 Issue 9; Russian rules are ours
---

# Simple Tech Writing (RU + EN)

Write for a tired reader who is not a native speaker of the language you write in.
Each sentence must survive one read. The rules below remove the usual signs of
machine-written text — long sentences, synonym rotation, hedges, filler — as a
side effect.

## Your task

1. **Pick the language.** Write in the language of the source text, or of the
   request when there is no source. Never mix languages inside one document.
2. **Apply the shared rules**, then **only the block for your language**. The
   Russian block is meaningless for English text, and the reverse.
3. **Classify each passage** as procedural (instructions) or descriptive
   (explanations). Every length rule depends on this.
4. **Fix your terms before drafting.** One verb for the check/verify concept, one
   noun for the settings concept. Nothing else for those concepts in the document.
5. **Run the self-check** for your language. This step is not optional.
6. **Never touch** code, identifiers, commands, paths, or quoted errors.

Mode: by default apply the structural rules and keep the domain vocabulary of the
project ("idempotent", "webhook", "воркер", "шард"). When the user asks for strict
ASD-STE100 compliance, say that full compliance needs the official dictionary
(free at asd-ste100.org), and do not cite rule numbers you have not read.

## Shared rules (both languages)

| | Procedural | Descriptive |
|---|---|---|
| Purpose | tell the reader what to do | explain what a thing is or does |
| Sentence limit | **20 words** | **25 words** |
| Unit | one instruction per sentence | one topic per paragraph, max six sentences |
| Mood | imperative | no imperative |

- Put the condition before the command, with a comma.
- One concept, one term, in the whole document.
- Active voice. Passive only in descriptive text when the actor is unknown.
- In a warning: the command or the condition first, the risk second.
- Vertical list for more than two steps or items.
- Code, flags, paths, identifiers and quoted errors stay exact and count as one
  word each toward the sentence limit.
- Delete words that carry no fact. If a word states no measurable property,
  it is filler.

## Specifications and requirements

A normative document — specification, requirements list, design doc, ADR, PRD,
API contract, RFC — states levels of obligation with specific words: **MUST /
SHOULD / MAY / MUST NOT** and **«должен» / «следует» / «может» / «не должен»**.
These words are the meaning, not filler. Keep them exactly as the author wrote
them, in both languages. The modality rules of the language blocks below do not
apply to them.

Everything else applies as usual, and matters more here than anywhere: one term
per concept, the condition before the requirement, the length limits, active
voice, no «является» and no "is designed to".

Three extra rules for this kind of document:

- One requirement per sentence. A requirement that says "and" twice is two
  requirements.
- Keep requirement identifiers (`REQ-14`, `SPEC-3.2`) exactly as written; they
  are technical names.
- Name the actor of every requirement. "Данные валидируются" hides who validates
  and cannot be tested; write "Сервис проверяет данные".

A requirement level word is protected only inside a normative document. In a
README or a guide, the modality rules below apply as normal.

## If the text is in Russian

| Правило | Плохо | Хорошо |
|---|---|---|
| Повелительное наклонение совершенного вида | Осуществите запуск миграции | Запустите миграцию |
| Глагол вместо отглагольного существительного | Выполните настройку клиента | Настройте клиент |
| Без «-ся»-пассива и безличных форм | Конфигурация загружается сервисом | Сервис загружает конфигурацию |
| Деепричастный оборот → отдельное предложение | Настроив клиент, запустите синхронизацию | Настройте клиент. Затем запустите синхронизацию |
| Причастный оборот → отдельное предложение | Запросы, обрабатываемые воркером в фоне, попадают в очередь | Воркер обрабатывает запросы в фоне. Эти запросы попадают в очередь |
| Не более трёх существительных подряд в родительном | значение таймаута подключения пула базы | таймаут подключения для пула базы |
| Условие впереди | Увеличьте таймаут, если сеть медленная | Если сеть медленная, увеличьте таймаут |
| Прямая модальность | Следует убедиться, что бэкап создан | Убедитесь, что бэкап создан |
| Полная грамматика, без телеграфа | Проверить наличие бэкапа перед миграцией | Убедитесь, что бэкап создан. Затем запустите миграцию |
| Идентификаторы не склоняются | пропиши в конфиге | задайте значение в файле `config.yaml` |

Модальность: «следует», «рекомендуется», «желательно», «стоит», «по возможности»,
«при необходимости» → «нужно», повелительное наклонение или удалить. Оставь
«можно», «нельзя», «нужно», «будет». Исключение — нормативный документ: там
«должен», «следует», «может» задают уровень обязательности, и ты их не трогаешь.

Заимствования: один вариант на понятие во всём документе. «Развёртывание» или
«деплой» — выбери одно и не чередуй.

Мусор в русском тексте: просто, легко, бесшовно, гибкий, мощный, современный,
удобный, из коробки (→ «по умолчанию»), под капотом (→ «внутри»), в рамках, в
целях (→ «чтобы»), на сегодняшний день, следует отметить, стоит упомянуть,
является (→ прямая связка: «Сервис — брокер задач»), осуществлять / производить
(→ конкретный глагол).

Орфография: буква «ё» пишется, кавычки-ёлочки, тире — длинное. Один стандарт на
весь документ.

## If the text is in English

Keep complete grammar: no contractions, keep the articles, keep "that"
("make sure that the file exists"). Verbs only as: infinitive, imperative, simple
present, simple past, simple future, past participle as an adjective. No present
perfect ("has completed" → "completed"). No "-ing" verb forms (", making it easy"
→ a new sentence). Approved modals: **can, will, must**. Banned: should, would,
may, might, could — a requirement becomes "must", a suggestion is stated as fact
or deleted. Exception: in a normative document, MUST / SHOULD / MAY carry the
requirement level and stay exactly as written. Noun chains of three words maximum; break longer ones with
prepositions ("the timeout value for the connection pool"). No semicolons — write
two sentences. American spelling.

Filler in English text: simply, just, easily, seamlessly, effortlessly, robust,
powerful, comprehensive, performant, leverage (→ use), utilize (→ use), in order
to (→ to), prior to (→ before), ensure (→ make sure that), it is worth noting
that (→ delete), enables you to (→ you can), is designed to (→ say what it does),
out of the box (→ by default), under the hood (→ internally), gracefully handles
(→ say what it does), e.g. / i.e. (→ for example / that is), etc. (→ name the
items).

## One term per concept

Collapse each rotation to a single term and keep it for the whole document:

| Concept | Russian | English |
|---|---|---|
| verification | проверить / убедиться / удостовериться → одно | check / verify / confirm / validate → one |
| settings | настройки / конфигурация / параметры / опции → одно | config / configuration / settings → one |
| execution | запустить / выполнить / стартовать → одно | run / execute / invoke / launch → one |
| failure | ошибка (сообщение) / сбой (событие) | error (message) / failure (operation) |
| display | показать / вывести / отобразить → одно | show / display / render → one |

## Untouchables

Leave these exact, even when they break the rules above: code blocks, inline
code, identifiers, CLI commands, flags, file paths, quoted error messages and log
lines, product names, API endpoints, config keys, numbers with units.

## Self-check before you deliver

Both languages: count the words in your three longest sentences and split
anything over the limit. Find every condition word and move it to the front of
its sentence. Find the synonyms of the terms you fixed in step 4 and replace them.

Russian text — search for and rewrite: слова на «-ание», «-ение» рядом с
«выполнить», «произвести», «осуществить»; окончания «-ется», «-ются», «-ался»;
деепричастия на «-в», «-вши», «-вшись», «-я» в начале оборота; причастия на
«-ющий», «-вший», «-емый», «-имый»; «следует», «рекомендуется», «желательно»;
«является»; «если» и «когда» в середине предложения.

English text — search for and rewrite: `'ll`, `'re`, `'s` as a contraction,
`has been`, `have been`, `should`, `, making`, `, allowing`, `, ensuring`,
semicolons, `e.g.`, `i.e.`, `etc.`, `if` and `when` mid-sentence.

## Examples

**Русский, процедурный.**

Before:
> Перед выполнением миграции рекомендуется осуществить проверку наличия
> резервной копии, поскольку в случае возникновения ошибки данные могут быть
> потеряны, при этом восстановление осуществляется вручную.

After:
> ПРЕДУПРЕЖДЕНИЕ: Перед миграцией создайте резервную копию. Без копии данные
> восстанавливаются только вручную.
>
> 1. Создайте резервную копию командой `backup create`.
> 2. Убедитесь, что копия появилась в списке `backup list`.
> 3. Запустите миграцию командой `migrate up`.

**Русский, описательный.**

Before:
> Сервис является брокером задач, обеспечивающим доставку сообщений, при этом
> осуществляется гарантированная обработка, что позволяет не терять данные.

After:
> Сервис — брокер задач. Он доставляет каждое сообщение не менее одного раза.
> Если обработчик отказал, сервис повторяет доставку три раза.

**English, procedural.**

Before:
> You'll want to grab the API key from the dashboard before configuring the
> client, which you can do under Settings.

After:
> Get the API key from the dashboard, under Settings. Then configure the client
> with this key.

## Limits

These rules are for technical facts and instructions. Do not apply them to
marketing copy, launch posts, or brand writing — they delete persuasion by
design. When the user asks for this style on marketing text, say so and offer it
for the documentation instead.

The English block paraphrases the structural rules of ASD-STE100 Issue 9 and
reproduces no dictionary content. The standard is a free download at
asd-ste100.org. This skill is unofficial and guarantees no compliance.

## References

- `references/short-prompt.md` — the same rules compressed for a system prompt,
  AGENTS.md, or a chat without skill support. Russian and English versions.
- `evals/` — Russian violation counter and the measured results for this skill.
