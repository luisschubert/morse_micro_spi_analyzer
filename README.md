# Morse Micro MM6108 SPI Analyzer

High-level analyzer extension for Saleae Logic 2 to decode SDIO-over-SPI protocol used by Morse Micro MM6108 WiFi chips.

## Features

- Decodes SDIO CMD53 commands (read/write operations)
- Identifies IRQ status read and clear operations
- Displays address, function number, transfer count, and mode
- Distinguishes between block/byte mode and fixed/increment addressing

## Usage

1. Load this extension in Saleae Logic 2
2. Add an SPI analyzer to your capture
3. Add this High Level Analyzer on top of the SPI analyzer
4. Configure settings if needed (Basic vs Detailed mode)

## Protocol Details

The analyzer decodes the SDIO-over-SPI protocol structure:

### Command Format (7+ bytes)
- Byte 0: 0xFF (start marker)
- Byte 1: Direction (0x40) | Command Index
- Bytes 2-5: 32-bit argument (big-endian)
  - Bit 31: Write (1) or Read (0)
  - Bits 30-28: Function number (0-7)
  - Bit 27: Block mode (1) or Byte mode (0)
  - Bit 26: Opcode (1=increment, 0=fixed address)
  - Bits 25-9: 17-bit address
  - Bits 8-0: 9-bit byte/block count
- Byte 6: CRC7 | 0x01

### Known Register Addresses
- `0x6050`: INT1_STS (Interrupt Status)
- `0x6054`: INT1_SET (Interrupt Set)
- `0x6058`: INT1_CLR (Interrupt Clear)

## Output Examples

With function descriptions and IRQ bit decoding:

- `IRQ RD: Registers/Control (≤4B) | 0x6050 [Pager1,Pager2,Pager3,Pager4,Pager5,Pager6,Pager7,Pager10]`
- `IRQ CLR: Registers/Control (≤4B) | 0x6058 (val:0x000004FE) [Pager1,Pager2,Pager3,Pager4,Pager5,Pager6,Pager7,Pager10]`
- `BULK RD: Bulk Data (>4B) | 0x9420 [1536 bytes] Block,Incr`
- `CMD53 WR: Registers/Control (≤4B) | Addr:0x4200 Cnt:245 Byte,Incr`
- `CARD: Card Control (CCCR) | Addr:0x0004 Write Cnt:1`

### Function Descriptions

The analyzer automatically labels each function:
- **Function 0**: Card Control (CCCR) - Used for SDIO card initialization
- **Function 1**: Registers/Control (≤4B) - Used for register access and small transfers
- **Function 2**: Bulk Data (>4B) - Used for large WiFi packet transfers

### IRQ Bit Decoding

The analyzer automatically decodes the 32-bit INT1_STS register into human-readable interrupt sources:

- **Bits 0-13**: `Pager0` through `Pager13` - Data available or TX buffer returns for each pager
- **Bit 15**: `TxStatus` - TX status available (bypass mode)
- **Bits 17-24**: `Beacon0` through `Beacon7` - Beacon ready for VIF 0-7
- **Bits 25-26**: `NDP0`, `NDP1` - NDP probe request for VIF 0-1  
- **Bit 27**: `HW_STOP` - Hardware stop notification

Example: `0x000004FE` decodes to `Pager1,Pager2,Pager3,Pager4,Pager5,Pager6,Pager7,Pager10`

## Development

Based on analysis of Morse Micro driver (`morse_driver/spi.c`, `morse_driver/hw.h`) and SDIO specification Part E1.