import websocket
import json
import hashlib
import random
import threading
import hmac
import logging
import base64
import bcrypt

from enum import Enum, auto
from time import sleep
from types import SimpleNamespace

_LOGGER = logging.getLogger(__name__)

CONST_HASH_PBKDF2 = 'pbkdf2'
CONST_HASH_BCRYPT = 'bcrypt'
CONST_WPFLEX_DEVICETYPE='wattpilot_flex'

class LoadMode():
    """Wrapper Class to represent the Load Mode of the Wattpilot"""
    DEFAULT=3
    ECO=4
    NEXTTRIP=5


class Event(Enum):
    # Wattpilot events:
    WP_AUTH = auto(),
    WP_AUTH_ERROR = auto(),
    WP_AUTH_SUCCESS = auto(),
    WP_CLEAR_INVERTERS = auto(),
    WP_CONNECT = auto(),
    WP_DELTA_STATUS = auto(),
    WP_DISCONNECT = auto(),
    WP_FULL_STATUS = auto(),
    WP_FULL_STATUS_FINISHED = auto(),
    WP_HELLO = auto(),
    WP_INIT = auto(),
    WP_PROPERTY = auto(),
    WP_RESPONSE = auto(),
    WP_UPDATE_INVERTER = auto(),
    # WebSocketApp events:
    WS_CLOSE = auto(),
    WS_ERROR = auto(),
    WS_MESSAGE = auto(),
    WS_OPEN = auto(),

class Wattpilot(object):
    
    carValues = {}
    alwValues = {}
    astValues = {}
    lmoValues = {}
    ustValues = {}
    errValues = {}
    acsValues = {}

    lmoValues[3] = "Default"
    lmoValues[4] = "Eco"
    lmoValues[5] = "Next Trip"

    astValues[0] = "open"
    astValues[1] = "locked"
    astValues[2] = "auto"

    carValues[1] = "no car"
    carValues[2] = "charging"
    carValues[3] = "ready"
    carValues[4] = "complete"

    alwValues[0] = False
    alwValues[1] = True

    ustValues[0] = "Normal"
    ustValues[1] = "AutoUnlock"
    ustValues[2] = "AlwaysLock"

    errValues[0] = "Unknown Error"
    errValues[1] = "Idle"
    errValues[2] = "Charging"
    errValues[3] = "Wait Car"
    errValues[4] = "Complete"
    errValues[5] = "Error"

    acsValues[0] = "Open"
    acsValues[1] = "Wait"

    _authhashtype = CONST_HASH_PBKDF2
    _hashedpassword = b''

    @property
    def allProps(self):
        """Returns a dictionary with all properties"""
        return self._allProps

    @property
    def allPropsInitialized(self):
        """Returns true, if all properties have been initialized"""
        return self._allPropsInitialized

    @property
    def cableType(self):
        """Returns the Cable Type (Ampere) of the connected cable"""
        return self._cableType

    @property
    def frequency(self):
        """Returns the power frequency"""
        return self._frequency

    @property
    def phases(self):
        """returns the phases"""
        return self._phases
    
    @property
    def energyCounterSinceStart(self):
        """Returns used kwh since start of charging"""
        return self._energyCounterSinceStart
    
    @property
    def errorState(self):
        """Returns error State"""
        return self._errorState

    @property
    def cableLock(self):
        return self._cableLock
    
    @property
    def energyCounterTotal(self):
        return self._energyCounterTotal

    @property
    def serial(self):
        """Returns the serial number of Wattpilot Device (read only)"""
        return self._serial
    @serial.setter
    def serial(self,value):
        self._serial = value
        if (self._password is not None) & (self._serial is not None):
            self.__update_hashedpassword(self._password,self._serial)
           
    @property
    def name(self):
        """Returns the name of Wattpilot Device (read only)"""
        return self._name


    @property
    def hostname(self):
        """Returns the DNS Hostname of Wattpilot Device (read only)"""
        return self._hostname

    @property
    def friendlyName(self):
        """Returns the friendly name of Wattpilot Device (read only)"""
        return self._friendlyName

    @property
    def manufacturer(self):
        """Returns the Manufacturer of Wattpilot Device (read only)"""
        return self._manufacturer

    @property
    def devicetype(self):
        return self._devicetype

    @property
    def protocol(self):
        return self._protocol
    
    @property
    def secured(self):
        return self._secured

    @property
    def password(self):
        return self._password
    @password.setter
    def password(self,value):
        self._password = value
        if (self._password is not None) & (self._serial is not None):
            self.__update_hashedpassword(self._password,self._serial)


    @property
    def url(self):
        return self._url
    @url.setter
    def url(self,value):
        self._url = value

    @property
    def connected(self):
        return self._connected

    @property
    def voltage1(self):
        return self._voltage1

    @property
    def voltage2(self):
        return self._voltage2

    @property
    def voltage3(self):
        return self._voltage3

    @property
    def voltageN(self):
        return self._voltageN

    @property
    def amps1(self):
        return self._amps1

    @property
    def amps2(self):
        return self._amps2

    @property
    def amps3(self):
        return self._amps3

    @property
    def power1(self):
        return self._power1

    @property
    def power2(self):
        return self._power2

    @property
    def power3(self):
        return self._power3

    @property
    def powerN(self):
        return self._powerN

    @property
    def power(self):
        return self._power

    @property
    def version(self):
        return self._version

    @property
    def amp(self):
        return self._amp

    @property
    def AccessState(self):
        return self._AccessState

    @property
    def firmware(self):
        """Returns the Firmwareversion of Wattpilot Device (read only)"""
        return self._firmware

    @property
    def WifiSSID(self):
        """Returns the SSID of the Wifi network currently connected (read only)"""
        return self._WifiSSID

    @property
    def AllowCharging(self):
        return self._AllowCharging

    @property
    def mode(self):
        return self._mode

    @property
    def carConnected(self):
        return self._carConnected

    @property
    def cae(self):
        """Returns true if Cloud API Access is enabled (read only)"""
        return self._cae

    @property
    def cak(self):
        """Returns the API Key for Cloud API Access (read only)"""
        return self._cak


    def __str__(self):
        """Returns a String representation of the core Wattpilot attributes"""
        if self.connected:
            ret = "Wattpilot: " + str(self.name) + "\n"
            ret = ret +  "Serial: " + str(self.serial) + "\n"
            ret = ret +  "Connected: " + str(self.connected) + "\n"
            ret = ret + "Car Connected: " + str(self.carConnected) + "\n"
            ret = ret + "Charge Status " + str(self.AllowCharging) + "\n"
            ret = ret + "Mode: " + str(self.mode) + "\n"
            ret = ret + "Power: " + str(self.amp) + "\n"
            ret = ret +  "Charge: " + "%.2f" % self.power + "kW" + " ---- " + str(self.voltage1) + "V/" + str(self.voltage2) + "V/" + str(self.voltage3) + "V" + " -- "
            ret = ret + "%.2f" % self.amps1 + "A/" + "%.2f" % self.amps2 + "A/" + "%.2f" % self.amps3 + "A" + " -- "
            ret = ret + "%.2f" % self.power1 + "kW/" + "%.2f" % self.power2 + "kW/" + "%.2f" % self.power3 + "kW" + "\n"
        else:
            ret = "Not connected"

        return ret
    def connect(self):
        self._wst = threading.Thread(target=self._wsapp.run_forever)
        self._wst.daemon = True
        self._wst.start()
        self.__call_event_handler(Event.WP_CONNECT)
        _LOGGER.info("Wattpilot connected")

    def disconnect(self, auto_reconnect=False):
        self._wsapp.close()
        self._connected=False
        self._auto_reconnect = auto_reconnect
        self.__call_event_handler(Event.WP_DISCONNECT)
        _LOGGER.info("Wattpilot disconnected")

    # Wattpilot Event Handling

    # def __init_event_handler():
    #     eh = {}
    #     for event_type in list(Event):
    #         eh[event_type.value] = []
    #     return eh

    def add_event_handler(self,event_type,callback_fn):
        if event_type not in self._event_handler:
            self._event_handler[event_type] = []
        self._event_handler[event_type].append(callback_fn)

    def remove_event_handler(self,event_type,callback_fn):
        if event_type in self._event_handler and callback_fn in self._event_handler[event_type]:
            self._event_handler[event_type].remove(callback_fn)

    def __call_event_handler(self, event_type, *args):
        _LOGGER.debug(f"Calling event handler for event type '{event_type} ...")
        if event_type not in self._event_handler:
            return
        for callback_fn in self._event_handler[event_type]:
            event = {
                "type": event_type,
                "wp": self,
            }
            callback_fn(event,*args)


    def set_power(self,power):
        self.send_update("amp",power)

    def set_mode(self,mode):
        self.send_update("lmo",mode)


    def send_update(self,name,value):
        message = {}
        message["type"]="setValue"
        self.__requestid = self.__requestid+1
        message["requestId"]=self.__requestid
        message["key"]=name
        message["value"]=value
        if (self._secured is not None):
            if  (self._secured > 0):
                self.__send(message,True)
            else:
                self.__send(message)
        else:
            self.__send(message)

    def unpairInverter(self,InverterID):
        message = {}
        message["type"]="unpairInverter"
        self.__requestid = self.__requestid+1
        message["requestId"]=self.__requestid
        message["inverterId"]=InverterID
        if (self._secured is not None):
            if  (self._secured > 0):
                self.__send(message,True)
            else:
                self.__send(message)
        else:
            self.__send(message)

    def pairInverter(self,InverterID):
        message = {}
        message["type"]="pairInverter"
        self.__requestid = self.__requestid+1
        message["requestId"]=self.__requestid
        message["inverterId"]=InverterID
        if (self._secured is not None):
            if  (self._secured > 0):
                self.__send(message,True)
            else:
                self.__send(message)
        else:
            self.__send(message)

    def __update_property(self,name,value):

        self._allProps[name] = value
        if name=="acs":
            self._AccessState = Wattpilot.acsValues[value]

        if name=="cbl":
            self._cableType = value

        if name=="fhz":
            self._frequency = value

        if name=="pha":
            self._phases = value
        
        if name=="wh":
            self._energyCounterSinceStart = value

        if name=="err":
            self._errorState = Wattpilot.errValues[value]

        if name=="ust":
            self._cableLock = Wattpilot.ustValues[value]

        if name=="eto":
            self._energyCounterTotal = value

        if name=="cae":
            self._cae = value
        if name=="cak":
            self._cak = value
        if name=="lmo":
            self._mode = Wattpilot.lmoValues[value]
        if name=="car":
            self._carConnected = Wattpilot.carValues[value]
        if name=="alw":
            self._AllowCharging = Wattpilot.alwValues[value]
        if name=="nrg":
            self._voltage1=value[0]
            self._voltage2=value[1]
            self._voltage3=value[2]
            self._voltageN=value[3]
            self._amps1=value[4]
            self._amps2=value[5]
            self._amps3=value[6]
            self._power1=value[7]*0.001
            self._power2=value[8]*0.001
            self._power3=value[9]*0.001
            self._powerN=value[10]*0.001
            self._power=value[11]*0.001
        if name=="amp":
            self._amp = value
        if name=="version":
            self._version = value
        if name=="ast":
            self._AllowCharging = self._astValues[value]
        if name=="fwv":
            self._firmware = value
        if name=="wss":
            self._WifiSSID=value
        if name=="upd":
            if value=="0":
                self._updateAvailable = False
            else:
                self._updateAvailable = True
        self.__call_event_handler(Event.WP_PROPERTY, name, value)

    def __on_hello(self,message):
        _LOGGER.info("Connected to WattPilot Serial %s",message.serial)
        if hasattr(message,"hostname"):
            self._name=message.hostname
        self.serial = message.serial
        if hasattr(message,"hostname"):
            self._hostname=message.hostname
        if hasattr(message,"version"):
            self._version=message.version
        self._manufacturer=message.manufacturer
        self._devicetype=message.devicetype
        self._protocol=message.protocol
        if hasattr(message,"secured"):
            self._secured=message.secured
        self.__call_event_handler(Event.WP_HELLO, message)

    def __on_auth(self,wsapp,message):
        ran = random.randrange(10**80)
        self._token3 = "%064x" % ran
        self._token3 = self._token3[:32]
        if hasattr(message,'hash'):
            self._authhashtype = message.hash            
        elif self._devicetype == CONST_WPFLEX_DEVICETYPE:
            self._authhashtype = CONST_HASH_BCRYPT
        self.__update_hashedpassword()
        hash1 = hashlib.sha256((message.token1.encode()+self._hashedpassword)).hexdigest()
        hash = hashlib.sha256((self._token3 + message.token2+hash1).encode()).hexdigest()
        response = {}
        response["type"] = "auth"
        response["token3"] = self._token3
        response["hash"] = hash
        self.__send(response)
        self.__call_event_handler(Event.WP_AUTH, message)

    def __update_hashedpassword(self,password=None,serial=None):
        if password is None:
            password = self._password
        if serial is None:
            serial = self._serial        
        if (password is None) or (serial is None):
            _LOGGER.info("__update_hashedpassword: password or serial empty - keep current _hashedpassword")
            return
        _LOGGER.debug("__update_hashedpassword: generating password hash of type: %s", self._authhashtype)
        if self._authhashtype == CONST_HASH_PBKDF2:
            self._hashedpassword = base64.b64encode(hashlib.pbkdf2_hmac('sha512',password.encode(),self.serial.encode(),100000,256))[:32]
        elif self._authhashtype == CONST_HASH_BCRYPT:
            hashedpw = self.__bcrypt_hash_password(password, serial)
            self._hashedpassword = hashedpw.encode()
        else:
           _LOGGER.error("__update_hashedpassword: unknown authhashtype: %s", self._authhashtype)

    def __bcryptjs_base64_encode(self,b: bytes, length: int) -> str:
        #manual implementation of javascript bcrypt.encodeBase64 function
        #encodeBase64 from https://github.com/dcodeIO/bcrypt.js/blob/28e510389374f5736c447395443d4a6687325048/index.js#L1133C17-L1133C29
        #base64_encode from https://github.com/dcodeIO/bcrypt.js/blob/28e510389374f5736c447395443d4a6687325048/index.js#L427
        #BASE64_CODE from: https://github.com/dcodeIO/bcrypt.js/blob/28e510389374f5736c447395443d4a6687325048/index.js#L402C1-L403C80
        BASE64_CODE = list("./ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")        
        off = 0
        rs = []
        
        if length <= 0 or length > len(b):
            raise ValueError(f"Illegal len: {length}")
            
        while off < length:
            c1 = b[off] & 0xff
            off += 1
            rs.append(BASE64_CODE[(c1 >> 2) & 0x3f])
            c1 = (c1 & 0x03) << 4
            if off >= length:
                rs.append(BASE64_CODE[c1 & 0x3f])
                break

            c2 = b[off] & 0xff
            off += 1
            c1 |= (c2 >> 4) & 0x0f
            rs.append(BASE64_CODE[c1 & 0x3f])
            c1 = (c2 & 0x0f) << 2
            if off >= length:
                rs.append(BASE64_CODE[c1 & 0x3f])
                break

            c2 = b[off] & 0xff
            off += 1
            c1 |= (c2 >> 6) & 0x03
            rs.append(BASE64_CODE[c1 & 0x3f])
            rs.append(BASE64_CODE[c2 & 0x3f])

        return "".join(rs)

    def __bcryptjs_encodeBase64(self,s: str, length: int) -> str:
        #helper wrapper function for __bcryptjs_base64_encode
        #ensures python & java encoding is handled equally
        if s.isdigit(): #numeric only serial
            vals = [ord(ch) - ord('0') for ch in s]
            b = bytes([0] * (length - len(vals)) + vals)
        else: #not sure about serials in future - fallback
            _LOGGER.error("__bcryptjs_encodeBase64: check serial string - should be digits only: %s", s)
            raise ValueError(f"Check serial string - should be digits only: %s", s)
        return self.__bcryptjs_base64_encode(b,length)
     
    def __bcrypt_hash_password(self,password,serial,iterations=8) -> str:
        #hash bassword bcrypt / wattpilot flex compatible
        password_hash_sha256 = hashlib.sha256(password.encode('utf-8')).hexdigest()
        serial_b64 = self.__bcryptjs_encodeBase64(serial, 16)
        salt = []
        salt.append("$2a$")
        if (iterations < 10):
            salt.append("0")
        salt.append(str(iterations))
        salt.append("$")
        salt.append(serial_b64)
        salt=''.join(salt)
        bsalt = salt.encode("utf-8")
        bpassword = password_hash_sha256.encode('utf-8')
        pwhash = bcrypt.hashpw(bpassword, bsalt)
        salt_length = len(salt)
        pwhash_sub = pwhash[salt_length:].decode('ascii')
        return pwhash_sub

    def __send(self,message,secure=False):
        # If the  connection to wattpilot is over a unsecure channel (http) all send messages are wrapped in
        # a "securedMsg" Message which contains the original messageobject and a sha256 HMAC Hashed created
        # using the password
        if secure:
            messageid=message["requestId"]
            payload=json.dumps(message)
            h = hmac.new(bytearray(self._hashedpassword), bytearray(payload.encode()), hashlib.sha256 )
            message={}
            message["type"]="securedMsg"
            message["data"]=payload
            message["requestId"]=str(messageid)+"sm"
            message["hmac"]=h.hexdigest()

        _LOGGER.debug("Message send: %s",json.dumps(message)  )
        self._wsapp.send(json.dumps(message))

    def __on_AuthSuccess(self,message):
        self._connected = True
        self.__call_event_handler(Event.WP_AUTH_SUCCESS, message)
        _LOGGER.info("Authentication successful")

    def __on_FullStatus(self,message):
        props = message.status.__dict__
        for key in props:
            self.__update_property(key,props[key])
        self.__call_event_handler(Event.WP_FULL_STATUS, message)
        self._allPropsInitialized = not message.partial
        if message.partial == False:
            self.__call_event_handler(Event.WP_FULL_STATUS_FINISHED, message)

    def __on_AuthError(self,message):
        if message.message=="Wrong password":
            self._wsapp.close()
            _LOGGER.error("Authentication failed: %s", message.message)
        self.__call_event_handler(Event.WP_AUTH_ERROR, message)

    def __on_DeltaStatus(self,message):
        props = message.status.__dict__
        for key in props:
            self.__update_property(key,props[key])
        self.__call_event_handler(Event.WP_DELTA_STATUS, message)

    def __on_clearInverters(self,message):
        self.__call_event_handler(Event.WP_CLEAR_INVERTERS, message)

    def __on_updateInverter(self,message):
        self.__call_event_handler(Event.WP_UPDATE_INVERTER, message)

    def __on_response(self,message):
        if message.success:
            if hasattr(message,"status"):
                props = message.status.__dict__
                for key in props:
                    self.__update_property(key,props[key])
        else:
            _LOGGER.error("Error Sending Request %s. Message: %s" ,message.requestId,message.message)
        self.__call_event_handler(Event.WP_RESPONSE, message)

    def __on_open(self,wsapp):
        self.__call_event_handler(Event.WS_OPEN, wsapp)

    def __on_error(self,wsapp,err):
        self.__call_event_handler(Event.WS_ERROR, wsapp, err)
        _LOGGER.error(f"Error received from WebSocketApp: {err}")

    def __on_close(self,wsapp,code,msg):
        self._connected=False
        self.__call_event_handler(Event.WS_CLOSE, wsapp, code, msg)
        if (self._auto_reconnect):
            sleep(self._reconnect_interval)
            self._wsapp.run_forever()

    def __on_message(self, wsapp, message):
        ## called whenever a message through websocket is received
        _LOGGER.debug("Message received: %s", message)
        msg=json.loads(message, object_hook=lambda d: SimpleNamespace(**d))
        self.__call_event_handler(Event.WS_MESSAGE, message)
        if (msg.type == 'hello'):  # Hello Message -> Received upon connection before auth
            self.__on_hello(msg)
        if (msg.type == 'authRequired'): # Auth Required -> Received after hello 
            self.__on_auth(wsapp,msg)
        if (msg.type == 'response'): # Response Message -> Received after sending a update and contains result of update
            self.__on_response(msg)
        if (msg.type == 'authSuccess'): # Auth Success -> Received after sending correct authentication message
            self.__on_AuthSuccess(msg)
        if (msg.type == 'authError'): # Auth Error -> Received after sending incorrect authentication message (e.g. wrong password)
            self.__on_AuthError(msg)
        if (msg.type == 'fullStatus'): # Full Status -> Received after successful connection. Contains all properties of Wattpilot
            self.__on_FullStatus(msg)
        if (msg.type == 'deltaStatus'): # Delta Status -> Whenever a property changes a Delta Status is send
            self.__on_DeltaStatus(msg)
        if (msg.type == 'clearInverters'): # Unknown
            self.__on_clearInverters(msg)
        if (msg.type == 'updateInverter'): # Contains information of connected Photovoltaik inverter / powermeter
            self.__on_updateInverter(msg)

    def __init__(self, ip ,password,serial=None,cloud=False):
        self._auto_reconnect = True
        self._reconnect_interval = 30
        self._websocket_default_timeout = 10
        self.__requestid = 0
        self._name = None
        self._hostname = None
        self._friendlyName = None
        self._manufacturer = None
        self._devicetype = None
        self._protocol = None
        self._secured = None
        self._serial = None
        self._password = None

        self.password = password

        if(cloud):
            self._url= "wss://app.wattpilot.io/app/" + serial + "?version=1.2.9"
        else:
            self._url = "ws://"+ip+"/ws"
        self.serial = None
        self._connected = False
        self._allProps={}
        self._allPropsInitialized=False
        self._voltage1=None
        self._voltage2=None
        self._voltage3=None
        self._voltageN=None
        self._amps1=None
        self._amps2=None
        self._amps3=None
        self._power1=None
        self._power2=None
        self._power3=None
        self._powerN=None
        self._power=None
        self._version = None
        self._amp = None
        self._AccessState = None
        self._firmware = None
        self._WifiSSID = None
        self._AllowCharging = None
        self._mode=None
        self._carConnected=None
        self._cae=None
        self._cak=None
        self._event_handler = {}

        self._wst=threading.Thread()

        websocket.setdefaulttimeout(self._websocket_default_timeout)
        self._wsapp = websocket.WebSocketApp(
            self.url,
            on_close=self.__on_close,
            on_error=self.__on_error,
            on_message=self.__on_message,
            on_open=self.__on_open,
        )
        self.__call_event_handler(Event.WP_INIT)
        _LOGGER.info ("Wattpilot %s initialized",self.serial)

