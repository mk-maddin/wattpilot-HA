import aiohttp
import asyncio
import json
import hashlib
import random
import hmac
import logging
import base64
import re
import bcrypt

from types import SimpleNamespace

_LOGGER = logging.getLogger(__name__)

CONST_HASH_PBKDF2 = 'pbkdf2'
CONST_HASH_BCRYPT = 'bcrypt'
CONST_WPFLEX_DEVICETYPE='wattpilot_flex'

RECONNECT_SECONDS = 30
CONST_RECEIVE_TIMEOUT_SECONDS = 120
CONST_CONNECT_TIMEOUT_SECONDS = 10

# pushed through the property callback when the socket drops
CONST_CONNECTION_SENTINEL = '__wattpilot_connection__'
CONST_SECRET_PROPERTIES = ('cak', 'ocppck', 'ocppcc', 'ocppsc')
CONST_SECRET_PATTERN = re.compile(r'("(?:' + '|'.join(CONST_SECRET_PROPERTIES) + r')"\s*:\s*)"(?:[^"\\]|\\.)*"')
__version__ = '0.2.2i'

def _mask_secrets(message):
    """Return the message with the values of secret properties replaced by ***."""
    return CONST_SECRET_PATTERN.sub(r'\1"***"', str(message))

class LoadMode():
    """Wrapper Class to represent the Load Mode of the Wattpilot"""
    DEFAULT=3
    ECO=4
    NEXTTRIP=5


def _namespace(value):
    """Return JSON objects as SimpleNamespace, as the property values have always been."""
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _namespace(v) for k, v in value.items()})
    if isinstance(value, list) and any(isinstance(v, (dict, list)) for v in value):
        return [_namespace(v) for v in value]
    return value


def _hash_password(password, serial, hashtype):
    """Return the hashed password the charger expects; CPU heavy, run it in an executor."""
    if hashtype == CONST_HASH_PBKDF2:
        return base64.b64encode(hashlib.pbkdf2_hmac('sha512', password.encode(), serial.encode(), 100000, 256))[:32]
    if hashtype == CONST_HASH_BCRYPT:
        return _bcrypt_hash_password(password, serial).encode()
    raise ValueError("unknown authhashtype: %s" % hashtype)


def _bcryptjs_base64_encode(b: bytes, length: int) -> str:
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


def _bcryptjs_encodeBase64(s: str, length: int) -> str:
    #helper wrapper function for _bcryptjs_base64_encode
    #ensures python & java encoding is handled equally
    if s.isdigit(): #numeric only serial
        vals = [ord(ch) - ord('0') for ch in s]
        b = bytes([0] * (length - len(vals)) + vals)
    else: #not sure about serials in future - fallback
        _LOGGER.error("_bcryptjs_encodeBase64: check serial string - should be digits only: %s", s)
        raise ValueError(f"Check serial string - should be digits only: %s", s)
    return _bcryptjs_base64_encode(b,length)


def _bcrypt_hash_password(password,serial,iterations=8) -> str:
    #hash bassword bcrypt / wattpilot flex compatible
    password_hash_sha256 = hashlib.sha256(password.encode('utf-8')).hexdigest()
    serial_b64 = _bcryptjs_encodeBase64(serial, 16)
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


def _translate(table, value):
    """Translate a raw charger value, without raising out of the ws callback."""
    try:
        return table[value]
    except KeyError:
        _LOGGER.warning("_translate: no entry for value %r in %s - reporting as unknown", value, table)
        return "unknown (%s)" % (value,)


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

    carValues[0] = "Unknown"
    carValues[1] = "no car"
    carValues[2] = "charging"
    carValues[3] = "ready"
    carValues[4] = "complete"
    carValues[5] = "Error"

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
        """Start the websocket task on the running event loop; it reconnects whenever the socket drops."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._stop = False
        self._task = asyncio.get_running_loop().create_task(self._run(), name="wattpilot websocket")
        _LOGGER.info("connect: Wattpilot connecting")

    def disconnect(self):
        """Close the socket and stop reconnecting."""
        self._stop = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
        for task in list(self._send_tasks):
            task.cancel()
        self._set_disconnected()
        _LOGGER.info("disconnect: Wattpilot disconnected")

    async def async_disconnect(self):
        """Close the socket, stop reconnecting and wait until the websocket task has ended."""
        task = self._task
        self.disconnect()
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise

    async def _run(self):
        session = self._session
        own_session = session is None
        try:
            if own_session:
                session = aiohttp.ClientSession()
            while not self._stop and not session.closed:
                ws = None
                try:
                    async with asyncio.timeout(CONST_CONNECT_TIMEOUT_SECONDS):
                        ws = await session.ws_connect(self._url, origin=self._origin)
                    try:
                        self._wsapp = ws
                        self._close_requested = False
                        await self._receive(ws)
                    finally:
                        await ws.close()
                except asyncio.CancelledError:
                    raise
                except TimeoutError:
                    if ws is None:
                        _LOGGER.warning("connect: charger did not answer within %s seconds", CONST_CONNECT_TIMEOUT_SECONDS)
                    else:
                        _LOGGER.warning("connect: no message from the charger for %s seconds", CONST_RECEIVE_TIMEOUT_SECONDS)
                    self._set_disconnected()
                except Exception as e:
                    _LOGGER.warning("connect: websocket loop raised %s (%s)", str(e), type(e).__name__)
                    self._set_disconnected()
                finally:
                    self._wsapp = None
                if self._stop or session.closed:
                    break
                _LOGGER.warning("connect: websocket closed, reconnecting in %s seconds", RECONNECT_SECONDS)
                await asyncio.sleep(RECONNECT_SECONDS)
        finally:
            if own_session and session is not None:
                await session.close()

    async def _receive(self, ws):
        while True:
            message = await ws.receive(timeout=CONST_RECEIVE_TIMEOUT_SECONDS)
            if message.type in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
                self.__on_message(ws, message.data)
                if self._close_requested:
                    await ws.close()
                    self.__on_close(ws, ws.close_code, None)
                    return
            elif message.type == aiohttp.WSMsgType.ERROR:
                self.__on_error(ws, message.data)
                return
            elif message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                self.__on_close(ws, ws.close_code, None)
                return

    def _set_disconnected(self):
        """Mark the socket down and notify the property listener."""
        self._connected = False
        if self._property_callback is not None:
            try:
                self._property_callback(CONST_CONNECTION_SENTINEL, False)
            except Exception as e:
                _LOGGER.debug("_set_disconnected: sentinel callback failed: %s", str(e))

    def register_message_callback(self,callback_fn):
        """signature of callback_fn: (wsapp,msg)"""
        self._message_callback = callback_fn

    def unregister_message_callback(self):
        self._message_callback = None

    def register_property_callback(self,callback_fn):
        """signature of callback_fn: (name,value)"""
        self._property_callback = callback_fn

    def unregister_property_callback(self):
        self._property_callback = None

    def set_power(self,power):
        self.send_update("amp",power)

    def set_mode(self,mode):
        self.send_update("lmo",mode)


    def send_update(self,name,value):
        """Send a new property value; schedules the send on the running event loop."""
        task = asyncio.get_running_loop().create_task(self.async_send_update(name,value))
        self._send_tasks.add(task)
        task.add_done_callback(self._send_done)

    def _send_done(self,task):
        self._send_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            _LOGGER.error("send_update: sending failed: %s", str(task.exception()))

    async def async_send_update(self,name,value):
        """Send a new property value to the charger; raises ConnectionError when not connected."""
        message = {}
        message["type"]="setValue"
        self.__requestid = self.__requestid+1
        message["requestId"]=self.__requestid
        message["key"]=name
        message["value"]=value
        await self.__send(message, self._secured is not None and self._secured > 0)

    def __update_property(self,name,value):

        value = _namespace(value)
        self._allProps[name] = value
        if name=="acs":
            self._AccessState = _translate(Wattpilot.acsValues, value)

        if name=="cbl":
            self._cableType = value

        if name=="fhz":
            self._frequency = value

        if name=="pha":
            self._phases = value
        
        if name=="wh":
            self._energyCounterSinceStart = value

        if name=="err":
            self._errorState = _translate(Wattpilot.errValues, value)

        if name=="ust":
            self._cableLock = _translate(Wattpilot.ustValues, value)

        if name=="eto":
            self._energyCounterTotal = value

        if name=="cae":
            self._cae = value
        if name=="cak":
            self._cak = value
        if name=="lmo":
            self._mode = _translate(Wattpilot.lmoValues, value)
        if name=="car":
            self._carConnected = _translate(Wattpilot.carValues, value)
        if name=="alw":
            self._AllowCharging = _translate(Wattpilot.alwValues, value)
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
            self._AllowCharging = _translate(self._astValues, value)
        if name=="fwv":
            self._firmware = value
        if name=="wss":
            self._WifiSSID=value
        if name=="upd":
            if value=="0":
                self._updateAvailable = False
            else:
                self._updateAvailable = True
        if self._property_callback != None:
            self._property_callback(name,value)

    def __on_hello(self,message):
        _LOGGER.info("Connected to WattPilot Serial %s",message["serial"])
        if "hostname" in message:
            self._name=message["hostname"]
        self.serial = message["serial"]
        if "hostname" in message:
            self._hostname=message["hostname"]
        if "version" in message:
            self._version=message["version"]
        self._manufacturer=message.get("manufacturer")
        self._devicetype=message.get("devicetype")
        self._protocol=message.get("protocol")
        if "secured" in message:
            self._secured=message["secured"]

    def __on_auth(self,wsapp,message):
        task = asyncio.get_running_loop().create_task(self._async_auth(wsapp,message))
        self._send_tasks.add(task)
        task.add_done_callback(self._auth_done)

    def _auth_done(self,task):
        self._send_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            _LOGGER.error("__on_auth: authentication failed: %s", str(task.exception()))

    async def _async_auth(self,wsapp,message):
        ran = random.randrange(10**80)
        self._token3 = "%064x" % ran
        self._token3 = self._token3[:32]
        if "hash" in message:
            self._authhashtype = message["hash"]
        elif self._devicetype == CONST_WPFLEX_DEVICETYPE:
            self._authhashtype = CONST_HASH_BCRYPT
        await self.__update_hashedpassword()
        hash1 = hashlib.sha256((message["token1"].encode()+self._hashedpassword)).hexdigest()
        hash = hashlib.sha256((self._token3 + message["token2"]+hash1).encode()).hexdigest()
        response = {}
        response["type"] = "auth"
        response["token3"] = self._token3
        response["hash"] = hash

        await self.__send(response, ws=wsapp)

    async def __update_hashedpassword(self):
        password = self._password
        serial = self._serial
        if (password is None) or (serial is None):
            _LOGGER.info("__update_hashedpassword: password or serial empty - keep current _hashedpassword")
            return
        key = (password, serial, self._authhashtype)
        if self._hashedpasswordkey == key:
            return
        _LOGGER.debug("__update_hashedpassword: generating password hash of type: %s", self._authhashtype)
        try:
            self._hashedpassword = await asyncio.get_running_loop().run_in_executor(None, _hash_password, password, serial, self._authhashtype)
        except ValueError as e:
            _LOGGER.error("__update_hashedpassword: %s", str(e))
            return
        self._hashedpasswordkey = key

    async def __send(self,message,secure=False,ws=None):
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

        if ws is None:
            ws = self._wsapp
        if ws is None or ws.closed:
            raise ConnectionError("websocket not connected")
        payload = json.dumps(message)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Message send: %s", _mask_secrets(payload))
        await ws.send_str(payload)

    def __on_AuthSuccess(self,message):
        self._connected = True
        _LOGGER.info("Authentication successful")

    def __on_FullStatus(self,message):
        props = message["status"]
        for key in props:
            self.__update_property(key,props[key])
        if "partial" in message and not self._allPropsInitialized:
            self._allPropsInitialized = not message["partial"]
        else:
            self.__allPropsInitializedFallback=True

    def __on_AuthError(self,message):
        if message.get("message")=="Wrong password":
            self._close_requested = True
            _LOGGER.error("Authentication failed: %s", message.get("message"))

    def __on_DeltaStatus(self,message):
        self._allPropsInitialized=True # Assume all properties have been initialized when first delta status is received
        props = message["status"]
        for key in props:
            self.__update_property(key,props[key])

    def __on_clearInverters(self,message):
        pass

    def __on_updateInverter(self,message):
        pass

    def __on_response(self,message):
        if message.get("success"):
            if "status" in message:
                props = message["status"]
                for key in props:
                    self.__update_property(key,props[key])
        else:
            _LOGGER.error("Error Sending Request %s. Message: %s", message.get("requestId"), message.get("message", message))

    def __on_error(self,wsapp,err):
        # reconnection is owned by connect()
        _LOGGER.warning("__on_error: charger websocket error: %s", err)
        self._set_disconnected()

    def __on_close(self,wsapp,code,msg):
        # notify here: the websocket task reconnects on its own
        _LOGGER.warning("__on_close: charger websocket closed (code=%s)", code)
        self._set_disconnected()

    def __on_message(self, wsapp, message):
        ## called whenever a message through websocket is received
        try:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("Message received: %s", _mask_secrets(message))
            msg=json.loads(message)
            msg_type = msg.get("type")
            if (msg_type == 'hello'):  # Hello Message -> Received upon connection before auth
                self.__on_hello(msg)
            if (msg_type == 'authRequired'): # Auth Required -> Received after hello 
                self.__on_auth(wsapp,msg)
            if (msg_type == 'response'): # Response Message -> Received after sending a update and contains result of update
                self.__on_response(msg)
            if (msg_type == 'authSuccess'): #Auth Success -> Received after sending  correct authentication message
                self.__on_AuthSuccess(msg)
            if (msg_type == 'authError'): # AUth errot -> Received after sending incorrect authentication message (e.g. wrong password)
                self.__on_AuthError(msg)
            if (msg_type == 'fullStatus'): #Full Status -> Received after successfull connection. Contains all Properties of Wattpilot
                self.__on_FullStatus(msg)
            if (msg_type == 'deltaStatus'): # Delta Status -> Whenever a property changes a Delta Status is send
                self.__on_DeltaStatus(msg)
            if (msg_type == 'clearInverters'): # Unknown
                self.__on_clearInverters(msg)
            if (msg_type == 'updateInverter'): # Contains information of connected Photovoltaik inverter / powermeter
                self.__on_updateInverter(msg)
            if self._message_callback != None:
                self._message_callback(self,wsapp,_namespace(msg),message)
        except Exception as e:
            _LOGGER.warning("__on_message: failed to process message: %s (%s)", str(e), type(e).__name__)


    def __init__(self, ip ,password,serial=None,cloud=False,session=None):
        self.__requestid=0
        self._session = session
        self._task = None
        self._stop = False
        self._wsapp = None
        self._close_requested = False
        self._send_tasks = set()
        self._hashedpasswordkey = None
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
            self._origin = "https://app.wattpilot.io"
        else:
            self._url = "ws://"+ip+"/ws"
            self._origin = "http://"+ip
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
        self._message_callback=None
        self._property_callback=None

        _LOGGER.info ("Wattpilot %s initilized",self.serial)

