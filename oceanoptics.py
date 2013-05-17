import logging
import usb.core
import usb.util
import struct
import numpy 

__all__ = ['USB4000']

commands = { \
    0x01: ('init', 'initialize USB4000'), 
    0x02: ('set_i', 'set integration time in uS'), 
    0x03: ('set_strobe', 'set strobe enable status'), 
    0x05: ('ask', 'query information'), 
    0x06: ('write', 'write information'), 
    0x09: ('get_spectra', 'request spectra'), 
    \
    0x0A: ('set_trigger', 'set trigger mode'),
    0x0B: ('num_plugins', 'query number of plug-in accessories present'),
    0x0C: ('plugin_ids', 'query plug-in identifiers'),
    0x0D: ('detect_plugins', 'detect plug-ins'),
    \
    0x60: ('read_i2c', 'general I2C read'),
    0x61: ('write_i2c', 'general I2C write'),
    0x62: ('spi_io', 'general spi I/O'),
    0x68: ('read_psoc', 'PSOC read'),
    0x69: ('write_psoc', 'PSOC write'),
    0x6A: ('write_reg', 'write register information'),
    0x6B: ('read_reg', 'read register information'),
    0x6C: ('read_temp', 'read PCB temperature'),
    0x6D: ('read_calib', 'read irradiance calibration factors'),
    0x6E: ('write_calib', 'write irradiance calibration factors'),
    \
    0xFE: ('ask_2', 'query information')
}

config_regs = {\
    0: 'serial_number',
    1: '0_order_wavelength_coeff',
    2: '1_order_wavelength_coeff',
    3: '2_order_wavelength_coeff',
    4: '3_order_wavelength_coeff',
    5: 'stray_light_constant',
    6: '0_order_nonlinear_coeff',
    7: '1_order_nonlinear_coeff',
    8: '2_order_nonlinear_coeff',
    9: '3_order_nonlinear_coeff',
    10: '4_order_nonlinear_coeff',
    11: '5_order_nonlinear_coeff',
    12: '6_order_nonlinear_coeff',
    13: '7_order_nonlinear_coeff',
    14: 'polynomial_order',
    15: 'bench_configuration',
    16: 'USB4000_config',
    17: 'autonull',
    18: 'baud_rate' \
}   

class USB4000(object):
    '''Class representing Ocean Optics spectrometer'''
    
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s')

    idVendor = 0x2457
    idProduct = 0x1022
    
    def __new__(cls, id=0):
        avail = usb.core.find(idVendor=cls.idVendor, idProduct=cls.idProduct)
        if avail is None:
            raise RuntimeError('no ocean optics devices found')
        
        if isinstance(avail, list):
            print 'Got {:d} devices, taking {:d}'.format(len(avail), id)
            avail = avail[id]
        obj = super(USB4000, cls).__new__(cls)
        obj._device = avail
        return obj
    
    def __init__(self):
        logging.debug('In init!')
        
        if self._device.is_kernel_driver_active(0):
            try:
                self._device.detach_kernel_driver(0)
            except usb.core.USBError as e:
                logging.fatal("Could not detatch kernel driver: %s" % str(e))
                raise e
                
        try:
            self._device.set_configuration() # There is only one configuration
            self._device.reset()
        except usb.core.USBError as e:
            logging.fatal("could not set configuration" % str(e))
            raise e
            
        cfg = self._device.get_active_configuration()
        
        self._cmd_w = usb.util.find_descriptor(cfg[(0,0)], bEndpointAddress=0x01)
        self._spec_hi = usb.util.find_descriptor(cfg[(0,0)], bEndpointAddress=0x82)
        self._spec_lo = usb.util.find_descriptor(cfg[(0,0)], bEndpointAddress=0x86)
        self._cmd_r = usb.util.find_descriptor(cfg[(0,0)], bEndpointAddress=0x81)
        
        # initialize spectrometer
        self.init()
        
    def init(self):
        '''sends the initialization command to the USB4000 spectrometer
            
        This command initializes certain parameters on the USB4000 and sets internal variables
        based on the USB communication speed. This command is called at object instantiation.
        '''
        self._cmd_w.write(struct.pack('<B', 0x01))
        
    def set_integration_time(self, dt):
        '''sets the integration time to use by the spectrometer in microseconds

        This command sets the integration time that the USB4000 uses when acquiring spectra. The
        value is passed as a 32 bit integer and has a valid range between 10 and 65,535,000 us. 
        '''
        logging.debug('setting {} for the integration time'.format(repr(dt)))
        if isinstance(dt, int):

            if dt < 10: 
                logging.warning('integration time {:d} too low, setting to minimum of 10us'.format(dt))
                dt = 10 # can't integrate for less than 10 us
            if dt > 65535000: # largest value of 32 bit unsigned int
                logging.warning('integration time {:d} too high, setting to maximum of 65,535,000 us'.format(dt))
                dt = 65535000 # can't integrate for less than 10 us
                
            cmd = struct.pack('<BI', 0x02, dt)
            logging.debug('Sending {:s}'.format(repr(cmd)))
            return self._cmd_w.write(cmd)
        
        logging.info('wrong type of data in set_integration_time, {}'.format(type(dt)))
        
    def query_config(self):
        '''returns the value stored in register `reg` of the spectrometer
        '''
        logging.debug('getting configuration parameters')
        
        config = {}
        
        for x in xrange(19):
            cmd = struct.pack('<2B', 0x05, x)
            logging.debug('Sending {:s}'.format(repr(cmd)))
            self._cmd_w.write(cmd)
            resp = bytearray(self._cmd_r.read(64, timeout=1000))
            logging.debug('config {:d} is {:s}'.format(x, repr(resp)))
            
            assert resp[0:2] == bytearray([0x05, x]) # Check that proper echo is returned
            
            logging.info('{:s} : {:s}'.format(config_regs[x], resp[2:].decode('ascii', errors='ignore')))
            config.update({config_regs[x] : resp[2:].decode('ascii', errors='ignore').strip('\x00')})
            
        return config
            
    def reset(self):
        logging.debug('resetting device')
        self._device.reset()
    
    def read_temp(self):
        logging.debug('getting pcb temperature')
        cmd = struct.pack('<B', 0x6C)
        self._cmd_w.write(cmd)
        
        logging.debug('sending {:s}'.format(repr(cmd)))
        
        resp = bytearray(self._cmd_r.read(3, timeout=1000))
        logging.debug('got {:s}'.format(repr(resp)))
        
        assert resp[0:1] == bytearray([0x08]) # Check that proper echo is returned
        
        t = struct.unpack('<h', resp[1:3])[0]
        logging.info('temperature is {}'.format(t*0.003906))
        return t*0.003906
    
    def firmware_version(self):
        logging.debug('getting firmware version')
        cmd = struct.pack('<2B', 0x6B, 0x04)
        logging.debug('sending {:s}'.format(repr(cmd)))
        self._cmd_w.write(cmd)
        
        resp = bytearray(self._cmd_r.read(3, timeout=200))
        logging.debug('got {:s}'.format(repr(resp)))
        
        #assert resp[0:1] == bytearray([0x04]) # Check that proper echo is returned
        
        vers = struct.unpack('>H', resp[1:3])[0]
        logging.info('firmware is {:d}'.format(vers))
        return vers
    
    def set_trigger_mode(self, mode=0):
        logging.debug('setting {} for the trigger mode'.format(repr(mode)))
        if isinstance(mode, int):
            cmd = struct.pack('<BH', 0x0A, mode)
            logging.debug('Sending {:s}'.format(repr(cmd)))
            return self._cmd_w.write(cmd)
        
        logging.info('wrong type of data in set_trigger_mode {}'.format(type(mode)))
        
      
    def request_spectra(self):
        cmd = struct.pack('<B', 0x09)
        logging.debug('Requesting spectra')
        logging.debug('Sending {:s}'.format(repr(cmd)))
        self._cmd_w.write(cmd)
        
        data_lo = self._spec_lo.read(512*4, timeout=20)
        data_hi = self._spec_hi.read(512*11, timeout=20)

        data_sync = self._spec_hi.read(1, timeout=20)

        assert struct.unpack('<B', data_sync)[0] == 0x69
        
        data = numpy.zeros(shape=(3840,), dtype='<u2')

        data[:1024], data[1024:] =  numpy.frombuffer(data_lo, dtype='<u2'), \
                                    numpy.frombuffer(data_hi, dtype='<u2')

        logging.debug('obtained spectra')

        return data

    def get_status(self):
        logging.debug('getting status parameters')
        
        cmd = struct.pack('<B', 0xFE)
        logging.debug('Sending {:s}'.format(repr(cmd)))
        self._cmd_w.write(cmd)
        resp = bytearray(self._cmd_r.read(16, timeout=1000))
        logging.debug('status is {:s}'.format(repr(resp)))
        
        stat = {\
            'num_pixels' : struct.unpack('<H', resp[0:2])[0],
            'integration_time' : struct.unpack('<I', resp[2:6])[0],
            'lamp_enable': bool(struct.unpack('<B', resp[6:7])[0]),
            'trigger_mode' : struct.unpack('<B', resp[7:8])[0],
            'acq_status' : struct.unpack('<B', resp[8:9])[0],
            'packets_in_spectra' : struct.unpack('<B', resp[9:10])[0],
            'power_down' : bool(struct.unpack('<B', resp[10:11])[0]),
            'packet_count' : struct.unpack('<B', resp[11:12])[0],
            'usb_speed' : struct.unpack('<B', resp[14:15])[0]
        }
        
        return stat
        
    def close(self):
        usb.util.dispose_resources(self._device)
        
    status = property(lambda self: self.get_status())