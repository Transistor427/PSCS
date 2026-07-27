# PSCS — Print Surface Control System

Расширение Klipper: во время печати следит за концевиком автоуровня (`[probe]`). Если зонд срабатывает вне процедур probing/homing — печать ставится на паузу. Обычно это значит, что деталь отлипла или подорвало угол.

## Установка в одну строку

```bash
cd ~ && git clone -b v2 https://github.com/Transistor427/PSCS.git && ln -sf ~/PSCS/print_surface_control_system.py ~/klipper/klippy/extras/print_surface_control_system.py && mkdir -p ~/printer_data/config/klipper-config && cp ~/PSCS/pscs.cfg ~/printer_data/config/klipper-config/pscs.cfg
```

Затем добавьте в `printer.cfg` и сделайте `FIRMWARE_RESTART`:

```ini
[include klipper-config/pscs.cfg]
```

Нужны секции `[probe]` (или совместимый зонд), `[pause_resume]` и `[save_variables]`.

## Команды

| Команда | Описание |
|---|---|
| `CHANGE_PSCS` | Переключить контроль поверхности печати |
| `SURFACE_CTRL_ENABLE` | Включить мониторинг |
| `SURFACE_CTRL_DISABLE` | Выключить мониторинг |
| `SURFACE_CTRL_STATUS` | Статус и состояние зонда |

По умолчанию мониторинг выключен. После перезагрузки или аварийной остановки `delayed_gcode` в `pscs.cfg` снова отключает функцию и сбрасывает сохранённую переменную. Пауза срабатывает только когда принтер реально печатает (`idle_timeout` = Printing). Во время homing / bed mesh / `PROBE` срабатывания игнорируются.

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
# pause_message: Контроль поверхности печати: сработал зонд...

# Дополнительный g-code при срабатывании (после PAUSE)
# trigger_gcode:
#     M117 Проверьте адгезию!
#     RESPOND TYPE=error MSG="PSCS: вероятно отрыв детали"
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
