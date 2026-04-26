import machine
import rp2
import array
import uctypes
import time

class DMA_ADC:
    def __init__(self, pin=26):
        """
        Initializes the High-Speed DMA ADC for the RP2350.
        :param pin: GPIO pin number (26, 27, 28, or 29)
        """
        # RP2350 specific constants
        self.ADC_BASE = 0x400A0000
        self.ADC_CS   = self.ADC_BASE + 0x00
        self.ADC_FCS  = self.ADC_BASE + 0x08
        self.ADC_FIFO = self.ADC_BASE + 0x0C
        self.ADC_DIV  = self.ADC_BASE + 0x10
        self.ADC_DREQ = 48 

        # Validate and map pin to ADC channel
        if not (26 <= pin <= 29):
            raise ValueError("ADC pin must be 26, 27, 28, or 29")
        self.channel = pin - 26
        
        self.adc_pin = machine.ADC(pin) 

        self.buffer = None
        self.samples = 0
        
        # Setup DMA Controller
        self.dma = rp2.DMA()
        self.ctrl = self.dma.pack_ctrl(
            size=1,             # 16-bit (Half-word)
            inc_read=False,     # Always read the FIFO address
            inc_write=True,     # Increment through the buffer
            treq_sel=self.ADC_DREQ 
        )

        # Set safe defaults
        self.set_sample_size(10000)
        self.set_sample_rate(500_000)

    def set_sample_size(self, size):
        """Allocates a new internal buffer of the requested size."""
        self.samples = size
        self.buffer = array.array('H', [0] * self.samples)
        return self.buffer

    def set_sample_buffer(self, custom_buffer):
        """Allows you to pass your own pre-allocated array.array."""
        if not isinstance(custom_buffer, array.array) or custom_buffer.typecode != 'H':
            raise ValueError("Buffer must be an array.array of type 'H'")
        self.buffer = custom_buffer
        self.samples = len(custom_buffer)

    def set_sample_rate(self, freq_hz):
        """Calculates and sets the hardware pacing timer."""
        if freq_hz >= 500_000:
            machine.mem32[self.ADC_DIV] = 0 # Max speed (free-running)
        else:
            div = (48_000_000 / freq_hz) - 1
            machine.mem32[self.ADC_DIV] = int(div) << 8

    def capture(self, blocking=True, timeout_ms=2000):
        """
        Triggers the DMA and ADC to fill the buffer.
        :param blocking: If True, waits for completion. If False, returns immediately.
        """
        if self.buffer is None or self.samples == 0:
            raise RuntimeError("Buffer not initialized")

        # 1. Stop any rogue processes and clear FIFO
        self.stop()
        machine.mem32[self.ADC_FCS] = 0
        
        # 2. Power on ADC (Bit 0)
        machine.mem32[self.ADC_CS] = (1 << 0)
        
        # 3. Configure FIFO (Threshold 1, DREQ Enable, FIFO Enable)
        machine.mem32[self.ADC_FCS] = (1 << 24) | (1 << 3) | (1 << 0)
        
        # 4. Route DMA to buffer
        self.dma.config(
            read=self.ADC_FIFO, 
            write=uctypes.addressof(self.buffer),
            count=self.samples,
            ctrl=self.ctrl
        )
        self.dma.active(1)
        
        # 5. Start ADC continuous sampling
        # Channel select, START_MANY (Bit 3), EN (Bit 0)
        machine.mem32[self.ADC_CS] = (self.channel << 12) | (1 << 3) | (1 << 0)

        # 6. Handle blocking behavior
        if blocking:
            start = time.ticks_ms()
            while self.dma.active():
                if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                    self.stop()
                    raise RuntimeError("DMA Capture Timed Out!")
            self.stop() # Turn off continuous mode to save power

    def is_busy(self):
        """Returns True if a non-blocking capture is currently running."""
        return self.dma.active()

    def stop(self):
            """Forces the ADC and DMA to halt and cleanly resets all hardware registers."""
            
            # 1. Stop the DMA channel immediately
            self.dma.active(0)
            
            # 2. SURGICAL SHUTDOWN: 
            # Turn off START_MANY (Bit 3) to stop the barrage of data, 
            # but LEAVE the ADC powered on (Bit 0) so MicroPython can still use it!
            machine.mem32[self.ADC_CS] &= ~(1 << 3)
            
            # 3. Clean up the FIFO Control Register (ADC_FCS)
            # Disable DREQ_EN (bit 3) and FIFO_EN (bit 0)
            machine.mem32[self.ADC_FCS] &= ~((1 << 3) | (1 << 0))
            
            # 4. Flush the pipes! 
            # Clear FIFO Error (Bit 11) and FIFO Empty (Bit 10) flags.
            machine.mem32[self.ADC_FCS] |= (1 << 11) | (1 << 10)
        
    def get_data(self):
        """Returns the internal buffer."""
        return self.buffer
