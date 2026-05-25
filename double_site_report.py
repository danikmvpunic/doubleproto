#!/usr/bin/env python3
"""
Double · Pre-construction Site Intelligence — MVP v0.1
Вход: координаты участка (lat, lon)
Выход: markdown-отчёт с климатом, рельефом, адресом
       и предварительными рекомендациями по фундаменту.
Источники: Open-Meteo (климат + рельеф), Nominatim (адрес).
"""

import sys
import json
import datetime
import urllib.request
from pathlib import Path


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Double-MVP/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def get_address(lat, lon):
    url = (
        f"https://nominatim.openstreetmap.org/reverse"
        f"?lat={lat}&lon={lon}&format=json&accept-language=ru"
    )
    return fetch(url).get("display_name", "Unknown")


def get_elevation(lat, lon):
    url = (
        f"https://api.open-meteo.com/v1/elevation"
        f"?latitude={lat}&longitude={lon}"
    )
    elevs = fetch(url).get("elevation", [])
    return elevs[0] if elevs else None


def get_climate(lat, lon):
    end = datetime.date.today() - datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=365)
    url = (
        "https://archive-api.open-meteo.com/v1/archive?"
        f"latitude={lat}&longitude={lon}"
        f"&start_date={start}&end_date={end}"
        "&daily=temperature_2m_min,temperature_2m_max,"
        "precipitation_sum,snowfall_sum&timezone=auto"
    )
    return fetch(url)


def summarize(climate):
    d = climate.get("daily", {})

    def clean(xs):
        return [x for x in xs if x is not None]

    tmin = clean(d.get("temperature_2m_min", []))
    tmax = clean(d.get("temperature_2m_max", []))
    precip = clean(d.get("precipitation_sum", []))
    snow = clean(d.get("snowfall_sum", []))

    return {
        "min_temp_c": min(tmin) if tmin else None,
        "max_temp_c": max(tmax) if tmax else None,
        "annual_precip_mm": round(sum(precip), 1),
        "annual_snow_cm": round(sum(snow), 1),
    }


def foundation_notes(elev, s):
    notes = []
    if s["min_temp_c"] is not None and s["min_temp_c"] < -15:
        notes.append(
            "Глубокое промерзание — заглубление фундамента ≥ 1.5 м "
            "либо утеплённая шведская плита."
        )
    if s["annual_precip_mm"] > 400:
        notes.append(
            "Высокие осадки — обязательная гидроизоляция и дренаж по периметру."
        )
    if elev is not None and elev > 800:
        notes.append(
            "Высокая отметка — учесть ветровые нагрузки и сезонный сток."
        )
    if not notes:
        notes.append(
            "Климат умеренный. Базовая рекомендация: мелкозаглубленный "
            "ленточный фундамент с уточнением по локальной геологии."
        )
    return notes


def build_report(lat, lon):
    print("→ Получаю адрес...")
    address = get_address(lat, lon)
    print("→ Получаю высоту...")
    elev = get_elevation(lat, lon)
    print("→ Получаю климат за 365 дней...")
    climate = get_climate(lat, lon)
    s = summarize(climate)
    notes = foundation_notes(elev, s)
    now = datetime.datetime.now().isoformat(timespec="seconds")

    out = f"""# Double · Site Report

**Сгенерировано:** {now}
**Координаты:** {lat}, {lon}
**Адрес:** {address}

## Рельеф
- Высота над уровнем моря: **{elev} м**

## Климат (последние 365 дней)
- Минимальная температура: **{s['min_temp_c']} °C**
- Максимальная температура: **{s['max_temp_c']} °C**
- Сумма осадков за год: **{s['annual_precip_mm']} мм**
- Снег за год: **{s['annual_snow_cm']} см**

## Предварительные рекомендации по фундаменту
"""
    for n in notes:
        out += f"- {n}\n"
    out += (
        "\n---\n*MVP v0.1. Локальная геология должна быть "
        "подтверждена обследованием на участке.*\n"
    )
    return out


def main():
    if len(sys.argv) < 3:
        print("Usage: python double_site_report.py <lat> <lon>")
        print("Пример (Астана): python double_site_report.py 51.1605 71.4704")
        sys.exit(1)
    lat, lon = float(sys.argv[1]), float(sys.argv[2])
    report = build_report(lat, lon)
    Path("reports").mkdir(exist_ok=True)
    fname = f"reports/site_{datetime.datetime.now():%Y%m%d_%H%M%S}.md"
    Path(fname).write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\n✓ Сохранено: {fname}")


if __name__ == "__main__":
    main()
