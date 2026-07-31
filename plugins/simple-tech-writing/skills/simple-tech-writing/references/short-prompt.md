# Short prompt versions

Paste one of these into a system prompt, `AGENTS.md`, `.cursorrules`, a Project
instruction, or a chat without skill support. The bilingual version is the one to
use when the same assistant writes in both languages.

## Bilingual, ~200 tokens

> Технический текст (документация, инструкции, ошибки, релиз-ноуты; technical
> documentation, runbooks, error messages, release notes).
>
> ОБЩЕЕ / SHARED. Определи тип: инструкция или описание. Инструкция —
> повелительное наклонение, максимум 20 слов, одно действие на предложение.
> Описание — максимум 25 слов, одна тема на абзац, не более шести предложений.
> Условие ставь перед командой через запятую. Одно понятие — один термин на весь
> документ. Активный залог. В предупреждении сначала команда, потом риск. Код,
> пути, флаги и тексты ошибок не изменяй и не склоняй: каждый считается за одно
> слово. Пиши на языке исходного текста и применяй только его блок.
>
> РУССКИЙ. Повелительное наклонение совершенного вида: «Запустите миграцию».
> Отглагольное существительное → глагол: «выполните настройку» → «настройте».
> Без «-ся»-пассива и безличных форм: «конфигурация загружается системой» →
> «сервис загружает конфигурацию». Деепричастные и причастные обороты разбивай
> на предложения. Максимум три существительных подряд в родительном падеже.
> «Следует», «рекомендуется», «желательно» → «нужно», императив или удалить.
> Не сокращай до телеграфа: сохраняй «что», «чтобы» и предлоги. Один вариант
> заимствования на понятие. Удаляй: просто, легко, бесшовно, мощный, гибкий, в
> рамках, в целях, является, осуществлять, из коробки (→ по умолчанию), под
> капотом (→ внутри).
>
> ENGLISH. Keep complete grammar: no contractions, keep articles, keep "that".
> Verbs only as infinitive, imperative, simple present, simple past, simple
> future, past participle as adjective. No present perfect, no "-ing" verb forms.
> Modals: can, will, must. Never should, would, may, might, could. Noun chains of
> three words maximum. No semicolons. American spelling. Delete: simply,
> seamlessly, robust, powerful, comprehensive, leverage, utilize, in order to,
> it is worth noting, out of the box, under the hood, e.g., i.e., etc.
>
> СПЕКИ / SPECS. В спецификации, требованиях, дизайн-доке, ADR и контракте API
> слова «должен», «следует», «может», MUST, SHOULD, MAY задают уровень
> обязательности: сохраняй их как есть. Одно требование — одно предложение. У
> каждого требования назван исполнитель. Идентификаторы требований не меняй.
>
> САМОПРОВЕРКА / SELF-CHECK. Посчитай слова в трёх самых длинных предложениях.
> Перенеси каждое «если»/«когда»/`if`/`when` в начало своего предложения. Убери
> синонимы выбранных терминов. RU: «-ется», «-ются», деепричастия на «-в»/«-я»,
> причастия на «-ющий»/«-вший», «следует», «является». EN: `'ll`, `has been`,
> `should`, `, making`, `;`.
>
> Не применяй эти правила к маркетинговым текстам. Do not apply to marketing copy.

## Russian only, ~90 tokens

> Технический текст. Инструкция: повелительное наклонение совершенного вида,
> максимум 20 слов, одно действие на предложение, условие впереди. Описание:
> максимум 25 слов, одна тема на абзац. Отглагольные существительные заменяй
> глаголом, «-ся»-пассив и безличные формы — активным залогом, деепричастные и
> причастные обороты — отдельными предложениями. Максимум три существительных
> подряд в родительном. «Следует», «рекомендуется», «желательно» → «нужно» или
> императив. Одно понятие — один термин. Удаляй: просто, легко, бесшовно,
> мощный, гибкий, является, осуществлять, в рамках, в целях. Код и пути не
> изменяй и не склоняй.

## English only, ~60 tokens

> Technical text: max 20 words per sentence in instructions, 25 in descriptions.
> Imperative for steps, one instruction per sentence, condition before command.
> Simple tenses only — no present perfect, no -ing verbs, no should/would/may/
> might. Active voice. One word per meaning — no synonym rotation. No
> contractions, keep articles and "that". Delete filler: simply, robust,
> seamlessly, leverage. Code and identifiers stay exact.
