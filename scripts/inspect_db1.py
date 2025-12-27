import sys
import os
import struct
import time

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_settings
from app.plc.s7_client import S7Client

def print_hex_dump(data, width=16):
    print(f"{'Offset':<8} {'Hex':<48} {'ASCII'}")
    print("-" * 70)
    for i in range(0, len(data), width):
        chunk = data[i:i+width]
        hex_str = ' '.join(f'{b:02X}' for b in chunk)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        print(f"{i:04X}     {hex_str:<48} {ascii_str}")

def parse_status_block(name, data, offset):
    """解析标准状态块 (4 bytes)"""
    # Byte 0: Flags
    b0 = data[offset]
    done = (b0 >> 0) & 1
    busy = (b0 >> 1) & 1
    error = (b0 >> 2) & 1
    
    # Byte 2-3: Status Code (Big Endian)
    status_code = struct.unpack('>H', data[offset+2:offset+4])[0]
    
    print(f"{name:<25} Offset:{offset:<4} Flags:[D:{done} B:{busy} E:{error}] Status:0x{status_code:04X} ({status_code})")

def main():
    settings = get_settings()
    print(f"============================================================")
    print(f"PLC DB1 Inspector")
    print(f"Target: {settings.plc_ip} (Rack: {settings.plc_rack}, Slot: {settings.plc_slot})")
    print(f"============================================================")
    
    client = S7Client(settings.plc_ip, settings.plc_rack, settings.plc_slot)
    
    try:
        print(f"Connecting...")
        if client.connect():
            print("Connected successfully!")
            
            # Read DB1
            db_number = 1
            size = 270
            print(f"Reading DB{db_number} ({size} bytes)...")
            
            data = client.read_db_block(db_number, 0, size)
            
            print("\n=== DB1 Hex Dump ===")
            print_hex_dump(data)
            
            print("\n=== Parsed Values (Sample) ===")
            
            # MB_COMM_LOAD (Offset 0)
            # Special case: DONE(0.0), ERROR(0.1) - No BUSY bit documented in config but likely similar
            b0 = data[0]
            done = (b0 >> 0) & 1
            error = (b0 >> 1) & 1 # Config says 0.1
            status_code = struct.unpack('>H', data[2:4])[0]
            print(f"{'MB_COMM_LOAD':<25} Offset:0    Flags:[D:{done} E:{error}]     Status:0x{status_code:04X} ({status_code})")
            
            # Sample a few devices
            parse_status_block("ELEC_0", data, 4)
            parse_status_block("ELEC_1", data, 8)
            parse_status_block("ELEC_36 (Last Elec)", data, 148)
            
            parse_status_block("THERMAL_0", data, 152)
            parse_status_block("THERMAL_17 (Last Therm)", data, 220)
            
            parse_status_block("FLOW_0", data, 228)
            parse_status_block("WEIGH_0", data, 236)
            
            # Check for common errors
            print("\n=== Error Analysis ===")
            error_count = 0
            for i in range(4, 264, 4): # Scan all standard blocks
                if i >= 224 and i < 228: continue # Skip gap
                
                code = struct.unpack('>H', data[i+2:i+4])[0]
                if code != 0:
                    error_count += 1
                    # Try to identify device name roughly
                    dev_name = "Unknown"
                    if 4 <= i <= 148: dev_name = f"ELEC_{(i-4)//4}"
                    elif 152 <= i <= 220: dev_name = f"THERMAL_{(i-152)//4}"
                    elif 228 <= i <= 232: dev_name = f"FLOW_{(i-228)//4}"
                    elif 236 <= i <= 260: dev_name = f"WEIGH_{(i-236)//4}"
                    
                    print(f"Found Error: {dev_name:<15} Code: 0x{code:04X} ({code})")
            
            if error_count == 0:
                print("No errors found in scanned blocks.")
            else:
                print(f"Total devices with non-zero status: {error_count}")

        else:
            print("Failed to connect to PLC.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if client.client:
            client.disconnect()
            print("\nDisconnected.")

if __name__ == "__main__":
    main()
