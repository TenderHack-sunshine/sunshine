from __future__ import annotations

"""Build a reproducible, local-only profanity regression benchmark."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/eval/profanity_benchmark.jsonl"


def add(rows: list[dict], category: str, values: list[str], expected: bool) -> None:
    for value in values:
        rows.append({"id": f"{category}_{len(rows) + 1:03}", "category": category, "text": value, "expected_profane": expected})


def main() -> None:
    rows: list[dict] = []
    direct = ["хуй", "хуйня", "какого хуя", "пиздец", "блять", "ебать", "сука", "мудак", "мудила", "заебал"]
    add(rows, "direct", direct + [value.upper() for value in direct] + [f"Это {value}" for value in direct] + [f"Пользователь написал: {value}" for value in direct] + [f"Просьба: {value}" for value in direct] + [f"Ответьте: {value}" for value in direct], True)
    add(rows, "morphology", ["хуями", "хуевый", "хуесос", "пизда", "пиздюк", "пиздеть", "блядь", "бляха", "ебаный", "ебнулся", "заебешь", "сукой",
                               "нахуй", "похуй", "нихуя", "охуеть", "охуенно", "доебаться", "проебал", "наебал", "уебок", "долбоёб"], True)
    add(rows, "capitalization", ["ХУЙ", "ПиЗдЕц", "БЛЯТЬ", "ЕбАть", "СУКА", "МуДаК", "ХуЙнЯ", "ЗаЕбАл"], True)
    add(rows, "obfuscation", ["х*й", "х_й", "х-й", "х.й", "х у й", "хуууй", "п*здец", "п и з д е ц", "бл*ть", "б л я т ь", "е*ать", "с*ка", "му*ак", "н а х у й", "на*уй"], True)
    add(rows, "mixed_script", ["xуй", "хyй", "хуuй", "пиздeц", "бл*ть", "eбать", "cyка", "мyдак"], True)
    clean_support = [
        "Как добавить МЧД?", "Не получается подписать документ", "Где найти закупку?", "Ошибка при загрузке файла",
        "Как изменить сертификат?", "Не могу загрузить XML", "Как создать оферту?", "Не открывается котировочная сессия",
    ]
    add(rows, "clean_support", [f"{prefix} {item}" for prefix in ("", "Пожалуйста, ", "Подскажите: ", "Срочно: ", "Добрый день. ") for item in clean_support], False)
    add(rows, "tricky_negative", [
        "ебатьево", "суконная ткань", "мудрость пользователя", "пизанская башня", "художественный каталог",
        "блямба на чертеже", "контракт подписан", "переебывать данные не требуется", "система не отвечает",
        "хуже отображается страница", "суккулент в офисе", "мудрый выбор поставщика", "объект успешно добавлен",
        "пизанская пицца", "хурма в столовой",
        "похудеть к лету", "материал загружен", "XML файл не загружается",
    ], False)
    if not 150 <= len(rows) <= 250:
        raise ValueError(f"unexpected benchmark size: {len(rows)}")
    OUT.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"Wrote {len(rows)} cases to {OUT}")


if __name__ == "__main__":
    main()
