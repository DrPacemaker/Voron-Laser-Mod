"""Laser panel for KlipperScreen (port of DrPacemaker/Voron-Laser-Mod to the post-2023 panel API).

Menu items come from [menu __main laser ...] in KlipperScreen.conf. Items whose params contain
"orientation": "left" go in the left column next to the Z jog controls; all others go in the right grid.
"""
import json
import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk
from ks_includes.KlippyGcodes import KlippyGcodes
from panels.menu import Panel as MenuPanel


class Panel(MenuPanel):
    distances = ['.1', '.5', '1', '5', '10', '25', '50']
    distance = distances[2]
    # Left-column buttons highlighted while the pin is non-zero; each pin may be an output_pin or a pwm_tool
    state_pins = {
        'laser_switch': "laser_switch_pin",
        'laser_test_mode': "laser_pwm_pin",
    }
    poll_interval_ms = 500
    poll_timer = None

    def __init__(self, screen, title, items=None):
        # Stop a poll left running from before a reinit
        self.deactivate()
        if items is None:
            items = screen._config.get_menu_items("__main laser")
        self.items_left, self.items_right = self.split_by_orientation(items)
        super().__init__(screen, title, items)
        logging.info("### Making LaserMenu")
        self.dist_buttons = {}
        self.state_objects = self.find_state_objects()

        grid = Gtk.Grid(row_homogeneous=True, column_homogeneous=True, hexpand=True, vexpand=True)
        grid.attach(self.create_left_panel(), 0, 0, 1, 1)
        if self._screen.vertical_mode:
            grid.attach(self.scroll, 0, 1, 1, 1)
        else:
            grid.attach(self.scroll, 1, 0, 1, 1)
        self.content.add(grid)

    @staticmethod
    def split_by_orientation(items):
        # "orientation" only picks the column; strip it so it isn't sent to Moonraker with the script
        left, right = [], []
        for entry in items:
            item = next(iter(entry.values()))
            try:
                params = json.loads(item['params'])
            except (TypeError, ValueError):
                params = None
            orientation = 'right'
            if isinstance(params, dict):
                orientation = params.pop('orientation', 'right')
                item['params'] = json.dumps(params)
            (left if orientation == 'left' else right).append(entry)
        return left, right

    def activate(self):
        # Re-evaluate enable: conditions (e.g. quad_gantry_level) every time the panel is shown
        self.j2_data = self._printer.get_printer_status_data()
        for child in self.scroll.get_children():
            self.scroll.remove(child)
        columns = 3 if self._screen.vertical_mode else 2
        self.scroll.add(self.arrangeMenuItems(self.items_right, columns, True))
        # KlipperScreen only subscribes to output_pin objects, so poll any pwm_tool pins while the panel is shown
        if self.poll_timer is None and self.unsubscribed_objects():
            logging.debug(f"Polling {self.unsubscribed_objects()} every {self.poll_interval_ms} ms")
            self.poll_timer = GLib.timeout_add(self.poll_interval_ms, self.poll_pins)

    def deactivate(self):
        if self.poll_timer is not None:
            logging.debug("Stopped polling laser pins")
            GLib.source_remove(self.poll_timer)
            self.poll_timer = None

    def find_state_objects(self):
        sections = self._printer.get_config_section_list()
        objects = {}
        for key, pin in self.state_pins.items():
            for prefix in ("output_pin", "pwm_tool"):
                if f"{prefix} {pin}" in sections:
                    objects[key] = f"{prefix} {pin}"
        return objects

    def unsubscribed_objects(self):
        return [obj for obj in self.state_objects.values() if not obj.startswith("output_pin ")]

    def poll_pins(self):
        objects = {obj: ["value"] for obj in self.unsubscribed_objects()}
        self._screen._ws.send_method("printer.objects.query", {"objects": objects}, self.on_pins_queried)
        return True

    def on_pins_queried(self, response, method, params):
        if 'result' in response:
            self.process_update("notify_status_update", response['result']['status'])

    def create_left_panel(self):
        top = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        enabled = [next(iter(entry)) for entry in self.items_left
                   if self.evaluate_enable(next(iter(entry.values()))['enable'])]
        for i, key in enumerate(enabled):
            top.attach(self.labels[key], i % 2, i // 2, 1, 1)

        zgrid = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        for col, (direction, icon) in enumerate((("+", "z-farther"), ("-", "z-closer"))):
            button = self._gtk.Button(icon, f"Z{direction}", "color3")
            button.connect("clicked", self.move, "Z", direction)
            zgrid.attach(button, col, 0, 1, 1)

        distgrid = Gtk.Grid()
        for j, i in enumerate(self.distances):
            button = self._gtk.Button(label=i)
            button.set_direction(Gtk.TextDirection.LTR)
            button.connect("clicked", self.change_distance, i)
            ctx = button.get_style_context()
            ctx.add_class("horizontal_togglebuttons")
            if i == self.distance:
                ctx.add_class("horizontal_togglebuttons_active")
            distgrid.attach(button, j, 0, 1, 1)
            self.dist_buttons[i] = button

        left = Gtk.Grid(row_homogeneous=True, column_homogeneous=True)
        left.attach(top, 0, 0, 1, 2)
        left.attach(zgrid, 0, 2, 1, 2)
        left.attach(distgrid, 0, 4, 1, 1)
        return left

    def process_update(self, action, data):
        if action != "notify_status_update":
            return
        for key, obj in self.state_objects.items():
            if key not in self.labels or obj not in data or 'value' not in data[obj]:
                continue
            ctx = self.labels[key].get_style_context()
            if data[obj]['value'] > 0:
                ctx.add_class("button_active")
            else:
                ctx.remove_class("button_active")

    def change_distance(self, widget, distance):
        logging.info(f"### Distance {distance}")
        self.dist_buttons[self.distance].get_style_context().remove_class("horizontal_togglebuttons_active")
        self.dist_buttons[distance].get_style_context().add_class("horizontal_togglebuttons_active")
        self.distance = distance

    def move(self, widget, axis, direction):
        if self._config.get_config()['main'].getboolean(f"invert_{axis.lower()}", False):
            direction = "-" if direction == "+" else "+"

        dist = f"{direction}{self.distance}"
        config_key = "move_speed_z" if axis == "Z" else "move_speed_xy"
        speed = None if self.ks_printer_cfg is None else self.ks_printer_cfg.getint(config_key, None)
        if speed is None:
            speed = self._config.get_config()['main'].getint(config_key, 20)
        speed = 60 * max(1, speed)
        script = f"{KlippyGcodes.MOVE_RELATIVE}\nG0 {axis}{dist} F{speed}"
        if self._printer.get_stat("gcode_move", "absolute_coordinates"):
            script += f"\n{KlippyGcodes.MOVE_ABSOLUTE}"
        self._screen._send_action(widget, "printer.gcode.script", {"script": script})
