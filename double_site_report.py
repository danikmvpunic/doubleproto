#!/usr/bin/env python3
"""
Double · Pre-construction Site Intelligence — MVP v0.2

Вход: координаты участка (lat, lon)
Выход: markdown- или json-отчёт по участку:
  - адрес, рельеф
  - климат за 365 дней (Open-Meteo Archive)
  - почвенный состав 0-30 см (SoilGrids v2.0)
  - расчёт нормативной глубины промерзания по СНиП 2.02.01-83
  - снеговая нагрузка по укрупнённым зонам РК
  - рекомендации по фундаменту с обоснованием

Формулы:
  d_f = d_0 · sqrt(M_t)  — СНиП 2.02.01-83 п. 2.27
  M_t — сумма абсолютных значений среднемесячных отрицательных
  температур воздуха
  d_0 — коэффициент по типу грунта

Дисклеймер: расчёты предварительные. Финальные параметры фундамента —
после инженерно-геологических изысканий на участке.
"""

import sys
import json
import math
import argparse
import datetime
import urllib.request
import urllib.error
from pathlib import Path
from collections import defaultdict

USER_AGENT = "Double-MVP/0.2 (danik.real1205@gmail.com)"


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def safe_fetch(url, label, timeout=30):
    try:
        return fetch(url, timeout=timeout), None
    except urllib.error.HTTPError as e:
        return None, f"{label}: HTTP {e.code}"
    except urllib.error.URLError as e:
        return None, f"{label}: сеть недоступна ({e.reason})"
    except Exception as e:
        return None, f"{label}: {type(e).__name__} {e}"


# ---------- Источники данных ----------

def get_address(lat, lon):
    url = (
        f"https://nominatim.openstreetmap.org/reverse"
        f"?lat={lat}&lon={lon}&format=json&accept-language=ru&zoom=14"
    )
    data, err = safe_fetch(url, "Nominatim")
    if err:
        return None, err
    return data.get("display_name", "Unknown"), None


def get_elevation(lat, lon):
    url = (
        f"https://api.open-meteo.com/v1/elevation"
        f"?latitude={lat}&longitude={lon}"
    )
    data, err = safe_fetch(url, "Open-Meteo Elevation")
    if err:
        return None, err
    elevs = data.get("elevation", [])
    return (elevs[0] if elevs else None), None


def get_climate(lat, lon):
    end = datetime.date.today() - datetime.timedelta(days=5)
    start = end - datetime.timedelta(days=365)
    url = (
        "https://archive-api.open-meteo.com/v1/archive?"
        f"latitude={lat}&longitude={lon}"
        f"&start_date={start}&end_date={end}"
        "&daily=temperature_2m_min,temperature_2m_max,temperature_2m_mean,"
        "precipitation_sum,snowfall_sum&timezone=auto"
    )
    return safe_fetch(url, "Open-Meteo Archive", timeout=45)


def get_soil(lat, lon):
    url = (
        "https://rest.isric.org/soilgrids/v2.0/properties/query"
        f"?lon={lon}&lat={lat}"
        "&property=clay&property=sand&property=silt"
        "&depth=0-30cm&value=mean"
    )
    return safe_fetch(url, "SoilGrids", timeout=60)


# ---------- Аналитика ----------

def summarize_climate(climate):
    d = (climate or {}).get("daily", {}) or {}
    dates = d.get("time", []) or []
    tmin = d.get("temperature_2m_min", []) or []
    tmax = d.get("temperature_2m_max", []) or []
    tmean = d.get("temperature_2m_mean", []) or []
    precip = d.get("precipitation_sum", []) or []
    snow = d.get("snowfall_sum", []) or []

    def clean(xs):
        return [x for x in xs if x is not None]

    by_month = defaultdict(list)
    for date_str, t in zip(dates, tmean):
        if t is None:
            continue
        by_month[date_str[:7]].append(t)

    monthly_means = {
        ym: sum(vals) / len(vals) for ym, vals in by_month.items() if vals
    }
    mt_sum = sum(-v for v in monthly_means.values() if v < 0)

    return {
        "min_temp_c": min(clean(tmin)) if clean(tmin) else None,
        "max_temp_c": max(clean(tmax)) if clean(tmax) else None,
        "annual_precip_mm": round(sum(clean(precip)), 1) if precip else 0.0,
        "annual_snow_cm": round(sum(clean(snow)), 1) if snow else 0.0,
        "monthly_means_c": {k: round(v, 1) for k, v in monthly_means.items()},
        "freezing_index_mt": round(mt_sum, 1),
    }


def classify_soil(soil_payload):
    if not soil_payload:
        return None
    layers = (soil_payload.get("properties", {}) or {}).get("layers", []) or []
    out = {}
    for layer in layers:
        name = layer.get("name")
        depths = layer.get("depths", []) or []
        if not depths:
            continue
        values = depths[0].get("values", {}) or {}
        mean = values.get("mean")
        if mean is not None:
            out[name] = round(mean / 10, 1)
    if not out:
        return None

    clay = out.get("clay", 0)
    sand = out.get("sand", 0)
    silt = out.get("silt", 0)

    if clay >= 35:
        soil_type = "Глина / суглинок тяжёлый"
        d0 = 0.23
    elif clay >= 20:
        soil_type = "Суглинок"
        d0 = 0.23
    elif sand >= 60 and clay < 10:
        soil_type = "Песок средней крупности / крупный"
        d0 = 0.30
    elif sand >= 40 and silt >= 20:
        soil_type = "Супесь / песок пылеватый"
        d0 = 0.28
    else:
        soil_type = "Смешанный (преобладает суглинок)"
        d0 = 0.23

    return {
        "clay_pct": clay,
        "sand_pct": sand,
        "silt_pct": silt,
        "soil_type": soil_type,
        "d0_coeff_m_per_sqrt_C_month": d0,
    }


def frost_depth(d0, mt):
    if d0 is None or mt is None or mt <= 0:
        return None
    return round(d0 * math.sqrt(mt), 2)


def snow_zone_kz(annual_snow_cm):
    if annual_snow_cm is None:
        return None, None
    s = annual_snow_cm
    if s < 30:
        return "I", 0.8
    if s < 60:
        return "II", 1.2
    if s < 90:
        return "III", 1.8
    if s < 120:
        return "IV", 2.4
    if s < 180:
        return "V", 3.2
    return "VI", 4.0


def foundation_recommendations(elev, climate_sum, soil, df):
    notes = []
    reasoning = []

    tmin = climate_sum.get("min_temp_c")
    precip = climate_sum.get("annual_precip_mm")
    mt = climate_sum.get("freezing_index_mt")

    if df is not None and df >= 1.4:
        notes.append(
            f"Глубокое промерзание ({df} м). Рекомендуется заглубление "
            f"подошвы фундамента ниже расчётной глубины промерзания "
            f"или утеплённая шведская плита (УШП)."
        )
        reasoning.append(
            f"d_f = d_0·√M_t = {soil.get('d0_coeff_m_per_sqrt_C_month')}·√{mt}"
            f" = {df} м (СНиП 2.02.01-83 п. 2.27)"
        )
    elif df is not None:
        notes.append(
            f"Умеренное промерзание ({df} м). Допустим мелкозаглубленный "
            f"ленточный фундамент с противопучинистыми мероприятиями."
        )
        reasoning.append(
            f"d_f = {df} м по СНиП 2.02.01-83 при типе грунта "
            f"«{soil.get('soil_type')}»"
        )

    if soil and soil.get("clay_pct", 0) >= 30:
        notes.append(
            "Высокое содержание глины — риск морозного пучения. Обязательны: "
            "дренаж, утепление отмостки, замена пучинистого грунта в зоне "
            "промерзания или свайно-винтовое основание."
        )
        reasoning.append(
            f"Глина = {soil['clay_pct']}% (порог пучинистости ≥ 30%)"
        )

    if precip is not None and precip > 400:
        notes.append(
            f"Сумма осадков {precip} мм/год — обязательная гидроизоляция "
            f"и кольцевой дренаж по периметру."
        )
        reasoning.append(f"Осадки {precip} мм > порога 400 мм/год")

    if elev is not None and elev > 800:
        notes.append(
            f"Высота {elev} м — учитывать ветровые нагрузки и сезонный сток."
        )
        reasoning.append(f"Отметка {elev} м > 800 м")

    if tmin is not None and tmin < -30:
        notes.append(
            f"Экстремальный минимум {tmin}°C — теплотехнический расчёт "
            f"ограждающих конструкций и цоколя обязателен."
        )
        reasoning.append(f"T_min = {tmin}°C < -30°C")

    if not notes:
        notes.append(
            "Климат и грунты благоприятные. Базовая рекомендация: "
            "мелкозаглубленный ленточный фундамент."
        )

    return notes, reasoning


# ---------- Отчёт ----------

def build_payload(lat, lon):
    errors = []

    address, e = get_address(lat, lon)
    if e: errors.append(e)
    elev, e = get_elevation(lat, lon)
    if e: errors.append(e)
    climate, e = get_climate(lat, lon)
    if e: errors.append(e)
    soil_raw, e = get_soil(lat, lon)
    if e: errors.append(e)

    climate_sum = summarize_climate(climate) if climate else {}
    soil = classify_soil(soil_raw)
    df = None
    if soil and climate_sum.get("freezing_index_mt"):
        df = frost_depth(soil["d0_coeff_m_per_sqrt_C_month"],
                         climate_sum["freezing_index_mt"])

    snow_zone, snow_load = snow_zone_kz(climate_sum.get("annual_snow_cm"))
    notes, reasoning = foundation_recommendations(
        elev, climate_sum, soil or {}, df
    )

    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "input": {"lat": lat, "lon": lon},
        "address": address,
        "elevation_m": elev,
        "climate": climate_sum,
        "soil": soil,
        "frost_depth_m": df,
        "snow_zone_kz": snow_zone,
        "snow_load_kpa_approx": snow_load,
        "recommendations": notes,
        "reasoning": reasoning,
        "data_errors": errors,
        "disclaimer": (
            "MVP v0.2. Расчётные значения предварительны. Финальные "
            "параметры фундамента — после инженерно-геологических "
            "изысканий на участке."
        ),
    }


def render_markdown(p):
    c = p.get("climate", {}) or {}
    s = p.get("soil") or {}
    lines = [
        "# Double · Site Report",
        "",
        f"**Сгенерировано:** {p['generated_at']}",
        f"**Координаты:** {p['input']['lat']}, {p['input']['lon']}",
        f"**Адрес:** {p.get('address') or '—'}",
        "",
        "## Рельеф",
        f"- Высота над уровнем моря: **{p.get('elevation_m')} м**",
        "",
        "## Климат (последние 365 дней)",
        f"- Минимальная температура: **{c.get('min_temp_c')} °C**",
        f"- Максимальная температура: **{c.get('max_temp_c')} °C**",
        f"- Сумма осадков за год: **{c.get('annual_precip_mm')} мм**",
        f"- Снег за год: **{c.get('annual_snow_cm')} см**",
        f"- Индекс промерзания M_t (СНиП): **{c.get('freezing_index_mt')} °C·мес**",
        "",
        "## Грунт (SoilGrids, 0–30 см)",
    ]
    if s:
        lines += [
            f"- Глина: **{s['clay_pct']} %**",
            f"- Песок: **{s['sand_pct']} %**",
            f"- Ил: **{s['silt_pct']} %**",
            f"- Тип: **{s['soil_type']}**",
            f"- Коэффициент d_0: **{s['d0_coeff_m_per_sqrt_C_month']} м/√(°C·мес)**",
        ]
    else:
        lines.append("- данные SoilGrids недоступны")
    lines += [
        "",
        "## Расчёт промерзания (СНиП 2.02.01-83)",
        f"- Нормативная глубина промерзания **d_f = {p.get('frost_depth_m')} м**",
        "",
        "## Снеговая нагрузка (приближённо, СП РК)",
        f"- Зона: **{p.get('snow_zone_kz') or '—'}**",
        f"- Расчётная снеговая нагрузка: **≈ {p.get('snow_load_kpa_approx') or '—'} кПа**",
        "",
        "## Рекомендации по фундаменту",
    ]
    for n in p.get("recommendations", []):
        lines.append(f"- {n}")
    lines += ["", "### Обоснование"]
    for r in p.get("reasoning", []):
        lines.append(f"- {r}")
    if p.get("data_errors"):
        lines += ["", "### Замечания по данным"]
        for e in p["data_errors"]:
            lines.append(f"- {e}")
    lines += ["", "---", f"*{p['disclaimer']}*", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Double · Pre-construction Site Intelligence (MVP v0.2)"
    )
    parser.add_argument("lat", type=float, help="Широта")
    parser.add_argument("lon", type=float, help="Долгота")
    parser.add_argument("--json", action="store_true",
                        help="Вывод в JSON вместо Markdown")
    parser.add_argument("--out", type=str, default=None,
                        help="Имя файла для сохранения")
    args = parser.parse_args()

    print(f"→ Анализ участка {args.lat}, {args.lon}...")
    payload = build_payload(args.lat, args.lon)

    if args.json:
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        ext = "json"
    else:
        body = render_markdown(payload)
        ext = "md"

    Path("reports").mkdir(exist_ok=True)
    fname = args.out or (
        f"reports/site_{datetime.datetime.now():%Y%m%d_%H%M%S}.{ext}"
    )
    Path(fname).write_text(body, encoding="utf-8")
    print("\n" + body)
    print(f"\n✓ Сохранено: {fname}")


if __name__ == "__main__":
    main()
