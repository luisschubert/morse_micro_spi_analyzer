# Morse Micro SPI Analyzer - Implementation Summary

## Overview

This Saleae Logic 2 High Level Analyzer decodes SDIO-over-SPI protocol used by Morse Micro MM6108 WiFi chips. It was developed based on real-world SPI captures from an RK3588 system running the Morse Micro driver.

## What It Does

The analyzer automatically decodes SPI transactions and identifies:

1. **SDIO Function Classification**
   - **Function 0 (Card Control)**: SDIO card initialization
   - **Function 1 (Registers/Control)**: Register access, IRQ operations (≤4 bytes)
   - **Function 2 (Bulk Data)**: Large WiFi packet transfers (>4 bytes)
   - Shows descriptive labels for each function type

2. **IRQ Operations (Function 1)**
   - Status reads (INT1_STS @ 0x6050)
   - Status clears (INT1_CLR @ 0x6058)
   - Shows the value being written to clear register

3. **Bulk Data Transfers (Function 2)**
   - Identifies large WiFi packet transfers
   - Shows address, size, and transfer mode
   - Helps identify efficient block-mode operations

4. **Generic CMD53 Operations**
   - All SDIO read/write commands
   - Function description, address, count, mode
   - Block vs byte mode, increment vs fixed addressing

## Files Included

| File | Purpose |
|------|---------|
| `HighLevelAnalyzer.py` | Main analyzer implementation |
| `extension.json` | Saleae extension metadata |
| `test_decoder.py` | Validation script for testing decoder logic |
| `README.md` | Quick start and overview |
| `USAGE_GUIDE.md` | Detailed usage instructions |
| `PATTERN_REFERENCE.md` | Pattern analysis and optimization guide |
| `SUMMARY.md` | This file |

## Validation

The analyzer has been validated against known transactions from your captures:

### Test Case A1/B1: IRQ Status Read
```
Input:  FF 75 14 C0 A0 04 89 ...
Output: "IRQ RD: Registers/Control (≤4B) | 0x6050"
✓ Correctly identifies INT1_STS read
✓ Shows Function 1 (Registers/Control)
```

### Test Case A2/B2: IRQ Clear
```
Input:  FF 75 94 C0 B0 04 CD ...
Output: "IRQ CLR: Registers/Control (≤4B) | 0x6058 (val:0xFE04)"
✓ Correctly identifies INT1_CLR write
✓ Extracts value from MISO data
✓ Shows Function 1 (Registers/Control)
```

### Test Case A3/B3: Data Buffer Access
```
Input:  FF 75 15 84 28 04 3F ...
Output: "CMD53 RD: Registers/Control (≤4B) | Addr:0xC214 Cnt:4 Byte,Incr"
✓ Correctly decodes address 0xC214
✓ Shows Function 1 (Registers/Control)
✓ Identifies small register access
```

### Test Case: Function 2 Bulk Transfer
```
Input:  Your Saleae capture showing "CMD53 RD: Fn2 Addr:0x9420 Cnt:3 Block,Incr"
Output: "BULK RD: Bulk Data (>4B) | 0x9420 [1536 bytes] Block,Incr"
✓ Correctly identifies Function 2 bulk transfer
✓ Calculates total bytes (3 blocks × 512 = 1536 bytes)
✓ Shows descriptive "Bulk Data (>4B)" label
```

## Key Features

### 1. Protocol Decoding
- Parses SDIO CMD53 command format per SDIO Specification Part E1
- Extracts all fields: R/W, function, block mode, opcode, address, count
- Validates command structure (looks for 0xFF + 0x4X pattern)

### 2. Address Classification
- Automatically recognizes known interrupt registers
- Identifies common data buffer addresses
- Differentiates control vs data operations

### 3. MISO Response Analysis
- Captures response data from slave
- Displays values written to registers
- Helps understand bidirectional communication

### 4. Performance Analysis Support
- Shows transaction duration (via frame timing)
- Enables measurement of inter-transaction delays
- Helps identify bottlenecks and optimization opportunities

## Technical Implementation

### Command Detection
The analyzer looks for the SDIO CMD53 pattern:
```
Byte 0: 0xFF (start/padding)
Byte 1: 0x7X (0x40 direction bit + 0x35 CMD53)
Bytes 2-5: 32-bit argument (big-endian)
Byte 6: CRC7
```

### Argument Decoding
```python
write_bit   = (arg >> 31) & 0x1      # Read or Write
function    = (arg >> 28) & 0x7      # SDIO function (0-7)
block_mode  = (arg >> 27) & 0x1      # Block vs byte mode
opcode      = (arg >> 26) & 0x1      # Increment vs fixed
address     = (arg >> 9) & 0x1FFFF   # 17-bit address
count       = arg & 0x1FF            # 9-bit count
```

### Classification Logic
```
IF address == 0x6050 → IRQ Status Read
IF address == 0x6058 → IRQ Clear
IF address in DATA_BUFS AND count > 32 → Data Read/Write
ELSE → Generic CMD53 Read/Write
```

## Usage Workflow

1. **Install** the extension in Saleae Logic 2
2. **Capture** SPI traffic (CLK, MOSI, MISO, CS)
3. **Add** SPI analyzer with correct settings
4. **Add** this HLA on top of the SPI analyzer
5. **Analyze** patterns and timing
6. **Export** to CSV for statistical analysis

## Insights from Your Data

Based on the patterns observed in your captures:

### Current Performance
- **Receive**: 6-7 Mbps (1-2.3ms between transactions)
- **Transmit**: 12-15 Mbps (600-800μs between transactions)
- **Bottleneck**: Inter-transaction delays and small transfer sizes

### Optimization Opportunities
1. **Increase minimum transfer size to 64 bytes** to always engage DMA
2. **Align all transfers to 8-byte boundaries** for RK3588 optimization
3. **Batch multiple operations** to reduce CS toggle overhead
4. **Use block mode** for transfers ≥512 bytes when possible

### Transaction Size Impact
Your testing showed dramatic throughput differences:
- 26 bytes: 1.74 Mbps (FIFO mode)
- 64 bytes: 4.40 Mbps (DMA mode)
- 8192 bytes: 19.70 Mbps (DMA + optimal size)

The analyzer will help you verify if driver changes achieve larger, more efficient transfers.

## Known Addresses

From `morse_driver/mm6108.c` and your captures:

**Interrupt Registers:**
- `0x6050`: INT1_STS - Read interrupt status
- `0x6054`: INT1_SET - Set interrupt (trigger)
- `0x6058`: INT1_CLR - Clear interrupt flags

**Data Buffers** (commonly observed):
- `0xBF40`, `0xC110`, `0xC214`, `0xC310`

You can add more addresses to `KNOWN_ADDRS` dictionary as you discover them.

## Future Enhancements

Potential improvements:
1. **Statistics tracking**: Count transaction types, calculate throughput
2. **Timing analysis**: Automatically flag slow transactions
3. **Protocol validation**: Verify CRC7 checksums
4. **Response decoding**: Parse SDIO R5 response format
5. **Custom address mapping**: User-configurable address labels

## Questions Answered

This analyzer helps answer your original questions:

✓ **"What are the other types of interactions?"**
  - IRQ status/clear (identified)
  - Data buffer reads/writes (classified)
  - Control register access (decoded)

✓ **"Can I identify patterns and delays?"**
  - Yes, transaction types are labeled
  - Use Logic 2 timing measurements between frames
  - Export to CSV for statistical analysis

✓ **"How can I optimize throughput?"**
  - Analyzer shows current transaction sizes
  - Compare before/after driver changes
  - Identify overhead from small transfers

## Support

The decoder is based on:
- SDIO Specification Part E1 (SDIO-over-SPI)
- Morse Micro driver source (`morse_driver/spi.c`)
- Your detailed analysis in `morse_question.md`

For issues or enhancements, modify `HighLevelAnalyzer.py` and reload the extension.

## Testing

Run the test decoder to validate:
```bash
python3 test_decoder.py
```

This will decode the example transactions and verify the logic matches your expected output.

