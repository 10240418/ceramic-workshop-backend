D:\portable_package\python\python.exe -c "
import sys, snap7
PLC_IP='192.168.50.235'
client=snap7.client.Client()
print('='*60)
print('PLC Connection Diagnostic')
print('='*60)
try:
    client.connect(PLC_IP,0,1)
    print(f'[1] Connect: OK (connected={client.get_connected()})')
except Exception as e:
    print(f'[1] Connect: FAILED - {e}')
    sys.exit(1)
try:
    info=client.get_cpu_info()
    print(f'[2] CPU Info: {info.ModuleTypeName.decode().strip()} / {info.SerialNumber.decode().strip()}')
except Exception as e:
    print(f'[2] CPU Info: {e}')
try:
    print(f'[3] CPU State: {client.get_cpu_state()}')
except Exception as e:
    print(f'[3] CPU State: {e}')
try:
    print(f'[4] PDU Size: {client.get_param(10)}')
except Exception as e:
    print(f'[4] PDU Size: {e}')
for db,sz,name in [(1,4,'DB1-MasterStatus'),(2,4,'DB2-SensorData'),(3,4,'DB3-SlaveStatus')]:
    try:
        d=client.db_read(db,0,sz)
        print(f'[5] {name}: OK -> {bytes(d).hex().upper()}')
    except Exception as e:
        print(f'[5] {name}: FAILED -> {e}')
client.disconnect()
print('='*60)
"