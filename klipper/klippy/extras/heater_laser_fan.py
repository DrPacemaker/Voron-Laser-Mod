# Support fans that are enabled when a heater plus another output pin is on
#
# Copyright (C) 2022 Dr.Pacemaker
#
# This file may be distributed under the terms of the GNU GPLv3 license.
from . import fan
import logging

PIN_MIN_TIME = 0.100

class PrinterHeaterLaserFan:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.printer.load_object(config, 'heaters')
        self.printer.register_event_handler("klippy:ready", self.handle_ready)
        self.heater_names = config.getlist("heater", ("extruder",))
        self.heater_temp = config.getfloat("heater_temp", 50.0)
        self.heaters = []
        
        self.fan = fan.Fan(config, default_shutdown_speed=1.)
        self.fan_speed = config.getfloat("fan_speed", 1., minval=0., maxval=1.)
        self.last_speed = 0.

        self.laser_switch_config_name = config.get('laser_switch_config_name')
        self.laser_status = 0

    def handle_ready(self):
        pheaters = self.printer.lookup_object('heaters')
        self.heaters = [pheaters.lookup_heater(n) for n in self.heater_names]
        reactor = self.printer.get_reactor()
        reactor.register_timer(self.callback, reactor.monotonic()+PIN_MIN_TIME)
        
    def get_status(self, eventtime):
        return self.fan.get_status(eventtime)

    def set_laser_status(self, eventtime):
        laser_switch_pin = self.printer.lookup_object(self.laser_switch_config_name)
        if laser_switch_pin:
            pin_status = laser_switch_pin.get_status(eventtime)['value']
            logging.debug("Laser Pin Status: %s" %(pin_status))
            curtime = self.printer.get_reactor().monotonic()
            print_time = self.fan.get_mcu().estimated_print_time(curtime)
            if pin_status == 1.:
                self.laser_status = 1
                self.fan.set_speed(print_time + PIN_MIN_TIME, self.fan_speed)
            else:
                self.laser_status = 0
                self.fan.set_speed(print_time + PIN_MIN_TIME, 0)

    def callback(self, eventtime):
        self.set_laser_status(eventtime)
        speed = 0.
        for heater in self.heaters:
            current_temp, target_temp = heater.get_temp(eventtime)
            if target_temp or current_temp > self.heater_temp:
                speed = self.fan_speed
                
        if self.laser_status == 1:
            speed = self.fan_speed

        if speed != self.last_speed:
            self.last_speed = speed
            curtime = self.printer.get_reactor().monotonic()
            print_time = self.fan.get_mcu().estimated_print_time(curtime)
            self.fan.set_speed(print_time + PIN_MIN_TIME, speed)
        return eventtime + 1.

def load_config_prefix(config):
    return PrinterHeaterLaserFan(config)
