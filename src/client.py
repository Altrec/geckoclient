#!/usr/bin/python3
"""
    Client program for geckolib. Publishs most relevant data
    on a configured broker.

    version 0.5
"""

# import configuration variables
from math import factorial
import config
import const

import logging
import logging.handlers

import asyncio
import signal

from mqtt import Mqtt
from paho.mqtt.client import MQTT_ERR_QUEUE_SIZE

from geckolib import GeckoConstants, GeckoSpaState


#from geckolib.spa import GeckoSpa

from mySpa import MySpa

### CONSTANTS ###
refresh_interval = 10

# keep running until terminated
stop_service = False

# handler for signals


def handler_stop_signals(signum, frame):
    global stop_service, logger
    logger.debug(f'Thread interrupted: {signum}')
    stop_service = True


# prepare logger
def prepare_logger():
    global logger

    root = logging.getLogger()

    root.setLevel(config.DEBUG_LEVEL)

    # create routating file handler
    # log file location is depanding on write access
    try:
        rfh = logging.handlers.RotatingFileHandler(
            config.LOGFILE, mode='a', maxBytes=100000, backupCount=config.BACKUP_COUNT, encoding=None, delay=False)
    except PermissionError:
        rfh = logging.handlers.RotatingFileHandler(
            "gecko_client.log", mode='a', maxBytes=100000, backupCount=config.BACKUP_COUNT, encoding=None, delay=False)
    rfh.setLevel(config.DEBUG_LEVEL)

    # create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # add formatter to rtf
    rfh.setFormatter(formatter)

    # separate level for geckolib
    geckolib = logging.getLogger("geckolib")
    geckolib.setLevel('WARN')

    # add rtf to logger
    root.addHandler(rfh)

######################
#
# Main routine connecting to the SPA and start looping
#
##########


async def main() -> None:

    # prepare MQTT
    mqtt = Mqtt(config.BROKER_ADDRESS, config.BROKER_PORT)

    result = await mqtt.connect_mqtt(config.BROKER_USERNAME, config.BROKER_PASSWORD)
    if result != 0:
        logger.error("Stopping - Can't connect to broker")
        exit(1)
    
    if config.SPA_IP_ADDRESS == "DHCP":
        ip = None
    else:
        ip = config.SPA_IP_ADDRESS

    async with MySpa(config.CLIENT_ID, spa_address=ip, spa_identifier=config.SPA_IDENTIFIER, spa_name=config.SPA_NAME) as spaman:

        await asyncio.sleep(GeckoConstants.ASYNCIO_SLEEP_TIMEOUT_FOR_YIELD)

        # Add the value chnage callback to publish on mqtt
        spaman.onValueChange(mqtt.publish_state)

        # Now wait for the facade to be ready
        await spaman.wait_for_facade()

        # subscripbe and add callbacks
        await mqtt.subscribe_and_message_callback_async(
            const.TOPIC_WATERHEAT + "/cmnd", spaman.set_temperature)
        await mqtt.subscribe_and_message_callback_async(
            const.TOPIC_LIGHTS + "/cmnd", spaman.set_lights)
        await mqtt.subscribe_and_message_callback_async(
            const.TOPIC_PUMPS + "/cmnd", spaman.set_pumps)
        await mqtt.subscribe_and_message_callback_async(
            const.TOPIC_BLOWERS + "/cmnd", spaman.set_blowers)
        await mqtt.subscribe_and_message_callback_async(
            const.TOPIC_WATERCARE + "/cmnd", spaman.set_watercare)            

        # get the facade
        facade = spaman.facade

        logger.info("GeckoClient starting...")
        logger.info("GC Version     : " + const.GECK_CLIENT_VERSION)
        logger.info("Spa Name       : " + spaman.facade.spa.descriptor.name)
        logger.info("Spa Version    : " + spaman.facade.spa.version)
        logger.info("Spa Revison    : " + spaman.facade.spa.revision)
        logger.info("Spa IP address : " + spaman.facade.spa.descriptor.ipaddress)

        reconnectButton = spaman.reconnect_button

        # Start loop until break signal received
        refresh_counter = refresh_interval
        while not stop_service:

            refresh_counter += 1
            # check each 10 seconds if mySpa is still connected
            if (refresh_counter > refresh_interval):

                refresh_counter = 1
                if spaman.spa_state is not GeckoSpaState.CONNECTED:
                    logger.info("Reconnecting...")
                    await reconnectButton.async_press()

            await asyncio.sleep(1)

        # final cleanup
        await facade.disconnect()
        mqtt.close()


#########
# main

if __name__ == "__main__":

    # prepare the logging
    prepare_logger()
    logger = logging.getLogger("geckoclient")

    # add signal listners
    signal.signal(signal.SIGINT, handler_stop_signals)
    signal.signal(signal.SIGTERM, handler_stop_signals)

    asyncio.run(main())
