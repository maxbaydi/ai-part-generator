# AI Part Generator для REAPER

AI Part Generator - это ReaScript, который генерирует и аранжирует MIDI-партии в выбранном диапазоне с помощью ИИ. Скрипт работает через локальный Python-мост (bridge) и набор профилей инструментов.

## Возможности
- Генерация одной партии по выбранному профилю, типу, стилю и настроению.
- Arrange: оркестровка по MIDI-скетчу (перенос материала на несколько инструментов).
- Compose: многодорожечная генерация с нуля (без исходного скетча).
- Prompt Enhancer: расширение текстового запроса с учетом контекста и инструментов.
- Профили инструментов с артикуляциями (CC/keyswitch/none), каналами и диапазонами.
- Контекст из выбранных MIDI-итемов и горизонтальный контекст вокруг выделения.
- Автоопределение тональности и опциональные изменения темпа/размера.

## Требования
- REAPER с поддержкой ReaScript.
- ReaImGui для полноценного интерфейса (без него будет упрощенный диалог).
- Python и зависимости моста: `fastapi`, `uvicorn`.
- Доступ к модели:
  - Local (LM Studio) через OpenAI-совместимый API.
  - OpenRouter (нужен API-ключ).
- HTTP-клиент: `curl` (если есть) или PowerShell на Windows.

## Установка
1) Скопируйте папки `ReaScript`, `Profiles` и `bridge` рядом друг с другом. Скрипт ищет профили по пути `../Profiles` относительно `ReaScript`.

Пример структуры:
```
AI Part Generator/
  Profiles/
    *.json
  ReaScript/
    AI Part Generator.lua
    ai_part_generator/
    vendor/
  bridge/
```

2) В REAPER: `Actions` -> `Show action list` -> `ReaScript: Load...` -> выберите `ReaScript/AI Part Generator.lua`.

3) ReaImGui (для полноценного UI):
   - Распространяется через ReaPack (см. репозиторий ReaImGui).
   - Если собираете из исходников, в README ReaImGui указаны шаги через Meson:
     ```
     meson setup build
     cd build
     ninja
     meson install --tags runtime
     ```

4) Установите зависимости Python-моста:
```
python -m pip install -r bridge/requirements.txt
```

5) Запустите мост (или дайте скрипту сделать это автоматически):
```
bridge/start.ps1    # Windows
bridge/start.sh     # macOS/Linux
```

Если Python не в PATH, в `start.ps1`/`start.sh` можно задать переменную `AI_PART_GENERATOR_PYTHON`.

## Быстрый старт (Generate)
1) В REAPER выделите диапазон времени (Time Selection).
2) Выберите MIDI-трек и запустите скрипт.
3) Вкладка `Generate`: выберите профиль, тип, стиль и настроение (или включите Free Mode).
4) По желанию отметьте `Use Selected Items as Context`, выделив нужные MIDI-итемы.
5) Нажмите `GENERATE PART`.

## Режимы работы
### Generate (одиночная партия)
Подходит для быстрого создания мелодии, баса, падов или ритма в активном треке (или в новом треке - переключатель `Insert To`).

### Arrange (по скетчу)
1) Выберите MIDI-итем со скетчем и нажмите `Set Selected Item as Source`.
2) Выделите целевые треки (минимум один, кроме трека-источника).
3) При необходимости вручную выберите профили инструментов в таблице.
4) Нажмите `ARRANGE (From Source)`.

### Compose (с нуля)
1) Выделите 2+ трека для генерации ансамбля.
2) Нажмите `COMPOSE (Scratch)`.
3) Скрипт сначала строит план, затем генерирует партии по очереди.

### Prompt Enhancer
Как использовать: введите запрос и нажмите `Enhance Prompt with AI`. Запрос будет расширен с учетом темпа, тональности и выбранных инструментов.

## Настройки API (вкладка Settings)
- Provider: `Local (LM Studio)` или `OpenRouter (Cloud)`.
- Base URL: по умолчанию `http://127.0.0.1:1234/v1` (local) или `https://openrouter.ai/api/v1`.
- Model Name: задайте модель, доступную в вашем провайдере.
- API Key: нужен только для OpenRouter.

## Профили инструментов
Профили находятся в `Profiles/*.json`. Они описывают инструмент, диапазоны, MIDI-канал и артикуляции. Скрипт:
- автоматически подбирает профиль по названию трека,
- сохраняет выбранный профиль в атрибут трека,
- использует артикуляции и контроллеры для корректной генерации.

Посмотрите примеры:
- `Profiles/Cello - CSS.json`
- `Profiles/Drums - GM.json`
- `Profiles/Bass - EZBass.json`

## Как действовать в разных ситуациях
- **Нужно быстро набросать идею:** включите Free Mode, введите короткий запрос, нажмите `GENERATE PART`.
- **Есть гармония/ритм на других дорожках:** выделите эти MIDI-итемы и оставьте `Use Selected Items as Context`.
- **Есть фортепианный скетч:** используйте `Arrange` и распределите материал по инструментам.
- **Хотите ансамбль "с нуля":** выберите 2+ трека и используйте `Compose`.
- **Нужен стабильный темп:** оставьте `Allow Tempo Changes` выключенным.
- **Нужны выразительные изменения темпа/размера:** включите `Allow Tempo/Time Sig Changes` и проверяйте результат.

## Частые проблемы
- **"No time selection set."** - задайте Time Selection.
- **"No profiles found in Profiles/ directory."** - проверьте структуру папок.
- **"ReaImGui not found..."** - установите ReaImGui или используйте упрощенный диалог.
- **"Bridge dependencies not found (fastapi/uvicorn)."** - выполните `python -m pip install -r bridge/requirements.txt`.
- **"Bridge server did not start..."** - запустите `bridge/start.ps1` или `bridge/start.sh` вручную.
- **"No arrange source set..."** - выберите MIDI-итем и нажмите `Set Selected Item as Source`.
