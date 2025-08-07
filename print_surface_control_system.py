# surface_control.py
# Klipper extension for automatic pausing on probe trigger
#
# Copyright (C) 2025 Vlad Trigorlov <427departament@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging
import time

class SurfaceControl:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.reactor = self.printer.get_reactor()
        # State variables
        self.enabled = False
        self.last_state = "OPEN"  # Start with OPEN state
        self.last_trigger_time = 0
        self.last_log_time = 0
        self.probe = None
        # Register commands
        self.gcode.register_command(
            'SURFACE_CTRL_ENABLE',
            self.cmd_SURFACE_CTRL_ENABLE,
            desc=self.cmd_SURFACE_CTRL_ENABLE_help
        )
        self.gcode.register_command(
            'SURFACE_CTRL_DISABLE',
            self.cmd_SURFACE_CTRL_DISABLE,
            desc=self.cmd_SURFACE_CTRL_DISABLE_help
        )
        # Register event handlers
        self.printer.register_event_handler("klippy:ready", self._handle_ready)
        self.printer.register_event_handler("klippy:disconnect", self._handle_disconnect)
    cmd_SURFACE_CTRL_ENABLE_help = "Enable automatic pausing on probe trigger"
    def cmd_SURFACE_CTRL_ENABLE(self, gcmd):
        if self.enabled:
            gcmd.respond_info("Surface control is already enabled")
            return
        # Get probe object
        if self.probe is None:
            try:
                self.probe = self.printer.lookup_object('probe')
            except:
                gcmd.respond_error("Probe not found. Is [probe] section configured?")
                return
        self.enabled = True
        self.last_state = "OPEN"
        self.last_trigger_time = 0
        gcmd.respond_info("Surface control ENABLED - printer will pause on probe trigger")
        logging.info("SurfaceControl: Enabled probe monitoring")
    cmd_SURFACE_CTRL_DISABLE_help = "Disable automatic pausing on probe trigger"
    def cmd_SURFACE_CTRL_DISABLE(self, gcmd):
        if not self.enabled:
            gcmd.respond_info("Surface control is already disabled")
            return
        self.enabled = False
        gcmd.respond_info("Surface control DISABLED")
        logging.info("SurfaceControl: Disabled probe monitoring")
    def _handle_ready(self):
        # Initialize probe reference when printer is ready
        try:
            self.probe = self.printer.lookup_object('probe')
            logging.info("SurfaceControl: Probe object initialized")
        except:
            logging.warning("SurfaceControl: Failed to find probe object")
    def _handle_disconnect(self):
        # Reset state on disconnect
        self.enabled = False
    def _get_probe_state(self, eventtime):
        """Get probe state using the existing probe object"""
        if self.probe is None:
            return "OPEN"
        try:
            # Get the toolhead for timing
            toolhead = self.printer.lookup_object('toolhead')
            print_time = toolhead.get_last_move_time()
            # Query probe state
            triggered = self.probe.mcu_probe.query_endstop(print_time)
            return "TRIGGERED" if triggered else "OPEN"
        except Exception as e:
            logging.error(f"SurfaceControl: Error querying probe: {str(e)}")
            return "ERROR"
    def check_probe_trigger(self, eventtime):
        if not self.enabled:
            return eventtime + 1.0
        try:
            # Diagnostic logging (once per second)
            if eventtime - self.last_log_time > 1.0:
                state = self._get_probe_state(eventtime)
                logging.info(f"SurfaceControl: Active (state={state}, enabled={self.enabled})")
                self.last_log_time = eventtime
            # Get current probe state
            current_state = self._get_probe_state(eventtime)
            # Detect state change from OPEN to TRIGGERED
            if current_state == "TRIGGERED" and self.last_state == "OPEN":
                # Anti-bounce protection
                if eventtime - self.last_trigger_time > 0.5:
                    self.last_trigger_time = eventtime
                    # Get print status
                    print_stats = self.printer.lookup_object('print_stats', None)
                    # Check if printing
                    if print_stats is not None and print_stats.get_status(eventtime)['state'] == 'printing':
                        # Create message
                        trigger_msg = "Probe triggered! Pausing print..."
                        # Log and notify
                        logging.info("SurfaceControl: " + trigger_msg)
                        # Send message to console and pause
                        self.gcode.run_script_from_command(
                            f'M118 "{trigger_msg}"\n'
                            'PAUSE'
                        )
                        logging.info("SurfaceControl: Sent PAUSE command")

            # Update last known state
            self.last_state = current_state
        except Exception as e:
            logging.error("SurfaceControl: Error in main loop: %s" % str(e))
        return eventtime + 0.05  # Check every 50ms

    def start(self):
        # Start periodic probe checking
        self.check_timer = self.reactor.register_timer(
            self.check_probe_trigger,
            self.reactor.NOW
        )
        logging.info("SurfaceControl: Monitoring started")

    def stop(self):
        # Stop periodic checking
        if hasattr(self, 'check_timer'):
            self.reactor.unregister_timer(self.check_timer)
            del self.check_timer
            logging.info("SurfaceControl: Monitoring stopped")

# Module initialization
def load_config(config):
    ext = SurfaceControl(config)
    config.get_printer().register_event_handler("klippy:connect", ext.start)
    config.get_printer().register_event_handler("klippy:disconnect", ext.stop)
    return ext