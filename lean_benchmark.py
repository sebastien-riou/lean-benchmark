import datetime
import time
import serial 
import sys,os,argparse
from pysatl import Utils
import logging
import io
import pickle
import math
import humanfriendly
import leancom

def get_timestamp(ts=None) -> str:
    if ts:
        dt = datetime.datetime.fromtimestamp(ts)
    else:
        dt = datetime.datetime.now()
    return dt.strftime('%Y%m%d-%H-%M-%S')

def format_number(num: int, *,precision=1,exact_in_brackets=False) -> str:
    units={'K':10**3,'M':10**6,'G':10**9}
    for u in ['G','M','K']:
        divider = units[u]
        if num > divider:
            r = num/divider
            out = f'{r:.{precision}f}{u}'
            if exact_in_brackets:
                out += f' ({num})'
            return out
    return f'{num}'

def format_timestamp(seconds: float,*,precision=1) -> str:
    units={'s':1,'ms':10**3,'us':10**6,'ns':10**9}
    for u in ['ms','us','ns']:
        divider = units[u]
        r = round(seconds*divider)
        if r > 0:
            out = f'{seconds*divider:.{precision}f}{u}'
            return out
    return f'{seconds} s'

def format_size(size) -> str:
    out = f'{humanfriendly.format_size(size,binary=True)}'
    if size > 0:
        out += f' ({size} bytes)'
    return out

def describe_results(data,*,details=True) -> str:
    out = io.StringIO()
    def p(s):
        print(s,file=out)
    info = data['info']
    results = data['results']
    for i in range(0,len(info),2) :
        p(f'{info[i]}: {info[i+1]}')

    keys = data['info'][::2] #items at even index
    values = data['info'][1::2] #items at odd index
    info = dict(zip(keys,values))

    logging.debug(info)
    frequency = None
    if 'frequency_mhz' in info.keys():
        frequency = float(info['frequency_mhz']) * 1000 * 1000

    nresults = len(results)
    p(f'{nresults} records')
    consolidated = {}
    heap_reported = True
    for r in results:
        info=r['setup info']
        case_index=r.get('case_index',0)
        cycles = get_field(r['data'],'cycles')
        min_cycles = min(cycles)
        max_cycles = max(cycles)
        ave_cycles = math.ceil(sum(cycles)/len(cycles))
        stack_sizes = get_field(r['data'],'stack size')
        max_stack = max(stack_sizes)
        try:
            heap_sizes = get_field(r['data'],'heap size')
            max_heap = max(heap_sizes)
        except:
            max_heap = 0
            heap_reported = False
        key = f'{info['dut name']}-{info['args setup name']}'
        if key not in consolidated:
            consolidated[key]=[]
        consolidated[key].append({'min_cycles':min_cycles,'max_cycles':max_cycles,'ave_cycles':ave_cycles,'max_stack':max_stack,'max_heap':max_heap})
        
        if details:
            p(f'{r['timestamp']}: {info['dut name']} with {info['args setup name']}, {info['ntrials']} trials, case {case_index}')
            p(f'\tMin cycles: {min_cycles}')
            p(f'\tAve cycles: {ave_cycles}')
            p(f'\tMax cycles: {max_cycles}')
            p(f'\tMax-Min: {max_cycles-min_cycles}')
            for t in r['data']:
                stack = ''
                if t['stack size'] == info['max stack size']:
                    stack = 'more than '
                stack_size = format_size(t['stack size'])
                stack += stack_size
                msg = f'\t{format_number(t['cycles'],exact_in_brackets=True)} cycles, {stack} of stack'
                if heap_reported:
                    heap = format_size(t['heap size'])
                    msg+=f', {heap} of heap'
                p(msg)
                extra_data = t['extra data']
                for d in extra_data:
                    p(f'\t\t{d[0]}:{Utils.hexstr(d[1])}')
    
    for key,val in consolidated.items():
        min_cycles = min([v['min_cycles'] for v in val])
        max_cycles = max([v['max_cycles'] for v in val])
        ave_cycles = math.ceil(sum([v['ave_cycles'] for v in val])/len(val))
        max_stack = max([v['max_stack'] for v in val])
        max_heap = max([v['max_heap'] for v in val])
        t_min_str = ''
        t_ave_str = ''
        t_max_str = ''
        if frequency:
            t_min = min_cycles/frequency
            t_ave = ave_cycles/frequency
            t_max = max_cycles/frequency
            #t_min_str = f' ({humanfriendly.format_timespan(t_min)})' #not good for sub seconds :-(
            #t_ave_str = f' ({humanfriendly.format_timespan(t_ave)})'
            #t_max_str = f' ({humanfriendly.format_timespan(t_max)})'
            t_min_str = f' ({format_timestamp(t_min)})'
            t_ave_str = f' ({format_timestamp(t_ave)})'
            t_max_str = f' ({format_timestamp(t_max)})'
        p(f'Consolidated stats for {key}:')
        p(f'\tMin cycles: {format_number(min_cycles)}{t_min_str}')
        p(f'\tAve cycles: {format_number(ave_cycles)}{t_ave_str}')
        p(f'\tMax cycles: {format_number(max_cycles)}{t_max_str}')
        p(f'\tMax stack:  {format_size(max_stack)}')
        if heap_reported:
            p(f'\tMax heap:   {format_size(max_heap)}')
        else:
            p(f'\tHeap not reported')
        
    return out.getvalue()

def get_field(data, field, *, sort=False):
    out = []
    for t in data:
        out.append(t[field])
    if sort:
        out.sort()
    return out

def build_pickle_file_name(ts,info):
    description = 'lean-benchmark'
    values = info[1::2] # keep only elements at odd indexes (we expect constant labels at even indexes)
    last = len(values)
    if last > 0:
        while True:
            description = '-'.join(values[:last])
            if len(description) < 256:
                break
            last -= 1
        description = "".join(x if (x.isalnum() or x in "._- ") else '-' for x in description )
    return f'{ts}-{description}.pickle'

class DeviceRuntimeError(RuntimeError):
    pass

class SyncTimeout(RuntimeError):
    pass

class _Wait():
    """Bookkeeping for a wait made of many short polls.

    The deadline is held by the port and covers the whole handshake, not this
    one wait: bytes flowing without the handshake completing is itself a
    failure (a board mid-benchmark, or two state machines skewed by line
    noise), so a per-wait or inactivity-based bound would never fire on it.
    Warnings are per-wait and do reset on progress, which is what makes them
    readable during a long measurement.
    """
    def __init__(self, port, what_for):
        self.port = port
        self.what_for = what_for
        self.last = time.monotonic()
        self.warned = 0
        # Every wait checks on entry as well as on each poll: a livelocked
        # handshake never runs out of bytes, so it would never reach a poll.
        self._check(self.last)

    def _check(self, now):
        if self.port.expires_at is not None and now >= self.port.expires_at:
            raise SyncTimeout(f'{self.port.what}: the lean-com handshake did not complete '
                              f'within {self.port.deadline}s (waiting for {self.what_for})')

    def tick(self, progressed=False):
        """Account for one poll. Raises once the port deadline, if any, is past."""
        now = time.monotonic()
        self._check(now)
        if progressed:
            self.last = now
            self.warned = 0
            return
        waited = now - self.last
        n = int(waited // self.port.WARN_EVERY)
        if n > self.warned:
            self.warned = n
            logging.warning(f'{self.port.what}: still no {self.what_for} after {int(waited)}s')

class PollingPort():
    """Wrap a pyserial port so that waiting happens here, not inside a blocking read.

    The port is kept on a short poll timeout and every wait is a loop over those
    polls. That makes "wait forever" and "give up after n seconds" the same code
    path, differing only by the deadline, and it leaves room between polls to
    report that nothing is coming back.

    A deadline is only ever armed for the lean-com handshake: a target computes
    for many seconds between packets during a benchmark, so no bound is safe
    once measurements start. Without a deadline the loop warns and keeps waiting,
    which is what the port did before, only no longer silently.
    """
    POLL = 1.0        # seconds spent in one port read before we look up
    DRAIN_POLL = 0.05 # seconds between checks that the output queue moved
    WARN_EVERY = 5.0  # seconds between "still nothing" warnings

    def __init__(self, impl, what='device'):
        self.impl = impl
        self.what = what
        self.deadline = None
        self.expires_at = None
        self.impl.timeout = self.POLL

    def __getattr__(self, name):
        return getattr(self.impl, name)

    def set_deadline(self, timeout):
        """Arm a deadline `timeout` seconds from now, or None to wait forever."""
        self.deadline = timeout
        self.expires_at = None if timeout is None else time.monotonic() + timeout
        # Bounding a write is only safe while writes are single bytes, so it is
        # armed with the handshake deadline and never during measurements.
        self.impl.write_timeout = self.POLL if timeout is not None else None

    def read(self, size=1):
        if size <= 0:
            return b'' # a zero-length lean-com packet is legitimate
        out = bytearray()
        w = _Wait(self, 'answer')
        while len(out) < size:
            c = self.impl.read(size - len(out))
            out += c
            if len(out) < size:
                w.tick(progressed=bool(c)) # keep partial reads, a poll ending is not an error
        return bytes(out)

    def readline(self):
        out = bytearray()
        w = _Wait(self, 'answer')
        while True:
            c = self.impl.read(1)
            out += c
            if c == b'\n':
                return bytes(out)
            w.tick(progressed=bool(c))

    def _drain(self, what_for):
        w = _Wait(self, what_for)
        while True:
            try:
                pending = self.impl.out_waiting
            except (OSError, NotImplementedError, serial.SerialException):
                return # nothing to gate on, let the caller proceed
            if not pending:
                return
            time.sleep(self.DRAIN_POLL)
            w.tick()

    def write(self, data):
        # Gate on the output queue instead of bounding the write: pyserial
        # reports no partial count on a write timeout, so retrying could
        # duplicate protocol bytes. Once the queue is empty a lean-com write is
        # small enough to always fit, so it cannot block.
        self._drain('room to send')
        try:
            self.impl.write(data)
        except serial.SerialTimeoutException as e:
            raise SyncTimeout(f'{self.what}: cannot send, the device is not reading') from e

    def flush(self):
        self._drain('room to send')

class SerialWithException():
    EXCEPTION = "EXCEPTION".encode()
    def __init__(self, impl):
        self.impl = impl
        self.threshold = len(self.EXCEPTION)
        self.level=0
        self.all = bytearray()

    def read1(self):
        c = self.impl.read(1)
        self.all += c
        e = self.EXCEPTION[self.level]
        i = c[0]
        if i == e:
            self.level+=1
            if self.level == self.threshold:
                self.level = 0
                raise DeviceRuntimeError()
        else:
            self.level = 0
        return c
    
    def read(self, n):
        out = bytearray()
        for i in range(0,n):
            out += self.read1()
        return bytes(out)

    def readline(self):
        out = bytearray()
        while(True):
            c = self.read1()
            out += c
            if c == b'\n':
                return bytes(out)
    
    def write(self, data):
        self.impl.write(data)

if __name__ == '__main__':
    scriptname = os.path.basename(__file__)
    parser = argparse.ArgumentParser(scriptname)
    levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    parser.add_argument('--log-level', default='INFO', choices=levels)
    parser.add_argument(
        '--device', help='Path to the serial device', type=str
    )
    parser.add_argument(
        '--baud', default=115200, help='Baudrate', type=int
    )
    parser.add_argument(
        '--exclusive', help='Exclusive access', action='store_true'
    )
    parser.add_argument(
        '--describe', default=None, help='Path to pickle file', type=str
    )
    parser.add_argument(
        '--uart-log', default=None, help='Path to raw UART output', type=str
    )
    parser.add_argument(
        '--details', help='Show all details', default=1, type=int
    )
    parser.add_argument(
        '--write-pickle', help='Write pickle file', default=1, type=int
    )
    parser.add_argument(
        '--leancom', help='0: use raw protocol, 1: use lean-com protocol', default=1, type=int
    )
    parser.add_argument(
        '--send', help='send a string after opening com in raw protocol', default=None, type=str
    )
    parser.add_argument(
        '--device-timeout', help="timeout in seconds to wait in case the device does not exist, 0 don't wait, -1 block undefintely", default=0, type=int
    )    
    parser.add_argument(
        '--sync-timeout', help="maximum seconds for the lean-com handshake to complete, -1 block indefinitely", default=-1, type=float
    )
    parser.add_argument(
        '--exception-wait', help="after the device reports an exception: maximum seconds to wait for its error code "
        "line before exiting with an error, -1 block indefinitely", default=10, type=float
    )

    args = parser.parse_args()

    if args.sync_timeout <= 0 and args.sync_timeout != -1:
        parser.error('--sync-timeout must be a positive number of seconds, or -1 to block indefinitely')
    if args.exception_wait < 0 and args.exception_wait != -1:
        parser.error('--exception-wait must be a number of seconds, or -1 to block indefinitely')

    logformat = '%(asctime)s.%(msecs)03d %(levelname)s:\t%(message)s'
    logdatefmt = '%Y-%m-%d %H:%M:%S'
    logging.basicConfig(level=args.log_level, format=logformat, datefmt=logdatefmt)
    
    if args.describe:
        with open(args.describe,'rb') as f:
            results = pickle.load(f)
            print(describe_results(results,details=args.details))
        sys.exit()

    if args.device is None and args.uart_log is None:
        parser.print_help()
        exit(-1)
    
    polling_port = None # the PollingPort under a lean-com link, which can bound a wait
    if args.device:
        exist1 = os.path.exists(args.device)
        time.sleep(.2)
        exist2 = os.path.exists(args.device)
        if not exist1 or not exist2:
            logging.info(f'{args.device} not found')
            if args.device_timeout == -1:
                logging.info('waiting until it is detected')
            if args.device_timeout > 0:
                logging.info(f'waiting up to {args.device_timeout} seconds for it')
            start = datetime.datetime.now()
            while args.device_timeout == -1 or (datetime.datetime.now()-start).total_seconds() < args.device_timeout:
                time.sleep(.5)
                if os.path.exists(args.device):
                    can_read = os.access(args.device, os.R_OK) # Check for read access
                    can_write = os.access(args.device, os.W_OK) # Check for write access
                    logging.info(f'{args.device} detected (can read:{can_read}, can write:{can_write})')
                    if can_read and can_write:
                        break
                        
        if args.leancom:
            port = PollingPort(serial.Serial(args.device, exclusive=args.exclusive,baudrate=args.baud), what=args.device)
            polling_port = port
            port.set_deadline(None if args.sync_timeout < 0 else args.sync_timeout)
            ser = leancom.Device(port)
            logging.info(f'{args.device}: waiting for the lean-com handshake')
            try:
                ser.synchronize()
            except SyncTimeout as e:
                sys.exit(f'{e}; likely a halted core, a crash before the handshake, stale '
                         'firmware, no reset since the last run, or line noise')
            logging.info(f'{args.device}: lean-com handshake done')
            port.set_deadline(None) # a benchmark can compute for a long time between packets
        else:
            ser = serial.Serial(args.device, exclusive=args.exclusive,baudrate=args.baud)
            if args.send:
                ser.write(Utils.ba(args.send))
                ser.flush()
        source = SerialWithException(ser)
        timestamp = None #we will generate timestamps during the processing
    else:
        # we use the timestamp from OS (last modification timestamp)
        timestamp = os.path.getmtime(args.uart_log)
        source = SerialWithException(open(args.uart_log,'rb')) 

    def read_lines_until(expected,log_level=logging.DEBUG) -> bytes:
        out = bytearray()
        while True:
            line = source.readline()
            out += line
            line = line.strip()
            try:
                logging.log(level=log_level,msg=line.decode())
            except:
                logging.log(level=log_level,msg=Utils.hexstr(line))
            if(line.endswith(expected)):
                break
        return bytes(out)

    def read_u32() -> int:
        b = source.read(4)
        out = int.from_bytes(b,byteorder='little')
        logging.debug(f'read_u32: {out}')
        return out
    
    def read_u64() -> int:
        b = source.read(8)
        out = int.from_bytes(b,byteorder='little')
        logging.debug(f'read_u64: {out}')
        return out

    def read_string() -> str:
        size = read_u32()  
        out = source.read(size)
        try:
            out_str = out.decode('utf-8')
            logging.debug(f'read_string: "{out}"')
        except UnicodeDecodeError as e:
            logging.error(Utils.hexstr(out))
            raise e
        return out_str

    try:
        read_lines_until(b'lean-benchmark start')
        
        info = []
        ninfo = read_u32()
        for i in range(0,ninfo):
            info.append(read_string())
        results = list()
        while True:
            setup_info = dict()
            setup_info['dut name'] = read_string()
            if 0 == len(setup_info['dut name']):
                break #end of benchmark
            setup_info['args setup name'] = read_string()
            setup_info['nargs'] = read_u32()
            setup_info['ntrials'] = read_u32()
            setup_info['max stack size'] = read_u32()
            nextra_data = read_u32()
            case_index = read_u32()
            result = dict()
            if timestamp:
                result['timestamp'] = timestamp
            else:
                result['timestamp'] = get_timestamp()
            result['setup info'] = setup_info
            result['case_index'] = case_index
            results_data = list()
            for i in range(0,setup_info['ntrials']):
                cycles = read_u32()
                stack  = read_u32()
                heap   = read_u64()
                extra_data = list()
                for j in range(0,nextra_data):
                    #get extra data
                    name = read_string()
                    length = read_u32()
                    v = source.read(length)
                    extra_data.append([name,v])
                results_data.append({'cycles':cycles, 'stack size':stack, 'heap size': heap, 'extra data':extra_data})
            result['data'] = results_data
            results.append(result)
    except DeviceRuntimeError:
        # The device stops after reporting an exception: log what it prints next (crypto-benchmark prints an
        # "Error code: 0x..." line), then fail instead of waiting for results that will not come. No pickle.
        logging.error("Device raised an exception")
        wait = args.exception_wait
        if wait >= 0:
            if polling_port is not None:
                polling_port.set_deadline(wait)
            elif isinstance(source.impl, serial.Serial):
                source.impl.timeout = wait
        while True:
            try:
                raw = source.impl.readline()
            except SyncTimeout:
                logging.error(f'no error code from the device within {wait:g}s')
                break
            if not raw:
                break # end of the UART log, or a raw serial port past --exception-wait
            s = raw.decode(errors='replace').strip()
            logging.error(s)
            if s.startswith('Error code'):
                break
        sys.exit('the device raised an exception: no results')

    out = {'info':info,'results':results}
    if args.write_pickle != 0:
        name = build_pickle_file_name(get_timestamp(timestamp),info)
        if timestamp is None:#avoid overwriting results (unless timestamp was comming from uart-log file)
            while os.path.exists(name):
                name = build_pickle_file_name(get_timestamp(),info) 
        with open(name,'wb') as f:
            pickle.dump(out,f)
    print(describe_results(out,details=args.details))
        
