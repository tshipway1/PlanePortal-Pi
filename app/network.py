import time

import adafruit_connection_manager
import adafruit_requests
import board
from adafruit_esp32spi import adafruit_esp32spi
from digitalio import DigitalInOut


class NetworkManager:
    def __init__(self, config):
        self._config = config
        self._esp = None
        self._session = None
        self._build_radio()

    def _build_radio(self):
        esp32_cs = DigitalInOut(board.ESP_CS)
        esp32_ready = DigitalInOut(board.ESP_BUSY)
        esp32_reset = DigitalInOut(board.ESP_RESET)

        spi = board.SPI()
        self._esp = adafruit_esp32spi.ESP_SPIcontrol(
            spi, esp32_cs, esp32_ready, esp32_reset
        )
        pool = adafruit_connection_manager.get_radio_socketpool(self._esp)
        ssl_context = adafruit_connection_manager.get_radio_ssl_context(self._esp)
        self._session = adafruit_requests.Session(pool, ssl_context)

    @property
    def session(self):
        return self._session

    @property
    def is_connected(self):
        return bool(self._esp and self._esp.is_connected)

    @property
    def ip_address(self):
        if not self.is_connected:
            return "offline"
        return self._esp.pretty_ip(self._esp.ipv4_address)

    def connect(self, retries=4):
        if self.is_connected:
            return

        if self._esp.status == adafruit_esp32spi.WL_IDLE_STATUS and self._config.debug:
            print("ESP32 found and in idle mode")
            print("Firmware", self._esp.firmware_version)

        last_error = None
        for attempt in range(retries):
            try:
                self._esp.connect_AP(self._config.wifi_ssid, self._config.wifi_password)
                return
            except RuntimeError as error:
                last_error = error
                if self._config.debug:
                    print("WiFi connect attempt", attempt + 1, "failed:", error)
                time.sleep(1.0)

        raise RuntimeError("WiFi connection failed: {}".format(last_error))