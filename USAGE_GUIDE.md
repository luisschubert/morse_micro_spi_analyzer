# Morse Micro SPI Analyzer - Usage Guide

## Installation

1. Open Saleae Logic 2
2. Go to Extensions → Load Extension
3. Select the `morse_micro_spi_analyzer` directory

## Setup

1. **Configure SPI Analyzer**
   - Add an SPI analyzer to your capture
   - Configure for your hardware:
     - Clock: Your SPI CLK signal
     - MOSI: Master Out Slave In
     - MISO: Master In Slave Out
     - Enable: Chip Select (active low typically)
     - Mode: 0 (CPOL=0, CPHA=0)
     - Bits per Transfer: 8

2. **Add High Level Analyzer**
   - Click the "+" button next to your SPI analyzer
   - Select "Morse Micro MM6108 SPI Analyzer"
   - Choose decode level (Basic or Detailed)

## Understanding the Output

### Transaction Types

The analyzer will decode and label transactions automatically with function descriptions:

#### IRQ Operations
- **IRQ RD**: Reading the interrupt status register (0x6050)
  ```
  IRQ RD: Registers/Control (≤4B) | 0x6050 [Pager1,Pager2,Pager3,Pager4,Pager5,Pager6,Pager7,Pager10]
  ```
  The analyzer automatically decodes the 32-bit IRQ value showing which interrupt sources are active.
  
- **IRQ CLR**: Clearing interrupt flags (0x6058)
  ```
  IRQ CLR: Registers/Control (≤4B) | 0x6058 (val:0x000004FE) [Pager1,Pager2,Pager3,Pager4,Pager5,Pager6,Pager7,Pager10]
  ```
  Shows both the raw hex value and the decoded interrupt bits being cleared.

#### Bulk Data Transfers (Function 2)
- **BULK RD**: Large data reads from buffer addresses
  ```
  BULK RD: Bulk Data (>4B) | 0x9420 [1536 bytes] Block,Incr
  ```
- **BULK WR**: Large data writes to buffer addresses
  ```
  BULK WR: Bulk Data (>4B) | 0xC310 [512 bytes] Block,Incr
  ```

#### Generic CMD53 Operations (Function 1)
- **CMD53 RD**: Generic SDIO read commands
  ```
  CMD53 RD: Registers/Control (≤4B) | Addr:0x2800 Cnt:4 Byte,Incr
  ```
- **CMD53 WR**: Generic SDIO write commands
  ```
  CMD53 WR: Registers/Control (≤4B) | Addr:0x4200 Cnt:8 Byte,Incr
  ```

#### Card Control Operations (Function 0)
- **CARD**: SDIO card initialization and configuration
  ```
  CARD: Card Control (CCCR) | Addr:0x0004 Write Cnt:1
  ```

### Decoding Fields

Each transaction shows:
- **Function Description**: Automatically identified based on function number
  - **Card Control (CCCR)**: Function 0 - SDIO card initialization
  - **Registers/Control (≤4B)**: Function 1 - Register access, IRQ, small transfers
  - **Bulk Data (>4B)**: Function 2 - Large WiFi packet transfers
- **Address**: 17-bit address being accessed (shown in hex)
- **Count (Cnt)**: Number of bytes or blocks to transfer
- **Mode**: 
  - Block/Byte: Transfer mode (Block = 512 bytes, Byte = 1 byte)
  - Incr/Fixed: Address increment (Incr = sequential memory, Fixed = FIFO)
- **IRQ Bits** (for INT1_STS/INT1_CLR only): Decoded interrupt sources
  - **Pager0-13**: Data available or TX buffer returns for each pager
  - **TxStatus**: TX status available (bypass mode)
  - **Beacon0-7**: Beacon ready for VIF 0-7
  - **NDP0-1**: NDP probe request for VIF 0-1
  - **HW_STOP**: Hardware stop notification

## Analyzing Patterns

### Identifying Performance Issues

1. **IRQ Response Time**
   - Measure time between IRQ assertions and Status Read
   - Look for delays > 1ms

2. **Transfer Patterns**
   - **Good**: Large block transfers (512+ bytes) with minimal gaps
   - **Bad**: Many small byte-mode transfers with large inter-transaction delays

3. **Throughput Analysis**
   - Use Logic 2's measurement tools to calculate:
     - Transaction duration
     - Inter-transaction delays
     - Effective data rate

### Common Transaction Sequences

**Normal IRQ Handling (Function 1):**
```
IRQ RD: Registers/Control (≤4B) | 0x6050 [Pager1,Pager2,Pager3,Pager4,Pager5,Pager6,Pager7,Pager10]
IRQ CLR: Registers/Control (≤4B) | 0x6058 (val:0x000004FE) [Pager1,Pager2,Pager3,Pager4,Pager5,Pager6,Pager7,Pager10]
```
*Interpretation*: Multiple pagers (1-7, 10) have data ready. These will be processed by the driver's work handler.

**Receive Data Pattern (Function 1 → Function 2):**
```
IRQ RD: Registers/Control (≤4B) | 0x6050 [Pager2,Pager5]          (Fn1: Check status - Pagers 2,5 active)
IRQ CLR: Registers/Control (≤4B) | 0x6058 (val:0x00000024) [Pager2,Pager5]   (Fn1: Clear IRQ)
BULK RD: Bulk Data (>4B) | 0x9420 [1536 bytes] Block,Incr   (Fn2: Read packet from pager)
```
*Interpretation*: IRQ triggered by pagers 2 and 5. Driver reads status, clears interrupts, then processes data.

**Transmit Pattern (Function 2 → Function 1):**
```
BULK WR: Bulk Data (>4B) | 0xC310 [512 bytes] Block,Incr    (Fn2: Write packet)
IRQ RD: Registers/Control (≤4B) | 0x6050 [TxStatus]          (Fn1: Check status - TX complete)
IRQ CLR: Registers/Control (≤4B) | 0x6058 (val:0x00008000) [TxStatus]   (Fn1: Clear TX status IRQ)
```
*Interpretation*: TX status interrupt (bit 15) indicates transmission completed. Driver acknowledges and can send next packet.

**Beacon Pattern:**
```
IRQ RD: Registers/Control (≤4B) | 0x6050 [Beacon0,Pager1]
IRQ CLR: Registers/Control (≤4B) | 0x6058 (val:0x00020002) [Beacon0,Pager1]
```
*Interpretation*: Beacon for VIF 0 (bit 17) is ready along with data on pager 1.

**Initialization (Function 0):**
```
CARD: Card Control (CCCR) | Addr:0x0004 Write Cnt:1  (Enable interrupts)
CARD: Card Control (CCCR) | Addr:0x0007 Write Cnt:1  (Configure card)
```

## Troubleshooting

### "Unknown" Transactions
If you see many unknown transactions:
- Check SPI polarity/phase settings
- Verify chip select is configured correctly
- Ensure clock speed is within capture limits

### Missing Transactions
- Check your trigger settings
- Ensure buffer depth is sufficient
- Verify all SPI signals are properly connected

## Technical Details

### SDIO Function Selection

The MM6108 driver automatically selects the appropriate function based on transfer size:

**From `morse_driver/spi.c` (lines 812-822):**
```c
if (size > sizeof(u32)) {
    func_to_use = SPI_SDIO_FUNC_2;  // Bulk transfers (>4 bytes)
} else if (mspi->bulk_addr_base == calculated_base_address) {
    func_to_use = SPI_SDIO_FUNC_2;  // Already using bulk address space
} else {
    func_to_use = SPI_SDIO_FUNC_1;  // Register access (≤4 bytes)
}
```

**Function Usage:**
- **Function 0**: Card initialization only (CMD52 single-byte operations)
- **Function 1**: Register reads/writes and control operations (≤4 bytes)
- **Function 2**: All bulk data transfers (>4 bytes) including WiFi packets

This separation allows independent address spaces and optimized data paths.

### SDIO CMD53 Format
The analyzer decodes the 48-bit SDIO CMD53 command:
- Byte 0: Start marker (0xFF)
- Byte 1: Direction (0x40) | Command (0x35 for CMD53)
- Bytes 2-5: 32-bit argument
  - [31]: R/W bit (0=read, 1=write)
  - [30:28]: Function number
  - [27]: Block mode flag
  - [26]: Address increment flag
  - [25:9]: 17-bit address
  - [8:0]: Byte/block count
- Byte 6: CRC7 + stop bit

### Known Registers
From `morse_driver/mm6108.c`:
- `0x6050`: INT1_STS - Interrupt Status
- `0x6054`: INT1_SET - Interrupt Set
- `0x6058`: INT1_CLR - Interrupt Clear

### Data Buffer Addresses
Commonly observed buffer addresses:
- `0xC110`, `0xC214`, `0xC310`: Data buffers
- `0xBF40`: Data buffer

## Tips for Optimization

Based on your RK3588 analysis:

1. **Align transfers to 8-byte boundaries** for optimal DMA performance
2. **Use transfers ≥64 bytes** to ensure DMA is engaged (not FIFO mode)
3. **Minimize inter-transaction delays** by batching operations
4. **Look for patterns** where multiple small transfers could be combined

## Export and Analysis

You can export the decoded data:
1. Right-click on the analyzer
2. Select "Export to CSV"
3. Analyze patterns in spreadsheet software or custom scripts

## Further Development

To add custom address decoding:
1. Edit `HighLevelAnalyzer.py`
2. Add entries to the `KNOWN_ADDRS` dictionary
3. Reload the extension in Logic 2

