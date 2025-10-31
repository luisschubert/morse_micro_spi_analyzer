#!/usr/bin/env python3
"""
Test script to validate the SDIO-over-SPI decoder against known transactions
"""

def decode_cmd53(mosi_bytes):
    """
    Decode a CMD53 command from MOSI bytes
    
    Args:
        mosi_bytes: List of bytes from MOSI line
    
    Returns:
        Dictionary with decoded fields
    """
    if len(mosi_bytes) < 7:
        return None
    
    # Find command start (0xFF followed by byte with 0x40 bit set)
    cmd_start = -1
    for i in range(min(3, len(mosi_bytes) - 6)):
        if mosi_bytes[i] == 0xFF and (mosi_bytes[i+1] & 0x40):
            cmd_start = i
            break
    
    if cmd_start == -1:
        return None
    
    # Extract command and argument
    cmd = mosi_bytes[cmd_start + 1]
    arg = (mosi_bytes[cmd_start + 2] << 24) | \
          (mosi_bytes[cmd_start + 3] << 16) | \
          (mosi_bytes[cmd_start + 4] << 8) | \
          (mosi_bytes[cmd_start + 5])
    
    # Decode CMD53 format
    write_bit = (arg >> 31) & 0x1
    function = (arg >> 28) & 0x7
    block_mode = (arg >> 27) & 0x1
    opcode = (arg >> 26) & 0x1
    address = (arg >> 9) & 0x1FFFF
    count = arg & 0x1FF
    crc = mosi_bytes[cmd_start + 6]
    
    # Determine mode string
    mode = 'Block' if block_mode else 'Byte'
    addr_mode = 'Incr' if opcode else 'Fixed'
    rw = 'WRITE' if write_bit else 'READ'
    
    # Check for known registers
    reg_name = None
    if address == 0x6050:
        reg_name = "INT1_STS"
    elif address == 0x6054:
        reg_name = "INT1_SET"
    elif address == 0x6058:
        reg_name = "INT1_CLR"
    
    return {
        'command': cmd,
        'argument': arg,
        'write': write_bit,
        'function': function,
        'block_mode': block_mode,
        'opcode': opcode,
        'address': address,
        'count': count,
        'crc': crc,
        'mode_str': f"{mode},{addr_mode}",
        'rw': rw,
        'reg_name': reg_name
    }


def decode_cmd52(mosi_bytes):
    """
    Decode a CMD52 command from MOSI bytes
    
    Args:
        mosi_bytes: List of bytes from MOSI line
    
    Returns:
        Dictionary with decoded fields
    """
    if len(mosi_bytes) < 7:
        return None
    
    # Find command start (0xFF followed by byte with 0x40 bit set)
    cmd_start = -1
    for i in range(min(3, len(mosi_bytes) - 6)):
        if mosi_bytes[i] == 0xFF and (mosi_bytes[i+1] & 0x40):
            cmd_start = i
            break
    
    if cmd_start == -1:
        return None
    
    # Extract command and argument
    cmd = mosi_bytes[cmd_start + 1]
    arg = (mosi_bytes[cmd_start + 2] << 24) | \
          (mosi_bytes[cmd_start + 3] << 16) | \
          (mosi_bytes[cmd_start + 4] << 8) | \
          (mosi_bytes[cmd_start + 5])
    
    # Check if this is CMD52 (0x74 = 0x40 | 52)
    if cmd != 0x74:
        return None
    
    # Decode CMD52 format
    write_bit = (arg >> 31) & 0x1
    function = (arg >> 28) & 0x7
    raw_bit = (arg >> 27) & 0x1
    address = (arg >> 9) & 0x1FFFF
    data = arg & 0xFF
    crc = mosi_bytes[cmd_start + 6]
    
    rw = 'WRITE' if write_bit else 'READ'
    
    # Check for known registers
    reg_name = None
    if address == 0x10000:
        reg_name = "WINDOW_0"
    elif address == 0x10001:
        reg_name = "WINDOW_1"
    elif address == 0x10002:
        reg_name = "WINDOW_CONFIG"
    elif address == 0x6050:
        reg_name = "INT1_STS"
    elif address == 0x6054:
        reg_name = "INT1_SET"
    elif address == 0x6058:
        reg_name = "INT1_CLR"
    
    return {
        'command': cmd,
        'argument': arg,
        'write': write_bit,
        'function': function,
        'raw_bit': raw_bit,
        'address': address,
        'data': data,
        'crc': crc,
        'rw': rw,
        'reg_name': reg_name
    }


def calculate_windowed_address(window_0, window_1, sdio_address):
    """Calculate 32-bit address from window registers and SDIO address"""
    return (window_1 << 24) | (window_0 << 16) | (sdio_address & 0xFFFF)


def decode_irq_bits(irq_value):
    """Decode IRQ status bits into human-readable description"""
    if irq_value == 0:
        return "None"
    
    bits = []
    
    # Bits 0-13: Pager interrupts
    for i in range(14):
        if irq_value & (1 << i):
            bits.append(f"Pager{i}")
    
    # Bit 15: TX status available
    if irq_value & (1 << 15):
        bits.append("TxStatus")
    
    # Bits 17-24: Beacon VIF interrupts
    for i in range(17, 25):
        if irq_value & (1 << i):
            bits.append(f"Beacon{i-17}")
    
    # Bits 25-26: NDP probe request interrupts
    if irq_value & (1 << 25):
        bits.append("NDP0")
    if irq_value & (1 << 26):
        bits.append("NDP1")
    
    # Bit 27: HW stop notification
    if irq_value & (1 << 27):
        bits.append("HW_STOP")
    
    # Bits 28-31: Reserved/unknown
    for i in range(28, 32):
        if irq_value & (1 << i):
            bits.append(f"Bit{i}")
    
    return ",".join(bits) if bits else "Unknown"

def get_func_description(func_num):
    """Get function description"""
    descriptions = {
        0: "Card Control (CCCR)",
        1: "Registers/Control (≤4B)",
        2: "Bulk Data (>4B)",
    }
    return descriptions.get(func_num, f"Fn{func_num}")

def print_decode_cmd52(label, mosi_bytes):
    """Print decoded CMD52 information"""
    print(f"\n{label}:")
    print(f"  Raw MOSI: {' '.join([f'{b:02X}' for b in mosi_bytes[:10]])}{'...' if len(mosi_bytes) > 10 else ''}")
    
    result = decode_cmd52(mosi_bytes)
    if result:
        func_desc = get_func_description(result['function'])
        
        if result['reg_name']:
            print(f"  Type: CMD52 {result['rw']} {result['reg_name']}")
        else:
            print(f"  Type: CMD52 {result['rw']}")
        print(f"  Function: {result['function']} - {func_desc}")
        print(f"  Address: 0x{result['address']:05X}")
        print(f"  Data: 0x{result['data']:02X}")
        print(f"  CRC: 0x{result['crc']:02X}")
    else:
        print("  Could not decode as CMD52")

def print_decode(label, mosi_bytes, miso_bytes=None):
    """Print decoded information for a transaction"""
    print(f"\n{label}:")
    print(f"  Raw MOSI: {' '.join([f'{b:02X}' for b in mosi_bytes[:10]])}{'...' if len(mosi_bytes) > 10 else ''}")
    if miso_bytes:
        print(f"  Raw MISO: {' '.join([f'{b:02X}' for b in miso_bytes[:20]])}{'...' if len(miso_bytes) > 20 else ''}")
    
    result = decode_cmd53(mosi_bytes)
    if result:
        func_desc = get_func_description(result['function'])
        
        if result['reg_name']:
            print(f"  Type: {result['rw']} {result['reg_name']}")
        else:
            print(f"  Type: CMD53 {result['rw']}")
        print(f"  Function: {result['function']} - {func_desc}")
        print(f"  Address: 0x{result['address']:04X}")
        print(f"  Count: {result['count']}")
        print(f"  Mode: {result['mode_str']}")
        print(f"  CRC: 0x{result['crc']:02X}")
        
        # Decode IRQ bits if this is an IRQ register access
        if result['reg_name'] in ['INT1_STS', 'INT1_CLR'] and miso_bytes:
            # Data typically starts at position 11 (after 7 bytes cmd + 4 bytes response/padding)
            if len(miso_bytes) >= 15:
                miso_data = miso_bytes[11:15]
                irq_value = (miso_data[3] << 24) | (miso_data[2] << 16) | (miso_data[1] << 8) | miso_data[0]
                irq_bits_str = decode_irq_bits(irq_value)
                print(f"  IRQ Value: 0x{irq_value:08X}")
                print(f"  IRQ Bits: {irq_bits_str}")
    else:
        print("  Could not decode")


# Test cases from your analysis
print("=" * 60)
print("Testing transactions from morse_question.md")
print("=" * 60)

# A1 - IRQ Status Read (with MISO showing IRQ status)
a1_mosi = [0xFF, 0x75, 0x14, 0xC0, 0xA0, 0x04, 0x89, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
a1_miso = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0xFF, 0xFE, 0x04, 0x00, 0x00, 0x00, 0xCA, 0xF1, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
print_decode("A1 (IRQ Status Read)", a1_mosi, a1_miso)

# A2 - IRQ Clear (with MISO echoing the cleared value)
a2_mosi = [0xFF, 0x75, 0x94, 0xC0, 0xB0, 0x04, 0xCD, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
a2_miso = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0xFF, 0xFE, 0x04, 0x00, 0x00, 0x00, 0xCA, 0xF1, 0xFF, 0xE5, 0x0F, 0xFF]
print_decode("A2 (IRQ Clear)", a2_mosi, a2_miso)

print("\n" + "=" * 60)
print("Testing transactions from morse_question_spi_rk3588.md")
print("=" * 60)

# A3 from morse_question_spi_rk3588.md
a3_mosi = [0xFF, 0x75, 0x15, 0x84, 0x28, 0x04, 0x3F, 0xFF, 0xFF, 0xFF]
print_decode("A3", a3_mosi)

# B1
b1_mosi = [0xFF, 0x75, 0x14, 0xC0, 0xA0, 0x04, 0x89, 0xFF, 0xFF, 0xFF]
print_decode("B1 (should be same as A1)", b1_mosi)

# B2
b2_mosi = [0xFF, 0x75, 0x94, 0xC0, 0xB0, 0x04, 0xCD, 0xFF, 0xFF, 0xFF]
print_decode("B2 (should be same as A2)", b2_mosi)

# B3
b3_mosi = [0xFF, 0x75, 0x15, 0x84, 0x28, 0x04, 0x3F, 0xFF, 0xFF, 0xFF]
print_decode("B3 (should be same as A3)", b3_mosi)

print("\n" + "=" * 60)
print("Testing Function 2 (Bulk Data)")
print("=" * 60)

# Simulate a Function 2 bulk transfer: 0x75 0x2D 0x35 0x09 0x42 0x03
# This would be: CMD53 READ, Fn2, Block mode, Incr, Addr 0x9420, Count 3 blocks
fn2_mosi = [0xFF, 0x75, 0x2D, 0x35, 0x09, 0x42, 0x03, 0xFF]
print_decode("Function 2 Bulk Read (3 blocks = 1536 bytes)", fn2_mosi)

print("\n" + "=" * 60)
print("Testing unknown patterns from morse_question.md")
print("=" * 60)

# These are the values you couldn't decode - let's see what they are
unknown_patterns = [0x1842800, 0x1862000, 0x17E8000, 0x1822000]

for pattern in unknown_patterns:
    # These might be arguments without the full command structure
    # Let's decode them as if they were the 32-bit argument
    write_bit = (pattern >> 31) & 0x1
    function = (pattern >> 28) & 0x7
    block_mode = (pattern >> 27) & 0x1
    opcode = (pattern >> 26) & 0x1
    address = (pattern >> 9) & 0x1FFFF
    count = pattern & 0x1FF
    
    print(f"\nPattern 0x{pattern:07X}:")
    print(f"  Write: {write_bit}, Fn: {function}, Block: {block_mode}, Op: {opcode}")
    print(f"  Address: 0x{address:04X}, Count: {count}")


print("\n" + "=" * 60)
print("Testing CMD52 Transactions")
print("=" * 60)

# CMD52 Write to WINDOW_0 (Function 1) - Setting upper address bits [23:16] = 0x12
# Command: 0x74, Arg: 0x90800012
cmd52_win0_fn1 = [0xFF, 0x74, 0x90, 0x80, 0x00, 0x12, 0x9D, 0xFF, 0xFF]
print_decode_cmd52("CMD52: FUNC1 WINDOW_0 = 0x12", cmd52_win0_fn1)

# CMD52 Write to WINDOW_1 (Function 1) - Setting upper address bits [31:24] = 0x20
# Command: 0x74, Arg: 0x90800220
cmd52_win1_fn1 = [0xFF, 0x74, 0x90, 0x80, 0x02, 0x20, 0x4F, 0xFF, 0xFF]
print_decode_cmd52("CMD52: FUNC1 WINDOW_1 = 0x20", cmd52_win1_fn1)

# CMD52 Write to WINDOW_CONFIG (Function 1) - Setting access size = 4 bytes
# Command: 0x74, Arg: 0x90800404
cmd52_config_fn1 = [0xFF, 0x74, 0x90, 0x80, 0x04, 0x04, 0xE3, 0xFF, 0xFF]
print_decode_cmd52("CMD52: FUNC1 CONFIG = 0x04 (4-byte access)", cmd52_config_fn1)

# CMD52 Write to WINDOW_0 (Function 2) - Setting upper address bits for bulk
# Command: 0x74, Arg: 0x98800034
cmd52_win0_fn2 = [0xFF, 0x74, 0x98, 0x80, 0x00, 0x34, 0x7A, 0xFF, 0xFF]
print_decode_cmd52("CMD52: FUNC2 WINDOW_0 = 0x34", cmd52_win0_fn2)

# CMD52 Write to FUNC_0 (SDIO CCCR) - Enable interrupts
# Command: 0x74, Arg: 0x80000803 (write 0x03 to address 0x04)
cmd52_cccr_ien = [0xFF, 0x74, 0x80, 0x00, 0x08, 0x03, 0xB8, 0xFF, 0xFF]
print_decode_cmd52("CMD52: FUNC0 CCCR_IEN = 0x03", cmd52_cccr_ien)


print("\n" + "=" * 60)
print("Testing Window Tracking Sequence")
print("=" * 60)

print("\n--- Scenario: Setting up FUNC1 window then reading from 0x20001234 ---")

# Step 1: Set WINDOW_0 = 0x12
print("\nStep 1: Configure WINDOW_0")
print_decode_cmd52("  CMD52 WR FUNC1 WINDOW_0", cmd52_win0_fn1)

# Step 2: Set WINDOW_1 = 0x20
print("\nStep 2: Configure WINDOW_1")
print_decode_cmd52("  CMD52 WR FUNC1 WINDOW_1", cmd52_win1_fn1)

# Step 3: Set CONFIG = 0x04
print("\nStep 3: Configure access size")
print_decode_cmd52("  CMD52 WR FUNC1 CONFIG", cmd52_config_fn1)

# Step 4: Now do CMD53 read from SDIO address 0x1234
# With window set, this becomes: (0x20 << 24) | (0x12 << 16) | 0x1234 = 0x20121234
# CMD53: 0x75, Read, Fn1, Byte mode, Incr, Addr 0x1234, Count 4
cmd53_windowed_read = [0xFF, 0x75, 0x14, 0x24, 0x90, 0x04, 0xC5, 0xFF, 0xFF, 0xFF]
print("\nStep 4: Read 4 bytes (will use window)")
print_decode("  CMD53 RD FUNC1 0x1234", cmd53_windowed_read)

# Calculate and display the full address
window_0 = 0x12
window_1 = 0x20
sdio_addr = 0x1234
full_addr = calculate_windowed_address(window_0, window_1, sdio_addr)
print(f"\n  >>> Calculated Full Address: 0x{full_addr:08X}")
print(f"      (window_1=0x{window_1:02X}, window_0=0x{window_0:02X}, sdio=0x{sdio_addr:04X})")


print("\n" + "=" * 60)
print("Testing FUNC1 vs FUNC2 Independent Windows")
print("=" * 60)

print("\n--- Scenario: FUNC1 and FUNC2 maintain separate windows ---")
print("\nFUNC1 Window: 0x20120000")
print("FUNC2 Window: 0x30340000")
print("\nFUNC1 accessing SDIO 0x5678 → Full address: 0x20125678")
full_f1 = calculate_windowed_address(0x12, 0x20, 0x5678)
print(f"  Calculated: 0x{full_f1:08X}")

print("\nFUNC2 accessing SDIO 0x5678 → Full address: 0x30345678")
full_f2 = calculate_windowed_address(0x34, 0x30, 0x5678)
print(f"  Calculated: 0x{full_f2:08X}")


print("\n" + "=" * 60)
print("Testing IRQ Register Access with Window")
print("=" * 60)

print("\n--- Scenario: Reading IRQ status at 0x20006050 (INT1_STS) ---")
# INT1_STS is at 0x6050, but after windowing it's at 0x20006050
# Window: 0x20 << 24 | 0x00 << 16 = 0x20000000
# SDIO address: 0x6050
# Full: 0x20006050

print("\nStep 1: Configure window for 0x2000xxxx range")
cmd52_win0_irq = [0xFF, 0x74, 0x90, 0x80, 0x00, 0x00, 0x61, 0xFF, 0xFF]
cmd52_win1_irq = [0xFF, 0x74, 0x90, 0x80, 0x02, 0x20, 0x4F, 0xFF, 0xFF]
print_decode_cmd52("  CMD52 WR FUNC1 WINDOW_0 = 0x00", cmd52_win0_irq)
print_decode_cmd52("  CMD52 WR FUNC1 WINDOW_1 = 0x20", cmd52_win1_irq)

print("\nStep 2: Read INT1_STS (SDIO 0x6050)")
# Note: The existing test case A1 reads from 0x6050
print_decode("  CMD53 RD IRQ Status", a1_mosi, a1_miso)

window_0_irq = 0x00
window_1_irq = 0x20
sdio_irq = 0x6050
full_irq_addr = calculate_windowed_address(window_0_irq, window_1_irq, sdio_irq)
print(f"\n  >>> Calculated Full IRQ Address: 0x{full_irq_addr:08X}")
print(f"      This matches INT1_STS at 0x20006050!")


print("\n" + "=" * 60)
print("Testing Decoder Modes")
print("=" * 60)

print("\n--- Basic Mode: Simple classification ---")
print("  Window config transaction → Shows: WINDOW: Fn1 | WINDOW_0 = 0x12")
print("  CMD53 transaction → Shows: DATA: Fn1 RD | Addr:0x1234 Cnt:4")

print("\n--- Detailed Mode: Full address resolution ---")
print("  Window config transaction → Shows: WINDOW: Fn1 | WINDOW_0 = 0x12")
print("  CMD53 with known window → Shows: DATA RD: Fn1 | 0x20121234 (SDIO:0x1234) [4 bytes]")
print("  CMD53 with unknown window → Shows: DATA RD: Fn1 | UNKNOWN_WIN (SDIO:0x1234) [4 bytes]")

print("\n--- Debug Mode: Maximum detail ---")
print("  Same as Detailed mode plus all raw protocol information")

print("\n" + "=" * 60)
print("All tests completed!")
print("=" * 60)
