# print_surface_control_system.py
# Klipper extension: pause print when the bed probe triggers mid-print
# (typical sign of part detachment or a lifted corner).
#
# Copyright (C) 2025 Vlad Trigorlov <427departament@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging

class SurfaceControl:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        # Config
        self.enabled = config.getboolean('enable_on_startup', False)
        self.check_interval = config.getfloat(
            'check_interval', 0.05, minval=0.02, maxval=1.0)
        self.debounce_time = config.getfloat(
            'debounce_time', 0.5, minval=0.0, maxval=10.0)
        self.recovery_time = config.getfloat(
            'recovery_time', 2.0, minval=0.0, maxval=60.0)
        self.pause_on_trigger = config.getboolean('pause_on_trigger', True)
        default_msg = (
            "Контроль поверхности печати: сработал зонд во время печати. "
            "Вероятно, деталь отлипла или подорвало край. Пауза."
        )
        self.pause_message = config.get('pause_message', default_msg)
        if self.pause_on_trigger:
            self.printer.load_object(config, 'pause_resume')
        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        self.trigger_gcode = None
        if (self.pause_on_trigger
                or config.get('trigger_gcode', None) is not None):
            self.trigger_gcode = gcode_macro.load_template(
                config, 'trigger_gcode', '')
        # Runtime state
        self.probe = None
        self.query_endstop = None
        self.last_state = False
        self.last_trigger_time = 0.
        self.suppress_until = 0.
        self.in_homing_or_probe = 0
        self.check_timer = None
        self.pausing = False
        # Commands
        self.gcode.register_command(
            'SURFACE_CTRL_ENABLE', self.cmd_SURFACE_CTRL_ENABLE,
            desc=self.cmd_SURFACE_CTRL_ENABLE_help)
        self.gcode.register_command(
            'SURFACE_CTRL_DISABLE', self.cmd_SURFACE_CTRL_DISABLE,
            desc=self.cmd_SURFACE_CTRL_DISABLE_help)
        self.gcode.register_command(
            'SURFACE_CTRL_STATUS', self.cmd_SURFACE_CTRL_STATUS,
            desc=self.cmd_SURFACE_CTRL_STATUS_help)
        # Events
        self.printer.register_event_handler(
            "klippy:connect", self._handle_connect)
        self.printer.register_event_handler(
            "klippy:ready", self._handle_ready)
        self.printer.register_event_handler(
            "klippy:disconnect", self._handle_disconnect)
        self.printer.register_event_handler(
            "homing:homing_move_begin", self._homing_begin)
        self.printer.register_event_handler(
            "homing:homing_move_end", self._homing_end)
        self.printer.register_event_handler(
            "probe:multi_probe_begin", self._probe_begin)
        self.printer.register_event_handler(
            "probe:multi_probe_end", self._probe_end)

    def _handle_connect(self):
        self.probe = self.printer.lookup_object('probe', None)
        if self.probe is None:
            raise self.printer.config_error(
                "[print_surface_control_system] requires a [probe] "
                "(or compatible) section")
        self.query_endstop = self._resolve_query_endstop(self.probe)
        if self.query_endstop is None:
            raise self.printer.config_error(
                "[print_surface_control_system] probe does not support "
                "endstop queries")

    def _resolve_query_endstop(self, probe):
        mcu_probe = getattr(probe, 'mcu_probe', None)
        if mcu_probe is not None:
            qe = getattr(mcu_probe, 'query_endstop', None)
            if qe is not None:
                return qe
        cmd_helper = getattr(probe, 'cmd_helper', None)
        if cmd_helper is not None:
            qe = getattr(cmd_helper, 'query_endstop', None)
            if qe is not None:
                return qe
        return None

    def _handle_ready(self):
        self.suppress_until = self.reactor.monotonic() + self.recovery_time
        self._sync_probe_state()
        self._update_timer()
        logging.info(
            "SurfaceControl: ready (enabled=%s, interval=%.3fs)",
            self.enabled, self.check_interval)

    def _handle_disconnect(self):
        self.enabled = False
        self._stop_timer()

    def _homing_begin(self, hmove):
        self.in_homing_or_probe += 1

    def _homing_end(self, hmove):
        self.in_homing_or_probe = max(0, self.in_homing_or_probe - 1)
        self._arm_recovery()

    def _probe_begin(self):
        self.in_homing_or_probe += 1

    def _probe_end(self):
        self.in_homing_or_probe = max(0, self.in_homing_or_probe - 1)
        self._arm_recovery()

    def _arm_recovery(self):
        self.suppress_until = self.reactor.monotonic() + self.recovery_time
        self._sync_probe_state()

    def _sync_probe_state(self):
        try:
            self.last_state = self._is_probe_triggered()
        except Exception:
            self.last_state = False

    def _is_probe_triggered(self):
        toolhead = self.printer.lookup_object('toolhead')
        print_time = toolhead.get_last_move_time()
        return bool(self.query_endstop(print_time))

    def _is_printing(self, eventtime):
        idle_timeout = self.printer.lookup_object('idle_timeout')
        return idle_timeout.get_status(eventtime)['state'] == 'Printing'

    def _update_timer(self):
        if self.enabled:
            self._start_timer()
        else:
            self._stop_timer()

    def _start_timer(self):
        if self.check_timer is not None:
            return
        self.check_timer = self.reactor.register_timer(
            self._check_probe, self.reactor.NOW)

    def _stop_timer(self):
        if self.check_timer is None:
            return
        self.reactor.unregister_timer(self.check_timer)
        self.check_timer = None

    def _check_probe(self, eventtime):
        if not self.enabled or self.query_endstop is None:
            return self.reactor.NEVER
        try:
            if (self.in_homing_or_probe
                    or eventtime < self.suppress_until
                    or self.pausing):
                self._sync_probe_state()
                return eventtime + self.check_interval
            triggered = self._is_probe_triggered()
            if triggered and not self.last_state:
                if eventtime - self.last_trigger_time >= self.debounce_time:
                    self.last_trigger_time = eventtime
                    if self._is_printing(eventtime):
                        self._handle_trigger(eventtime)
            self.last_state = triggered
        except Exception:
            logging.exception("SurfaceControl: error in probe check")
        return eventtime + self.check_interval

    def _handle_trigger(self, eventtime):
        self.pausing = True
        logging.warning("SurfaceControl: %s", self.pause_message)
        self.reactor.register_callback(self._execute_trigger)

    def _execute_trigger(self, eventtime):
        try:
            prefix = ""
            if self.pause_on_trigger:
                pause_resume = self.printer.lookup_object('pause_resume')
                pause_resume.send_pause_command()
                prefix = "PAUSE\n"
            self.gcode.respond_info(self.pause_message)
            script = prefix
            if self.trigger_gcode is not None:
                script += self.trigger_gcode.render()
            if script:
                self.gcode.run_script(script + "\nM400")
        except Exception:
            logging.exception("SurfaceControl: error while handling trigger")
        finally:
            self.pausing = False
            self.suppress_until = (
                self.reactor.monotonic() + self.recovery_time)
            self._sync_probe_state()

    def get_status(self, eventtime):
        return {
            'enabled': bool(self.enabled),
            'probe_triggered': bool(self.last_state),
            'monitoring': bool(
                self.enabled and not self.in_homing_or_probe
                and eventtime >= self.suppress_until),
        }

    cmd_SURFACE_CTRL_ENABLE_help = (
        "Включить контроль поверхности печати")

    def cmd_SURFACE_CTRL_ENABLE(self, gcmd):
        if self.enabled:
            gcmd.respond_info("Контроль поверхности печати уже включён")
            return
        self.enabled = True
        self._arm_recovery()
        self._update_timer()
        gcmd.respond_info(
            "Контроль поверхности печати включён — при срабатывании "
            "зонда во время печати будет пауза")
        logging.info("SurfaceControl: enabled")

    cmd_SURFACE_CTRL_DISABLE_help = "Выключить контроль поверхности печати"

    def cmd_SURFACE_CTRL_DISABLE(self, gcmd):
        if not self.enabled:
            gcmd.respond_info("Контроль поверхности печати отключён")
            return
        self.enabled = False
        self._update_timer()
        gcmd.respond_info("Контроль поверхности печати отключён")
        logging.info("SurfaceControl: disabled")

    cmd_SURFACE_CTRL_STATUS_help = "Статус контроля поверхности печати"

    def cmd_SURFACE_CTRL_STATUS(self, gcmd):
        eventtime = self.reactor.monotonic()
        status = self.get_status(eventtime)
        try:
            triggered = self._is_probe_triggered()
        except Exception:
            triggered = status['probe_triggered']
        gcmd.respond_info(
            "Контроль поверхности печати: включён=%s мониторинг=%s зонд=%s" % (
                "да" if status['enabled'] else "нет",
                "да" if status['monitoring'] else "нет",
                "СРАБОТАЛ" if triggered else "ОТКРЫТ"))


def load_config(config):
    return SurfaceControl(config)
