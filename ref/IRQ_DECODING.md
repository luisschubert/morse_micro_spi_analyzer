# IRQ Bit Decoding Feature

## Overview

The Morse Micro MM6108 SPI Analyzer now automatically decodes the 32-bit INT1_STS interrupt register, providing human-readable interrupt source information directly in your Saleae Logic 2 captures.

## What Was Added

### 1. Automatic IRQ Status Decoding

The analyzer now extracts and decodes the IRQ status value from MISO data during INT1_STS reads and INT1_CLR writes, showing exactly which interrupt sources are active.

### 2. Comprehensive Bit Definitions

Based on the Morse Micro driver source code (`morse_driver/hw.h`, `morse_driver/pager_if.h`, `morse_driver/chip_if.h`):

| Bits | Name | Description |
|------|------|-------------|
| 0-13 | **Pager0-13** | Data available from chip or TX buffer returns for each pager |
| 14 | *Reserved* | Not used |
| 15 | **TxStatus** | TX status available (bypass mode) |
| 16 | *Reserved* | Not used |
| 17-24 | **Beacon0-7** | Beacon ready for VIF (Virtual Interface) 0-7 |
| 25-26 | **NDP0-1** | NDP probe request for VIF 0-1 |
| 27 | **HW_STOP** | Hardware stop notification |
| 28-31 | *Reserved* | Not defined |

### 3. Enhanced Output Format

**Before:**
```
IRQ RD: Registers/Control (≤4B) | 0x6050
IRQ CLR: Registers/Control (≤4B) | 0x6058 (val:0xFE04)
```

**After (with IRQ decoding):**
```
IRQ RD: Registers/Control (≤4B) | 0x6050 [Pager1,Pager2,Pager3,Pager4,Pager5,Pager6,Pager7,Pager10]
IRQ CLR: Registers/Control (≤4B) | 0x6058 (val:0x000004FE) [Pager1,Pager2,Pager3,Pager4,Pager5,Pager6,Pager7,Pager10]
```

## Real-World Example

From your actual SPI capture (`morse_question.md`):

### Transaction A1 - IRQ Status Read
```
MOSI: FF 75 14 C0 A0 04 89 FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF
MISO: FF FF FF FF FF FF FF FF 00 00 FF FE 04 00 00 00 CA F1 FF FF FF FF FF FF
                                       ^^^^^^^^^^^^^^
                                       IRQ Value (little-endian)
```

**Decoded:**
- **Raw Value**: `0x000004FE`
- **Binary**: `0000 0000 0000 0000 0000 0100 1111 1110`
- **Active Bits**: 1, 2, 3, 4, 5, 6, 7, 10
- **Meaning**: Pagers 1-7 and 10 have data ready or buffer returns pending

### Transaction A2 - IRQ Clear
```
MOSI: FF 75 94 C0 B0 04 CD FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF FF
MISO: FF FF FF FF FF FF FF FF 00 00 FF FE 04 00 00 00 CA F1 FF E5 0F FF
```

**Decoded:**
- Same IRQ bits (`0x000004FE`) being cleared
- Driver acknowledges these 8 pager interrupts

## How It Works

### Technical Implementation

1. **MISO Data Extraction**
   - After CMD53 command (7 bytes) + response padding (4 bytes)
   - Actual data starts at byte offset 11
   - Reads 4 bytes in little-endian format

2. **Bit Decoding**
   - Checks each bit position against known definitions
   - Formats active bits as human-readable names
   - Handles multiple simultaneous interrupts

3. **Driver Correlation**
   - Pager interrupts (0-13) → `morse_pager_irq_handler()`
   - Beacon interrupts (17-24) → `morse_beacon_irq_handle()`
   - NDP interrupts (25-26) → `morse_ndp_probe_req_resp_irq_handle()`
   - HW stop (27) → `to_host_hw_stop_irq_handle()`

## Usage in Analysis

### Identifying Data Transfer Activity

When you see:
```
IRQ RD: 0x6050 [Pager1,Pager2,Pager3,Pager4,Pager5,Pager6,Pager7,Pager10]
```

This tells you:
- **Multiple pagers active** → High data throughput scenario
- **Sequential pagers (1-7)** → Likely RX data from chip
- **Pager 10** → Could be TX buffer return

### Debugging IRQ Storms

If you see the same IRQ bits repeatedly without being cleared:
```
IRQ RD: 0x6050 [Pager1] ... (many times)
IRQ CLR: 0x6058 (val:0x00000000) [None]  ← Problem! Not clearing Pager1
```

This indicates a driver bug where interrupts aren't being properly acknowledged.

### Performance Analysis

Count pager interrupt frequency to understand workload:
- **High pager activity** → Driver spending time processing data
- **Beacon interrupts** → AP mode operation
- **TxStatus interrupts** → TX-heavy workload

## Files Modified

1. **HighLevelAnalyzer.py**
   - Added `_decode_irq_bits()` method
   - Enhanced IRQ transaction detection to extract MISO data
   - Updated result format strings

2. **test_decoder.py**
   - Added `decode_irq_bits()` function
   - Updated test cases with MISO data
   - Validates IRQ decoding against known values

3. **Documentation**
   - **README.md**: IRQ bit definitions and examples
   - **CHANGELOG.md**: Version 0.3.0 release notes
   - **SUMMARY.md**: Validation with IRQ examples
   - **USAGE_GUIDE.md**: Interpretation guide with real patterns
   - **extension.json**: Version bump to 0.3.0

## Testing

Run the test suite to validate:
```bash
cd morse_micro_spi_analyzer
python3 test_decoder.py
```

Expected output shows correct decoding of `0x000004FE` into pager bits 1-7 and 10.

## Future Enhancements

Potential additions:
1. **Statistics**: Count interrupt sources over time
2. **IRQ Rate Analysis**: Calculate interrupts per second
3. **Correlation**: Link IRQ bits to subsequent data transfers
4. **Alerts**: Flag unusual IRQ patterns (e.g., stuck bits)
5. **INT2_STS Support**: Decode secondary interrupt register if needed

## References

- **Morse Micro Driver**: `morse_driver/hw.h`, `morse_driver/hw.c`
- **Pager Interface**: `morse_driver/pager_if.h`, `morse_driver/pager_if.c`
- **Chip Interface**: `morse_driver/chip_if.h`
- **Your Analysis**: `morse_ljs_docs/morse_cursor_tx_delays.md`

## Version

- **Version**: 0.3.0
- **Date**: 2024
- **Author**: Luis Schubert

