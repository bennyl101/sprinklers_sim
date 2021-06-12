#Benny Lin
#DHT Sensor Libraries
import RPi.GPIO as GPIO
import board

import smbus
import time

import urllib.request
import codecs
import csv

import multiprocessing
import adafruit_dht
import sys

time_of_water = 0
water_flag = 0
local_time_offset = 0
local_lcd_flag = 0


#initialize DHT sensor
DHT_SENSOR = adafruit_dht.DHT11(board.D17)

###Credit to https://learn.adafruit.com/drive-a-16x2-lcd-directly-with-a-raspberry-pi for the LCD code tutorial

# Define some device parameters
I2C_ADDR  = 0x27 # I2C device address
LCD_WIDTH = 16   # Maximum characters per line

# Define some device constants
LCD_CHR = 1 # Mode - Sending data
LCD_CMD = 0 # Mode - Sending command

LCD_LINE_1 = 0x80 # LCD RAM address for the 1st line
LCD_LINE_2 = 0xC0 # LCD RAM address for the 2nd line
LCD_LINE_3 = 0x94 # LCD RAM address for the 3rd line
LCD_LINE_4 = 0xD4 # LCD RAM address for the 4th line

LCD_BACKLIGHT  = 0x08  # On

ENABLE = 0b00000100 # Enable bit

# Timing constants
E_PULSE = 0.0005
E_DELAY = 0.0005

#Open I2C interface
bus = smbus.SMBus(1) # Rev 2 Pi uses 1

def lcd_init():
  # Initialise display
  lcd_byte(0x33,LCD_CMD) # 110011 Initialise
  lcd_byte(0x32,LCD_CMD) # 110010 Initialise
  lcd_byte(0x06,LCD_CMD) # 000110 Cursor move direction
  lcd_byte(0x0C,LCD_CMD) # 001100 Display On,Cursor Off, Blink Off 
  lcd_byte(0x28,LCD_CMD) # 101000 Data length, number of lines, font size
  lcd_byte(0x01,LCD_CMD) # 000001 Clear display
  time.sleep(E_DELAY)

def lcd_byte(bits, mode):
  # Send byte to data pins

  bits_high = mode | (bits & 0xF0) | LCD_BACKLIGHT
  bits_low = mode | ((bits<<4) & 0xF0) | LCD_BACKLIGHT

  # High bits
  bus.write_byte(I2C_ADDR, bits_high)
  lcd_toggle_enable(bits_high)

  # Low bits
  bus.write_byte(I2C_ADDR, bits_low)
  lcd_toggle_enable(bits_low)

def lcd_toggle_enable(bits):
  # Toggle enable
  time.sleep(E_DELAY)
  bus.write_byte(I2C_ADDR, (bits | ENABLE))
  time.sleep(E_PULSE)
  bus.write_byte(I2C_ADDR,(bits & ~ENABLE))
  time.sleep(E_DELAY)

def lcd_string(message,line):
  # Send string to display
  message = message.ljust(LCD_WIDTH," ")
  lcd_byte(line, LCD_CMD)
  for i in range(LCD_WIDTH):
    lcd_byte(ord(message[i]),LCD_CHR)
    
        


def lcd_scroll(messages):
    global local_time_offset
    global local_lcd_flag
    if len(messages[0]) >= len(messages[1]):
        length = len(messages[0])
    else:
        length = len(messages[1])
    if (length - 15) <= 0:
        length = 1
    else:
        length = length - 15
    message1 = messages[0]
    message2 = messages[1]
    if(local_lcd_flag == 0):
        for i in range (0, length):
            lcd_text = message1[i:(i+16)]
            lcd_string(lcd_text,LCD_LINE_1)
            lcd_text2 = message2[i:(i+16)]
            lcd_string(lcd_text2, LCD_LINE_2)
            time.sleep(0.5)
    else:
        for i in range (0, length):
            lcd_text = message1[i:(i+16)]
            lcd_string(lcd_text,LCD_LINE_1)
            lcd_text2 = message2[i:(i+16)]
            lcd_string(lcd_text2, LCD_LINE_2)
            time.sleep(0.5)
            if(local_lcd_flag == 1):
                local_time_offset += 0.5


def cal_local_val(local_val, lock): #Locks sensors to output the local measurements for water calculation
    global local_time_offset
    global local_lcd_flag
    while True:
        current_hour = local_val[3]
        if(local_val[0] == 3):
            break;
        cnt = 0;
        hum_sum = 0;
        temp_sum = 0;
        while cnt < 60:
            try:
                humidity = DHT_SENSOR.humidity
                temperature = DHT_SENSOR.temperature
                if humidity is not None and temperature is not None:
                    hum_sum += humidity
                    temp_sum += temperature
                    temperature_str = "Min " +str(cnt)+ ": Current Local Temp = {0:0.01f}C".format(temperature)
                    humidity_str = "Current Local Humidity = {0:0.01f}%".format(humidity)
                    messages = [temperature_str, humidity_str]
                    local_lcd_flag = 1
                    if (local_val[0] == 0):
                        lock.acquire()
                        while((36 - local_time_offset) > 0):
                            lcd_scroll(messages)
                            time.sleep(1.90)
                        lock.release()
                    else:
                        time.sleep(55)
                    local_lcd_flag = 0
                    local_time_offset = 0
                    cnt += 1
                    print("Local Temp={0:0.01f}C Local Humidity={1:0.1f}%".format(temperature, humidity))
                else:
                    print("Sensor failure. Check wiring.");
            except RuntimeError as error:
                #Accounts for errors
                print(error.args[0])
        if(cnt != 0):
            avg_h = hum_sum/cnt
            avg_t = temp_sum/cnt
        lock.acquire();
        local_val[0] = 1
        local_val[1] = avg_h
        local_val[2] = avg_t
        local_val[3] += 1
        lock.release();

def get_online_values():
    ftp = urllib.request.urlopen("ftp://ftpcimis.water.ca.gov/pub2/hourly/hourly075.csv") #Grabs weather reports from the weather station for Irvine, CA
    csv_file = csv.reader(codecs.iterdecode(ftp, 'utf-8'))
    list_val = []
    for line in reversed(list(csv_file)):
        if(line[4] != "--" and line[14] != "--" and line[22] != "--"):
            eto = line[4]
            humid = line[14]
            temp = line[22]
            list_val.append(float(eto))
            list_val.append(float(humid))
            list_val.append(float(temp))
            break;
    return list_val

def change_message(local_val, lock):
    f = open("24hour_report.txt","w+")
    while True:
        try:
            if(local_val[0] == 1): #This updates the message on the LCD screen every hour
                online_vals = get_online_values();
                online_vals[2] = ((online_vals[2]) - 32) * 5/9
                eto_factor = local_val[1]/online_vals[1]
                local_eto = online_vals[0]/eto_factor
        
                print("Avg. Temp={0:0.01f}C Avg. Humidity={1:0.1f}%".format(local_val[2], local_val[1]))
        
                temperature_str = "Avg. Temp = {0:0.01f}C".format(local_val[2])
                humidity_str = "Avg. Humidity = {0:0.01f}%".format(local_val[1])
                eto_str = "Local ETO = {0:0.02f}".format(local_eto)
        
                CIMIS_temp_str = "CIMIS Temp = {0:0.01f}C".format(online_vals[2])
                CIMIS_humidity_str = "CIMIS Humidity = {0:0.01f}%".format(online_vals[1])
                CIMIS_eto_str = "CIMIS ET0 = {0:0.02f}".format(online_vals[0])
            
                messages = [" ", " "]
            
                messages[0] = "Hour " + str(local_val[3]) + ": " + temperature_str + " " + humidity_str + " " + eto_str
                messages[1] =  "        " + CIMIS_temp_str + " " + CIMIS_humidity_str + " " + CIMIS_eto_str
                f.write(messages[0])
                f.write("\r\n")
                f.write(messages[1])
                f.write("\r\n")
                water_status = [" ", " "]
            
                gal_water_day = (local_eto*1*200*.62)/0.75 #Formula converting online measurements to gallon based units
                gal_water_hour = gal_water_day/24
                gal_water_sec = gal_water_hour/(1020/3600)
            
                gal_water_saved = (((online_vals[0]*200*.62)/0.75) - gal_water_day)/24 
                water_status[0] = "Water will run for {0:0.01f} seconds...".format(gal_water_sec)
                gal_str = "Gallons to be consumed: {0:0.01f}".format(gal_water_hour) + "  Gallons saved: {0:0.001f}".format(gal_water_saved)
                
                f.write(water_status[0])
                f.write("\r\n")
                f.write(gal_str)
                f.write("\r\n")
                
                water_status[1] = gal_str
                global time_of_water
                global water_flag
                time_of_water = gal_water_sec
                lock.acquire()
                lcd_scroll(messages)
                lcd_scroll(water_status)
            
                while(time_of_water >= 0): #Loop that shows how long the sprinklers are running for on the LCD Screen
                    water_flag = 1
                    water_status[0] = "Water is on..."
                    water_status[1] = "Time left: {0:0.01f} secs".format(time_of_water)
                    lcd_string(water_status[0], LCD_LINE_1)
                    lcd_string(water_status[1], LCD_LINE_2)
                    time_of_water -= 0.5
                    time.sleep(0.5)
                
                water_status[0] = "Water is now off!"
                water_status[1] = " "
                water_flag = 0
                lcd_scroll(water_status)
                local_val[0] = 0
                lock.release()
            
                if(local_val[3] == 24):
                    lock.acquire()
                    local_val[0] = 3
                    lock.release()
                    break;
            time.sleep(1);
        except RuntimeError as error:
            print(error.args[0])
        except urllib.error.URLError as error:
            print(error.args[0])
    f.close()
    
def main():
    print("Program is running ...")
    with multiprocessing.Manager() as manager:
        lock = multiprocessing.Lock()
        messages = [" Starting Program..." , " Gathering Local Data..."]

        local_val = multiprocessing.Array('f', 4) #Array[0] = 0 when no new value
        local_val[0] = 0; #0 for no new value
        local_val[1] = 0; #contains the avg humidity of the current hour
        local_val[2] = 0; #contains the avg temp of the current hour
        local_val[3] = 0; #contains the hour
        
        #p1 = multiprocessing.Process(target=lcd_scroll, args=(messages, lock))
        p2 = multiprocessing.Process(target=change_message, args=(local_val, lock))
        p3 = multiprocessing.Process(target= cal_local_val, args=(local_val, lock))
        
       # p1.start()
        lcd_scroll(messages)
        p2.start()
        p3.start()
        
       # p1.join()
        p2.join()
        p3.join()
        print("Program is finished! Exiting...")
        messages[0] = "Program is finished! Exiting ..."
        messages[1] = "Turning off LCD Screen..."
        lcd_scroll(messages)
        lcd_byte(0x01, LCD_CMD)


if __name__ == '__main__':
    lcd_init()
    try:
        main()
    except KeyboardInterrupt:
        lcd_byte(0x01, LCD_CMD)
        pass
    finally:
        lcd_byte(0x01, LCD_CMD)
        