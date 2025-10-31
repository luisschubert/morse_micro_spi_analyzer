# High Level Analyzer for Morse Micro MM6108 SDIO-over-SPI Protocol
# Decodes SDIO CMD53 commands and responses

from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame, ChoicesSetting


class Hla(HighLevelAnalyzer):
    # Settings
    decode_level = ChoicesSetting(choices=('Basic', 'Detailed', 'Debug'))

    # Result types for different message patterns
    result_types = {
        'cmd52_read': {
            'format': 'CMD52 RD: {{data.func_desc}} | Addr:0x{{data.address}} Data:0x{{data.data}}'
        },
        'cmd52_write': {
            'format': 'CMD52 WR: {{data.func_desc}} | Addr:0x{{data.address}} Data:0x{{data.data}}'
        },
        'window_config': {
            'format': 'WINDOW: {{data.func_desc}} | {{data.reg_name}} = 0x{{data.value}}'
        },
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
        'data_access': {
            'format': 'DATA: {{data.func_desc}} {{data.rw}} | Addr:0x{{data.address}} Cnt:{{data.count}}'
        },
        'control_access': {
            'format': 'CTRL: {{data.func_desc}} {{data.rw}} | Addr:0x{{data.address}}'
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
    
    # Window configuration registers (SDIO address windowing)
    WINDOW_0 = 0x10000  # bits [23:16] of 32-bit address
    WINDOW_1 = 0x10001  # bits [31:24] of 32-bit address
    WINDOW_CONFIG = 0x10002  # access size (1, 2, or 4 bytes)
    
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
        
        # Window state tracking (None = unknown until observed)
        self.func1_window = {'window_0': None, 'window_1': None, 'config': None}
        self.func2_window = {'window_0': None, 'window_1': None, 'config': None}

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

    def update_window_state(self, function, register_addr, value):
        '''Update window state for a function when CMD52 writes to window registers'''
        window = self.func1_window if function == 1 else self.func2_window
        
        if register_addr == self.WINDOW_0:
            window['window_0'] = value
        elif register_addr == self.WINDOW_1:
            window['window_1'] = value
        elif register_addr == self.WINDOW_CONFIG:
            window['config'] = value
    
    def is_window_known(self, function):
        '''Check if all window registers are known for a function'''
        window = self.func1_window if function == 1 else self.func2_window
        return all(v is not None for v in window.values())
    
    def calculate_full_address(self, function, sdio_address):
        '''Calculate 32-bit address from window state + SDIO address'''
        if not self.is_window_known(function):
            return None
        
        window = self.func1_window if function == 1 else self.func2_window
        # Combine: (window_1 << 24) | (window_0 << 16) | (sdio_address & 0xFFFF)
        full_addr = (window['window_1'] << 24) | (window['window_0'] << 16) | (sdio_address & 0xFFFF)
        return full_addr
    
    def find_r1_response(self, miso_buffer, start_offset):
        '''Find R1 response (0x00) in MISO buffer, return data start position'''
        # Search for first 0x00 byte after command (R1 success response)
        for i in range(start_offset, min(start_offset + 10, len(miso_buffer))):
            if miso_buffer[i] != 0xFF:
                if miso_buffer[i] == 0x00:
                    # R1 success, data starts after R1 (skip potential double 0x00)
                    data_start = i + 1
                    if data_start < len(miso_buffer) and miso_buffer[data_start] == 0x00:
                        data_start += 1
                    return data_start
                else:
                    # R1 error response
                    return None
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

    def _decode_cmd52(self, cmd_start, arg, function, address, data, write_bit):
        '''Decode CMD52 transaction'''
        func_desc = self.FUNC_DESCRIPTIONS.get(function, f"Fn{function}")
        
        # Check if this is a window configuration register write
        if write_bit and address in [self.WINDOW_0, self.WINDOW_1, self.WINDOW_CONFIG]:
            # Update window state tracking for Detailed mode
            if function in [1, 2]:
                self.update_window_state(function, address, data)
            
            # Determine register name
            if address == self.WINDOW_0:
                reg_name = "WINDOW_0"
            elif address == self.WINDOW_1:
                reg_name = "WINDOW_1"
            else:
                reg_name = "CONFIG"
            
            return AnalyzerFrame('window_config', self.transaction_start, self.transaction_end, {
                'func_desc': func_desc,
                'reg_name': reg_name,
                'value': f'{data:02X}'
            })
        
        # Regular CMD52 - show based on mode
        if self.decode_level == 'Basic':
            return AnalyzerFrame('control_access', self.transaction_start, self.transaction_end, {
                'func_desc': func_desc,
                'rw': 'WR' if write_bit else 'RD',
                'address': f'{address:04X}'
            })
        else:
            # Detailed/Debug mode
            frame_type = 'cmd52_write' if write_bit else 'cmd52_read'
            return AnalyzerFrame(frame_type, self.transaction_start, self.transaction_end, {
                'func_desc': func_desc,
                'address': f'{address:05X}',
                'data': f'{data:02X}'
            })
    
    def _decode_cmd53(self, cmd_start, arg, function, address, count, write_bit, block_mode, opcode):
        '''Decode CMD53 transaction'''
        func_desc = self.FUNC_DESCRIPTIONS.get(function, f"Fn{function}")
        
        # Determine mode string
        mode = 'Block' if block_mode else 'Byte'
        if opcode:
            mode += ',Incr'
        else:
            mode += ',Fixed'
        
        # In Basic mode, just classify as data access
        if self.decode_level == 'Basic':
            return AnalyzerFrame('data_access', self.transaction_start, self.transaction_end, {
                'func_desc': func_desc,
                'rw': 'WR' if write_bit else 'RD',
                'address': f'{address:04X}',
                'count': str(count if not block_mode else count * 512)
            })
        
        # Detailed/Debug mode - calculate full address if window is known
        full_address = None
        if function in [1, 2]:
            full_address = self.calculate_full_address(function, address)
        
        # Format address display
        if full_address is not None:
            addr_str = f'{full_address:08X}'
            addr_display = f'{addr_str} (SDIO:0x{address:04X})'
        else:
            addr_display = f'UNKNOWN_WIN (SDIO:0x{address:04X})'
        
        # Extract MISO response data for reads
        miso_data = None
        if not write_bit:
            r1_pos = self.find_r1_response(self.miso_buffer, cmd_start + 7)
            if r1_pos and r1_pos < len(self.miso_buffer):
                # Look for start token 0xFE
                for i in range(r1_pos, min(r1_pos + 10, len(self.miso_buffer))):
                    if self.miso_buffer[i] == 0xFE:
                        # Data starts after token
                        if i + 1 + 4 <= len(self.miso_buffer):
                            miso_data = self.miso_buffer[i + 1:i + 1 + 4]
                        break
                
                # Fallback to old method if token not found
                if miso_data is None and r1_pos + 4 <= len(self.miso_buffer):
                    miso_data = self.miso_buffer[r1_pos:r1_pos + 4]
        
        # Check for IRQ registers (use full address if known)
        check_addr = full_address if full_address is not None else address
        if check_addr == self.INT1_STS:
            irq_bits_str = "N/A"
            if miso_data and len(miso_data) >= 4:
                irq_value = (miso_data[3] << 24) | (miso_data[2] << 16) | (miso_data[1] << 8) | miso_data[0]
                irq_bits_str = self._decode_irq_bits(irq_value)
            return AnalyzerFrame('irq_read', self.transaction_start, self.transaction_end, {
                'address': addr_display if full_address is not None else f'{address:04X}',
                'func_desc': func_desc,
                'irq_bits': irq_bits_str
            })
        elif check_addr == self.INT1_CLR:
            value_str = 'N/A'
            irq_bits_str = "N/A"
            if miso_data and len(miso_data) >= 4:
                irq_value = (miso_data[3] << 24) | (miso_data[2] << 16) | (miso_data[1] << 8) | miso_data[0]
                value_str = f'{irq_value:08X}'
                irq_bits_str = self._decode_irq_bits(irq_value)
            return AnalyzerFrame('irq_clear', self.transaction_start, self.transaction_end, {
                'address': addr_display if full_address is not None else f'{address:04X}',
                'func_desc': func_desc,
                'value': value_str,
                'irq_bits': irq_bits_str
            })
        
        # Regular data transaction
        is_data_buf = address in self.KNOWN_ADDRS and 'DATA' in self.KNOWN_ADDRS[address]
        is_bulk = function == 2 or (is_data_buf and count > 32)
        
        if write_bit:
            if is_bulk:
                return AnalyzerFrame('data_write', self.transaction_start, self.transaction_end, {
                    'address': addr_display,
                    'count': str(count if not block_mode else count * 512),
                    'mode': mode,
                    'func_desc': func_desc
                })
            else:
                return AnalyzerFrame('cmd53_write', self.transaction_start, self.transaction_end, {
                    'address': addr_display,
                    'count': str(count),
                    'mode': mode,
                    'func_desc': func_desc
                })
        else:
            if is_bulk:
                return AnalyzerFrame('data_read', self.transaction_start, self.transaction_end, {
                    'address': addr_display,
                    'count': str(count if not block_mode else count * 512),
                    'mode': mode,
                    'func_desc': func_desc
                })
            else:
                return AnalyzerFrame('cmd53_read', self.transaction_start, self.transaction_end, {
                    'address': addr_display,
                    'count': str(count),
                    'mode': mode,
                    'func_desc': func_desc
                })
    
    def _decode_transaction(self):
        '''Decode a complete SPI transaction'''
        
        # Look for command pattern: 0xFF, 0x74 (CMD52) or 0x75 (CMD53), ...
        if len(self.mosi_buffer) < 7:
            return None
        
        # Find the start of a command (0xFF followed by 0x40+cmd)
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
            
            # Determine command type: CMD52 (0x74) or CMD53 (0x75)
            # CMD52: 0x40 | 52 = 0x74
            # CMD53: 0x40 | 53 = 0x75
            
            if cmd == 0x74:
                # CMD52: Single byte read/write
                # Argument format (from spi.c:441-474):
                # bit 31: R/W (1 = Write, 0 = Read)
                # bits 30-28: Function number
                # bit 27: RAW flag (unused)
                # bits 25-9: 17-bit address
                # bits 8-0: 8-bit data
                write_bit = (arg >> 31) & 0x1
                function = (arg >> 28) & 0x7
                address = (arg >> 9) & 0x1FFFF
                data = arg & 0xFF
                
                return self._decode_cmd52(cmd_start, arg, function, address, data, write_bit)
            
            elif cmd == 0x75:
                # CMD53: Block/byte read/write
                # Argument format (standard SDIO):
                # bit 31: R/W (1 = Write, 0 = Read)
                # bits 30-28: Function number
                # bit 27: Block mode (1) or Byte mode (0)
                # bit 26: OP Code (1 = Increment, 0 = Fixed)
                # bits 25-9: 17-bit address
                # bits 8-0: Count (blocks or bytes)
                write_bit = (arg >> 31) & 0x1
                function = (arg >> 28) & 0x7
                block_mode = (arg >> 27) & 0x1
                opcode = (arg >> 26) & 0x1
                address = (arg >> 9) & 0x1FFFF
                count = arg & 0x1FF
                
                # Special handling for Function 0 (Card Control)
                if function == 0:
                    func_desc = self.FUNC_DESCRIPTIONS.get(function, f"Fn{function}")
                    operation = f"Addr:0x{address:04X}"
                    if write_bit:
                        operation += f" Write Cnt:{count}"
                    else:
                        operation += f" Read Cnt:{count}"
                    return AnalyzerFrame('card_control', self.transaction_start, self.transaction_end, {
                        'func_desc': func_desc,
                        'operation': operation
                    })
                
                return self._decode_cmd53(cmd_start, arg, function, address, count, write_bit, block_mode, opcode)
            
            else:
                # Unknown command
                byte_str = f'Cmd:0x{cmd:02X} Arg:0x{arg:08X}'
                return AnalyzerFrame('unknown', self.transaction_start, self.transaction_end, {
                    'bytes': byte_str
                })
        
        except (IndexError, ValueError):
            byte_str = ' '.join([f'{b:02X}' for b in self.mosi_buffer[:min(10, len(self.mosi_buffer))]])
            return AnalyzerFrame('unknown', self.transaction_start, self.transaction_end, {
                'bytes': byte_str
            })
