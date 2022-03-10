import hassapi as hass
import serial
import asyncio
import queue
import mqttapi as mqtt

commands = queue.LifoQueue()


class Context:
    serial_port = None


class Rs232RelayMqtt(mqtt.Mqtt, hass.Hass):
    async def initialize(self):
        self.debug("Hello from AppDaemon serial " + str(Context.serial_port))

        command_topic = self.args["command_topic"]
        payloads = self.args["payloads"]

        for device_id in self.args["device_ids"]:
            c_topic = command_topic.replace("{{device-id}}", str(device_id))
            for payload in payloads.keys():
                self.debug("topic:" + c_topic + ", payload:" + str(payload))
                self.listen_event(
                    self.mqtt_callback,
                    event="MQTT_MESSAGE",
                    topic=c_topic,
                    payload=payload,
                    namespace="mqtt",
                )

        try:
            if Context.serial_port == None:
                self.debug("MQTT: -> open serial ... ")
                Context.serial_port = serial.Serial(
                    port="/dev/serial/by-id/usb-1a86_USB2.0-Ser_-if00-port0",  # /dev/ttyUSB0
                    baudrate=9600,  # 9600 bauds
                    bytesize=serial.EIGHTBITS,  # 7bits
                    parity=serial.PARITY_NONE,  # even parity
                    stopbits=serial.STOPBITS_ONE,  # 1 stop bit
                    xonxoff=False,  # no flow control
                    timeout=1,
                )

            self.debug("MQTT: -> serial is opened: " + Context.serial_port.name)
            await self.run_in(self.serial_read_loop, 2)
        except Exception as e:
            self.debug("MQTT: -> open serial ERROR " + str(e))

    # -------------------------------------------------------

    async def serial_read_loop(self, kwargs):
        # do some async stuff
        state_topic_prefix = self.args["state_topic_prefix"]
        while True:
            await asyncio.sleep(0.2)  # Time to yield in seconds. Use a shorter time if needed, i.e. 0.1.
            if Context.serial_port != None:
                if Context.serial_port.isOpen():
                    if not commands.empty():
                        command = commands.get()
                        self.debug("Sending command to realy board: " + command)
                        Context.serial_port.write(bytes(command, "ascii"))
                    try:
                        # read
                        doc = Context.serial_port.readline()
                        if len(doc) > 2:
                            received = str(doc.decode("ascii")).strip()
                            self.debug("Serial answer " + received)
                            if "Close" in received:
                                topic = received.replace("Close", state_topic_prefix)
                                self.mqtt_publish(topic, "off", retain=True)
                            if "Open" in received:
                                topic = received.replace("Open", state_topic_prefix)
                                self.mqtt_publish(topic, "on", retain=True)
                    except Exception as e:
                        self.debug("Error : try to parse an incomplete message")
                        pass
                #   Context.serial_port.flush()
                else:
                    self.debug("Error - serial closed ")

    # ----------------------------------------------------
    def terminate(self):
        self.debug("terminate enter")

        if Context.serial_port != None:
            Context.serial_port.close()
            self.debug("Error - serial closed ")

        self.debug("terminate exit")

    # ----------------------------------------------------
    def mqtt_callback(self, event, event_data, kwargs):
        self.debug("MQTT-mqtt_callback")

        topic = str(event_data.get("topic"))
        payload = str(event_data.get("payload")).lower()

        self.debug("MQTT: topic " + topic + ", payload " + payload)
        payloads = self.args["payloads"]
        command = payloads.get(payload)
        if command is not None:
            command = command.replace("{{device-id}}", topic.split("/")[1])
            commands.put(command)
        else:
            self.debug("Unknown command ")

    # ----------------------------------------------------
    def debug(self, text):
        if self.args["DEBUG"] == 1:
            self.log(text)
