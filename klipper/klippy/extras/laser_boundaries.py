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

        x_min, x_max, y_min, y_max = self.get_boundaries(self.get_newest_file())
        gcmd.respond_info("File name: %s" % self.get_newest_file())
        gcmd.respond_info("Current Position: x=%.3f, y=%.3f, z=%.3f" % (x,y,z))
        gcmd.respond_info("Boubdaries: x_min=%.3f, x_max=%.3f, y_min=%.3f, y_max=%.3f" % (x_min, x_max, y_min, y_max))
        gcmd.respond_info("Max Pos: x_max=%.3f, y_max=%.3f" % (self.x_max_bed, self.y_max_bed))
    
        if x_min<0 or x_max>self.x_max_bed or y_min<0 or y_max>self.y_max_bed:
            raise gcmd.error("Boundaries exceed bed size")

        self._move([x_min,y_min,None,None], self.speed)
        self._move([x_max,y_min,None,None], self.speed)
        self._move([x_max,y_max,None,None], self.speed)
        self._move([x_min,y_max,None,None], self.speed)
        self._move([x_min,y_min,None,None], self.speed)
        self._log_config()

    def get_newest_file(self):
        path = ("%s/%s" % (self.sdcard_dirname, self.file_regex))
        files = glob.glob(os.path.expanduser(path))
        if files and len(files)>0:
            files.sort(key=os.path.getmtime, reverse=True)
            return  os.path.basename(files[0])
        else:
            raise self.gcmd.error("Unable to find any files: %s" %(path))

    def get_boundaries(self, filename):
        x_min=self.x_max_bed
        x_max=0.0
        y_min=self.y_max_bed
        y_max=0.0
        try:
            fname = os.path.join(self.sdcard_dirname, filename)
            with open(fname) as f:
                for index, line in enumerate(f):
                    
                    # find ligthburn boundary comment
                    result = re.search(r"(; Bounds: )(X)([0-9]{1,3}\.?[0-9]{0,3})( Y)([0-9]{1,3}\.?[0-9]{0,3})( to )(X)([0-9]{1,3}\.?[0-9]{0,3})( Y)([0-9]{1,3}\.?[0-9]{0,3})", line)
                    if result:
                        x_min = float(result.group(3))
                        y_min = float(result.group(5))
                        x_max = float(result.group(8))
                        y_max = float(result.group(10))
                        return x_min, x_max, y_min, y_max

                    # find cura boundary comment
                    result = re.search(r"(;MINX:)([0-9]{1,3}\.?[0-9]{0,3})", line)
                    if result:
                        x_min = float(result.group(2))
                    result = re.search(r"(;MAXX:)([0-9]{1,3}\.?[0-9]{0,3})", line)    
                    if result:
                        x_max = float(result.group(2))
                    result = re.search(r"(;MINY:)([0-9]{1,3}\.?[0-9]{0,3})", line)    
                    if result:
                        y_min = float(result.group(2))
                    result = re.search(r"(;MAXY:)([0-9]{1,3}\.?[0-9]{0,3})", line)    
                    if result:
                        y_max = float(result.group(2))
                    if x_min<self.x_max_bed and x_max>0 and y_min<self.y_max_bed and y_max>0:
                        return x_min, x_max, y_min, y_max
                
                # if no cura or lightburn boundary comments found: Do it the hard way
                for index, line in enumerate(f):
                    result = re.search(r"(G[0-1])(.*)(X)([0-9]{1,3}\.?[0-9]{0,3})( Y)([0-9]{1,3}\.?[0-9]{0,3})(.*)", line)
                    if result:
                        x = float(result.group(4))
                        y = float(result.group(6))
                        if (x<x_min):
                            x_min=x
                        if (x>x_max):
                            x_max=x
                        if (y<y_min):
                            y_min=y
                        if (y>y_max):
                            y_max=y
                    if x_min<self.x_max_bed and x_max>0 and y_min<self.y_max_bed and y_max>0:
                        return x_min, x_max, y_min, y_max       
        except:
            logging.exception("virtual_sdcard file open")
            raise self.gcmd.error("Unable to open file")
        
        return x_min, x_max, y_min, y_max

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
