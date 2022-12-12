# Voron 2.4 Laser Mod

In this project I share how I attached a laser to my Voron 2.4 r2. The main goal was to keep the setup time between 3d printing & lasering as small as possible in combination with a "safe" assembly. You need a printed mount platform which is attached to the stealthburner cover with two screws. If you have an enclosed voron you need to open the doors during bed mesh leveling & quad gantry leveling otherwise the laser will crash into them due to the extended X carriage size.

## Video

('<video width="50%" controls><source src="./Videos/LaserDemo.mp4" type="video/mp4"></video>')

## Used Hardware

- Voron
  - Voron 2.4 r2 350x350 with Octopus V1.1  
  - Voron Stealthburner
- Neje
  - Laser N30610
  - Laser switch / test board for Neje laser module
  - z axis adjuster (with screws provided by Neje)
- PCBs
  - EA60-12V TOBSUN step down converter 24v o 12v
  - DollaTek Electronic Switch (optional)
- Cables
- Screws
  - Laser mount: 2x40mm M3 screws
  - Air assist/laser cover: 2x5mm M3 screws
  - PCB mount: can't remember

## Used Software

- [Klipper](#klipper-config)
- Moonraker (won't be detailed)
- Fluidd (won't be detailed)
- [KlipperScreen (TBD)](#klipperscreen)
- [Lightburn](#gcode-generation)

## Wiring

Due to safety concerns I have decided to use a separate switch which controls the general power supply of the laser. You need to route the 4 wires through the cable chains to the print head.

[![]('<img src="./Images/Wiring/WiringLaserVoron1.png" width="50%">')](Images/Wiring/WiringLaserVoron1.png)[![]('<img src="./Images/Wiring/WiringLaserVoron2.png" width="30%">')](Images/Wiring/WiringLaserVoron2.png)

## Printed Parts

- [Laser Mount](STLs/)
- [Laser PCB Mounts](STLs/)
- [Air Assist (optional)](STLs/)

## Laser Mount Assembly

[![]('<img src="./Images/StealthburnerMount/LaserMountAssembly1.png" width="30%">')]("Images/StealthburnerMount/LaserMountAssembly1.png")
[![]('<img src="./Images/StealthburnerMount/LaserMountAssembly2.png" width="30%">')]("Images/StealthburnerMount/LaserMountAssembly2.png")

[![]('<img src="./Images/StealthburnerMount/LaserMountAssembly3.jpg" width="30%">')]("Images/StealthburnerMount/LaserMountAssembly3.jpg")
[![]('<img src="./Images/StealthburnerMount/LaserMountAssembly4.jpg" width="30%">')]("Images/StealthburnerMount/LaserMountAssembly4.jpg")

## Software Settings

### Klipper Config

Add the following configs & macros to printer.cfg

```cfg
#####################################################################
#   LASER Control
#####################################################################

[output_pin laser_switch_pin]
pin: PB4
pwm: false

[output_pin laser_pwm_pin]
pin: !PD15 
pwm: true
cycle_time: 0.001

[gcode_macro M03]
gcode:
 {% set S = params.S|default(0.0)|float %}
    SET_PIN PIN=laser_pwm_pin VALUE={S / 255.0}

[gcode_macro M04]
gcode:
 {% set S = params.S|default(0.0)|float %}
    SET_PIN PIN=laser_pwm_pin VALUE={S / 255.0}

[gcode_macro M05]
gcode:
    SET_PIN PIN=laser_pwm_pin VALUE=0

[gcode_macro LASER_TEST_ON]
description: Turn laser test mode on
gcode:
    SET_PIN PIN=laser_pwm_pin VALUE=0.01

[gcode_macro LASER_TEST_OFF]
description: Turn laser test mode off
gcode:
    SET_PIN PIN=laser_pwm_pin VALUE=0

[gcode_macro LASER_ON]
description: Turn laser on
gcode:
    SET_PIN PIN=laser_switch_pin VALUE=1

[gcode_macro LASER_OFF]
description: Turn laser off
gcode:
    SET_PIN PIN=laser_switch_pin VALUE=0
#####################################################################
```

### Gcode generation

I decided to use Lightburn to create the necessary gcode. Main focus is on the usage of the M gcode commands for the laser and absolute coordinates usage due to printer boundary concerns. Last mentioned can be changed to relative but was not jet tested by me. Be aware to deactivate Z axis in lightburn, otherwise it will set Z0 which will cause a crash into the honeycomb board/material you want to laser.

There are plenty more options to tweak the laser quality in lightburn which I have not yet tested. For first usage the settings below are sufficient.

[![]('<img src="./Images/LightburnSettings/Lightburn1.png" width="60%">')]("Images/LightburnSettings/Lightburn1.png")
[![]('<img src="./Images/LightburnSettings/Lightburn2.png" width="30%">')]("Images/LightburnSettings/Lightburn2.png")

Once gcode file is created I uploaded it via Fluidd to the printer.

### KlipperScreen

TBD: Description will follow later

Preview: I noticed that it is extremely difficult to determine with absolute coordinates where the laser is going to do its job, so I wrote a very basic python script which traces the outer boundary of the expected cut. For visualization purpose I manually activate the laser test mode during this.

## Potential area of Improvement

1. Development of a less space consuming laser mount to avoid crashes into the front doors and to maximize the usage of laser area.
2. Development of a safe laser mount without the need of screws
3. Direct deployment of gcodes to klipper from lightburn including the usage of the trace boundary feature built in lightburn
4. Porting the inline laser feature known from Marlin to Klipper to increase printing speed
  
