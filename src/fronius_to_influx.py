import logging
import datetime
import json
from time import sleep
from typing import Any, Dict, List, Type

import pytz
from astral.location import Location
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from requests import get
from requests.exceptions import ConnectionError


class WrongFroniusData(Exception):
    pass


class SunIsDown(Exception):
    pass


class DataCollectionError(Exception):
    pass


class FroniusToInflux:
    BACKOFF_INTERVAL = 3
    IGNORE_SUN_DOWN = False

    def __init__(self, client: InfluxDBClient, bucket: str, location: Location, endpoints: List[str], tz: Any) -> None:
        self.client = client
        self.bucket = bucket
        self.location = location
        self.endpoints = endpoints
        self.tz = tz

        self.logger = logging.getLogger(self.__class__.__name__)
        self.data: Dict[Any, Any] = {}

    def get_float_or_zero(self, value: str) -> float:
        internal_data: Dict[Any, Any] = {}
        try:
            internal_data = self.data['Body']['Data']
        except KeyError:
            raise WrongFroniusData('Response structure is not healthy.')
        result = internal_data.get(value, {}).get('Value', 0)
        if result:
            return float(result)
        return 0.0

    def translate_response(self) -> List[Dict]:
        collection = self.data['Head']['RequestArguments']['DataCollection']
        timestamp = self.data['Head']['Timestamp']
        self.logger.debug(f"translate {collection}, {timestamp}: {self.data['Body']['Data']}")
        if collection == 'CommonInverterData':
            data = self.data['Body']['Data']

            device_status = {
                    'measurement': 'DeviceStatus',
                    'time': timestamp,
                    'fields': data['DeviceStatus']
                }

            inverter_data = {
                    'measurement': collection,
                    'time': timestamp,
                    'fields': {
                        'FAC': self.get_float_or_zero('FAC'),
                        'IAC': self.get_float_or_zero('IAC'),
                        'IDC': self.get_float_or_zero('IDC'),
                        'PAC': self.get_float_or_zero('PAC'),
                        'UAC': self.get_float_or_zero('UAC'),
                        'UDC': self.get_float_or_zero('UDC'),
                        'DAY_ENERGY': self.get_float_or_zero('DAY_ENERGY'),
                        'YEAR_ENERGY': self.get_float_or_zero('YEAR_ENERGY'),
                        'TOTAL_ENERGY': self.get_float_or_zero('TOTAL_ENERGY'),
                    }
                }

            # add additional fields for GEN24 Symo
            fields_strings = []
            if 'SAC' in data:
                fields_strings.append('SAC')
            if 'IDC_2' in data:
                fields_strings.extend(['IDC_2', 'UDC_2'])
            if 'IDC_3' in data:
                fields_strings.extend(['IDC_3', 'UDC_3'])
            if 'IDC_4' in data:
                fields_strings.extend(['IDC_4', 'UDC_4'])

            for field in fields_strings:
                inverter_data['fields'][field] = self.get_float_or_zero(field)

            return [device_status, inverter_data]
        elif collection == '3PInverterData':
            return [
                {
                    'measurement': collection,
                    'time': timestamp,
                    'fields': {
                        'IAC_L1': self.get_float_or_zero('IAC_L1'),
                        'IAC_L2': self.get_float_or_zero('IAC_L2'),
                        'IAC_L3': self.get_float_or_zero('IAC_L3'),
                        'UAC_L1': self.get_float_or_zero('UAC_L1'),
                        'UAC_L2': self.get_float_or_zero('UAC_L2'),
                        'UAC_L3': self.get_float_or_zero('UAC_L3'),
                    }
                }
            ]
        elif collection == 'MinMaxInverterData':
            return [
                {
                    'measurement': collection,
                    'time': timestamp,
                    'fields': {
                        'DAY_PMAX': self.get_float_or_zero('DAY_PMAX'),
                        'DAY_UACMAX': self.get_float_or_zero('DAY_UACMAX'),
                        'DAY_UDCMAX': self.get_float_or_zero('DAY_UDCMAX'),
                        'YEAR_PMAX': self.get_float_or_zero('YEAR_PMAX'),
                        'YEAR_UACMAX': self.get_float_or_zero('YEAR_UACMAX'),
                        'YEAR_UDCMAX': self.get_float_or_zero('YEAR_UDCMAX'),
                        'TOTAL_PMAX': self.get_float_or_zero('TOTAL_PMAX'),
                        'TOTAL_UACMAX': self.get_float_or_zero('TOTAL_UACMAX'),
                        'TOTAL_UDCMAX': self.get_float_or_zero('TOTAL_UDCMAX'),
                    }
                }
            ]
        else:
            raise DataCollectionError("Unknown data collection type.")


    def sun_is_shining(self) -> None:
        sun = self.location.sun()
        if not self.IGNORE_SUN_DOWN and not sun['sunrise'] < datetime.datetime.now(tz=self.tz) < sun['sunset']:
            raise SunIsDown
        return None

    def write_data_points(self, collected_data):
        write_api = self.client.write_api(write_options=SYNCHRONOUS)
        write_api.write(bucket=self.bucket, record=collected_data)
        self.logger.info(f'written data: {[d['measurement'] for d in collected_data]}')

    def run(self) -> None:
        self.logger.info("starting application")
        try:
            while True:
                try:
                    self.sun_is_shining()
                    collected_data = []
                    for url in self.endpoints:
                        response = get(url)
                        self.data = response.json()
                        collected_data.extend(self.translate_response())
                        sleep(self.BACKOFF_INTERVAL)
                    self.write_data_points(collected_data)
                    sleep(self.BACKOFF_INTERVAL)
                except SunIsDown:
                    self.logger.info("Waiting for sunrise")
                    sleep(60)
                    self.logger.info('Waited 60 seconds for sunrise')
                except ConnectionError:
                    self.logger.info("Waiting for connection...")
                    sleep(10)
                    self.logger.info('Waited 10 seconds for connection')
                except Exception as e:
                    self.logger.warning("Exception: {}".format(e), exc_info=True)
                    self.data = {}
                    sleep(10)
                    
        except KeyboardInterrupt:
            self.logger.info("Finishing. Goodbye!")
