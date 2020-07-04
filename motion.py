#!/usr/bin/env python

from __future__ import division
import time
import serial
import Adafruit_PCA9685
import time
import RPi.GPIO as GPIO
import datetime
import subprocess
import ConfigParser
import sys

LVL_NONE            = 70
LVL_CRITICAL        = 60
LVL_ERROR           = 50
LVL_WARNING         = 40
LVL_INFORMATION     = 30
LVL_DEBUGGING       = 20
LVL_DEBUG_DEEP      = 10
LVL_ALL             = 0

DEBUG = LVL_DEBUGGING

TRACE       = 0

LEFT  = 0
RIGHT = 1

STP = 0
RWD = -1
FWD = 1

IDLE    = 0
MOVE    = 1
EXIT    = 2
WAIT    = 3
CALIB   = 4
MANUAL  = 5
CONTROL = 6
INIT    = 7

OFFSETS = [0, 0]    # overwritten by ini file settings
MIDDLE = 400        # overwritten by ini file settings

# low level abstraction
# l, r: PWMs (direction, middle point and offset are corrected here)
def run(l, r):
    global pwmL, pwmR
    pwmL = MIDDLE + OFFSETS[LEFT] + l
    pwmR = MIDDLE - OFFSETS[RIGHT] - r
    pwm.set_pwm(LEFT, 0, pwmL)
    pwm.set_pwm(RIGHT, 0, pwmR)
    #print("PWMs: "+str(pwmL)+", "+str(pwmR))

def freerun():
    pwm.set_pwm(LEFT, 0, 0)
    pwm.set_pwm(RIGHT, 0, 0)

def resetEncoder():
    global leftEncoderZero, rightEncoderZero, encoderL, encoderR

    logEvent(LVL_INFORMATION, "Reset encoder")
    while(not readEncoder()):
        pass
    leftEncoderZero += encoderL
    rightEncoderZero += encoderR
    #encoderL = 0
    #encoderR = 0
    while(not readEncoder()):
        pass

def readIni():
    global OFFSETS

    logEvent(LVL_INFORMATION, "Read ini file")
    Config = ConfigParser.ConfigParser()
    Config.read("config.ini")
    OFFSETS[LEFT] = Config.getint('motor', 'offset_left')
    OFFSETS[RIGHT] = Config.getint('motor', 'offset_right')
    MIDDLE = Config.getint('motor', 'middle')
    #print("Offset Left: "+str(OFFSETS[LEFT]))

def initLog():
    global logfile
    if(DEBUG < LVL_NONE):
        logfile = open("robot.log","w+")
        logfile.write("Starting session\r\n")

def initTrace():
    global tracefile
    if(TRACE == 1):
        tracefile = open("trace.txt","w+")
        tracefile.write("timestamp;pwmL;pwmR;speedL;speedR;encoderL;encoderR\r\n")

def writeTrace():
    if (DEBUG <= LVL_DEBUGGING):
        print("pwmL: "+str(pwmL)+", pwmR: "+str(pwmR)+", SpeedL: "+str(speedL)+", SpeedR: "+str(speedR)+", encoderL: "+str(encoderL)+", encoderR: "+str(encoderR))
    if (TRACE == 1):
        tracefile.write(str(time.time())+";"+str(pwmL)+";"+str(pwmR)+";"+str(speedL)+";"+str(speedR)+";"+str(encoderL)+";"+str(encoderR)+"\r\n")

def logEvent(level, event):
    if (level >= LVL_INFORMATION):
        print event
        logfile.write(str(time.time()) + ";" + event + "\r\n")

def readCommand():
    global state

    c = raw_input("""Command (man, ctrl, cal, exit, )?: """)
    logEvent(LVL_INFORMATION, "Command by user: " + str(c))
    if(c == "man"):
        state = MANUAL
    elif(c == "ctrl"):
        state = CONTROL
    elif(c == "cal"):
        state = CALIB
    elif(c == "exit"):
        state = EXIT
    elif(c == "idle"):
        state = IDLE
    else:
        state = EXIT

def readEncoder():
    global encoderL, encoderR, speedL, speedR
    success = False
    line = ser.readline()   #read a '\n' terminated line (timeout set in open statement)
    data = line.split(';')
    if(data[0] == "MOV"):
        encoderL = int(data[1]) - leftEncoderZero
        encoderR = int(data[2]) - rightEncoderZero
        speedL = int(data[3])
        speedR = int(data[4])
        writeTrace()
        success = True
    if(data[0] == "DBG"):
        logEvent(LVL_DEBUG_DEEP, line)
    return success

def control(leftSpeedTarget, rightSpeedTarget, leftEncoderTarget, rightEncoderTarget, timeout):
    global directionL, directionR
    ser.flushInput()
    t = time.time()
    if(leftSpeedTarget > 0):
        directionL = FWD
    elif(leftSpeedTarget < 0):
        directionL = RWD
    else:
        directionL = STP
    if(rightSpeedTarget > 0):
        directionR = FWD
    elif(rightSpeedTarget < 0):
        directionR = RWD
    else:
        directionR = STP
    pl = 10*directionL
    pr = 10*directionR

    while((time.time() - t) < timeout):
        if(readEncoder() == True):
            if(directionL*speedL < int(leftSpeedTarget)):
                pl = pl + 1
            elif(directionL*speedL > int(leftSpeedTarget)+15):
                pl = pl - 1
            if(directionR*speedR < int(rightSpeedTarget)):
                pr = pr + 1
            elif(directionR*speedR > int(rightSpeedTarget)+15):
                pr = pr - 1
            if(encoderL >= leftEncoderTarget) :
                pl = 0
            if(encoderR >= rightEncoderTarget):
                pr = 0
            run(pl, pr)
            if((encoderL >= leftEncoderTarget) and (encoderR >= rightEncoderTarget)):
                break
    run(0, 0)

# Main script
###########################################
#
#### INIT #################################
# Initialise the PCA9685 using the default address (0x40).
pwm = Adafruit_PCA9685.PCA9685()
pwm.set_pwm_freq(60)
ser = serial.Serial('/dev/ttyS0', 115200, timeout=0.1)
state = INIT
lastState = IDLE
lasttime = time.time()
encoderL = 0
encoderR = 0
leftEncoderZero = 0
rightEncoderZero = 0
directionL = STP
directionR = STP
speedL = 0
speedR = 0
pwmL = 0
pwmR = 0
calibL = 0
calibR = 0
e_speedL_I = 0
e_speedR_I = 0
e_pos_I = 0
pl = 0 # power in PWM unit
pr = 0 # power in PWM unit

initLog()
logEvent(LVL_INFORMATION, "Starting session")
readIni()

#
#### MAIN #################################
#
try:
    while True:
        # Handle states
        if(state==INIT):
            readCommand()
        elif(state==IDLE):
            logEvent(LVL_INFORMATION, "Idle state")
            ser.flushInput()
            t = time.time()
            while((time.time() - t) < 2):
                readEncoder()
            resetEncoder()
            state = INIT
        elif(state==MANUAL):
            logEvent(LVL_INFORMATION, "Starting manual mode")
            pl = input("power left ?")
            pr = input("power right ?")
            duration = input("duration ?")
            resetEncoder()
            #print "pwm L: ", pl, ", pwm R: ", pr
            run(pl, pr)
            ser.flushInput()
            t = time.time()
            while((time.time() - t) < int(duration)):
                readEncoder()
            freerun()
            state = INIT
        elif(state==CONTROL):
            logEvent(LVL_INFORMATION, "Starting Control mode")
            sl  = input("speed left ?")
            sr  = input("speed right ?")
            pl = input("steps left ?")
            pr = input("steps right ?")
            t = input("timeout ?")
            resetEncoder()
            control(sl, sr, pl, pr, int(t))
            state = INIT
        elif(state==CALIB):
            logEvent(LVL_INFORMATION, "Starting calibration mode")
            ser.flushInput()
            for i in range(-15, 15):
                t = time.time()
                meanSpeedLeft  = 0
                meanSpeedRight = 0
                nb_values = 0
                run(i, i)
                while((time.time() - t) < 3):
                    if(readEncoder() == True):
                        meanSpeedLeft  += speedL
                        meanSpeedRight += speedR
                        nb_values += 1
                        logEvent(LVL_DEBUGGING, "CAL: Left [PWM="+str(i)+"; speed="+str(speedL)+"], Right [PWM="+str(i)+"; speed="+str(speedR)+"]")
                meanSpeedLeft = meanSpeedLeft/nb_values
                meanSpeedRight = meanSpeedRight/nb_values
                logEvent(LVL_INFORMATION, "CAL: Left [PWM="+str(i)+"; speed="+str(meanSpeedLeft)+"], Right [PWM="+str(i)+"; speed="+str(meanSpeedRight)+"]")
            state = EXIT
        elif(state==EXIT):
            #print "State EXIT"
            #state = IDLE
            freerun()
            ser.close()
            if(DEBUG < LVL_NONE):
                logfile.close()
            if(TRACE == 1):
                tracefile.close()
            break
        if(state != lastState):
            logEvent(LVL_INFORMATION, "State change to: " + str(state))
        lastState = state

# Cyclic statements
#        time.sleep(0.1)

except KeyboardInterrupt:
    logEvent(LVL_WARNING,"Exit by KeyboardInterrupt")
    #GPIO.cleanup()
    freerun()
    ser.close()
    if(DEBUG < LVL_NONE):
        logfile.close()
    if(TRACE == 1):
        tracefile.close()
