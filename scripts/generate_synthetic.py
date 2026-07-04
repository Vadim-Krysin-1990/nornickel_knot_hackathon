"""Генератор синтетического корпуса под структуру данных трека:
документы (md-отчёты), ground truth (готовые ExtractionResult-json),
каталоги (материалы, оборудование, сотрудники, свойства).

Зачем: разработать и прогнать ВЕСЬ пайплайн до 3 июля, не дожидаясь реальных данных.
Ground truth позволяет наполнять граф без LLM; LLM-экстракцию тестируем на тех же md.

Только stdlib. Детерминирован (seed). Запуск: python scripts/generate_synthetic.py
"""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path

random.seed(42)
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "synthetic"

# ---------------- Справочники ----------------
MATERIALS = [
    ("ЭП718", ["ХН45МВТЮБР"], "жаропрочный никелевый сплав", "Ni-Cr-Mo-W"),
    ("ВЖ159", ["ХН58МБЮ"], "жаропрочный никелевый сплав", "Ni-Cr-Mo-Nb"),
    ("ЭИ437Б", ["ХН77ТЮР"], "жаропрочный никелевый сплав", "Ni-Cr-Ti-Al"),
    ("МНЖ5-1", [], "медно-никелевый сплав", "Cu-Ni-Fe-Mn"),
    ("НМЖМц 28-2,5-1,5", ["монель"], "медно-никелевый сплав", "Ni-Cu-Fe-Mn"),
    ("Сплав Х-7", ["X-7"], "экспериментальный порошковый сплав", "Ni-Co-Cr (порошок)"),
]
PROPERTIES = [
    ("Твёрдость HV", "HV"),
    ("Предел прочности σв", "МПа"),
    ("Относительное удлинение δ", "%"),
    ("Ударная вязкость KCV", "Дж/см²"),
    ("Коррозионная стойкость", "балл"),
    ("Пористость", "%"),
]
EQUIPMENT = [
    ("Печь Nabertherm LH 30/14", "камерная печь"),
    ("Вакуумная печь СНВЭ-1.3.1", "вакуумная печь"),
    ("ГИП-установка QIH-9", "газостат"),
    ("Разрывная машина Instron 5982", "испытательная машина"),
    ("СЭМ TESCAN MIRA 3", "электронный микроскоп"),
    ("Твердомер ТК-2М", "твердомер"),
]
LABS = [
    "Лаборатория жаропрочных сплавов",
    "Лаборатория порошковой металлургии",
    "Лаборатория коррозионных испытаний",
]
PEOPLE_POOL = [
    "Алексей Иванов", "Мария Петрова", "Дмитрий Смирнов", "Ольга Кузнецова",
    "Сергей Соколов", "Анна Волкова", "Павел Морозов", "Ирина Федорова",
    "Никита Орлов", "Елена Захарова", "Андрей Лебедев", "Татьяна Козлова",
]
TAGS = ["термообработка", "ГИП", "механические свойства", "коррозия", "порошковая металлургия", "микроструктура"]

PROCESSES = ["отжиг", "закалка со старением", "ГИП", "гомогенизация"]

# Намеренные пробелы (Material x Property без экспериментов) — для демо вкладки «Пробелы»
EXCLUDE = {
    ("МНЖ5-1", "Ударная вязкость KCV"),
    ("МНЖ5-1", "Пористость"),
    ("Сплав Х-7", "Коррозионная стойкость"),
    ("ЭИ437Б", "Пористость"),
    ("НМЖМц 28-2,5-1,5", "Твёрдость HV"),
}

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya", "σ": "s", "δ": "d", "в": "v",
}


def slug(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch in TRANSLIT:
            out.append(TRANSLIT[ch])
        elif ch.isalnum() and ch.isascii():
            out.append(ch)
        elif ch in " -_,./":
            out.append("-")
    s = "".join(out)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def make_mode():
    process = random.choice(PROCESSES)
    if process == "отжиг":
        t, h, atm = random.choice([800, 900, 1000]), random.choice([1, 2, 4]), random.choice(["аргон", "вакуум", "воздух"])
        return dict(process=process, temperature_c=t, duration_h=h, atmosphere=atm, pressure_mpa=None,
                    label=f"Отжиг {t}°C / {h} ч / {atm}")
    if process == "закалка со старением":
        t, h = random.choice([1050, 1100]), random.choice([4, 8, 16])
        return dict(process=process, temperature_c=t, duration_h=h, atmosphere="воздух", pressure_mpa=None,
                    label=f"Закалка {t}°C + старение {h} ч")
    if process == "ГИП":
        return dict(process=process, temperature_c=1180, duration_h=3, atmosphere="аргон", pressure_mpa=150,
                    label="ГИП 1180°C / 150 МПа / 3 ч")
    t, h = 1150, random.choice([6, 12])
    return dict(process=process, temperature_c=t, duration_h=h, atmosphere="вакуум", pressure_mpa=None,
                label=f"Гомогенизация {t}°C / {h} ч")


def effect_for(process: str, prop: str):
    """Полуосмысленная физика, чтобы ответы выглядели правдоподобно."""
    rules = {
        ("ГИП", "Пористость"): ("decrease", -60, -85),
        ("ГИП", "Предел прочности σв"): ("increase", 5, 15),
        ("отжиг", "Твёрдость HV"): ("decrease", -8, -20),
        ("отжиг", "Относительное удлинение δ"): ("increase", 10, 30),
        ("закалка со старением", "Твёрдость HV"): ("increase", 12, 28),
        ("закалка со старением", "Предел прочности σв"): ("increase", 8, 18),
    }
    if (process, prop) in rules:
        d, lo, hi = rules[(process, prop)]
        return d, f"{random.randint(min(lo, hi), max(lo, hi)):+d}%"
    d = random.choice(["increase", "decrease", "none"])
    return d, (None if d == "none" else f"{random.randint(3, 15) * (1 if d == 'increase' else -1):+d}%")


def main(n_experiments: int = 40):
    docs_dir, truth_dir, cat_dir = OUT / "docs", OUT / "truth", OUT / "catalogs"
    for d in (docs_dir, truth_dir, cat_dir):
        d.mkdir(parents=True, exist_ok=True)

    pool = PEOPLE_POOL.copy()
    random.shuffle(pool)
    persons = []
    for i, lab in enumerate(LABS):
        for _ in range(4):
            persons.append({"name": pool.pop(), "lab": lab})

    for k in range(1, n_experiments + 1):
        mat_name, aliases, mclass, comp = random.choice(MATERIALS)
        mode = make_mode()
        eq_name, eq_type = EQUIPMENT[2] if mode["process"] == "ГИП" else random.choice(EQUIPMENT[:2])
        meas_eq = random.choice(EQUIPMENT[3:])
        lab = random.choice(LABS)
        team = random.sample([p for p in persons if p["lab"] == lab], 2)
        props = random.sample(PROPERTIES, k=random.choice([1, 2]))
        props = [p for p in props if (mat_name, p[0]) not in EXCLUDE] or [("Твёрдость HV", "HV")]
        if (mat_name, props[0][0]) in EXCLUDE:
            props = [("Предел прочности σв", "МПа")]
        date = f"{random.choice([2023, 2024, 2025])}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
        tags = random.sample(TAGS, 2)

        doc_id = f"doc-{k:03d}"
        exp_id = f"exp-{k:03d}"
        mat_id = f"mat-{slug(mat_name)}"
        mode_id = f"mode-{slug(mode['label'])}"
        title = f"Отчёт №{k:03d}. {mode['process'].capitalize()} сплава {mat_name}"

        findings, find_lines, relations = [], [], []
        relations += [
            {"source": doc_id, "type": "DESCRIBES", "target": exp_id, "props": {}},
            {"source": exp_id, "type": "USES_MATERIAL", "target": mat_id, "props": {}},
            {"source": exp_id, "type": "UNDER_MODE", "target": mode_id, "props": {}},
            {"source": exp_id, "type": "ON_EQUIPMENT", "target": f"eq-{slug(eq_name)}", "props": {}},
            {"source": exp_id, "type": "CONDUCTED_BY", "target": f"lab-{slug(lab)}", "props": {}},
        ]
        for p in team:
            pid = f"pers-{slug(p['name'])}"
            relations.append({"source": doc_id, "type": "AUTHORED_BY", "target": pid, "props": {}})
            relations.append({"source": pid, "type": "MEMBER_OF", "target": f"lab-{slug(p['lab'])}", "props": {}})
        for tg in tags:
            relations.append({"source": doc_id, "type": "TAGGED", "target": f"tag-{slug(tg)}", "props": {}})

        for pname, punit in props:
            pid = f"prop-{slug(pname)}"
            direction, magnitude = effect_for(mode["process"], pname)
            fid = f"find-{k:03d}-{slug(pname)}"
            human = {"increase": "повышение", "decrease": "снижение", "none": "значимого изменения не выявлено"}[direction]
            text = (f"{human.capitalize()} показателя «{pname}»"
                    + (f" на {magnitude.lstrip('+').lstrip('-')} ({magnitude})" if magnitude else "")
                    + f" после обработки: {mode['label'].lower()}.")
            findings.append({"id": fid, "text": text, "effect_direction": direction, "magnitude": magnitude})
            find_lines.append(f"- {pname}: {text}")
            relations += [
                {"source": exp_id, "type": "MEASURES", "target": pid, "props": {}},
                {"source": exp_id, "type": "HAS_FINDING", "target": fid, "props": {}},
                {"source": fid, "type": "AFFECTS", "target": pid,
                 "props": {"direction": direction, "magnitude": magnitude or ""}},
            ]

        md = f"""# {title}

DOC_ID: {doc_id}
Дата: {date}
Подразделение: {lab}
Исполнители: {", ".join(p["name"] for p in team)}
Теги: {", ".join(tags)}

## Цель работы
Оценить влияние режима «{mode['label']}» на свойства сплава {mat_name} ({mclass}, система {comp}).

## Материал
Сплав {mat_name}{(" (синонимы: " + ", ".join(aliases) + ")") if aliases else ""}, состояние поставки — пруток.

## Режим обработки
{mode['label']}. Оборудование: {eq_name} ({eq_type}).

## Методика измерений
Измерения выполнены на установке {meas_eq[0]} ({meas_eq[1]}) по стандартной методике лаборатории.

## Результаты
{chr(10).join(find_lines)}

## Выводы
Режим «{mode['label']}» {"рекомендован к дальнейшей отработке" if any(f["effect_direction"] == "increase" for f in findings) else "требует дополнительных исследований"} для сплава {mat_name}.
"""
        (docs_dir / f"{doc_id}.md").write_text(md, encoding="utf-8")

        truth = {
            "materials": [{"id": mat_id, "name": mat_name, "aliases": aliases,
                           "material_class": mclass, "composition": comp}],
            "properties": [{"id": f"prop-{slug(p)}", "name": p, "unit": u} for p, u in props],
            "modes": [{"id": mode_id, **mode}],
            "equipment": [{"id": f"eq-{slug(eq_name)}", "name": eq_name, "eq_type": eq_type},
                          {"id": f"eq-{slug(meas_eq[0])}", "name": meas_eq[0], "eq_type": meas_eq[1]}],
            "persons": [{"id": f"pers-{slug(p['name'])}", "name": p["name"], "role": "инженер-исследователь"} for p in team],
            "labs": [{"id": f"lab-{slug(lab)}", "name": lab}],
            "experiments": [{"id": exp_id, "title": title, "date": date,
                             "objective": f"Влияние режима «{mode['label']}» на свойства {mat_name}"}],
            "findings": findings,
            "documents": [{"id": doc_id, "title": title, "doc_type": "отчёт", "date": date,
                           "source_path": f"data/synthetic/docs/{doc_id}.md"}],
            "tags": [{"id": f"tag-{slug(t)}", "name": t} for t in tags],
            "relations": relations,
        }
        (truth_dir / f"{doc_id}.json").write_text(
            json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    # Каталоги — имитация справочников, которые выдадут организаторы
    def write_csv(name, rows, fields):
        with open(cat_dir / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    write_csv("materials.csv",
              [{"name": m, "aliases": ";".join(a), "class": c, "composition": s} for m, a, c, s in MATERIALS],
              ["name", "aliases", "class", "composition"])
    write_csv("equipment.csv", [{"name": n, "type": t} for n, t in EQUIPMENT], ["name", "type"])
    write_csv("properties.csv", [{"name": n, "unit": u} for n, u in PROPERTIES], ["name", "unit"])
    write_csv("people.csv", persons, ["name", "lab"])
    write_csv("tags.csv", [{"name": t} for t in TAGS], ["name"])

    print(f"OK: {n_experiments} экспериментов -> {OUT}")
    print(f"  docs:     {len(list((OUT / 'docs').glob('*.md')))} md")
    print(f"  truth:    {len(list((OUT / 'truth').glob('*.json')))} json")
    print(f"  catalogs: {len(list((OUT / 'catalogs').glob('*.csv')))} csv")
    print(f"  гарантированные пробелы: {sorted(EXCLUDE)}")


if __name__ == "__main__":
    main()
