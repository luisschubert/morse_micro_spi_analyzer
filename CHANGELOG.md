# Changelog

## Version 0.2.0 - Function Descriptions Added

### New Features

**Function-Aware Decoding**
- Added automatic SDIO function classification with descriptive labels
- Function 0: "Card Control (CCCR)" - SDIO card initialization
- Function 1: "Registers/Control (≤4B)" - Register access, IRQ operations
- Function 2: "Bulk Data (>4B)" - Large WiFi packet transfers

### Updated Output Formats

**Before:**
```
CMD53 RD: Fn1 Addr:0x6050 Cnt:4 Byte,Incr
CMD53 RD: Fn2 Addr:0x9420 Cnt:3 Block,Incr
IRQ Status Read: 0x6050
IRQ Clear: 0x6058
```

**After (with function descriptions):**
```
CMD53 RD: Registers/Control (≤4B) | Addr:0x6050 Cnt:4 Byte,Incr
BULK RD: Bulk Data (>4B) | 0x9420 [1536 bytes] Block,Incr
IRQ RD: Registers/Control (≤4B) | 0x6050
IRQ CLR: Registers/Control (≤4B) | 0x6058 (val:0xFE04)
```

### Enhanced Features

1. **Bulk Transfer Detection**
   - Function 2 transactions automatically labeled as "BULK RD/WR"
   - Shows total byte count for block transfers
   - Example: 3 blocks displayed as "[1536 bytes]"

2. **Card Control Operations**
   - New transaction type for Function 0 operations
   - Displays as "CARD: Card Control (CCCR) | ..."
   - Used during initialization sequences

3. **Improved Classification**
   - Function 2 always treated as bulk data path
   - Function 1 for control/register operations
   - Better distinction between data and control planes

### Documentation Updates

- **README.md**: Updated with new output examples and function descriptions
- **USAGE_GUIDE.md**: Added function selection logic and usage patterns
- **SUMMARY.md**: Enhanced validation examples with function labels
- **test_decoder.py**: Added Function 2 test case

### Technical Changes

**HighLevelAnalyzer.py:**
- Added `FUNC_DESCRIPTIONS` dictionary mapping function numbers to descriptions
- Updated all `result_types` to include `func_desc` field
- Enhanced `_decode_transaction()` to classify based on function number
- Added special handling for Function 0 (card control) operations
- Improved bulk transfer detection using function number

### Why This Matters

The MM6108 uses different SDIO functions for different purposes:

1. **Performance Analysis**: Function 2 usage indicates efficient bulk transfers
2. **Debugging**: Clearly see control vs data path operations
3. **Driver Understanding**: Matches the `morse_driver/spi.c` logic where:
   - Transfers ≤4 bytes use Function 1
   - Transfers >4 bytes use Function 2
   - Initialization uses Function 0

### Example Interpretation

When you see:
```
IRQ RD: Registers/Control (≤4B) | 0x6050          ← Fn1: Small control operation
IRQ CLR: Registers/Control (≤4B) | 0x6058         ← Fn1: Clear interrupt
BULK RD: Bulk Data (>4B) | 0x9420 [1536 bytes]   ← Fn2: Large packet transfer
```

You now know:
- First two are control operations (Function 1, ≤4 bytes)
- Last one is bulk data (Function 2, 1536 bytes = 3 × 512-byte blocks)
- This is an efficient receive sequence!

---

## Version 0.1.0 - Initial Release

- Basic SDIO CMD53 decoding
- IRQ status/clear detection
- Data transfer classification
- Register address recognition
- Support for all three SDIO functions (0, 1, 2)

