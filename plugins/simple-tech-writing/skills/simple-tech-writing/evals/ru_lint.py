#!/usr/bin/env python3
"""Счётчик стилевых промахов в русском техническом тексте.

Ловит то, что ловится регулярным выражением: длину предложения, канцелярит
(«выполнить настройку»), «-ся»-пассив, деепричастные и причастные обороты,
хеджи («следует», «рекомендуется»), мусорные слова, условие в конце предложения,
чередование синонимов.

Потолок метода: это не морфологический разбор. Счётчик пропускает часть
нарушений (цепочки родительного падежа, согласование) и даёт ложные
срабатывания на терминах вроде «подключение». Числа сравнимы между двумя
текстами, прогнанными через одну версию счётчика; это не вердикт о качестве.

Использование:
  python3 ru_lint.py --type procedural file.md
  cat text.md | python3 ru_lint.py --type descriptive -
  python3 ru_lint.py --self-test
"""
import json
import re
import sys

NOMINALIZATION = re.compile(
    r"\b(выполн|производ|осуществл|осуществ|произвед|провед)\w*\s+\w*(ание|ения|ение|ку|ки|ию|ия)\b", re.I)
PASSIVE_SYA = re.compile(r"\b\w{4,}(ется|ются|ался|ались|алось|алась)\b", re.I)
GERUND = re.compile(
    r"\b\w{4,}(вшись|вши)\b|(?:^|[.!?;]\s+|,\s+)([а-яё]{5,}(?:ая|яя|ав|ив|ев|ув))\s", re.I | re.M)
GERUND_STOP = {"актив", "архив", "мотив", "объектив", "норматив", "коллектив",
               "детектив", "локатив", "негатив", "позитив", "альтернатив"}
PARTICIPLE = re.compile(
    r"\b[а-яё]{5,}(ющий|ющая|ющее|ющие|ющих|ющим|ющего|вший|вшая|вшие|вших|вшего|"
    r"емый|емая|емые|емых|имый|имая|имые|имых)\b", re.I)
HEDGE = re.compile(
    r"\b(следует|рекомендуется|рекомендуем|желательно|стоит|по возможности|"
    r"при необходимости|как правило|при этом)\b", re.I)
SLOP = re.compile(
    r"\b(просто|легко|бесшовн\w*|мощн\w*|гибк\w*|удобн\w*|современн\w*|"
    r"из коробки|под капотом|в рамках|в целях|на сегодняшний день|"
    r"явля\w+ся|осуществля\w+|производит\w*)\b", re.I)
TRAILING_COND = re.compile(r"\w[^.!?\n]{3,}\s(если|когда|в случае)\s", re.I)
ROTATION_SETS = [
    ("проверка", re.compile(r"\b(провер|убеди|убежд|удостовер|валидир)\w*", re.I)),
    ("настройки", re.compile(r"\b(настройк|конфигурац|параметр|опци)\w*", re.I)),
    ("запуск", re.compile(r"\b(запуст|запуск|выполн|стартов|стартуй)\w*", re.I)),
]
LIMITS = {"procedural": 20, "descriptive": 25}


def strip_code(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]+`", " КОД ", text)  # один идентификатор — одно слово
    text = re.sub(r"^#+\s.*$", " ", text, flags=re.M)  # заголовки не считаем
    text = re.sub(r"https?://\S+", " ССЫЛКА ", text)
    return text


def sentences(text):
    text = re.sub(r"^\s*([-*]|\d+\.)\s+", "", text, flags=re.M)
    parts = re.split(r"(?<=[.!?:])\s+", text)
    return [p.strip() for p in parts if len(p.strip().split()) >= 2]


def count_gerunds(body):
    n = 0
    for m in GERUND.finditer(body):
        word = (m.group(0) if m.group(2) is None else m.group(2)).strip().lower()
        if word not in GERUND_STOP:
            n += 1
    return n


def lint(text, text_type):
    body = strip_code(text)
    sents = sentences(body)
    limit = LIMITS[text_type]
    lengths = [len(s.split()) for s in sents]
    counts = {
        "sentence_over_limit": sum(1 for n in lengths if n > limit),
        "nominalization": len(NOMINALIZATION.findall(body)),
        "passive_sya": len(PASSIVE_SYA.findall(body)),
        "gerund": count_gerunds(body),
        "participle": len(PARTICIPLE.findall(body)),
        "hedge": len(HEDGE.findall(body)),
        "slop_word": len(SLOP.findall(body)),
        "trailing_condition": sum(
            1 for s in sents if TRAILING_COND.search(s)
            and not re.match(r"^(если|когда|в случае)\b", s, re.I)),
    }
    rotation = 0
    for _, rx in ROTATION_SETS:
        stems = {m.group(1).lower() for m in rx.finditer(body)}
        if len(stems) > 1:
            rotation += len(stems) - 1
    counts["synonym_rotation"] = rotation
    words = max(1, len(body.split()))
    total = sum(counts.values())
    return {
        "type": text_type,
        "words": words,
        "sentences": len(sents),
        "mean_sentence_words": round(sum(lengths) / max(1, len(lengths)), 1),
        "longest_sentence_words": max(lengths, default=0),
        "violations": counts,
        "violations_total": total,
        "violations_per_100w": round(100.0 * total / words, 2),
    }


SLOP_FIXTURE = """Перед выполнением миграции рекомендуется осуществить проверку наличия резервной
копии, поскольку данные могут быть потеряны, при этом восстановление осуществляется вручную и
занимает продолжительное время. Настроив клиент, запустите синхронизацию, если сеть доступна.
Запросы, обрабатываемые воркером, попадают в очередь. Сервис является простым и мощным."""

CLEAN_FIXTURE = """Создайте резервную копию командой `backup create`. Убедитесь, что копия есть
в списке. Затем запустите миграцию.

Если сеть недоступна, увеличьте таймаут. Сервис — брокер задач. Он доставляет каждое сообщение
не менее одного раза."""


def self_test():
    slop = lint(SLOP_FIXTURE, "procedural")
    clean = lint(CLEAN_FIXTURE, "procedural")
    v = slop["violations"]
    assert v["sentence_over_limit"] >= 1, slop
    assert v["nominalization"] >= 1, slop
    assert v["passive_sya"] >= 1, slop
    assert v["gerund"] >= 1, slop
    assert v["participle"] >= 1, slop
    assert v["hedge"] >= 1, slop
    assert v["slop_word"] >= 2, slop
    assert v["trailing_condition"] >= 1, slop
    assert clean["violations_total"] == 0, clean
    print("self-test OK:", slop["violations_total"], "промахов в грязном тексте, 0 в чистом")


def main():
    args = sys.argv[1:]
    if "--self-test" in args:
        self_test()
        return
    text_type = "descriptive"
    if "--type" in args:
        text_type = args[args.index("--type") + 1]
    src = args[-1]
    text = sys.stdin.read() if src == "-" else open(src).read()
    print(json.dumps(lint(text, text_type), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
