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
    distance = distances[-2] 

    def __init__(self, screen, title):
        super().__init__(screen, title)
        self.left_panel = None
        self.items = None
        self.h = 1
        self.items_left = []
        self.items_right = []
        self.devices = {}
        self.grid = self._gtk.HomogeneousGrid()
        self.grid.set_hexpand(True)
        self.grid.set_vexpand(True)

        self.buttons = {
            'z+': self._gtk.Button("z-farther", "Z+", "color3"),
            'z-': self._gtk.Button("z-closer", "Z-", "color3"),
        }
        self.buttons['z+'].connect("clicked", self.move, "Z", "+")
        self.buttons['z-'].connect("clicked", self.move, "Z", "-")


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
    
    def update_graph_visibility(self):
        if self.left_panel is None:
            return
        count = 0
        for device in self.devices:
            visible = self._config.get_config().getboolean(f"graph {self._screen.connected_printer}",
                                                           device, fallback=False)
            self.devices[device]['visible'] = visible
            if visible:
                count += 1
                self.devices[device]['name'].get_style_context().add_class(self.devices[device]['class'])
                self.devices[device]['name'].get_style_context().remove_class("graph_label_hidden")
            else:
                self.devices[device]['name'].get_style_context().add_class("graph_label_hidden")
                self.devices[device]['name'].get_style_context().remove_class(self.devices[device]['class'])

    def activate(self):
        self.update_graph_visibility()
        self._screen.base_panel_show_all()

    def add_left_menu(self):
        pos = 0
        if(len(self.items_left) > 0):
            for idx, config in enumerate(self.items_left):
                pos = idx
                for configname, attributes in config.items():
                    image = attributes['icon']
                    params = attributes['params']
                    method = attributes['method']
                    class_name = f"graph_label_sensor_{pos+1}"
                    dev_type = "sensor"
            
                    env = Environment(extensions=["jinja2.ext.i18n"], autoescape=True)
                    env.install_gettext_translations(self._config.get_lang())
                    j2_temp = env.from_string(attributes['name'])
                    parsed_name = j2_temp.render()

                    rgb = self._gtk.get_temp_color(dev_type)

                    name = self._gtk.Button(image, parsed_name.capitalize(), "max", 2, Gtk.PositionType.LEFT, 1)
                    name.connect("clicked", self.toggle_visibility, configname)
                    name.connect("clicked", self._screen._send_action, method, params)
                    name.set_alignment(.5, .5)
                
                    self.devices[configname] = {
                        "class": class_name,
                        "name": name,
                    }
                    self.labels['devices'].insert_row(pos+1)
                    self.labels['devices'].attach(name, 0, pos+1, 1, 1)
                    self.labels['devices'].show_all()
        
        subgrid = self._gtk.HomogeneousGrid()
        subgrid.attach(self.buttons['z+'], Gtk.PositionType.LEFT, 0, 1, 1)
        subgrid.attach(self.buttons['z-'], Gtk.PositionType.RIGHT, 0, 1, 1)

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
        
        self.labels['devices'].attach(distgrid, 0, pos+2, 1, 1)
        self.labels['devices'].attach(subgrid, 0, pos+3, 1, 1)
        
        return True

    def run_gcode_macro(self, widget, macro):
        params = ""
        for param in self.macros[macro]["params"]:
            value = self.macros[macro]["params"][param].get_text()
            if value:
                params += f'{param}={value} '
        self._screen._ws.klippy.gcode_script(f"{macro} {params}")

    def toggle_visibility(self, widget, device):
        self.devices[device]['visible'] ^= True
 
        section = f"graph {self._screen.connected_printer}"
        if section not in self._config.get_config().sections():
            self._config.get_config().add_section(section)
        self._config.set(section, f"{device}", f"{self.devices[device]['visible']}")
        self._config.save_user_config_options()

        self.update_graph_visibility()

    def create_left_panel(self):

        self.labels['devices'] = Gtk.Grid()
        self.labels['devices'].get_style_context().add_class('heater-grid')
        self.labels['devices'].set_vexpand(False)

        name = Gtk.Label("")

        self.labels['devices'].attach(name, 0, 0, 1, 1)

        scroll = self._gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.labels['devices'])

        self.left_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.left_panel.add(scroll)

        self.add_left_menu()
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
