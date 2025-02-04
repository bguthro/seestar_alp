import os

from device.config import Config

class EventCallback:
    """
    An event callback can be initialized from
    the current state of the device, or the result of get_device_state

    All future action should be based off of events, or inspecting the
    current state of the device object. All efforts should be made to
    avoid costly calls back out to the scope.

    This is meant to be a passive callback system that reacts to the events
    being reported by the scope.
    """
    def __init__(self, device, initial_state):
        return

    def fireOnEvents(self):
        return ['PiStatus']

    def eventFired(self, device, event_data):
        return



class BatteryWatch(EventCallback):
    """
    A callback class to watch battery levels, so we can do a safe shutdown
    if the battery gets too low
    """
    def __init__(self, device, initial_state):
        self.triggered = False
        self.logger = device.logger
        self.logger.info("BatteryWatch - init")

        # In case initial_state errors out
        if "pi_status" in initial_state:
            self.discharging = initial_state["pi_status"]["charger_status"] == "Discharging"
            self.charge_online = initial_state["pi_status"]["charge_online"]
            self.battery_capacity = initial_state["pi_status"]["battery_capacity"]
        else:
            self.discharging = False
            self.charge_online = True
            self.battery_capacity = 100

        return

    def fireOnEvents(self):
        return ['PiStatus']

    def eventFired(self, device, event_data):
        #self.logger.info("XXX BatteryWatch - eventFired")
        if 'charger_status' in event_data:
            self.discharging = event_data['charger_status'] == "Discharging"
        if 'charge_online' in event_data:
            self.charge_online = event_data['charge_online']
        if 'battery_capacity' in event_data:
            self.battery_capacity = event_data['battery_capacity']

        if self.discharging and \
           not self.charge_online and \
           self.battery_capacity <= Config.battery_low_limit and \
           not self.triggered:
            self.logger.info("BatteryWatch: Shutting down due to battery capacity lower limit reached")
            device.send_message_param_sync({"method":"pi_shutdown"})
            self.triggered = True
        #else:
        #    self.logger.info(f"BatteryWatch Ignoring event {event_data}")


class SensorTempWatch(EventCallback):
    """
    A callback class to watch the sensor temp, and take action if if changes more than a set value
    """
    def __init__(self, device, initial_state):
        self.triggered = False
        self.logger = device.logger
        self.logger.info("SensorTempWatch - init")
        self.max_change = Config.darks_temp_degrees

        if "pi_status" in initial_state:
            self.temp = initial_state["pi_status"]["temp"]
        else:
            self.temp = -1

    def fireOnEvents(self):
        return ['PiStatus']

    def eventFired(self, device, event_data):
        if 'temp' in event_data:
            curr_temp = event_data['temp']
            if self.temp < 0:
                self.temp = curr_temp
            if abs(self.temp - curr_temp) > self.max_change and not self.eventFired:
                self.logger.warn("SensorTempWatch: temp changed more than {self.max_change} degrees")
                if device.can_pause_scheduler() and Config.darks_temp_recalibrate:
                    device.pause_scheduler({})
                    device.try_dark_frame()
                    device.continue_scheduler({})
                    self.temp = curr_temp

                self.triggered = True
        #else:
        #    self.logger.info("SensorTempWatch Ignoring event {event_data}")

class UserScriptEvent(EventCallback):
    """
    A callback class to watch for GotoComplete events, that executes a script
    """
    def __init__(self, device, initial_state, user_script):
        self.logger = device.logger
        self.logger.info("UserScriptEvent - init")
        self.user_script = user_script

    def fireOnEvents(self):
        if "events" in self.user_script:
            return self.user_script["events"]
        else:
            return []

    def eventFired(self, device, event_data):
        self.logger.info("UserScriptGoto - event fired, execute {self.user_script}")
        os.system(self.user_script["execute"])
