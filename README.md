# PSCS — Print Surface Control System

Расширение Klipper: во время печати следит за концевиком автоуровня (`[probe]`). Если зонд срабатывает вне процедур probing/homing — печать ставится на паузу. Обычно это значит, что деталь отлипла или подорвало угол.

## Установка в одну строку

```bash
cd ~ && git clone -b v2 https://github.com/Transistor427/PSCS.git && ln -sf ~/PSCS/print_surface_control_system.py ~/klipper/klippy/extras/print_surface_control_system.py
```

Затем добавьте в `printer.cfg` и сделайте `FIRMWARE_RESTART`:

```ini
[print_surface_control_system]
```

Нужны секции `[probe]` (или совместимый зонд) и `[pause_resume]`.
## Команды

| Команда | Описание |
|---|---|
| `SURFACE_CTRL_ENABLE` | Включить мониторинг |
| `SURFACE_CTRL_DISABLE` | Выключить мониторинг |
| `SURFACE_CTRL_STATUS` | Статус и состояние зонда |

По умолчанию мониторинг выключен — включайте через `SURFACE_CTRL_ENABLE` (или `enable_on_startup: True`). Пауза срабатывает только когда принтер реально печатает (`idle_timeout` = Printing). Во время homing / bed mesh / `PROBE` срабатывания игнорируются.

## Пример в макросах печати

```ini
[gcode_macro START_PRINT]
gcode:
    # ... прогрев, home, mesh ...
    SURFACE_CTRL_ENABLE

[gcode_macro END_PRINT]
gcode:
    SURFACE_CTRL_DISABLE
    # ... остальное завершение ...
```

## Опции конфигурации

```ini
[print_surface_control_system]
# Включить мониторинг при старте Klipper (по умолчанию False)
# enable_on_startup: True

# Интервал опроса зонда, сек (по умолчанию 0.05)
check_interval: 0.05

# Антидребезг между срабатываниями, сек (по умолчанию 0.5)
debounce_time: 0.5

# Пауза после probing/homing, чтобы не ловить ложные срабатывания
recovery_time: 2.0

# Ставить печать на паузу (по умолчанию True)
pause_on_trigger: True

# Сообщение в консоль / UI
# pause_message: Surface control: probe triggered during print...

# Дополнительный g-code при срабатывании (после PAUSE)
# trigger_gcode:
#     M117 Check bed adhesion!
#     RESPOND TYPE=error MSG="PSCS: part likely detached"
```

## Статус в Moonraker / UI

Объект `print_surface_control_system`:

- `enabled` — мониторинг включён
- `probe_triggered` — последнее известное состояние зонда
- `monitoring` — сейчас активно отслеживается печать (не в homing/probe и не в recovery)

## Как это работает

1. Периодически опрашивается состояние pin зонда через API probe.
2. Переход OPEN → TRIGGERED во время печати запускает паузу (как у filament sensor: `pause_resume` + `PAUSE`).
3. Homing и multi-probe временно подавляют реакцию, после них действует `recovery_time`.

## Лицензия

GNU GPLv3 — см. [LICENSE](LICENSE).
