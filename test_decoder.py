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

