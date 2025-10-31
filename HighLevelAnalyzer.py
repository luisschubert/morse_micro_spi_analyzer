# High Level Analyzer for Morse Micro MM6108 SDIO-over-SPI Protocol
# Decodes SDIO CMD53 commands and responses

from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame, ChoicesSetting


class Hla(HighLevelAnalyzer):
    # Settings
    decode_level = ChoicesSetting(choices=('Basic', 'Detailed'))

    # Result types for different message patterns
    result_types = {
        'cmd53_read': {
            'format': 'CMD53 RD: {{data.func_desc}} | Addr:0x{{data.address}} Cnt:{{data.count}} {{data.mode}}'
        },
        'cmd53_write': {
            'format': 'CMD53 WR: {{data.func_desc}} | Addr:0x{{data.address}} Cnt:{{data.count}} {{data.mode}}'
        },
        'data_read': {
            'format': 'BULK RD: {{data.func_desc}} | 0x{{data.address}} [{{data.count}} bytes] {{data.mode}}'
        },
        'data_write': {
            'format': 'BULK WR: {{data.func_desc}} | 0x{{data.address}} [{{data.count}} bytes] {{data.mode}}'
        },
        'irq_read': {
            'format': 'IRQ RD: {{data.func_desc}} | 0x{{data.address}} [{{data.irq_bits}}]'
        },
        'irq_clear': {
            'format': 'IRQ CLR: {{data.func_desc}} | 0x{{data.address}} (val:0x{{data.value}}) [{{data.irq_bits}}]'
        },
        'card_control': {
            'format': 'CARD: {{data.func_desc}} | {{data.operation}}'
        },
        'unknown': {
            'format': 'Unknown: {{data.bytes}}'
        },
        'response': {
            'format': 'Response: {{data.info}}'
        }
    }

    # Known register addresses (from MM6108 driver)
    INT1_STS = 0x6050
    INT1_SET = 0x6054
    INT1_CLR = 0x6058
    
    # Common data buffer addresses
    KNOWN_ADDRS = {
        0x6050: "INT1_STS",
        0x6054: "INT1_SET", 
        0x6058: "INT1_CLR",
        0xC214: "DATA_BUF",
        0xC310: "DATA_BUF",
        0xBF40: "DATA_BUF",
        0xC110: "DATA_BUF",
    }
    
    # SDIO Function descriptions (from morse_driver/spi.c)
    FUNC_DESCRIPTIONS = {
        0: "Card Control (CCCR)",
        1: "Registers/Control (≤4B)",
        2: "Bulk Data (>4B)",
    }

    def __init__(self):
        '''Initialize the HLA'''
        self.mosi_buffer = []
        self.miso_buffer = []
        self.in_transaction = False
        self.transaction_start = None
        self.transaction_end = None

    def decode(self, frame: AnalyzerFrame):
        '''
        Process SPI frames and decode SDIO-over-SPI protocol
        '''
        
        # Handle enable/disable events
        if frame.type == 'enable':
            self.mosi_buffer = []
            self.miso_buffer = []
            self.in_transaction = True
            self.transaction_start = frame.start_time
            return None
        
        if frame.type == 'disable':
            self.transaction_end = frame.end_time
            if len(self.mosi_buffer) >= 7:
                result = self._decode_transaction()
                self.mosi_buffer = []
                self.miso_buffer = []
                self.in_transaction = False
                return result
            self.mosi_buffer = []
            self.miso_buffer = []
            self.in_transaction = False
            return None
        
        # Collect MOSI and MISO data
        if frame.type == 'result':
            if 'mosi' in frame.data:
                mosi = frame.data['mosi'][0] if isinstance(frame.data['mosi'], bytes) else frame.data['mosi']
                self.mosi_buffer.append(mosi)
            if 'miso' in frame.data:
                miso = frame.data['miso'][0] if isinstance(frame.data['miso'], bytes) else frame.data['miso']
                self.miso_buffer.append(miso)
        
        return None

    def _decode_irq_bits(self, irq_value):
        '''Decode IRQ status bits into human-readable description'''
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

    def _decode_transaction(self):
        '''Decode a complete SPI transaction'''
        
        # Look for command pattern: 0xFF, 0x75, ...
        # The command starts at index 1 typically
        if len(self.mosi_buffer) < 7:
            return None
        
        # Find the start of a command (0xFF followed by 0x75 or 0x40+cmd)
        cmd_start = -1
        for i in range(min(3, len(self.mosi_buffer) - 6)):
            if self.mosi_buffer[i] == 0xFF and (self.mosi_buffer[i+1] & 0x40):
                cmd_start = i
                break
        
        if cmd_start == -1:
            # No valid command found
            byte_str = ' '.join([f'{b:02X}' for b in self.mosi_buffer[:min(10, len(self.mosi_buffer))]])
            if len(self.mosi_buffer) > 10:
                byte_str += '...'
            return AnalyzerFrame('unknown', self.transaction_start, self.transaction_end, {
                'bytes': byte_str
            })
        
        # Extract command and argument
        try:
            cmd = self.mosi_buffer[cmd_start + 1]
            arg = (self.mosi_buffer[cmd_start + 2] << 24) | \
                  (self.mosi_buffer[cmd_start + 3] << 16) | \
                  (self.mosi_buffer[cmd_start + 4] << 8) | \
                  (self.mosi_buffer[cmd_start + 5])
            
            # Decode CMD53 format
            write_bit = (arg >> 31) & 0x1
            function = (arg >> 28) & 0x7
            block_mode = (arg >> 27) & 0x1
            opcode = (arg >> 26) & 0x1
            address = (arg >> 9) & 0x1FFFF
            count = arg & 0x1FF
            
            # Determine mode
            mode = 'Block' if block_mode else 'Byte'
            if opcode:
                mode += ',Incr'
            else:
                mode += ',Fixed'
            
            # Get function description
            func_desc = self.FUNC_DESCRIPTIONS.get(function, f"Fn{function}")
            
            # Extract MISO response data if available
            # After CMD53 (7 bytes), there's typically 4 bytes of response/padding, 
            # then the actual data starts at offset 11
            miso_data = None
            if len(self.miso_buffer) >= cmd_start + 15:
                # Data typically starts at cmd_start + 11
                miso_data = self.miso_buffer[cmd_start + 11:cmd_start + 15]
            
            # Special handling for Function 0 (Card Control)
            if function == 0:
                operation = f"Addr:0x{address:04X}"
                if write_bit:
                    operation += f" Write Cnt:{count}"
                else:
                    operation += f" Read Cnt:{count}"
                return AnalyzerFrame('card_control', self.transaction_start, self.transaction_end, {
                    'func_desc': func_desc,
                    'operation': operation
                })
            
            # Check for known register addresses
            if address == self.INT1_STS:
                # Decode IRQ status bits from MISO
                irq_bits_str = "N/A"
                if miso_data and len(miso_data) >= 4:
                    # IRQ status is 32-bit value in MISO (little-endian in response)
                    irq_value = (miso_data[3] << 24) | (miso_data[2] << 16) | (miso_data[1] << 8) | miso_data[0]
                    irq_bits_str = self._decode_irq_bits(irq_value)
                return AnalyzerFrame('irq_read', self.transaction_start, self.transaction_end, {
                    'address': f'{address:04X}',
                    'func_desc': func_desc,
                    'irq_bits': irq_bits_str
                })
            elif address == self.INT1_CLR:
                # Get value being written from MISO (echoed back)
                value_str = 'N/A'
                irq_bits_str = "N/A"
                if miso_data and len(miso_data) >= 4:
                    # IRQ clear value is 32-bit (little-endian)
                    irq_value = (miso_data[3] << 24) | (miso_data[2] << 16) | (miso_data[1] << 8) | miso_data[0]
                    value_str = f'{irq_value:08X}'
                    irq_bits_str = self._decode_irq_bits(irq_value)
                return AnalyzerFrame('irq_clear', self.transaction_start, self.transaction_end, {
                    'address': f'{address:04X}',
                    'func_desc': func_desc,
                    'value': value_str,
                    'irq_bits': irq_bits_str
                })
            
            # Check if this is a data buffer address or Function 2 (always bulk)
            is_data_buf = address in self.KNOWN_ADDRS and 'DATA' in self.KNOWN_ADDRS[address]
            is_bulk = function == 2 or (is_data_buf and count > 32)
            
            # Classify transaction type
            if write_bit:
                if is_bulk:
                    return AnalyzerFrame('data_write', self.transaction_start, self.transaction_end, {
                        'address': f'{address:04X}',
                        'count': str(count),
                        'mode': mode,
                        'func_desc': func_desc
                    })
                else:
                    return AnalyzerFrame('cmd53_write', self.transaction_start, self.transaction_end, {
                        'address': f'{address:04X}',
                        'count': str(count),
                        'mode': mode,
                        'func_desc': func_desc
                    })
            else:
                if is_bulk:
                    return AnalyzerFrame('data_read', self.transaction_start, self.transaction_end, {
                        'address': f'{address:04X}',
                        'count': str(count),
                        'mode': mode,
                        'func_desc': func_desc
                    })
                else:
                    return AnalyzerFrame('cmd53_read', self.transaction_start, self.transaction_end, {
                        'address': f'{address:04X}',
                        'count': str(count),
                        'mode': mode,
                        'func_desc': func_desc
                    })
        
        except (IndexError, ValueError):
            byte_str = ' '.join([f'{b:02X}' for b in self.mosi_buffer[:min(10, len(self.mosi_buffer))]])
            return AnalyzerFrame('unknown', self.transaction_start, self.transaction_end, {
                'bytes': byte_str
            })
