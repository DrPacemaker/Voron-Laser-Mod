import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from panels.menu import MenuPanel
from jinja2 import Environment
from ks_includes.KlippyGcodes import KlippyGcodes



def create_panel(*args):
    return LaserPanel(*args)

class LaserPanel(MenuPanel):
    distances = ['.1', '.5', '1', '5', '10', '25', '50']
    distance = distances[-4] 

    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.left_panel = None
        self.items = None
        self.h = 1
        self.items_left = []
        self.items_right = []
        self.buttons = {}
        self.grid = self._gtk.HomogeneousGrid()
        self.grid.set_hexpand(True)
        self.grid.set_vexpand(True)

    def createItemgroups(self):
        for config in self.items:
            for configname, attributes in config.items():
                for key in attributes:
                    if 'params' in key:
                        if 'orientation' in attributes[key]:
                            orientation_val = attributes[key]['orientation']
                            if orientation_val == 'left':
                                self.items_left.append(config)
                            elif orientation_val == 'right':
                                self.items_right.append(config)

    def initialize(self):
        logging.info("### Making LaserMenu")
        # small hack to get menu items from config
        self.items = self._config.get_menu_items("__main laser")
        self.createItemgroups()
        self.create_menu_items()
        grid = self._gtk.HomogeneousGrid()
        
        #left panel custom
        self._gtk.reset_temp_color()
        grid.attach(self.create_left_panel(), 0, 0, 1, 1)

        #right panel from config
        if self._screen.vertical_mode:
            self.labels['menu'] = self.arrangeMenuItems(self.items_right, 3, True)
            grid.attach(self.labels['menu'], 0, 1, 1, 1)
        else:
            self.labels['menu'] = self.arrangeMenuItems(self.items_right, 2, True)
            grid.attach(self.labels['menu'], 1, 0, 1, 1)

        self.grid = grid
        self.content.add(self.grid)
    
    def update_button_visibility(self):
        if self.left_panel is None:
            return
        for button in self.buttons:
            visible = self._config.get_config().getboolean(f"graph {self._screen.connected_printer}",
                                                           button, fallback=False)
            self.buttons[button]['visible'] = visible
            if visible:
                self.buttons[button]['name'].get_style_context().add_class(self.buttons[button]['class'])
            else:
                self.buttons[button]['name'].get_style_context().remove_class(self.buttons[button]['class'])

    def activate(self):
        self.update_button_visibility()
        self._screen.base_panel_show_all()

    def get_top_grid(self):
        top_grid = self._gtk.HomogeneousGrid()
        pos = 0
        if(len(self.items_left) > 0):
            for idx, config in enumerate(self.items_left):
                pos = idx+1
                for configname, attributes in config.items():
                    icon = attributes['icon']
                    params = attributes['params']
                    method = attributes['method']
                    class_name = f"graph_label_laser_{pos+1}"
                    dev_type = "sensor"
            
                    env = Environment(extensions=["jinja2.ext.i18n"], autoescape=True)
                    env.install_gettext_translations(self._config.get_lang())
                    j2_temp = env.from_string(attributes['name'])
                    parsed_name = j2_temp.render()

                    button = self._gtk.Button(icon, parsed_name.capitalize(), "max", 2, Gtk.PositionType.LEFT, 1)
                    button.connect("clicked", self.toggle_visibility, configname)
                    button.connect("clicked", self._screen._send_action, method, params)
                    button.set_alignment(.5, .5)
                
                    self.buttons[configname] = {
                        "class": class_name,
                        "name": button,
                    }
                    if pos % 2 == 0:    
                        top_grid.attach(button, Gtk.PositionType.RIGHT, pos-1, 1, 1)
                    else:
                        top_grid.attach(button, Gtk.PositionType.LEFT, pos, 1, 1)

                    top_grid.show_all()
        return top_grid
    
    def get_sub_grid(self):
        zbuttons = {
            'z+': self._gtk.Button("z-farther", "Z+", "color3"),
            'z-': self._gtk.Button("z-closer", "Z-", "color3"),
        }
        zbuttons['z+'].connect("clicked", self.move, "Z", "+")
        zbuttons['z-'].connect("clicked", self.move, "Z", "-")

        subgrid = self._gtk.HomogeneousGrid()
        subgrid.attach(zbuttons['z+'], Gtk.PositionType.LEFT, 0, 1, 1)
        subgrid.attach(zbuttons['z-'], Gtk.PositionType.RIGHT, 0, 1, 1)
        return subgrid

    def get_dist_grid(self):
        distgrid = Gtk.Grid()
        for j, i in enumerate(self.distances):
            self.labels[i] = self._gtk.Button(label=i)
            self.labels[i].set_direction(Gtk.TextDirection.LTR)
            self.labels[i].connect("clicked", self.change_distance, i)
            ctx = self.labels[i].get_style_context()
            if (self._screen.lang_ltr and j == 0) or (not self._screen.lang_ltr and j == len(self.distances) - 1):
                ctx.add_class("distbutton_top")
            elif (not self._screen.lang_ltr and j == 0) or (self._screen.lang_ltr and j == len(self.distances) - 1):
                ctx.add_class("distbutton_bottom")
            else:
                ctx.add_class("distbutton")
            if i == self.distance:
                ctx.add_class("distbutton_active")
            distgrid.attach(self.labels[i], j, 0, 1, 1)
        return distgrid

    def run_gcode_macro(self, widget, macro):
        params = ""
        for param in self.macros[macro]["params"]:
            value = self.macros[macro]["params"][param].get_text()
            if value:
                params += f'{param}={value} '
        self._screen._ws.klippy.gcode_script(f"{macro} {params}")

    def toggle_visibility(self, widget, button):
        self.buttons[button]['visible'] ^= True
        section = f"graph {self._screen.connected_printer}" 
        if section not in self._config.get_config().sections():
            self._config.get_config().add_section(section)
        self._config.set(section, f"{button}", f"{self.buttons[button]['visible']}")
        self._config.save_user_config_options()

        self.update_button_visibility()

    def create_left_panel(self):

        self.left_panel_grid = Gtk.Grid()
        self.left_panel_grid.get_style_context().add_class('heater-grid')
        self.left_panel_grid.set_vexpand(False)

        self.left_panel_grid.attach(self.get_top_grid(), 0, 1, 1, 1)
        self.left_panel_grid.attach(self.get_dist_grid(), 0, 2, 1, 1)
        self.left_panel_grid.attach(self.get_sub_grid(), 0, 3, 1, 1)

        scroll = self._gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.left_panel_grid)

        self.left_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.left_panel.add(scroll)

        return self.left_panel

    def change_distance(self, widget, distance):
        logging.info(f"### Distance {distance}")
        self.labels[f"{self.distance}"].get_style_context().remove_class("distbutton_active")
        self.labels[f"{distance}"].get_style_context().add_class("distbutton_active")
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

        self._screen._ws.klippy.gcode_script(f"{KlippyGcodes.MOVE_RELATIVE}\n{KlippyGcodes.MOVE} {axis}{dist} F{speed}")
        if self._printer.get_stat("gcode_move", "absolute_coordinates"):
            self._screen._ws.klippy.gcode_script("G90")
