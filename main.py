import gc
import network
import urequests
import ujson
import utime
from machine import I2C, Pin

import config
from oled_display.oled_spi import OLED_2inch23
from environmentSensor.BME280 import BME280  # pressure, temp, hum
from environmentSensor.LTR390 import LTR390  # UV
from environmentSensor.SGP40 import SGP40
from environmentSensor.TSL2591 import TSL2591
from environmentSensor.voc_algorithm import VOCAlgorithm


def mean(lst):
    return sum(lst) / len(lst)


# --------------------------------------------------------------------------- #
# sensors
i2c = I2C(0, scl=Pin(21), sda=Pin(20), freq=100000)

print("==================================================")
print("TSL2591 Light I2C address:0X29")
print("LTR390 UV I2C address:0X53")
print("SGP40 VOC I2C address:0X59")
print("icm20948 9-DOF I2C address:0X68")
print("bme280 T&H I2C address:0X76")

devices = i2c.scan()
if len(devices) == 0:
    print("No i2c device !")
else:
    print('i2c devices found:', len(devices))
for device in devices:
    print("Hex address: ", hex(device))

bme280 = BME280()
bme280.get_calib_param()
light = TSL2591()
sgp = SGP40()
uv = LTR390()
voc = VOCAlgorithm()
voc.vocalgorithm_init()

# --------------------------------------------------------------------------- #
# screen
screen = OLED_2inch23()
screen.fill(screen.black)
screen.text(f'Conn to wifi...', 1, 12, screen.white)
screen.show()

# --------------------------------------------------------------------------- #
# wifi connection
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(config.ssid, config.password)

# wait for connection
max_wait = 10
while max_wait > 0:
    if wlan.status() < 0 or wlan.status() >= 3:
        break
    max_wait -= 1
    print("Waiting for connection...")
    utime.sleep(1)

# fail if no connection
if wlan.status() != 3:
    screen.fill(screen.black)
    screen.text('Blad polaczenia', 1, 12, screen.white)
    screen.text('z wybrana siecia', 1, 22, screen.white)
    screen.show()
    raise RuntimeError('Network connection failed')
else:
    print('Connected')
    status = wlan.ifconfig()
    print(f'IP = {status}')

# --------------------------------------------------------------------------- #
# end setup
screen.fill(screen.black)
screen.text(f'Setup done', 1, 12, screen.white)
screen.show()
utime.sleep(3)

# --------------------------------------------------------------------------- #
# wait for SGP to heat up
screen.fill(screen.black)
screen.text(f'Heating SGP40...', 1, 12, screen.white)
screen.show()
start_time = utime.time()
while utime.time() - start_time < 60:
    gas_raw = round(sgp.raw(), 2)
    gas = voc.vocalgorithm_process(gas_raw)

# --------------------------------------------------------------------------- #
# main loop
try:
    while True:
        pressure, temp, hum, lux, uvs, gas_raw = [], [], [], [], [], []

        for i in range(20):

            bme = bme280.readData()
            pressure.append(round(bme[0], 2))
            temp.append(round(bme[1], 2))
            hum.append(round(bme[2], 2))
            lux.append(round(light.Lux(), 2))
            uvs.append(round(uv.UVS(), 2))
            gas_raw.append(round(sgp.raw(), 2))

            screen.fill(screen.black)
            screen.text(f'Data gathering' + '.' * (i % 3), 1, 12, screen.white)
            screen.show()
            utime.sleep(4)

        pressure.sort()
        pressure = round(mean(pressure[2:-2]), 2)
        temp.sort()
        temp = round(mean(temp[2:-2]), 2)
        hum.sort()
        hum = round(mean(hum[2:-2]), 2)
        lux.sort()
        lux = round(mean(lux[2:-2]), 2)
        uvs.sort()
        uvs = round(mean(uvs[2:-2]), 2)
        gas_raw.sort()
        gas_raw = round(mean(gas_raw[2:-2]), 2)
        gas = voc.vocalgorithm_process(gas_raw)

        print(temp, hum, pressure, gas, uvs, lux)
        screen.fill(screen.black)
        screen.text('Data gathered', 1, 12, screen.white)
        screen.show()

        post_data = ujson.dumps({
            "id": 1,
            "temperature": temp,
            "humidity": hum,
            "pressure": pressure,
            "voc": gas,
            "uv": uvs,
            "light": lux
        })
        r = urequests.post(f"{config.URL_API}/api/reading", headers={'content-type': 'application/json'}, data=post_data)
        r.close()

        screen.fill(screen.black)
        screen.text('Data sent to API', 1, 12, screen.white)
        screen.show()

        utime.sleep(5)

        for i in range(48):
            if i % 2:
                screen.fill(screen.black)
                screen.text(f'Temp: {temp}', 1, 2, screen.white)
                screen.text(f'Hum: {hum}', 1, 12, screen.white)
                screen.text(f'Pres: {pressure}', 1, 22, screen.white)
                screen.show()
            else:
                screen.fill(screen.black)
                screen.text(f'VOC: {gas}', 1, 2, screen.white)
                screen.text(f'UV: {uvs}', 1, 12, screen.white)
                screen.text(f'Light: {lux}', 1, 22, screen.white)
                screen.show()

            utime.sleep(5)
except KeyboardInterrupt:
    pass
except OSError as e:
    print(e)
    screen.fill(screen.black)
    screen.text('OSERROR', 1, 12, screen.white)
    screen.show()

