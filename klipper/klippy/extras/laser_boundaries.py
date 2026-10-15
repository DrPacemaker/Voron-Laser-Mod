# Klipper plugin for laser object boundary detection & tracing.
#
# Copyright (C) 2022  Dr.Pacemaker
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import os
import io
import re
import glob

NUMBER = r"(-?\d*\.?\d+)"
# LightBurn: "; Bounds: X20 Y25 to X60 Y65" (negative for a centred job origin)
LIGHTBURN_BOUNDS_RE = re.compile(
    r"; Bounds: X%s Y%s to X%s Y%s" % (NUMBER, NUMBER, NUMBER, NUMBER))
# Cura: ";MINX:12.3" etc.
CURA_BOUNDS_RE = re.compile(r";(MINX|MAXX|MINY|MAXY):" + NUMBER)
MOVE_RE = re.compile(r"G0*([01])(?!\d)")
POSITIONING_RE = re.compile(r"G9([01])(?!\d)")
AXIS_RE = re.compile(r"([XY])\s*" + NUMBER)

def _gcode(line):
    # The command part of a G-code line: comment removed, upper-cased
    end = line.find(';')
    return (line if end < 0 else line[:end]).strip().upper()

def _coord(old, value, relative):
    # New position on one axis; a relative move from an unknown position
    # stays unknown
    if not relative:
        return float(value)
    return None if old is None else old + float(value)

class LaserBoundariesHelper:
    def __init__(self, config):
        self.gcmd = None
        self.state = None
        self.z_endstop = None
        self.z_homing = None
        self.x_homing = None
        self.y_homing = None 
        self.last_state = False
        self.config = config
        self.printer = config.get_printer()
        self.z_min = config.getfloat("z_min", 0)
        self.x_max_bed = None
        self.y_max_bed = None
        self.file_regex = config.get('filename_regex')
        sd = config.get('3d_objects_folder_path')
        self.sdcard_dirname = os.path.normpath(os.path.expanduser(sd))
        self.speed = config.getfloat('speed', 50.0, above=0.)
        self.printer.register_event_handler("homing:home_rails_end",
                                            self.handle_home_rails_end)
        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command('LASER_BOUNDARIES', self.cmd_LASER_BOUNDARIES,
                                    desc=self.cmd_LASER_BOUNDARIES_help)

    def handle_home_rails_end(self, homing_state, rails):
        # get z homing position
        for rail in rails:
            if rail.get_steppers()[0].is_active_axis('z'):
                # get homing settings from z rail
                self.z_homing = rail.position_endstop
            if rail.get_steppers()[0].is_active_axis('x'):
                self.x_max_bed = rail.get_range()[1]
            if rail.get_steppers()[0].is_active_axis('y'):
                self.y_max_bed = rail.get_range()[1]

    def _build_config(self):
        pass
    cmd_LASER_BOUNDARIES_help = ("Traces the boundaries of the newest 3d object in given path")
    
    def cmd_LASER_BOUNDARIES(self, gcmd): 
        self.toolhead = self.printer.lookup_object('toolhead')
        self.gcmd = gcmd       
        if self.z_homing is None:
            raise gcmd.error("Must home axes first")

        x, y, z, e = self.toolhead.get_position()
        if z < self.z_min:
            raise gcmd.error("Z level too low")

        filename = self.get_newest_file()
        (x_min, x_max, y_min, y_max), relative = self.get_boundaries(filename, x, y)
        gcmd.respond_info("File name: %s (%s coordinates)"
                          % (filename, "relative" if relative else "absolute"))
        gcmd.respond_info("Current Position: x=%.3f, y=%.3f, z=%.3f" % (x,y,z))
        gcmd.respond_info("Boundaries: x_min=%.3f, x_max=%.3f, y_min=%.3f, y_max=%.3f" % (x_min, x_max, y_min, y_max))
        gcmd.respond_info("Max Pos: x_max=%.3f, y_max=%.3f" % (self.x_max_bed, self.y_max_bed))
    
        if x_min<0 or x_max>self.x_max_bed or y_min<0 or y_max>self.y_max_bed:
            raise gcmd.error("Boundaries exceed bed size")

        self._move([x_min,y_min,None,None], self.speed)
        self._move([x_max,y_min,None,None], self.speed)
        self._move([x_max,y_max,None,None], self.speed)
        self._move([x_min,y_max,None,None], self.speed)
        self._move([x_min,y_min,None,None], self.speed)
        # Return to the start position, which a relative job uses as origin
        self._move([x,y,None,None], self.speed)
        self._log_config()

    def get_newest_file(self):
        path = ("%s/%s" % (self.sdcard_dirname, self.file_regex))
        files = glob.glob(os.path.expanduser(path))
        if files and len(files)>0:
            files.sort(key=os.path.getmtime, reverse=True)
            return  os.path.basename(files[0])
        else:
            raise self.gcmd.error("Unable to find any files: %s" %(path))

    def get_boundaries(self, filename, start_x, start_y):
        # Returns the job's bounds in bed coordinates, and whether it is a
        # relative job (G91 at the first move, e.g. LightBurn "Start From:
        # Current Position"), which starts at (start_x, start_y)
        fname = os.path.join(self.sdcard_dirname, filename)
        try:
            with open(fname) as f:
                bounds, relative = self._find_bounds(f, start_x, start_y)
        except IOError:
            logging.exception("laser_boundaries: unable to open %s" % (fname,))
            raise self.gcmd.error("Unable to open file")
        if bounds is None:
            raise self.gcmd.error("No cutting moves found in %s" % (filename,))
        return bounds, relative

    def _find_bounds(self, f, start_x, start_y):
        # LightBurn and Cura write boundary comments before the first move.
        # Without them, use the bounds of the G1 (cutting) moves; G0 travel,
        # such as LightBurn's final move to its finish position, is left out.
        # Axes are modal, so a line may set only X or only Y.
        relative = False
        job_relative = None  # positioning mode at the first move
        header = None
        cura = {}
        x = y = None
        bounds = None
        for line in f:
            code = _gcode(line)
            move = MOVE_RE.match(code)
            if not move:
                positioning = POSITIONING_RE.match(code)
                if positioning:
                    relative = positioning.group(1) == '1'
                elif job_relative is None:
                    result = LIGHTBURN_BOUNDS_RE.search(line)
                    if result:
                        x_min, y_min, x_max, y_max = map(float, result.groups())
                        header = x_min, x_max, y_min, y_max
                    result = CURA_BOUNDS_RE.search(line)
                    if result:
                        cura[result.group(1)] = float(result.group(2))
                continue
            if job_relative is None:
                job_relative = relative
                if header is not None or len(cura) == 4:
                    break
                if relative:
                    x, y = start_x, start_y
            new_x, new_y = x, y
            for axis, value in AXIS_RE.findall(code, move.end()):
                if axis == 'X':
                    new_x = _coord(x, value, relative)
                else:
                    new_y = _coord(y, value, relative)
            if move.group(1) == '1' and x is not None and y is not None:
                bounds = self._extend(bounds, x, y)
                bounds = self._extend(bounds, new_x, new_y)
            x, y = new_x, new_y
        if header is None and len(cura) == 4:
            header = cura['MINX'], cura['MAXX'], cura['MINY'], cura['MAXY']
        if header is not None:
            bounds = header
            if job_relative:
                x_min, x_max, y_min, y_max = header
                bounds = (start_x + x_min, start_x + x_max,
                          start_y + y_min, start_y + y_max)
        return bounds, bool(job_relative)

    @staticmethod
    def _extend(bounds, x, y):
        if bounds is None:
            return x, x, y, y
        x_min, x_max, y_min, y_max = bounds
        return min(x_min, x), max(x_max, x), min(y_min, y), max(y_max, y)

    def _move(self, coord, speed):
        logging.debug("Move")
        self.printer.lookup_object('toolhead').manual_move(coord, speed)

    def _log_config(self):
        logging.debug("Laser Bounds:"
                      " speed=%.3f,"
                      % (self.speed
                        ))

def load_config(config):
    return LaserBoundariesHelper(config)
