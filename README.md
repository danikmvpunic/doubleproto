# Double · Pre-construction Site Intelligence

**MVP v0.1** — по координатам участка собирает отчёт по грунту, климату и предварительные рекомендации по фундаменту за минуту вместо месяца у геолога.

## Зачем

Частный заказчик ИЖС в Казахстане платит геологу 80–200 тыс. ₸ и ждёт 2–4 недели отчёт по грунту, чтобы выбрать фундамент. До этого момента стройка стоит. Double сокращает этот цикл до одного дня.

## Что делает v0.1

- Принимает координаты (lat, lon).
- Тянет климат за последние 365 дней из Open-Meteo.
- Тянет высоту участка из Open-Meteo Elevation.
- Тянет адрес из OpenStreetMap Nominatim.
- Генерирует markdown-отчёт с предварительными рекомендациями по фундаменту.

## Запуск

    python3 double_site_report.py 51.1605 71.4704

Отчёт сохраняется в reports/site_YYYYMMDD_HHMMSS.md и печатается в консоль.

## Запуск без установки Python (Google Colab)

1. Открой colab.research.google.com → New notebook.
2. В первую ячейку вставь:

    !wget -q https://raw.githubusercontent.com/danikmvpunic/doubleproto/main/double_site_report.py
    !python double_site_report.py 51.1605 71.4704

3. Shift+Enter — увидишь живой отчёт.

## Roadmap

- [ ] Интеграция геологических карт.
- [ ] Расчёт несущей способности грунта.
- [ ] Web-интерфейс с картой выбора участка.
- [ ] Первый платящий ИЖС-заказчик — июль 2026.

## Контакты

Ермек Даниал · danik.real1205@gmail.com · https://linkedin.com/in/danikermek13
