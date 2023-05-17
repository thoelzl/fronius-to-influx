from fronius_to_influx import FroniusToInflux
from influxdb_client import InfluxDBClient
from astral import LocationInfo
from astral.location import Location

import logging
import pytz

# configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')

client = InfluxDBClient(url='http://localhost:8087', username='grafana', password='grafana', org='fronius')
bucket = 'grafana'
location = Location(LocationInfo('Poznan', 'Europe', 'Europe/Warsaw', 52.408078, 16.933618))
tz = pytz.timezone('Europe/Warsaw')
endpoints = [
    'http://172.30.1.11:5000/3PInverterData.json',
    'http://172.30.1.11:5000/CommonInverterData.json',
    'http://172.30.1.11:5000/MinMaxInverterData.json'
]

z = FroniusToInflux(client, bucket, location, endpoints, tz)
z.IGNORE_SUN_DOWN = True
z.run()
