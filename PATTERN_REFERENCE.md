# SPI Transaction Pattern Reference

Quick reference for identifying and understanding MM6108 SPI patterns.

## Transaction Timing Patterns

### Idle State (100ms cycle)
```
Pattern: A-B pairs every 100ms, with 25ms internal spacing

Timeline:
|<----25ms---->|<---------75ms-------->|
    A1-A2            B1-B2

Where:
- A1/B1: IRQ Status Read (24 bytes)
- A2/B2: IRQ Clear (26 bytes)
```

### Receiving Data (AP → STA)
```
Pattern: Major transactions every 1-2.3 ms
         
Typical sequence:
1. IRQ Status Read (24 bytes)
2. IRQ Clear (26 bytes)  
3. Data Read (113-245 bytes typical, up to 2303 bytes)
```

### Transmitting Data (STA → AP)
```
Pattern: Major transactions every 600-800 μs (faster than RX)

Typical sequence:
1. Data Write (variable size)
2. IRQ Status Read (24 bytes)
3. IRQ Clear (26 bytes)
```

## Transaction Size Analysis

### Minimum Sizes
| Type | Size | Uses DMA? | Performance |
|------|------|-----------|-------------|
| IRQ Status | 24 bytes | No (FIFO) | ~1.74 Mbps |
| IRQ Clear | 26 bytes | No (FIFO) | ~1.74 Mbps |
| Small CMD53 | 56 bytes | No (FIFO) | ~1.69 Mbps |
| Medium CMD53 | 64 bytes | Yes | ~4.40 Mbps |
| Large CMD53 | 245 bytes | Yes | ~8.05 Mbps |
| Bulk transfer | 2303 bytes | Yes | ~10.04 Mbps |

### Optimal Sizes (8-byte aligned, RK3588)
| Size | DMA | Aligned | Throughput |
|------|-----|---------|------------|
| 4096 | Yes | Yes | ~18.30 Mbps |
| 8192 | Yes | Yes | ~19.70 Mbps |
| 16384 | Yes | Yes | ~20.77 Mbps |
| 32768 | Yes | Yes | ~21.19 Mbps |

## Decoded Command Examples

### IRQ Handling

**A1: Status Read**
```
MOSI: FF 75 14 C0 A0 04 89 ...
Decoded:
  - CMD53 READ
  - Function: 1
  - Address: 0x6050 (INT1_STS)
  - Count: 4 bytes
  - Mode: Byte, Increment
  
Analyzer Display: "IRQ Status Read: 0x6050"
```

**A2: Clear IRQ**
```
MOSI: FF 75 94 C0 B0 04 CD ...
MISO: FF FF FF FF FF FF FF FF 00 00 FF FE 04 00 00 00 CA F1 FF E5 0F FF
Decoded:
  - CMD53 WRITE
  - Function: 1
  - Address: 0x6058 (INT1_CLR)
  - Count: 4 bytes
  - Value being written: FE04
  
Analyzer Display: "IRQ Clear: 0x6058 (val:0xFE04)"
```

**A3: Data Buffer Read**
```
MOSI: FF 75 15 84 28 04 3F ...
Decoded:
  - CMD53 READ
  - Function: 1
  - Address: 0xC214 (DATA_BUF)
  - Count: 4 bytes
  - Mode: Byte, Increment
  
Analyzer Display: "CMD53 RD: Fn1 Addr:0xC214 Cnt:4 Byte,Incr"
```

## Performance Bottleneck Indicators

### 🔴 Bad: Small Transactions
```
IRQ Status Read: 0x6050           [24 bytes, ~1.7 Mbps]
  ↓ delay ~500μs
IRQ Clear: 0x6058                 [26 bytes, ~1.7 Mbps]
  ↓ delay ~1ms
DATA RD: 0xC214 [114 bytes]       [~4.4 Mbps]
  ↓ delay ~800μs
DATA RD: 0xC214 [114 bytes]       [~4.4 Mbps]

Effective throughput: ~6-7 Mbps (overhead dominated)
```

### 🟢 Good: Large Transactions
```
IRQ Status Read: 0x6050           [24 bytes]
  ↓ minimal delay
IRQ Clear: 0x6058                 [26 bytes]
  ↓ minimal delay
DATA RD: 0xC214 [2048 bytes]      [~20 Mbps]

Effective throughput: ~15-20 Mbps (data dominated)
```

## Delay Analysis

### Critical Timing Points
1. **IRQ assertion → Status Read**: Should be < 100μs
2. **Status Read → Clear**: Should be < 50μs
3. **Clear → Data Transfer**: Should be < 100μs
4. **Between data chunks**: Should be < 200μs

### Observed Delays (Your System)
- **Receive path**: 1-2.3ms between major transactions ⚠️
- **Transmit path**: 600-800μs between major transactions ⚠️

Both show room for improvement.

## Common Address Map

| Address | Purpose | Typical Access |
|---------|---------|----------------|
| 0x6050 | INT1_STS | Read (IRQ status) |
| 0x6054 | INT1_SET | Write (trigger IRQ) |
| 0x6058 | INT1_CLR | Write (clear IRQ) |
| 0xBF40 | Data Buffer | Read/Write |
| 0xC110 | Data Buffer | Read/Write |
| 0xC214 | Data Buffer | Read/Write |
| 0xC310 | Data Buffer | Read/Write |

## Optimization Checklist

When analyzing your captures, look for:

- [ ] Are IRQ status/clear using ≥64 byte transactions? (to use DMA)
- [ ] Are data transfers 8-byte aligned? (RK3588 optimization)
- [ ] Are inter-transaction delays < 200μs?
- [ ] Are bulk data transfers using block mode when possible?
- [ ] Can consecutive small transfers be combined?
- [ ] Is the SPI clock running at maximum speed (50MHz)?

## Decoder Statistics

To gather statistics from your captures:
1. Export analyzer output to CSV
2. Count transaction types
3. Calculate time spent in each category:
   - IRQ overhead
   - Data transfer
   - Inter-transaction delays
4. Identify optimization opportunities

Example Python analysis:
```python
import csv

irq_time = 0
data_time = 0
delay_time = 0

with open('export.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if 'IRQ' in row['type']:
            irq_time += float(row['duration'])
        elif 'DATA' in row['type']:
            data_time += float(row['duration'])

print(f"IRQ overhead: {irq_time/total*100:.1f}%")
print(f"Data transfer: {data_time/total*100:.1f}%")
```

