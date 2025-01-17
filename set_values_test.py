#apt-get install -y python3-pip
#python3 -m venv /tmp/venv
#/tmp/venv/bin/pip3 install wattpilot
#nano /tmp/venv/set_values_test.py
#/tmp/venv/bin/python3 /tmp/venv/set_values_test.py


import wattpilot
import time
import json
import types


charger=wattpilot.Wattpilot('<MyWattpilotIP>','<MyWattpilotPassword>')
charger.connect()

timer=0
timeout=30
while timeout > timer and not (charger.connected and charger.allPropsInitialized):
  time.sleep(1)
  timer+=1
if not charger.connected:
  print("Charger not connected")
  exit()
elif not charger.allPropsInitialized:
  print("Charger not initialized")
  charger._wsapp.close()
  exit()
elif not timeout > timer:
  print("Connection timeout")
  exit()
print("Charger connected")


def send_value(charger, identifier, value, force_type=None):
  #print("value = ", value)
  #print("value type =", type(value))
  #print("value dict =", value.__dict__)

  if str(value).lower() in ["false","true"] or force_type == 'bool':
    v=json.loads(str(value).lower())
  elif type(value) is types.SimpleNamespace:
    v=value.__dict__
  elif force_type == 'str':
    v=str(value)
  elif str(value).isnumeric() or force_type == 'int':
    v=int(value)
  elif str(value).isdecimal() or force_type == 'float':
    v=float(value)
  else:
    v=str(value)

  #print("v = ",v)
  #print("v type = ", type(v))
  #print("v dict = ", v.__dict__)

  charger.send_update(identifier,v)

def print_value(charger, identifier):
  print(identifier, " = ", charger.allProps[identifier])


print("====== GET VALUES PRE =======")
print_value(charger, 'ebe') #ebe is boost active/inactive - for simple check in apply if changes applied in general
print_value(charger, 'acs')
print_value(charger, 'ocppcs')
print_value(charger, 'npd')
print_value(charger, 'ebv')
print_value(charger, 'modelStatus')
print_value(charger,'cll')


print("======= SET VALUES =======")
if charger.allProps['ebe'] == True: send_value(charger,'ebe', False)
else: send_value(charger, 'ebe', True)
send_value(charger, 'acs', 1)
send_value(charger,'ocppcs', 1)
send_value(charger, 'npd', True)
send_value(charger, 'ebv', True)
#send_value(charger, 'modelStatus', 17) #ReadOnly value

cll=charger.allProps['cll']
#cll locked 11kW: namespace(accessControl=0, adapterCurrentLimit=16, cableCurrentLimit=32, currentLimitMax=16, requestedCurrent=16, temperatureCurrentLimit=32, unsymetryCurrentLimit=32) 
#cll unlocked 11kW: namespace( adapterCurrentLimit=16, cableCurrentLimit=32, currentLimitMax=16, requestedCurrent=16, temperatureCurrentLimit=32, unsymetryCurrentLimit=32) 
if hasattr(cll, 'accessControl'): del cll.accessControl
send_value(charger, 'cll', cll)

time.sleep(3)

print("====== GET VALUES POST =======")
print_value(charger, 'ebe')
print_value(charger, 'acs')
print_value(charger, 'ocppcs')
print_value(charger, 'npd')
print_value(charger, 'ebv')
print_value(charger, 'modelStatus')
print_value(charger,'cll')

time.sleep(1)

charger._wsapp.close()
